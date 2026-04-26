from flask import Flask, request, redirect, url_for, session, render_template, jsonify, Response
import bcrypt
import secrets
import datetime
import os
import csv
import io
import re
from flask_mail import Mail, Message
from db import get_db
from auth import login_required
from routes.student import student_bp
from routes.head import head_bp
from ai_engine import ask_apms_ai

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# ─── Mail config ─────────────────────────────────────────────────────────
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = "rahafbadwan574@gmail.com"
app.config["MAIL_PASSWORD"] = "ykma scjl fdwg ohlt"
app.config["MAIL_DEFAULT_SENDER"] = ("APMS — Birzeit University", "rahafbadwan574@gmail.com")

mail = Mail(app)

# ─── Register Blueprints ─────────────────────────────────────────────────
app.register_blueprint(student_bp)
app.register_blueprint(head_bp)


# ─── Helpers ─────────────────────────────────────────────────────────────
def fetch_supervisors():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT f.faculty_id, u.full_name,
               COUNT(DISTINCT p.project_id) AS assigned_projects
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        LEFT JOIN projects p ON p.supervisor_id = f.faculty_id
        WHERE u.role = 'supervisor'
        GROUP BY f.faculty_id, u.full_name
        ORDER BY u.full_name
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return rows


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


# ─── Login / Logout ──────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def login_page():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/login", methods=["POST"])
def login():
    uid = request.form.get("university_id", "").strip()
    pwd = request.form.get("password", "").strip()

    if not uid or not pwd:
        return render_template("login.html", error="Please fill in all fields.")

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
        return render_template("login.html", error=f"Database error: {e}")

    if not user:
        return render_template("login.html", error="Invalid University ID or password.")

    if not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
        return render_template("login.html", error="Invalid University ID or password.")

    session["user_id"] = user["user_id"]
    session["university_id"] = user["university_id"]
    session["full_name"] = user["full_name"]
    session["role"] = user["role"]
    session["avatar_initials"] = user["avatar_initials"] or user["full_name"][:2].upper()
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
        return render_template("reset_password.html", error=f"Database error: {e}", token=token)

    if not record:
        return render_template(
            "reset_password.html",
            invalid=True,
            error="This reset link is invalid or has expired. Please request a new one.",
        )

    if request.method == "GET":
        return render_template("reset_password.html", token=token, name=record["full_name"])

    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()

    if not new_password or not confirm_password:
        return render_template(
            "reset_password.html", token=token, name=record["full_name"], error="Please fill in all fields."
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
            "reset_password.html", token=token, name=record["full_name"], error="Passwords do not match."
        )

    try:
        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed, record["user_id"]))
        cursor.execute("UPDATE password_reset_tokens SET used = TRUE WHERE token = %s", (token,))
        db.commit()
        cursor.close()
        db.close()
        return render_template("reset_password.html", success=True)
    except Exception as e:
        return render_template(
            "reset_password.html", token=token, name=record["full_name"], error=f"An error occurred: {e}"
        )


# ─── Dashboard ───────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    role = session.get("role")
    routes = {
        "student": "student.dashboard",
        "supervisor": "supervisor_dashboard",
        "coordinator": "coordinator_dashboard",
        "head_of_department": "head.dashboard",
    }
    target = routes.get(role)
    if not target:
        return redirect(url_for("logout"))
    return redirect(url_for(target))


# ─── AI Conversation Archive Helpers ─────────────────────────────────────
AI_ARCHIVE_DAYS = 30
_AI_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,120}$")


def _new_ai_session_id():
    """Create a compact, URL-safe conversation id."""
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
    """Delete whole AI chat sessions whose first message is older than 30 days."""
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


