from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template,
    jsonify,
    Response,
)
import bcrypt
import secrets
import datetime
import os
import csv
import io
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()
from flask_mail import Mail, Message
from db import get_db
from auth import login_required
from routes.archive_search import archive_bp
from routes.shared_ai import shared_ai_bp
from routes.student import student_bp
from routes.head import head_bp
from routes.appCoordinator import coordinator_bp
from routes.supervisor_evaluation import supervisor_evaluation_bp
from ai_engine import ask_apms_ai, get_ai_health, get_archived_projects
from activate_student import activate_bp
from announcements import announcements_bp
from routes.general_supervisors import general_supervisors_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))
AI_RESPONSE_TIMEOUT_SECONDS = int(os.environ.get("AI_RESPONSE_TIMEOUT_SECONDS", "55"))
_ai_executor = ThreadPoolExecutor(max_workers=2)

# ─── Mail config ─────────────────────────────────────────────────────────
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "rahafbadwan574@gmail.com"
app.config["MAIL_PASSWORD"] = "ykma scjl fdwg ohlt"
app.config["MAIL_DEFAULT_SENDER"] = (
    "APMS — Birzeit University",
    "rahafbadwan574@gmail.com",
)

mail = Mail(app)


@app.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.png"))

# ─── Register Blueprints ─────────────────────────────────────────────────
app.register_blueprint(archive_bp)
app.register_blueprint(shared_ai_bp)
app.register_blueprint(student_bp)
app.register_blueprint(head_bp)
app.register_blueprint(coordinator_bp)
app.register_blueprint(supervisor_evaluation_bp)
app.register_blueprint(activate_bp)
app.register_blueprint(announcements_bp, url_prefix='/head')
app.register_blueprint(general_supervisors_bp, url_prefix='/supervisor')
# ─── Helpers ─────────────────────────────────────────────────────────────
def _get_active_semester(cursor):
    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code,
               COALESCE(distribution_open, 0) AS distribution_open,
               distribution_opened_at,
               distribution_closed_at
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
    """)
    return cursor.fetchone()


def _csv_response(filename, headers, rows):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    data = output.getvalue()
    output.close()
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _get_public_notice():
    """Return the active important notice for the public login page."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT title, body, highlight_text, button1_text, button2_text, button3_text, course_scope
            FROM system_notices
            WHERE is_active = TRUE
            ORDER BY updated_at DESC, notice_id DESC
            LIMIT 1
            """
        )
        notice = cursor.fetchone()
        cursor.close()
        db.close()
        return notice
    except Exception:
        return None


def _render_login(**context):
    context.setdefault("public_notice", _get_public_notice())
    return render_template("login.html", **context)


# ─── Login / Logout ──────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def login_page():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    # Messages saved here are used after redirecting from POST /login.
    # This prevents the browser from showing "Resubmit the form?" on refresh.
    error = session.pop("login_error", None)
    uid = session.pop("login_uid", "")
    return _render_login(error=error, university_id=uid)


@app.route("/login", methods=["GET"])
def login_get():
    return redirect(url_for("login_page"))


@app.route("/login", methods=["POST"])
def login():
    uid = request.form.get("university_id", "").strip()
    pwd = request.form.get("password", "").strip()

    def back_to_login(error_message):
        session["login_error"] = error_message
        session["login_uid"] = uid
        return redirect(url_for("login_page"))

    if not uid or not pwd:
        return back_to_login("Please fill in all fields.")

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM users WHERE university_id = %s AND is_active = TRUE", (uid,)
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception as e:
        return back_to_login(f"Database error: {e}")

    if not user:
        return back_to_login("Invalid University ID or password.")

    if not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
        return back_to_login("Invalid University ID or password.")

    session.pop("login_error", None)
    session.pop("login_uid", None)

    session["user_id"] = user["user_id"]
    session["university_id"] = user["university_id"]
    session["full_name"] = user["full_name"]
    session["role"] = user["role"]
    session["avatar_initials"] = (
        user["avatar_initials"] or user["full_name"][:2].upper()
    )
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))



# ─── Forgot Password ─────────────────────────────────────────────────────
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html")

    uid_or_email = request.form.get("uid_or_email", "").strip()
    if not uid_or_email:
        return render_template(
            "forgot_password.html", error="Please enter your University ID or email."
        )
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """SELECT user_id, email, full_name FROM users
               WHERE (university_id = %s OR email = %s) AND is_active = TRUE""",
            (uid_or_email, uid_or_email),
        )
        user = cursor.fetchone()

        if not user:
            cursor.close()
            db.close()
            return render_template(
                "forgot_password.html",
                success="If that account exists, a reset link has been sent to its email.",
            )

        token = secrets.token_urlsafe(48)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
        cursor.execute(
            "UPDATE password_reset_tokens SET used = TRUE WHERE user_id = %s AND used = FALSE",
            (user["user_id"],),
        )
        cursor.execute(
            "INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES (%s, %s, %s)",
            (user["user_id"], token, expires_at),
        )
        db.commit()
        cursor.close()
        db.close()

        reset_link = url_for("reset_password", token=token, _external=True)
        send_reset_email(user["email"], user["full_name"], reset_link)

        return render_template(
            "forgot_password.html",
            success="If that account exists, a reset link has been sent to its email.",
        )
    except Exception as e:
        return render_template("forgot_password.html", error=f"An error occurred: {e}")


def send_reset_email(to_email, full_name, reset_link):
    msg = Message(subject="APMS — Password Reset Request", recipients=[to_email])
    msg.html = f"""
    <div style="font-family:'Segoe UI',Tahoma,sans-serif;max-width:520px;margin:auto;
                background:#fff;border:1px solid #e0e0e0;border-radius:10px;overflow:hidden;">
      <div style="background:#2d6a38;padding:24px 32px;text-align:center;">
        <div style="display:inline-block;background:rgba(255,255,255,0.15);border-radius:8px;
                    padding:6px 14px;color:#fff;font-size:20px;font-weight:800;letter-spacing:1px;">APMS</div>
        <p style="color:#c8e6c9;font-size:12px;margin:8px 0 0;">
          Academic Project Management System<br>Birzeit University
        </p>
      </div>
      <div style="padding:32px;">
        <h2 style="color:#1a3d1f;font-size:18px;margin:0 0 12px;">Password Reset Request</h2>
        <p style="color:#444;font-size:14px;line-height:1.6;margin:0 0 20px;">
          Hello <strong>{full_name}</strong>,<br><br>
          We received a request to reset the password for your APMS account.
          Click the button below to set a new password. This link is valid for <strong>1 hour</strong>.
        </p>
        <div style="text-align:center;margin:28px 0;">
          <a href="{reset_link}"
             style="background:#2d6a38;color:#fff;text-decoration:none;padding:13px 32px;
                    border-radius:8px;font-size:14px;font-weight:600;display:inline-block;">
            Reset My Password
          </a>
        </div>
        <p style="color:#888;font-size:12px;line-height:1.6;margin:0;">
          If you didn't request this, you can safely ignore this email.<br><br>
          If the button doesn't work, copy and paste this link:<br>
          <a href="{reset_link}" style="color:#2d6a38;word-break:break-all;">{reset_link}</a>
        </p>
      </div>
    </div>
    """
    mail.send(msg)


# ─── Reset Password ──────────────────────────────────────────────────────
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """SELECT prt.*, u.full_name, u.email
               FROM password_reset_tokens prt
               JOIN users u ON u.user_id = prt.user_id
               WHERE prt.token = %s AND prt.used = FALSE AND prt.expires_at > UTC_TIMESTAMP()""",
            (token,),
        )
        record = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception as e:
        return render_template(
            "reset_password.html", error=f"Database error: {e}", token=token
        )

    if not record:
        return render_template(
            "reset_password.html",
            invalid=True,
            error="This reset link is invalid or has expired. Please request a new one.",
        )

    if request.method == "GET":
        return render_template(
            "reset_password.html", token=token, name=record["full_name"]
        )

    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not new_password or not confirm_password:
        return render_template(
            "reset_password.html",
            token=token,
            name=record["full_name"],
            error="Please fill in all fields.",
        )
    if len(new_password) < 8:
        return render_template(
            "reset_password.html",
            token=token,
            name=record["full_name"],
            error="Password must be at least 8 characters.",
        )
    if new_password != confirm_password:
        return render_template(
            "reset_password.html",
            token=token,
            name=record["full_name"],
            error="Passwords do not match.",
        )

    try:
        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s",
            (hashed, record["user_id"]),
        )
        cursor.execute(
            "UPDATE password_reset_tokens SET used = TRUE WHERE token = %s", (token,)
        )
        db.commit()
        cursor.close()
        db.close()
        return render_template("reset_password.html", success=True)
    except Exception as e:
        return render_template(
            "reset_password.html",
            token=token,
            name=record["full_name"],
            error=f"An error occurred: {e}",
        )


# ─── Dashboard ───────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    role = session.get("role")
    routes = {
        "student": "student.dashboard",
        "supervisor": "supervisor_dashboard",
        "coordinator": "coordinator_bp.coordinator_dashboard",
        "head_of_department": "head.dashboard",
    }
    target = routes.get(role)
    if not target:
        return redirect(url_for("logout"))
    return redirect(url_for(target))


# ─── AI Conversation Archive Helpers ─────────────────────────────────────
AI_ARCHIVE_DAYS = 30
_AI_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def _ensure_ai_archive_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_conversations (
            conv_id      INT PRIMARY KEY AUTO_INCREMENT,
            user_id      INT NOT NULL,
            session_id   VARCHAR(120) NOT NULL,
            message_role ENUM('user','assistant') NOT NULL,
            message_text MEDIUMTEXT NOT NULL,
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    try:
        cursor.execute("ALTER TABLE ai_conversations ADD COLUMN reply_to MEDIUMTEXT NULL")
    except Exception:
        pass
    try:
        cursor.execute(
            "CREATE INDEX idx_ai_user_session ON ai_conversations(user_id, session_id, created_at)"
        )
    except Exception:
        pass
    try:
        cursor.execute("CREATE INDEX idx_ai_created ON ai_conversations(created_at)")
    except Exception:
        pass


def _new_ai_session_id():
    return secrets.token_urlsafe(18)


def _normalize_ai_session_id(value):
    value = (value or "").strip()
    if value and _AI_SESSION_RE.match(value):
        return value
    return _new_ai_session_id()


def _dt_iso(value):
    if not value:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _purge_expired_ai_conversations(cursor):
    _ensure_ai_archive_table(cursor)
    cursor.execute(
        """
        DELETE ac
        FROM ai_conversations ac
        JOIN (
            SELECT session_id
            FROM (
                SELECT session_id
                FROM ai_conversations
                WHERE session_id IS NOT NULL
                GROUP BY session_id
                HAVING MIN(created_at) < (UTC_TIMESTAMP() - INTERVAL %s DAY)
            ) expired_sessions
        ) expired ON expired.session_id = ac.session_id
        """,
        (AI_ARCHIVE_DAYS,),
    )
    cursor.execute(
        """
        DELETE FROM ai_conversations
        WHERE session_id IS NULL
          AND created_at < (UTC_TIMESTAMP() - INTERVAL %s DAY)
        """,
        (AI_ARCHIVE_DAYS,),
    )


def _save_ai_exchange(user_id, session_id, question, answer, reply_to=None):
    db = get_db()
    cursor = db.cursor()
    try:
        _purge_expired_ai_conversations(cursor)
        cursor.execute(
            """
            INSERT INTO ai_conversations (user_id, session_id, message_role, message_text, reply_to)
            VALUES (%s, %s, 'user', %s, %s)
            """,
            (user_id, session_id, question, reply_to),
        )
        cursor.execute(
            """
            INSERT INTO ai_conversations (user_id, session_id, message_role, message_text)
            VALUES (%s, %s, 'assistant', %s)
            """,
            (user_id, session_id, answer),
        )
        db.commit()
        return True, None
    except Exception as exc:
        db.rollback()
        return False, str(exc)
    finally:
        cursor.close()
        db.close()


# ─── AI API ──────────────────────────────────────────────────────────────
def _load_ai_conversation_context(user_id, session_id, limit=10):
    if not session_id:
        return ""
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT message_role, message_text
            FROM ai_conversations
            WHERE user_id = %s AND session_id = %s
            ORDER BY created_at DESC, conv_id DESC
            LIMIT %s
            """,
            (user_id, session_id, limit),
        )
        rows = list(reversed(cursor.fetchall()))
        return "\n".join(
            f"{row.get('message_role')}: {row.get('message_text')}"
            for row in rows
            if row.get("message_text")
        )
    except Exception:
        return ""
    finally:
        cursor.close()
        db.close()


