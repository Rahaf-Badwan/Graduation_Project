import hashlib
import secrets
from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    session,
    Response,
)
import bcrypt
from werkzeug.utils import secure_filename
from db import get_db
from auth import login_required
from routes.supervisor_profile import supervisor_profile_bp

general_supervisors_bp = Blueprint(
    "general_supervisors",
    __name__,
    url_prefix="/general-supervisor"
)

general_supervisors_bp.register_blueprint(supervisor_profile_bp)


# ─── Dashboard ──────────────────────────────────────────────
@general_supervisors_bp.route("/")
@general_supervisors_bp.route("/dashboard")
@login_required(role="supervisor")
def dashboard():
    return render_template("supervisor/index.html")


# ─── Search ─────────────────────────────────────────────────
@general_supervisors_bp.route("/search")
@login_required(role="supervisor")
def search():
    return render_template("shared/archive_search.html", base_template="supervisor/base.html")


# ─── Notifications Page ─────────────────────────────────────
@general_supervisors_bp.route("/notifs")
@login_required(role="supervisor")
def notifs():
    return render_template("supervisor/notifs.html")


# ─── AI Assistant ───────────────────────────────────────────
@general_supervisors_bp.route("/ai")
@login_required(role="supervisor")
def ai():
    return render_template("shared/ai.html", base_template="supervisor/base.html")


# ─── Profile ────────────────────────────────────────────────
@general_supervisors_bp.route("/profile")
@login_required(role="supervisor")
def profile():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT user_id, university_id, full_name, email, avatar_initials
            FROM users
            WHERE user_id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception:
        user = None

    return render_template(
        "supervisor/profile.html",
        user=user,
        pwd_error=None,
        pwd_success=None
    )


# ─── Change Password ────────────────────────────────────────
@general_supervisors_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="supervisor")
def change_password():
    user_id = session["user_id"]
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    def get_user():
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT user_id, password_hash
                FROM users
                WHERE user_id = %s
                """,
                (user_id,),
            )
            u = cursor.fetchone()
            cursor.close()
            db.close()
            return u
        except Exception:
            return None

    user = get_user()

    if not current_pwd or not new_pwd or not confirm_pwd:
        return render_template("supervisor/profile.html", user=user, pwd_error="Fill all fields", pwd_success=None)

    if len(new_pwd) < 8:
        return render_template("supervisor/profile.html", user=user, pwd_error="Password too short", pwd_success=None)

    if new_pwd != confirm_pwd:
        return render_template("supervisor/profile.html", user=user, pwd_error="Passwords do not match", pwd_success=None)

    if not user or not bcrypt.checkpw(current_pwd.encode(), user["password_hash"].encode()):
        return render_template("supervisor/profile.html", user=user, pwd_error="Wrong current password", pwd_success=None)

    try:
        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s",
            (hashed, user_id),
        )
        db.commit()
        cursor.close()
        db.close()

        return render_template(
            "supervisor/profile.html",
            user=user,
            pwd_error=None,
            pwd_success="Password updated successfully!"
        )
    except Exception as e:
        return render_template("supervisor/profile.html", user=user, pwd_error=str(e), pwd_success=None)


# ============================================================
# Helpers (Supervisor-safe version)
# ============================================================

def _supervisor_table_exists(cursor, table):
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s",
        (table,),
    )
    return int(cursor.fetchone()["cnt"]) > 0


def _supervisor_db_column_exists(cursor, table, column):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME=%s
          AND COLUMN_NAME=%s
        """,
        (table, column),
    )
    return int(cursor.fetchone()["cnt"]) > 0


# ============================================================
# Notifications / Messaging
# ============================================================

def _ensure_supervisor_notification_schema(cursor):
    if _supervisor_table_exists(cursor, "notifications"):
        if not _supervisor_db_column_exists(cursor, "notifications", "course_scope"):
            cursor.execute("""
                ALTER TABLE notifications
                ADD COLUMN course_scope ENUM('introduction','graduation_project','both')
                NOT NULL DEFAULT 'both'
            """)

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_name"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255) NULL")

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_mime"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120) NULL")

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_data"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_data LONGBLOB NULL")


def _notification_attachment_fields(cursor):
    if _supervisor_db_column_exists(cursor, "notifications", "attachment_name"):
        return "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"
    return "NULL, NULL, 0"


def _row_to_json(row):
    if not row:
        return row
    r = dict(row)
    r["is_read"] = bool(r.get("is_read"))
    r["course_scope"] = r.get("course_scope") or "both"
    r["created_at"] = str(r.get("created_at")) if r.get("created_at") else None
    r.pop("attachment_data", None)
    return r


# ============================================================
# API: Inbox
# ============================================================

@general_supervisors_bp.route("/api/notifications/inbox")
@login_required(role="supervisor")
def inbox():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    _ensure_supervisor_notification_schema(cursor)
    db.commit()

    fields = _notification_attachment_fields(cursor)

    cursor.execute(f"""
        SELECT n.*, sender.full_name AS sender_name,
               {fields}
        FROM notifications n
        LEFT JOIN users sender ON sender.user_id = n.sender_id
        WHERE n.recipient_id = %s
        ORDER BY n.created_at DESC
        LIMIT 100
    """, (session["user_id"],))

    rows = [_row_to_json(r) for r in cursor.fetchall()]

    cursor.close()
    db.close()
    return jsonify({"notifications": rows})


# ============================================================
# API: Sent
# ============================================================

@general_supervisors_bp.route("/api/notifications/sent")
@login_required(role="supervisor")
def sent():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    _ensure_supervisor_notification_schema(cursor)
    db.commit()

    fields = _notification_attachment_fields(cursor)

    cursor.execute(f"""
        SELECT n.*, recipient.full_name AS recipient_name,
               {fields}
        FROM notifications n
        JOIN users recipient ON recipient.user_id = n.recipient_id
        WHERE n.sender_id = %s
        ORDER BY n.created_at DESC
        LIMIT 100
    """, (session["user_id"],))

    rows = [_row_to_json(r) for r in cursor.fetchall()]

    cursor.close()
    db.close()
    return jsonify({"sent": rows})


# ============================================================
# API: Send Notification
# ============================================================

@general_supervisors_bp.route("/api/notifications/send", methods=["POST"])
@login_required(role="supervisor")
def send():
    data = request.get_json(silent=True) or {}

    scope = (data.get("scope") or "").strip()
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()

    if not scope or not title or not message:
        return jsonify({"error": "Missing fields"}), 400

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT user_id FROM users WHERE role='student'")
    recipients = [r["user_id"] for r in cursor.fetchall()]

    for r in recipients:
        cursor.execute("""
            INSERT INTO notifications
            (recipient_id, sender_id, title, message, is_read)
            VALUES (%s, %s, %s, %s, FALSE)
        """, (r, session["user_id"], title, message))

    db.commit()
    cursor.close()
    db.close()

    return jsonify({"message": "Sent", "count": len(recipients)})


# ============================================================
# Mark Read
# ============================================================

@general_supervisors_bp.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required(role="supervisor")
def mark_read(nid):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE notifications SET is_read=TRUE WHERE notification_id=%s AND recipient_id=%s",
        (nid, session["user_id"]),
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "updated"})


# ============================================================
# Read All
# ============================================================

@general_supervisors_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required(role="supervisor")
def read_all():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE notifications SET is_read=TRUE WHERE recipient_id=%s",
        (session["user_id"],),
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "all updated"})