def _save_ai_exchange(user_id, session_id, question, answer):
    db = get_db()
    cursor = db.cursor()
    try:
        _purge_expired_ai_conversations(cursor)
        cursor.execute(
            """
            INSERT INTO ai_conversations (user_id, session_id, message_role, message_text)
            VALUES (%s, %s, 'user', %s)
            """,
            (user_id, session_id, question),
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
@app.route("/api/ai/ask", methods=["POST"])
@login_required()
def api_ai_ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    session_id = _normalize_ai_session_id(data.get("session_id"))

    if not question:
        return jsonify({"error": "Please write a question before sending.", "session_id": session_id}), 400

    answer = ask_apms_ai(question)
    saved, save_error = _save_ai_exchange(session["user_id"], session_id, question, answer)
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
        return jsonify({"conversations": conversations, "retention_days": AI_ARCHIVE_DAYS})
    except Exception as exc:
        return jsonify({"error": f"Could not load AI archive: {exc}"}), 500


@app.route("/api/ai/archive/<session_id>", methods=["GET"])
@login_required()
def api_ai_archive_detail(session_id):
    session_id = _normalize_ai_session_id(session_id)
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _purge_expired_ai_conversations(cursor)
        db.commit()
        cursor.execute(
            """
            SELECT message_role, message_text, created_at
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
    session_id = _normalize_ai_session_id(session_id)
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
@app.route("/api/student/distribution-submit", methods=["POST"])
@login_required(role="student")
def api_student_distribution_submit():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    group_name = (data.get("group_name") or "").strip()
    abstract = (data.get("abstract") or "").strip()
    keywords = (data.get("keywords") or "").strip()
    preferred = data.get("preferred_supervisors") or []
    member_ids = [str(x).strip() for x in (data.get("member_ids") or []) if str(x).strip()]
    user_uid = session.get("university_id")
    if user_uid and user_uid not in member_ids:
        member_ids.insert(0, user_uid)

    if not title:
        return jsonify({"error": "Project title is required."}), 400
    if len(member_ids) == 0:
        return jsonify({"error": "At least one team member is required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT semester_id FROM semesters WHERE is_active = TRUE ORDER BY semester_id DESC LIMIT 1")
        semester = cursor.fetchone()
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester is configured."}), 400

        pref_ids = [int(x) for x in preferred[:3] if str(x).strip().isdigit()]
        while len(pref_ids) < 3:
            pref_ids.append(None)

        cursor.execute(
            """
            INSERT INTO projects
            (title, group_name, abstract, keywords, project_type, semester_id, status, submission_date,
             preferred_supervisor_1, preferred_supervisor_2, preferred_supervisor_3)
            VALUES (%s, %s, %s, %s, 'software_engineering', %s, 'submitted', CURDATE(), %s, %s, %s)
            """,
            (
                title,
                group_name or None,
                abstract or None,
                keywords or None,
                semester["semester_id"],
                pref_ids[0],
                pref_ids[1],
                pref_ids[2],
            ),
        )
        project_id = cursor.lastrowid

        for i, uid in enumerate(member_ids):
            cursor.execute(
                """
                SELECT st.student_id
                FROM students st
                JOIN users u ON u.user_id = st.user_id
                WHERE u.university_id = %s AND u.role = 'student'
                """,
                (uid,),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, %s)",
                    (project_id, row["student_id"], i == 0),
                )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Project proposal submitted successfully.", "project_id": project_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/coordinator/distribution-data", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_distribution_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT p.project_id, p.title, p.group_name, p.status,
                   pref1.full_name AS preferred_1,
                   pref2.full_name AS preferred_2,
                   pref3.full_name AS preferred_3,
                   GROUP_CONCAT(u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', ') AS team_members
            FROM projects p
            LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
            LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
            LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
            LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
            LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
            LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            GROUP BY p.project_id, p.title, p.group_name, p.status, preferred_1, preferred_2, preferred_3
            ORDER BY p.project_id DESC
            """
        )
        forms = cursor.fetchall()

        cursor.execute(
            """
            SELECT st.student_id, u.university_id, u.full_name
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            LEFT JOIN project_members pm ON pm.student_id = st.student_id
            WHERE pm.member_id IS NULL
            ORDER BY u.full_name
            """
        )
        unassigned = cursor.fetchall()

        cursor.execute(
            """
            SELECT s.section_id,
                   s.section_name,
                   s.entered_by,
                   s.created_at,
                   u.full_name AS supervisor_name,
                   GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', ') AS assigned_students
            FROM student_distribution_sections s
            JOIN faculty f ON f.faculty_id = s.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = s.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users us ON us.user_id = st.user_id
            GROUP BY s.section_id, s.section_name, s.entered_by, s.created_at, u.full_name
            ORDER BY s.section_id DESC
            """
        )
        sections = cursor.fetchall()

        cursor.close()
        db.close()

        assigned_forms = sum(
            1
            for item in forms
            if item.get("status") in {"accepted", "under_review", "submitted", "committee_evaluation"}
        )
        stats = {
            "total_registered_students": len(unassigned) + sum(
                len((f.get("team_members") or "").split(", "))
                for f in forms
                if f.get("team_members")
            ),
            "assigned": assigned_forms,
            "waiting": len(unassigned),
            "active_groups": len(forms),
        }
        return jsonify(
            {
                "forms": forms,
                "unassigned_students": unassigned,
                "sections": sections,
                "stats": stats,
                "professors": fetch_supervisors(),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
        cursor.execute("SELECT semester_id FROM semesters WHERE is_active = TRUE ORDER BY semester_id DESC LIMIT 1")
        semester = cursor.fetchone()
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
            "INSERT INTO projects (title, group_name, project_type, semester_id, supervisor_id, status, submission_date) VALUES (%s, %s, 'software_engineering', %s, %s, 'under_review', CURDATE())",
            (f"Individual Project - {student['full_name']}", student["full_name"], semester["semester_id"], faculty_id),
        )
        project_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, TRUE)",
            (project_id, student_id),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Student assigned successfully.", "project_id": project_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/coordinator/add-section", methods=["POST"])