@app.route("/api/ai/archived-projects", methods=["GET"])
@login_required()
def api_ai_archived_projects():
    projects = [
        {
            "title": project.get("title"),
            "project_type": project.get("project_type"),
            "final_score": project.get("final_score"),
            "pdf": project.get("pdf"),
            "file_path": project.get("file_path"),
            "status": project.get("status"),
        }
        for project in get_archived_projects()
    ]
    return jsonify({"count": len(projects), "projects": projects})


@app.route("/api/ai/health", methods=["GET"])
@login_required()
def api_ai_health():
    return jsonify(get_ai_health())


@app.route("/api/ai/ask", methods=["POST"])
@login_required()
def api_ai_ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    session_id = _normalize_ai_session_id(data.get("session_id"))
    reply_to = (data.get("reply_to") or "").strip() or None

    if not question:
        return (
            jsonify(
                {
                    "error": "Please write a question before sending.",
                    "session_id": session_id,
                }
            ),
            400,
        )

    try:
        conversation_context = _load_ai_conversation_context(
            session["user_id"], session_id
        )
        future = _ai_executor.submit(
            ask_apms_ai, question, reply_to, conversation_context
        )
        answer = future.result(timeout=AI_RESPONSE_TIMEOUT_SECONDS)
    except TimeoutError:
        future.cancel()
        return (
            jsonify(
                {
                    "error": "AI service timed out. Please try a shorter question or try again in a moment.",
                    "session_id": session_id,
                }
            ),
            504,
        )
    except Exception as exc:
        import traceback

        traceback.print_exc()
        error_text = str(exc)
        status_code = 500
        user_message = "The AI assistant is temporarily unavailable. Please try again in a moment."
        if "quota exceeded" in error_text.lower() or "429" in error_text:
            status_code = 429
            user_message = "The AI assistant is temporarily busy or out of available credits. Please try again later."
        elif "api key" in error_text.lower() or "401" in error_text:
            status_code = 503
            user_message = "The AI assistant is not configured correctly right now. Please contact the system administrator."
        return (
            jsonify({"error": user_message, "session_id": session_id}),
            status_code,
        )

    try:
        saved, save_error = _save_ai_exchange(
            session["user_id"], session_id, question, answer, reply_to
        )
    except Exception as exc:
        saved, save_error = False, str(exc)

    payload = {"answer": answer, "session_id": session_id, "archive_saved": saved}
    if save_error:
        payload["archive_error"] = save_error
    return jsonify(payload)


