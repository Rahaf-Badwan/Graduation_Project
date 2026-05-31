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
from routes.supervisor_progress_submitted_api import supervisor_progress_api_bp
general_supervisors_bp = Blueprint(
    "general_supervisors",
    __name__,
    url_prefix="/supervisor"
)

general_supervisors_bp.register_blueprint(supervisor_progress_api_bp)

# Alias route for submitted files.
# This guarantees the endpoint is available under:
# /supervisor/api/supervisor/progress/submissions
@general_supervisors_bp.route("/api/supervisor/progress/submissions", methods=["GET"])
@login_required(role="supervisor")
def supervisor_submissions_alias():
    from routes.supervisor_progress_submitted_api import api_supervisor_submitted_files
    return api_supervisor_submitted_files()


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


# ─── Progress Page ──────────────────────────────────────────
@general_supervisors_bp.route("/progress")
@login_required(role="supervisor")
def progress():
    return render_template("supervisor/progress.html")


# ─── AI Assistant ───────────────────────────────────────────
@general_supervisors_bp.route("/ai")
@login_required(role="supervisor")
def ai():
    return render_template("shared/ai.html", base_template="supervisor/base.html")


# ─── Profile ────────────────────────────────────────────────
def _load_supervisor_profile_user(include_password=False):
    """Load one complete supervisor profile for direct or switched sessions."""
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        password_field = ", u.password_hash" if include_password else ""
        faculty_id = session.get("faculty_id")
        if faculty_id:
            cursor.execute(
                f"""
                SELECT u.user_id, u.university_id, u.full_name, u.email,
                       u.avatar_initials, f.faculty_id, f.specialization,
                       f.years_experience, f.title, f.office_number
                       {password_field}
                FROM users u
                JOIN faculty f ON f.user_id = u.user_id
                WHERE f.faculty_id = %s
                LIMIT 1
                """,
                (faculty_id,),
            )
        else:
            cursor.execute(
                f"""
                SELECT u.user_id, u.university_id, u.full_name, u.email,
                       u.avatar_initials, f.faculty_id, f.specialization,
                       f.years_experience, f.title, f.office_number
                       {password_field}
                FROM users u
                LEFT JOIN faculty f ON f.user_id = u.user_id
                WHERE u.user_id = %s
                LIMIT 1
                """,
                (session.get("user_id"),),
            )
        user = cursor.fetchone()
        if not user:
            return None

        title = (user.get("title") or "Dr.").strip()
        full_name = (user.get("full_name") or "").strip()
        if full_name.lower().startswith(f"{title.lower()} "):
            user["display_name"] = full_name
        else:
            user["display_name"] = f"{title} {full_name}".strip()
        if not user.get("avatar_initials"):
            parts = [part for part in full_name.replace("Dr.", "").split() if part]
            user["avatar_initials"] = "".join(part[0].upper() for part in parts[:2])
        return user
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@general_supervisors_bp.route("/profile")
@login_required(role="supervisor")
def profile():
    try:
        user = _load_supervisor_profile_user()
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
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    try:
        user = _load_supervisor_profile_user(include_password=True)
    except Exception:
        user = None

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
            (hashed, user["user_id"]),
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

        if not _supervisor_db_column_exists(cursor, "notifications", "can_reply"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN can_reply TINYINT(1) NOT NULL DEFAULT 1 AFTER is_read")

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_name"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255) NULL")

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_mime"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120) NULL")

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_data"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_data LONGBLOB NULL")


def _notification_attachment_fields(cursor):
    if _supervisor_db_column_exists(cursor, "notifications", "attachment_name"):
        return "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"
    return "NULL AS attachment_name, NULL AS attachment_mime, 0 AS has_attachment"


def _row_to_json(row):
    if not row:
        return row
    r = dict(row)
    r["is_read"] = bool(r.get("is_read"))
    r["course_scope"] = r.get("course_scope") or "both"
    r["created_at"] = str(r.get("created_at")) if r.get("created_at") else None
    r["has_attachment"] = bool(r.get("has_attachment"))
    r["can_reply"] = bool(r.get("can_reply", True))
    if not r["has_attachment"]:
        r["attachment_name"] = None
        r["attachment_mime"] = None
    r.pop("attachment_data", None)
    return r