@login_required(role="coordinator")
def api_add_section():
    data = request.get_json(silent=True) or {}
    section_name = (data.get("section_name") or "").strip()
    supervisor_id = data.get("supervisor_id")
    student_ids = data.get("student_ids") or []

    if not section_name or not supervisor_id:
        return jsonify({"error": "section_name and supervisor_id are required."}), 400

    if len(student_ids) > 3:
        return jsonify({"error": "A section can contain at most 3 students."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if student_ids:
            placeholders = ",".join(["%s"] * len(student_ids))
            cursor.execute(
                f"""
                SELECT st.student_id
                FROM students st
                LEFT JOIN project_members pm ON pm.student_id = st.student_id
                LEFT JOIN section_students ss ON ss.student_id = st.student_id
                WHERE st.student_id IN ({placeholders})
                GROUP BY st.student_id
                HAVING COUNT(pm.member_id) = 0 AND COUNT(ss.id) = 0
                """,
                tuple(student_ids),
            )
            valid_students = {row["student_id"] for row in cursor.fetchall()}

            if len(valid_students) != len(student_ids):
                cursor.close()
                db.close()
                return jsonify({"error": "One or more selected students are already assigned to a project or section."}), 400

        cursor.execute(
            """
            INSERT INTO student_distribution_sections (section_name, supervisor_id, entered_by)
            VALUES (%s, %s, %s)
            """,
            (section_name, supervisor_id, session.get("user_id")),
        )
        section_id = cursor.lastrowid

        for sid in student_ids:
            cursor.execute(
                "INSERT INTO section_students (section_id, student_id) VALUES (%s, %s)",
                (section_id, sid),
            )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Section added successfully.", "section_id": section_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/coordinator/export-groups", methods=["GET"])
@login_required(role="coordinator")
def api_export_groups():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT p.group_name, p.title,
               GROUP_CONCAT(u.full_name ORDER BY u.full_name SEPARATOR ', ') AS team_members,
               COALESCE(pref1.full_name, '') AS preferred_1,
               COALESCE(pref2.full_name, '') AS preferred_2,
               COALESCE(pref3.full_name, '') AS preferred_3,
               p.status
        FROM projects p
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
        LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
        LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
        LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
        LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
        LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
        GROUP BY p.project_id, p.group_name, p.title, preferred_1, preferred_2, preferred_3, p.status
        ORDER BY p.project_id DESC
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return _csv_response(
        "student_groups.csv",
        ["Group", "Idea Title", "Team Members", "Preferred 1", "Preferred 2", "Preferred 3", "Status"],
        [
            [
                r["group_name"],
                r["title"],
                r["team_members"],
                r["preferred_1"],
                r["preferred_2"],
                r["preferred_3"],
                r["status"],
            ]
            for r in rows
        ],
    )


@app.route("/api/coordinator/export-sections", methods=["GET"])
@login_required(role="coordinator")
def api_export_sections():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT s.section_name, u.full_name AS supervisor_name, s.created_at,
               GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', ') AS assigned_students
        FROM student_distribution_sections s
        JOIN faculty f ON f.faculty_id = s.supervisor_id
        JOIN users u ON u.user_id = f.user_id
        LEFT JOIN section_students ss ON ss.section_id = s.section_id
        LEFT JOIN students st ON st.student_id = ss.student_id
        LEFT JOIN users us ON us.user_id = st.user_id
        GROUP BY s.section_id, s.section_name, u.full_name, s.created_at
        ORDER BY s.section_id DESC
        """
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()
    return _csv_response(
        "sections.csv",
        ["Section", "Supervisor", "Students", "Created At"],
        [[r["section_name"], r["supervisor_name"], r["assigned_students"] or "", r["created_at"]] for r in rows],
    )


# ─── Supervisor routes ────────────────────────────────────────────────────
@app.route("/supervisor/")
@app.route("/supervisor/dashboard")
@login_required(role="supervisor")
def supervisor_dashboard():
    return render_template("supervisor/index.html")


@app.route("/supervisor/<path:subpage>")
@login_required(role="supervisor")
def supervisor_subpage(subpage):
    return render_template("supervisor/index.html")


# ─── Coordinator routes ───────────────────────────────────────────────────
COORDINATOR_PAGES = {
    "dashboard": "coordinator/index.html",
    "registration": "coordinator/registration.html",
    "hours": "coordinator/hours.html",
    "review": "coordinator/review.html",
    "committee": "coordinator/committee.html",
    "evaluation": "coordinator/evaluation.html",
    "lectures": "coordinator/lectures.html",
    "exams": "coordinator/exams.html",
    "search": "coordinator/search.html",
    "notifs": "coordinator/notifs.html",
    "ai": "coordinator/ai.html",
    "profile": "coordinator/profile.html",
}


@app.route("/coordinator/")
@app.route("/coordinator/dashboard")
@login_required(role="coordinator")
def coordinator_dashboard():
    return render_template("coordinator/index.html")


@app.route("/coordinator/<page>")
@login_required(role="coordinator")
def coordinator_page(page):
    template = COORDINATOR_PAGES.get(page)
    if not template:
        return redirect(url_for("coordinator_dashboard"))
    return render_template(template)


# ─── Run ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)