@app.route("/api/ai/archive", methods=["GET"])
@login_required()
def api_ai_archive():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _purge_expired_ai_conversations(cursor)
        db.commit()
        cursor.execute(
            """
            SELECT
                c.session_id,
                MIN(c.created_at) AS created_at,
                MAX(c.created_at) AS updated_at,
                COUNT(*) AS message_count,
                DATE_ADD(MIN(c.created_at), INTERVAL %s DAY) AS expires_at,
                GREATEST(
                    0,
                    TIMESTAMPDIFF(DAY, UTC_TIMESTAMP(), DATE_ADD(MIN(c.created_at), INTERVAL %s DAY))
                ) AS days_left,
                (
                    SELECT LEFT(m.message_text, 120)
                    FROM ai_conversations m
                    WHERE m.user_id = c.user_id
                      AND m.session_id = c.session_id
                      AND m.message_role = 'user'
                    ORDER BY m.created_at ASC, m.conv_id ASC
                    LIMIT 1
                ) AS title
            FROM ai_conversations c
            WHERE c.user_id = %s
              AND c.session_id IS NOT NULL
            GROUP BY c.session_id, c.user_id
            ORDER BY updated_at DESC
            LIMIT 60
            """,
            (AI_ARCHIVE_DAYS, AI_ARCHIVE_DAYS, session["user_id"]),
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        conversations = []
        for row in rows:
            conversations.append(
                {
                    "session_id": row["session_id"],
                    "title": row.get("title") or "Untitled chat",
                    "created_at": _dt_iso(row.get("created_at")),
                    "updated_at": _dt_iso(row.get("updated_at")),
                    "expires_at": _dt_iso(row.get("expires_at")),
                    "days_left": int(row.get("days_left") or 0),
                    "message_count": int(row.get("message_count") or 0),
                }
            )
        return jsonify(
            {"conversations": conversations, "retention_days": AI_ARCHIVE_DAYS}
        )
    except Exception as exc:
        return jsonify({"error": f"Could not load AI archive: {exc}"}), 500


@app.route("/api/ai/archive/<session_id>", methods=["GET"])
@login_required()
def api_ai_archive_detail(session_id):
    if not _AI_SESSION_RE.match((session_id or "").strip()):
        return jsonify({"error": "Invalid conversation id."}), 400
    session_id = session_id.strip()
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _purge_expired_ai_conversations(cursor)
        db.commit()
        cursor.execute(
            """
            SELECT message_role, message_text, reply_to, created_at
            FROM ai_conversations
            WHERE user_id = %s AND session_id = %s
            ORDER BY created_at ASC, conv_id ASC
            """,
            (session["user_id"], session_id),
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify(
            {
                "session_id": session_id,
                "messages": [
                    {
                        "role": row["message_role"],
                        "text": row["message_text"],
                        "reply_to": row.get("reply_to"),
                        "created_at": _dt_iso(row.get("created_at")),
                    }
                    for row in rows
                ],
            }
        )
    except Exception as exc:
        return jsonify({"error": f"Could not load conversation: {exc}"}), 500


@app.route("/api/ai/archive/<session_id>", methods=["DELETE"])
@login_required()
def api_ai_archive_delete(session_id):
    if not _AI_SESSION_RE.match((session_id or "").strip()):
        return jsonify({"error": "Invalid conversation id."}), 400
    session_id = session_id.strip()
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "DELETE FROM ai_conversations WHERE user_id = %s AND session_id = %s",
            (session["user_id"], session_id),
        )
        deleted = cursor.rowcount
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"deleted": deleted, "session_id": session_id})
    except Exception as exc:
        return jsonify({"error": f"Could not delete conversation: {exc}"}), 500