def _supervisor_notification_enum_values(cursor):
    cursor.execute(
        """
        SELECT COLUMN_TYPE AS column_type
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'notifications'
          AND COLUMN_NAME = 'notification_type'
        LIMIT 1
        """
    )
    row = cursor.fetchone() or {}
    column_type = str(row.get("column_type") or row.get("COLUMN_TYPE") or "")
    if not column_type.lower().startswith("enum("):
        return []

    raw = column_type[5:-1]
    values, current, in_quote = [], "", False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "'":
            if in_quote and i + 1 < len(raw) and raw[i + 1] == "'":
                current += "'"
                i += 1
            else:
                in_quote = not in_quote
        elif ch == "," and not in_quote:
            values.append(current)
            current = ""
        else:
            current += ch
        i += 1
    if current or raw:
        values.append(current)
    return [v for v in values if v]


def _supervisor_safe_notification_type(cursor, requested_type="system"):
    allowed = _supervisor_notification_enum_values(cursor)
    if not allowed:
        return requested_type or "system"
    if requested_type in allowed:
        return requested_type
    for fallback in ("system", "info", "message", "deadline_reminder", "urgent_alert", "alert"):
        if fallback in allowed:
            return fallback
    return allowed[0]


def _supervisor_active_semester_by_course(cursor, course_code):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE AND course_code = %s
        ORDER BY semester_id DESC
        LIMIT 1
        """,
        (course_code,),
    )
    return cursor.fetchone()


def _supervisor_course_from_scope(course_scope):
    if course_scope == "introduction":
        return "COMP4200"
    if course_scope == "graduation_project":
        return "COMP4300"
    return None


def _supervisor_coordinator_user_ids_for_scope(cursor, course_scope):
    course_code = _supervisor_course_from_scope(course_scope)
    if course_code and _supervisor_table_exists(cursor, "coordinator_assignments"):
        semester = _supervisor_active_semester_by_course(cursor, course_code)
        if semester:
            cursor.execute(
                """
                SELECT DISTINCT u.user_id
                FROM coordinator_assignments ca
                JOIN faculty f ON f.faculty_id = ca.faculty_id
                JOIN users u ON u.user_id = f.user_id
                WHERE ca.semester_id = %s
                  AND u.role = 'coordinator'
                  AND u.is_active = TRUE
                LIMIT 1
                """,
                (semester["semester_id"],),
            )
            rows = cursor.fetchall()
            if rows:
                return [r["user_id"] for r in rows]

    limit = 1 if course_scope in {"introduction", "graduation_project"} else 1000
    cursor.execute(
        "SELECT user_id FROM users WHERE role = 'coordinator' AND is_active = TRUE ORDER BY user_id LIMIT %s",
        (limit,),
    )
    return [r["user_id"] for r in cursor.fetchall()]


def _supervisor_comp4200_section_recipients(cursor, section_id=None):
    if not (_supervisor_table_exists(cursor, "student_distribution_sections") and _supervisor_table_exists(cursor, "section_students")):
        return []
    params = []
    section_filter = ""
    if section_id:
        section_filter = "AND sec.section_id = %s"
        params.append(section_id)
    cursor.execute(
        f"""
        SELECT DISTINCT recipient_id
        FROM (
            SELECT us.user_id AS recipient_id
            FROM student_distribution_sections sec
            JOIN section_students ss ON ss.section_id = sec.section_id
            JOIN students st ON st.student_id = ss.student_id
            JOIN users us ON us.user_id = st.user_id
            WHERE us.is_active = TRUE {section_filter}
            UNION
            SELECT u_sup.user_id AS recipient_id
            FROM student_distribution_sections sec
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            WHERE u_sup.is_active = TRUE {section_filter}
        ) x
        """,
        tuple(params + params),
    )
    return [r["recipient_id"] for r in cursor.fetchall()]


def _supervisor_comp4300_project_recipients(cursor, project_id=None):
    params = []
    project_filter = ""
    if project_id:
        project_filter = "AND p.project_id = %s"
        params.append(project_id)
    cursor.execute(
        f"""
        SELECT DISTINCT recipient_id
        FROM (
            SELECT us.user_id AS recipient_id
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users us ON us.user_id = st.user_id
            WHERE s.course_code = 'COMP4300'
              AND us.is_active = TRUE
              {project_filter}
            UNION
            SELECT u_sup.user_id AS recipient_id
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            WHERE s.course_code = 'COMP4300'
              AND u_sup.is_active = TRUE
              {project_filter}
        ) x
        """,
        tuple(params + params),
    )
    return [r["recipient_id"] for r in cursor.fetchall()]


def _supervisor_notification_recipients(cursor, scope, value=None, course_scope="both"):
    scope = (scope or "").strip()
    course_scope = (course_scope or "both").strip()

    if scope == "coordinators":
        return _supervisor_coordinator_user_ids_for_scope(cursor, course_scope)

    if scope == "coordinator":
        cursor.execute(
            "SELECT user_id FROM users WHERE user_id = %s AND role = 'coordinator' AND is_active = TRUE",
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]

    if scope == "doctors":
        cursor.execute("SELECT user_id FROM users WHERE role = 'supervisor' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]

    if scope == "doctor":
        cursor.execute(
            """
            SELECT u.user_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s
              AND u.role = 'supervisor'
              AND u.is_active = TRUE
            """,
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]

    if scope == "students":
        cursor.execute("SELECT user_id FROM users WHERE role = 'student' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]

    if scope == "student":
        cursor.execute(
            """
            SELECT u.user_id
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.student_id = %s
              AND u.role = 'student'
              AND u.is_active = TRUE
            """,
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]

    if scope == "section":
        if course_scope == "graduation_project" or str(value).startswith("p:"):
            project_id = str(value).replace("p:", "", 1)
            return _supervisor_comp4300_project_recipients(cursor, project_id)
        section_id = str(value).replace("s:", "", 1)
        return _supervisor_comp4200_section_recipients(cursor, section_id)

    if scope == "all_sections":
        recipients = []
        if course_scope in {"introduction", "both"}:
            recipients.extend(_supervisor_comp4200_section_recipients(cursor))
        if course_scope in {"graduation_project", "both"}:
            recipients.extend(_supervisor_comp4300_project_recipients(cursor))
        return sorted(set(recipients))

    if scope == "reply":
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND is_active = TRUE", (value,))
        return [r["user_id"] for r in cursor.fetchall()]

    return []


# ============================================================
# API: Options
# ============================================================

@general_supervisors_bp.route("/api/notifications/options", methods=["GET"])
@login_required(role="supervisor")
def options():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        coordinator_rows = []
        for course_scope, course_code in (("introduction", "COMP4200"), ("graduation_project", "COMP4300")):
            semester = _supervisor_active_semester_by_course(cursor, course_code)
            if semester and _supervisor_table_exists(cursor, "coordinator_assignments"):
                cursor.execute(
                    """
                    SELECT DISTINCT u.user_id, u.full_name, u.university_id,
                           %s AS course_scope, %s AS course_code
                    FROM coordinator_assignments ca
                    JOIN faculty f ON f.faculty_id = ca.faculty_id
                    JOIN users u ON u.user_id = f.user_id
                    WHERE ca.semester_id = %s
                      AND u.role = 'coordinator'
                      AND u.is_active = TRUE
                    LIMIT 1
                    """,
                    (course_scope, course_code, semester["semester_id"]),
                )
                coordinator_rows.extend(cursor.fetchall())
        if not coordinator_rows:
            cursor.execute(
                """
                SELECT user_id, full_name, university_id, 'both' AS course_scope, 'Both' AS course_code
                FROM users
                WHERE role = 'coordinator' AND is_active = TRUE
                ORDER BY full_name
                """
            )
            coordinator_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT f.faculty_id, u.user_id, u.full_name, u.university_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE u.role = 'supervisor' AND u.is_active = TRUE
            ORDER BY u.full_name
            """
        )
        doctors = cursor.fetchall()

        cursor.execute(
            """
            SELECT st.student_id, u.user_id, u.full_name, u.university_id,
                   CASE WHEN EXISTS (
                        SELECT 1
                        FROM project_members pm
                        JOIN projects p ON p.project_id = pm.project_id
                        JOIN semesters s ON s.semester_id = p.semester_id
                        WHERE pm.student_id = st.student_id AND s.course_code = 'COMP4300'
                   ) THEN 'graduation_project' ELSE 'introduction' END AS course_scope
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE u.role = 'student' AND u.is_active = TRUE
            ORDER BY u.full_name
            """
        )
        students = cursor.fetchall()

        sections = []
        if _supervisor_table_exists(cursor, "student_distribution_sections") and _supervisor_table_exists(cursor, "section_students"):
            cursor.execute(
                """
                SELECT CONCAT('s:', sec.section_id) AS section_key,
                       sec.section_id,
                       sec.section_name,
                       'introduction' AS course_scope,
                       'COMP4200' AS course_code,
                       u_sup.full_name AS supervisor_name,
                       COUNT(DISTINCT ss.student_id) AS students_count
                FROM student_distribution_sections sec
                JOIN faculty f ON f.faculty_id = sec.supervisor_id
                JOIN users u_sup ON u_sup.user_id = f.user_id
                LEFT JOIN section_students ss ON ss.section_id = sec.section_id
                GROUP BY sec.section_id, sec.section_name, u_sup.full_name
                ORDER BY sec.section_id DESC
                """
            )
            sections.extend(cursor.fetchall())

        cursor.execute(
            """
            SELECT CONCAT('p:', p.project_id) AS section_key,
                   p.project_id AS section_id,
                   COALESCE(NULLIF(p.title, ''), CONCAT('COMP4300 Project ', p.project_id)) AS section_name,
                   'graduation_project' AS course_scope,
                   'COMP4300' AS course_code,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COUNT(DISTINCT pm.student_id) AS students_count
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            WHERE s.course_code = 'COMP4300'
            GROUP BY p.project_id, p.title, u_sup.full_name
            HAVING students_count > 0
            ORDER BY p.project_id DESC
            """
        )
        sections.extend(cursor.fetchall())

        cursor.close()
        db.close()
        return jsonify(
            {
                "heads": [],
                "coordinators": coordinator_rows,
                "doctors": doctors,
                "students": students,
                "sections": sections,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        SELECT n.*, n.sender_id AS sender_user_id,
               sender.full_name AS sender_name, sender.role AS sender_role,
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
        SELECT n.*, n.recipient_id AS recipient_user_id,
               recipient.full_name AS recipient_name, recipient.role AS recipient_role,
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



def _supervisor_reply_allowed(cursor, notification_id, current_user_id, target_user_id):
    """Allow reply only when the original received notification has can_reply = 1."""
    if not notification_id:
        return False
    can_reply_expr = "COALESCE(can_reply, 1)" if _supervisor_db_column_exists(cursor, "notifications", "can_reply") else "1"
    cursor.execute(
        f"""
        SELECT notification_id
        FROM notifications
        WHERE notification_id = %s
          AND recipient_id = %s
          AND sender_id = %s
          AND {can_reply_expr} = 1
        LIMIT 1
        """,
        (notification_id, current_user_id, target_user_id),
    )
    return cursor.fetchone() is not None

# ============================================================
# API: Send Notification
# ============================================================

@general_supervisors_bp.route("/api/notifications/send", methods=["POST"])
@login_required(role="supervisor")
def send():
    is_multipart = bool(request.content_type and request.content_type.startswith("multipart/form-data"))
    if is_multipart:
        data = request.form
        uploaded_file = request.files.get("file")
    else:
        data = request.get_json(silent=True) or {}
        uploaded_file = None

    scope = (data.get("scope") or "").strip()
    value = data.get("value")
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    urgent = str(data.get("urgent") or "").lower() in ("1", "true", "on", "yes")
    course_scope = (data.get("course_scope") or "both").strip()
    can_reply = str(data.get("can_reply", data.get("allow_reply", "0"))).lower() in ("1", "true", "on", "yes")
    reply_to_notification_id = data.get("reply_to_notification_id") or data.get("notification_id")

    if course_scope not in {"introduction", "graduation_project", "both"}:
        return jsonify({"error": "Please choose the course scope."}), 400
    if not scope:
        return jsonify({"error": "Please choose who should receive the message."}), 400
    if not title:
        return jsonify({"error": "Please write a title."}), 400
    if not message:
        return jsonify({"error": "Please write a message."}), 400
    if scope in {"coordinator", "doctor", "student", "section", "reply"} and not value:
        return jsonify({"error": "Please choose the exact receiver."}), 400

    attachment_name = None
    attachment_mime = None
    attachment_data = None
    if uploaded_file and uploaded_file.filename:
        attachment_name = secure_filename(uploaded_file.filename) or "attachment"
        attachment_mime = uploaded_file.mimetype or "application/octet-stream"
        attachment_data = uploaded_file.read()
        if len(attachment_data) > 10 * 1024 * 1024:
            return jsonify({"error": "Attachment must be 10 MB or smaller."}), 400

    db = get_db()
    cursor = db.cursor(dictionary=True)

    _ensure_supervisor_notification_schema(cursor)
    recipients = _supervisor_notification_recipients(cursor, scope, value, course_scope)
    sender_id = session.get("user_id")

    if scope == "reply":
        raw_recipients = [int(r) for r in recipients if r]
        if not raw_recipients:
            cursor.close()
            db.close()
            return jsonify({"error": "No recipients found for this choice."}), 404
        target_user_id = raw_recipients[0]
        if not _supervisor_reply_allowed(cursor, reply_to_notification_id, sender_id, target_user_id):
            cursor.close()
            db.close()
            return jsonify({"error": "Replies are disabled for this message."}), 403
        can_reply = True
    recipients = sorted({int(r) for r in recipients if int(r) != int(sender_id)})
    if not recipients:
        cursor.close()
        db.close()
        return jsonify({"error": "No recipients found for this choice."}), 404

    notification_type = _supervisor_safe_notification_type(cursor, "urgent_alert" if urgent else "system")
    attachment_cols = _supervisor_db_column_exists(cursor, "notifications", "attachment_name")
    for r in recipients:
        if attachment_cols:
            cursor.execute("""
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read, can_reply,
                     attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE, %s, %s, %s, %s)
            """, (r, sender_id, notification_type, title, message, course_scope, 1 if can_reply else 0, attachment_name, attachment_mime, attachment_data))
        else:
            cursor.execute("""
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message, is_read)
                VALUES (%s, %s, %s, %s, %s, FALSE)
            """, (r, sender_id, notification_type, title, message))

    db.commit()
    cursor.close()
    db.close()

    return jsonify({"message": f"Message sent successfully to {len(recipients)} recipient(s).", "sent_count": len(recipients)})


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


@general_supervisors_bp.route("/api/notifications/<int:nid>/attachment", methods=["GET"])
@login_required(role="supervisor")
def attachment(nid):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_data"):
            cursor.close()
            db.close()
            return jsonify({"error": "Attachment not found."}), 404
        cursor.execute(
            """
            SELECT attachment_name, attachment_mime, attachment_data
            FROM notifications
            WHERE notification_id = %s
              AND (recipient_id = %s OR sender_id = %s)
            LIMIT 1
            """,
            (nid, session.get("user_id"), session.get("user_id")),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if not row or not row.get("attachment_data"):
            return jsonify({"error": "Attachment not found."}), 404
        filename = secure_filename(row.get("attachment_name") or "attachment") or "attachment"
        mimetype = row.get("attachment_mime") or "application/octet-stream"
        return Response(
            row["attachment_data"],
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@general_supervisors_bp.route("/api/notifications/unread-count", methods=["GET"])
def unread_count():
    if "user_id" not in session or session.get("role") != "supervisor":
        return jsonify({"unread": 0})
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE recipient_id = %s AND is_read = FALSE",
            (session.get("user_id"),),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return jsonify({"unread": int((row or {}).get("cnt") or 0)})
    except Exception:
        return jsonify({"unread": 0})