# ─── Student distribution APIs ───────────────────────────────────────────


@app.route("/api/coordinator/assign-student", methods=["POST"])
@login_required(role="coordinator")
def api_assign_student():
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")
    faculty_id = data.get("faculty_id")

    if not student_id or not faculty_id:
        return jsonify({"error": "student_id and faculty_id are required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)
        cursor.execute(
            "SELECT u.full_name FROM students st JOIN users u ON u.user_id = st.user_id WHERE st.student_id = %s",
            (student_id,),
        )
        student = cursor.fetchone()

        if not semester or not student:
            cursor.close()
            db.close()
            return jsonify({"error": "Student or active semester not found."}), 404

        cursor.execute(
            "INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date) VALUES (%s, 'software_engineering', %s, %s, 'under_review', CURDATE())",
            (
                f"Individual Project - {student['full_name']}",
                semester["semester_id"],
                faculty_id,
            ),
        )
        project_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, TRUE)",
            (project_id, student_id),
        )

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {"message": "Student assigned successfully.", "project_id": project_id}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Supervisor routes ────────────────────────────────────────────────────
SUPERVISOR_PAGES = {
    "dashboard": "supervisor/index.html",
    "mystudents": "supervisor/mystudents.html",
    "progress": "supervisor/progress.html",
    "feedback": "supervisor/feedback.html",
    "evaluation": "supervisor/evaluation.html",
    "search": "shared/archive_search.html",
    "notifs": "supervisor/notifs.html",
    "ai": "shared/ai.html",
    "profile": "supervisor/profile.html",
}


@app.route("/supervisor/")
@app.route("/supervisor/dashboard")
@login_required(role="supervisor")
def supervisor_dashboard():
    return render_template("supervisor/index.html")


@app.route("/supervisor/<page>")
@login_required(role="supervisor")
def supervisor_subpage(page):
    template = SUPERVISOR_PAGES.get(page)
    if not template:
        return redirect(url_for("supervisor_dashboard"))
    return render_template(template)


# ─── Supervisor feedback APIs ─────────────────────────────────────────────


@app.route("/api/supervisor/my-projects", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_my_projects():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        from routes.supervisor_progress_api import (
            _current_supervisor_faculty_id,
            _fetch_supervisor_projects,
        )

        faculty_id = _current_supervisor_faculty_id(cursor)
        projects = _fetch_supervisor_projects(cursor, faculty_id)
        return jsonify({"projects": projects})
    finally:
        cursor.close()
        db.close()


@app.route("/api/supervisor/submit-feedback", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_submit_feedback():
    user_id = session["user_id"]
    data = request.get_json(force=True)

    project_id = data.get("project_id")
    feedback_type = data.get("feedback_type", "general_performance")
    feedback_text = (data.get("feedback_text") or "").strip()
    priority = data.get("priority", "normal")
    is_draft = bool(data.get("is_draft", False))
    points = data.get("improvement_points", [])

    if not project_id or not feedback_text:
        return jsonify({"error": "project_id and feedback_text are required"}), 400
    if priority not in {"normal", "important", "urgent"}:
        return jsonify({"error": "Invalid feedback priority"}), 400

    db = get_db()
    cursor = db.cursor(dictionary=True)

    from routes.supervisor_progress_api import (
        _current_supervisor_faculty_id,
        _get_project_for_supervisor,
    )

    faculty_id = _current_supervisor_faculty_id(cursor)
    if not faculty_id or not _get_project_for_supervisor(cursor, project_id, faculty_id):
        cursor.close()
        db.close()
        return jsonify({"error": "You are not assigned to this project"}), 403

    cursor.execute(
        """
        INSERT INTO feedback (project_id, reviewer_id, feedback_type, feedback_text, priority, is_draft)
        VALUES (%s, %s, %s, %s, %s, %s)
    """,
        (project_id, user_id, feedback_type, feedback_text, priority, is_draft),
    )
    feedback_id = cursor.lastrowid

    for pt in points:
        pt = str(pt).strip()
        if pt:
            cursor.execute(
                "INSERT INTO feedback_improvement_points (feedback_id, point_text) VALUES (%s, %s)",
                (feedback_id, pt),
            )

    db.commit()
    cursor.close()
    db.close()
    return jsonify({"success": True, "feedback_id": feedback_id})


@app.route("/switch-back-to-coordinator", methods=["POST", "GET"])
@login_required(role="supervisor")
def switch_back_to_coordinator():
    """
    Return from supervisor view back to coordinator account.
    """
    if not session.get("is_switched_to_supervisor"):
        return redirect(url_for("supervisor_dashboard"))

    session["role"] = session.get("original_role", "coordinator")
    session["user_id"] = session.get("original_user_id", session.get("user_id"))
    session["full_name"] = session.get("original_full_name", session.get("full_name"))

    session.pop("original_role", None)
    session.pop("original_user_id", None)
    session.pop("original_full_name", None)
    session.pop("is_switched_to_supervisor", None)

    return redirect(url_for("coordinator_bp.coordinator_dashboard"))


@app.route("/api/supervisor/my-feedback", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_my_feedback():
    user_id = session["user_id"]
    project_id = request.args.get("project_id")
    db = get_db()
    cursor = db.cursor(dictionary=True)

    sql = """
        SELECT f.feedback_id, f.project_id, p.title AS project_title,
               f.feedback_type, f.feedback_text, f.priority,
               f.is_draft, f.created_at
        FROM   feedback f
        JOIN   projects p ON p.project_id = f.project_id
        WHERE  f.reviewer_id = %s
    """
    params = [user_id]
    if project_id:
        sql += " AND f.project_id = %s"
        params.append(project_id)
    sql += " ORDER BY f.created_at DESC LIMIT 20"

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    for r in rows:
        r["created_at"] = (
            r["created_at"].strftime("%b %d, %Y") if r["created_at"] else ""
        )
        r["is_draft"] = bool(r["is_draft"])

    cursor.close()
    db.close()
    return jsonify({"feedback": rows})

# ─── Supervisor Notifications / Messaging ───────────────────────────────
def _sup_notif_column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    return int((cursor.fetchone() or {}).get("cnt") or 0) > 0


def _sup_notif_table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    return int((cursor.fetchone() or {}).get("cnt") or 0) > 0


def _ensure_supervisor_notifications_schema(cursor):
    if _sup_notif_table_exists(cursor, "notifications"):
        if not _sup_notif_column_exists(cursor, "notifications", "course_scope"):
            cursor.execute(
                """
                ALTER TABLE notifications
                ADD COLUMN course_scope ENUM('introduction','graduation_project','both')
                NOT NULL DEFAULT 'both' AFTER message
                """
            )
        if not _sup_notif_column_exists(cursor, "notifications", "can_reply"):
            cursor.execute(
                "ALTER TABLE notifications ADD COLUMN can_reply TINYINT(1) NOT NULL DEFAULT 1 AFTER is_read"
            )
        if not _sup_notif_column_exists(cursor, "notifications", "attachment_name"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255) NULL")
        if not _sup_notif_column_exists(cursor, "notifications", "attachment_mime"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120) NULL")
        if not _sup_notif_column_exists(cursor, "notifications", "attachment_data"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_data LONGBLOB NULL")


def _sup_notification_enum_values(cursor):
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


def _sup_safe_notification_type(cursor, requested_type="system"):
    allowed = _sup_notification_enum_values(cursor)
    if not allowed:
        return requested_type or "system"
    if requested_type in allowed:
        return requested_type
    for fallback in ("system", "info", "message", "deadline_reminder", "urgent_alert", "alert"):
        if fallback in allowed:
            return fallback
    return allowed[0]


def _sup_notif_select_fields(cursor):
    attachment_fields = (
        "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"
        if _sup_notif_column_exists(cursor, "notifications", "attachment_name")
        else "NULL AS attachment_name, NULL AS attachment_mime, 0 AS has_attachment"
    )
    can_reply_field = (
        "COALESCE(n.can_reply, 1) AS can_reply"
        if _sup_notif_column_exists(cursor, "notifications", "can_reply")
        else "1 AS can_reply"
    )
    return attachment_fields, can_reply_field


def _sup_notif_row_to_json(row):
    clean = dict(row or {})
    if clean.get("created_at") is not None:
        clean["created_at"] = str(clean["created_at"])
    clean["is_read"] = bool(clean.get("is_read"))
    clean["course_scope"] = clean.get("course_scope") or "both"
    clean["has_attachment"] = bool(clean.get("has_attachment"))
    clean["can_reply"] = bool(clean.get("can_reply", True))
    if not clean["has_attachment"]:
        clean["attachment_name"] = None
        clean["attachment_mime"] = None
    clean.pop("attachment_data", None)
    return clean


def _sup_active_semester_by_course(cursor, course_code):
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


def _sup_coordinator_user_ids(cursor, course_scope="both"):
    course_code = "COMP4300" if course_scope == "graduation_project" else "COMP4200" if course_scope == "introduction" else None
    if course_code and _sup_notif_table_exists(cursor, "coordinator_assignments"):
        semester = _sup_active_semester_by_course(cursor, course_code)
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
                """,
                (semester["semester_id"],),
            )
            rows = [r["user_id"] for r in cursor.fetchall()]
            if rows:
                return rows
    cursor.execute("SELECT user_id FROM users WHERE role = 'coordinator' AND is_active = TRUE")
    return [r["user_id"] for r in cursor.fetchall()]


def _sup_comp4200_section_recipients(cursor, section_id=None):
    if not (_sup_notif_table_exists(cursor, "student_distribution_sections") and _sup_notif_table_exists(cursor, "section_students")):
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


def _sup_comp4300_project_recipients(cursor, project_id=None):
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


def _sup_notification_recipients(cursor, scope, value=None, course_scope="both"):
    scope = (scope or "").strip()
    course_scope = (course_scope or "both").strip()
    if scope == "heads":
        cursor.execute("SELECT user_id FROM users WHERE role = 'head_of_department' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "head":
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND role = 'head_of_department' AND is_active = TRUE", (value,))
        return [r["user_id"] for r in cursor.fetchall()]
    if scope in {"coordinators", "coordinator"}:
        if scope == "coordinator" and value:
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND role = 'coordinator' AND is_active = TRUE", (value,))
            return [r["user_id"] for r in cursor.fetchall()]
        return _sup_coordinator_user_ids(cursor, course_scope)
    if scope == "doctors":
        cursor.execute("SELECT user_id FROM users WHERE role = 'supervisor' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "doctor":
        cursor.execute(
            """
            SELECT u.user_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s AND u.role = 'supervisor' AND u.is_active = TRUE
            """,
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]
    if scope in {"students", "all_students", "comp4200_students", "comp4300_students"}:
        target = course_scope
        if scope == "comp4200_students":
            target = "introduction"
        elif scope == "comp4300_students":
            target = "graduation_project"
        if target == "graduation_project":
            return [r for r in _sup_comp4300_project_recipients(cursor) if r]
        if target == "introduction":
            if _sup_notif_table_exists(cursor, "student_course_results"):
                cursor.execute(
                    """
                    SELECT DISTINCT u.user_id
                    FROM student_course_results scr
                    JOIN semesters sem ON sem.semester_id = scr.semester_id
                    JOIN students st ON st.student_id = scr.student_id
                    JOIN users u ON u.user_id = st.user_id
                    WHERE sem.course_code = 'COMP4200' AND u.role = 'student' AND u.is_active = TRUE
                    """
                )
                rows = [r["user_id"] for r in cursor.fetchall()]
                if rows:
                    return rows
            return _sup_comp4200_section_recipients(cursor)
        cursor.execute("SELECT user_id FROM users WHERE role = 'student' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "student":
        cursor.execute(
            """
            SELECT u.user_id
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.student_id = %s AND u.role = 'student' AND u.is_active = TRUE
            """,
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "section":
        if course_scope == "graduation_project" or str(value).startswith("p:"):
            return _sup_comp4300_project_recipients(cursor, str(value).replace("p:", "", 1))
        return _sup_comp4200_section_recipients(cursor, str(value).replace("s:", "", 1))
    if scope == "all_sections":
        recipients = []
        if course_scope in {"introduction", "both"}:
            recipients.extend(_sup_comp4200_section_recipients(cursor))
        if course_scope in {"graduation_project", "both"}:
            recipients.extend(_sup_comp4300_project_recipients(cursor))
        return sorted(set(recipients))
    if scope == "reply":
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND is_active = TRUE", (value,))
        return [r["user_id"] for r in cursor.fetchall()]
    return []


def _sup_reply_allowed(cursor, notification_id, current_user_id, target_user_id):
    can_reply_expr = "COALESCE(can_reply, 1)" if _sup_notif_column_exists(cursor, "notifications", "can_reply") else "1"
    if notification_id:
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
    return False


@app.route("/supervisor/api/notifications/options", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_notifications_options():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_notifications_schema(cursor); db.commit()
        heads = []
        cursor.execute("SELECT user_id, full_name, university_id, 'both' AS course_scope, 'Both' AS course_code FROM users WHERE role = 'head_of_department' AND is_active = TRUE ORDER BY full_name")
        heads = cursor.fetchall()
        coordinator_rows = []
        for course_scope, course_code in (("introduction", "COMP4200"), ("graduation_project", "COMP4300")):
            semester = _sup_active_semester_by_course(cursor, course_code)
            if semester and _sup_notif_table_exists(cursor, "coordinator_assignments"):
                cursor.execute(
                    """
                    SELECT DISTINCT u.user_id, u.full_name, u.university_id, %s AS course_scope, %s AS course_code
                    FROM coordinator_assignments ca
                    JOIN faculty f ON f.faculty_id = ca.faculty_id
                    JOIN users u ON u.user_id = f.user_id
                    WHERE ca.semester_id = %s AND u.role = 'coordinator' AND u.is_active = TRUE
                    """,
                    (course_scope, course_code, semester["semester_id"]),
                )
                coordinator_rows.extend(cursor.fetchall())
        if not coordinator_rows:
            cursor.execute("SELECT user_id, full_name, university_id, 'both' AS course_scope, 'Both' AS course_code FROM users WHERE role = 'coordinator' AND is_active = TRUE ORDER BY full_name")
            coordinator_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT f.faculty_id, u.user_id, u.full_name, u.university_id
            FROM faculty f JOIN users u ON u.user_id = f.user_id
            WHERE u.role = 'supervisor' AND u.is_active = TRUE
            ORDER BY u.full_name
            """
        )
        doctors = cursor.fetchall()
        cursor.execute(
            """
            SELECT st.student_id, u.user_id, u.full_name, u.university_id,
                   CASE WHEN EXISTS (
                        SELECT 1 FROM project_members pm
                        JOIN projects p ON p.project_id = pm.project_id
                        JOIN semesters s ON s.semester_id = p.semester_id
                        WHERE pm.student_id = st.student_id AND s.course_code = 'COMP4300'
                   ) THEN 'graduation_project' ELSE 'introduction' END AS course_scope,
                   CASE WHEN EXISTS (
                        SELECT 1 FROM project_members pm
                        JOIN projects p ON p.project_id = pm.project_id
                        JOIN semesters s ON s.semester_id = p.semester_id
                        WHERE pm.student_id = st.student_id AND s.course_code = 'COMP4300'
                   ) THEN 'COMP4300' ELSE 'COMP4200' END AS course_code
            FROM students st JOIN users u ON u.user_id = st.user_id
            WHERE u.role = 'student' AND u.is_active = TRUE
            ORDER BY u.full_name
            """
        )
        students = cursor.fetchall()
        sections = []
        if _sup_notif_table_exists(cursor, "student_distribution_sections") and _sup_notif_table_exists(cursor, "section_students"):
            cursor.execute(
                """
                SELECT CONCAT('s:', sec.section_id) AS section_key, sec.section_id,
                       sec.section_name, 'introduction' AS course_scope, 'COMP4200' AS course_code,
                       u_sup.full_name AS supervisor_name, COUNT(DISTINCT ss.student_id) AS students_count
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
            SELECT CONCAT('p:', p.project_id) AS section_key, p.project_id AS section_id,
                   COALESCE(NULLIF(p.title, ''), CONCAT('COMP4300 Project ', p.project_id)) AS section_name,
                   'graduation_project' AS course_scope, 'COMP4300' AS course_code,
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
        cursor.close(); db.close()
        return jsonify({"heads": heads, "coordinators": coordinator_rows, "doctors": doctors, "students": students, "sections": sections})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/inbox", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_notifications_inbox():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_notifications_schema(cursor); db.commit()
        attachment_fields, can_reply_field = _sup_notif_select_fields(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.notification_type, n.title, n.message,
                   n.course_scope, n.related_project_id, n.is_read, n.created_at,
                   n.sender_id AS sender_user_id, sender.full_name AS sender_name, sender.role AS sender_role,
                   {can_reply_field}, {attachment_fields}
            FROM notifications n
            LEFT JOIN users sender ON sender.user_id = n.sender_id
            WHERE n.recipient_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_sup_notif_row_to_json(r) for r in cursor.fetchall()]
        cursor.close(); db.close()
        return jsonify({"notifications": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/sent", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_notifications_sent():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_notifications_schema(cursor); db.commit()
        attachment_fields, can_reply_field = _sup_notif_select_fields(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.title, n.message, n.notification_type,
                   n.course_scope, n.is_read, n.created_at,
                   n.recipient_id AS recipient_user_id, recipient.full_name AS recipient_name, recipient.role AS recipient_role,
                   {can_reply_field}, {attachment_fields}
            FROM notifications n
            JOIN users recipient ON recipient.user_id = n.recipient_id
            WHERE n.sender_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_sup_notif_row_to_json(r) for r in cursor.fetchall()]
        cursor.close(); db.close()
        return jsonify({"sent": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/send", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_notifications_send():
    is_multipart = bool(request.content_type and request.content_type.startswith("multipart/form-data"))
    data = request.form if is_multipart else (request.get_json(silent=True) or {})
    uploaded_file = request.files.get("file") if is_multipart else None
    scope = (data.get("scope") or "").strip()
    value = data.get("value")
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    urgent = str(data.get("urgent") or "").lower() in ("1", "true", "on", "yes")
    course_scope = (data.get("course_scope") or "both").strip()
    can_reply = str(data.get("can_reply") or "0").lower() in ("1", "true", "on", "yes")
    reply_to_notification_id = data.get("reply_to_notification_id") or data.get("notification_id")
    if course_scope not in {"introduction", "graduation_project", "both"}:
        return jsonify({"error": "Please choose the course scope."}), 400
    if not scope:
        return jsonify({"error": "Please choose who should receive the message."}), 400
    if not title:
        return jsonify({"error": "Please write a title."}), 400
    if not message:
        return jsonify({"error": "Please write a message."}), 400
    if scope in {"head", "coordinator", "doctor", "student", "section", "reply"} and not value:
        return jsonify({"error": "Please choose the exact receiver."}), 400
    attachment_name = attachment_mime = attachment_data = None
    if uploaded_file and uploaded_file.filename:
        attachment_name = secure_filename(uploaded_file.filename) or "attachment"
        attachment_mime = uploaded_file.mimetype or "application/octet-stream"
        attachment_data = uploaded_file.read()
        if len(attachment_data) > 10 * 1024 * 1024:
            return jsonify({"error": "Attachment must be 10 MB or smaller."}), 400
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_notifications_schema(cursor)
        sender_id = session.get("user_id")
        recipients = sorted({int(r) for r in _sup_notification_recipients(cursor, scope, value, course_scope) if int(r) != int(sender_id)})
        if not recipients:
            cursor.close(); db.close()
            return jsonify({"error": "No recipients found for this choice."}), 404
        if scope == "reply":
            for recipient_id in recipients:
                if not _sup_reply_allowed(cursor, reply_to_notification_id, sender_id, recipient_id):
                    cursor.close(); db.close()
                    return jsonify({"error": "Replies are disabled for this message."}), 403
            can_reply = True
        notification_type = _sup_safe_notification_type(cursor, "urgent_alert" if urgent else "system")
        for recipient_id in recipients:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read, can_reply,
                     attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE, %s, %s, %s, %s)
                """,
                (recipient_id, sender_id, notification_type, title, message, course_scope, 1 if can_reply else 0, attachment_name, attachment_mime, attachment_data),
            )
        db.commit(); cursor.close(); db.close()
        return jsonify({"message": f"Message sent successfully to {len(recipients)} recipient(s).", "sent_count": len(recipients)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/<int:notification_id>/read", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_notifications_mark_read(notification_id):
    try:
        db = get_db(); cursor = db.cursor()
        cursor.execute("UPDATE notifications SET is_read = TRUE WHERE notification_id = %s AND recipient_id = %s", (notification_id, session.get("user_id")))
        db.commit(); cursor.close(); db.close()
        return jsonify({"message": "Notification marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/read-all", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_notifications_mark_all_read():
    try:
        db = get_db(); cursor = db.cursor()
        cursor.execute("UPDATE notifications SET is_read = TRUE WHERE recipient_id = %s", (session.get("user_id"),))
        db.commit(); cursor.close(); db.close()
        return jsonify({"message": "All messages marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/<int:notification_id>/attachment", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_notification_attachment(notification_id):
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        if not _sup_notif_column_exists(cursor, "notifications", "attachment_data"):
            cursor.close(); db.close()
            return jsonify({"error": "Attachment not found."}), 404
        cursor.execute(
            """
            SELECT attachment_name, attachment_mime, attachment_data
            FROM notifications
            WHERE notification_id = %s
              AND (recipient_id = %s OR sender_id = %s)
            LIMIT 1
            """,
            (notification_id, session.get("user_id"), session.get("user_id")),
        )
        row = cursor.fetchone(); cursor.close(); db.close()
        if not row or not row.get("attachment_data"):
            return jsonify({"error": "Attachment not found."}), 404
        filename = secure_filename(row.get("attachment_name") or "attachment") or "attachment"
        mimetype = row.get("attachment_mime") or "application/octet-stream"
        return Response(row["attachment_data"], mimetype=mimetype, headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/unread-count", methods=["GET"])
def api_supervisor_notifications_unread_count():
    if "user_id" not in session or session.get("role") != "supervisor":
        return jsonify({"unread": 0})
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT COUNT(*) AS cnt FROM notifications WHERE recipient_id = %s AND is_read = FALSE", (session.get("user_id"),))
        row = cursor.fetchone(); cursor.close(); db.close()
        return jsonify({"unread": int((row or {}).get("cnt") or 0)})
    except Exception:
        return jsonify({"unread": 0})



# ─── Run ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)
