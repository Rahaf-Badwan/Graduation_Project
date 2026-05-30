import hashlib
import secrets
from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    session,
    Response,
)
import bcrypt
from werkzeug.utils import secure_filename
from db import get_db
from auth import login_required
from routes.add_student import add_student_bp
from routes.assign_rols import assign_rols_bp
from routes.promote import promote_bp
from routes.dashboard import dashboard_bp
from routes.profile import profile_bp
from routes.supervisors import supervisor_bp

head_bp = Blueprint("head", __name__, url_prefix="/head")
head_bp.register_blueprint(add_student_bp)
head_bp.register_blueprint(assign_rols_bp)
head_bp.register_blueprint(promote_bp)
head_bp.register_blueprint(dashboard_bp)
head_bp.register_blueprint(profile_bp)
head_bp.register_blueprint(supervisor_bp)
# ─── Dashboard ──────────────────────────────────────────────
@head_bp.route("/")
@head_bp.route("/dashboard")
@login_required(role="head_of_department")
def dashboard():
    return render_template("head/index.html")


# ─── Assign Roles ───────────────────────────────────────────
@head_bp.route("/assign")
@login_required(role="head_of_department")
def assign_role_page():
    return render_template("head/assign.html")

# ─── Supervisors ────────────────────────────────────────────
@head_bp.route("/supervisors")
@login_required(role="head_of_department")
def supervisors():
    return render_template("head/supervisors.html")


# ─── Section Results Approved by Coordinator ─────────────────────────────
def _ensure_section_results_schema(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS section_completion_status (
            status_id INT PRIMARY KEY AUTO_INCREMENT,
            course_scope ENUM('introduction','graduation_project') NOT NULL,
            reference_id INT NOT NULL,
            status ENUM('pending','succeeded','not_succeeded') NOT NULL DEFAULT 'pending',
            notes TEXT NULL,
            marked_by INT NULL,
            marked_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_section_completion (course_scope, reference_id),
            INDEX idx_section_completion_status (status),
            INDEX idx_section_completion_scope_status (course_scope, status),
            FOREIGN KEY (marked_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


@head_bp.route("/section-results")
@login_required(role="head_of_department")
def section_results():
    return render_template("head/section_results.html")


@head_bp.route("/api/section-results", methods=["GET"])
@login_required(role="head_of_department")
def api_head_section_results():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)

        cursor.execute("""
            SELECT sec.section_id AS reference_id,
                   sec.section_name,
                   'introduction' AS course_scope,
                   u_sup.full_name AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT st.student_id) AS student_count,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM section_completion_status scs
            JOIN student_distribution_sections sec
              ON scs.course_scope = 'introduction' AND scs.reference_id = sec.section_id
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            WHERE scs.status = 'succeeded'
            GROUP BY sec.section_id, sec.section_name, u_sup.full_name,
                     scs.notes, scs.marked_at, u_mark.full_name
            ORDER BY scs.marked_at DESC, sec.section_id DESC
            """)
        introduction_sections = cursor.fetchall()

        cursor.execute("""
            SELECT p.project_id AS reference_id,
                   COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS section_name,
                   'graduation_project' AS course_scope,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT st.student_id) AS student_count,
                   p.status AS project_status,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'graduation_project' AND scs.reference_id = p.project_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            WHERE scs.status = 'succeeded'
            GROUP BY p.project_id, p.title, p.status, u_sup.full_name,
                     scs.notes, scs.marked_at, u_mark.full_name
            ORDER BY scs.marked_at DESC, p.project_id DESC
            """)
        graduation_sections = cursor.fetchall()

        cursor.close()
        db.close()
        return jsonify(
            {
                "introduction_sections": introduction_sections,
                "graduation_sections": graduation_sections,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Search ─────────────────────────────────────────────────
@head_bp.route("/search")
@login_required(role="head_of_department")
def search():
    return render_template("shared/archive_search.html", base_template="head/base.html")


# ─── Notifications ──────────────────────────────────────────
@head_bp.route("/notifs")
@login_required(role="head_of_department")
def notifs():
    return render_template("head/notifs.html")


# ─── AI Assistant ───────────────────────────────────────────
@head_bp.route("/ai")
@login_required(role="head_of_department")
def ai():
    return render_template("shared/ai.html", base_template="head/base.html")


# ─── Profile ────────────────────────────────────────────────
@head_bp.route("/profile")
@login_required(role="head_of_department")
def profile():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT user_id, university_id, full_name, email, avatar_initials FROM users WHERE user_id = %s",
            (user_id,),
        )
        user = cursor.fetchone()
        cursor.close()
        db.close()
    except Exception:
        user = None
    return render_template(
        "head/profile.html", user=user, pwd_error=None, pwd_success=None
    )


# ─── Change Password ─────────────────────────────────────────
@head_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="head_of_department")
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
                "SELECT user_id, university_id, full_name, email, avatar_initials, password_hash FROM users WHERE user_id = %s",
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
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="Please fill in all fields.",
            pwd_success=None,
        )
    if len(new_pwd) < 8:
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="New password must be at least 8 characters.",
            pwd_success=None,
        )
    if new_pwd != confirm_pwd:
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="Passwords do not match.",
            pwd_success=None,
        )
    if not user or not bcrypt.checkpw(
        current_pwd.encode(), user["password_hash"].encode()
    ):
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error="Current password is incorrect.",
            pwd_success=None,
        )

    try:
        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed, user_id)
        )
        db.commit()
        cursor.close()
        db.close()
        return render_template(
            "head/profile.html",
            user=user,
            pwd_error=None,
            pwd_success="Password updated successfully!",
        )
    except Exception as e:
        return render_template(
            "head/profile.html", user=user, pwd_error=f"Error: {e}", pwd_success=None
        )


# ─── Add student ────────────────────────────────────────────────
@head_bp.route("/addStudent")
@login_required(role="head_of_department")
def add_student_page():
    return render_template("/head/addStudent.html")

# ─── Head Notifications / Messaging ─────────────────────────────────────
def _head_db_column_exists(cursor, table_name, column_name):
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


def _head_table_exists(cursor, table_name):
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


def _head_notification_enum_values(cursor):
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


def _head_safe_notification_type(cursor, requested_type="system"):
    allowed = _head_notification_enum_values(cursor)
    if not allowed:
        return requested_type or "system"
    if requested_type in allowed:
        return requested_type
    for fallback in ("system", "info", "message", "deadline_reminder", "urgent_alert", "alert"):
        if fallback in allowed:
            return fallback
    return allowed[0]


def _ensure_head_notification_schema(cursor):
    """Make the head notification page work even if older migrations were not run."""
    if _head_table_exists(cursor, "notifications"):
        if not _head_db_column_exists(cursor, "notifications", "course_scope"):
            cursor.execute(
                """
                ALTER TABLE notifications
                ADD COLUMN course_scope ENUM('introduction','graduation_project','both')
                NOT NULL DEFAULT 'both' AFTER message
                """
            )
        if not _head_db_column_exists(cursor, "notifications", "attachment_name"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255) NULL")
        if not _head_db_column_exists(cursor, "notifications", "attachment_mime"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120) NULL")
        if not _head_db_column_exists(cursor, "notifications", "attachment_data"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_data LONGBLOB NULL")
        if not _head_db_column_exists(cursor, "notifications", "can_reply"):
            cursor.execute(
                "ALTER TABLE notifications ADD COLUMN can_reply TINYINT(1) NOT NULL DEFAULT 1 AFTER is_read"
            )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS system_notices (
            notice_id INT PRIMARY KEY AUTO_INCREMENT,
            title VARCHAR(250) NOT NULL,
            body TEXT NOT NULL,
            highlight_text VARCHAR(150) NULL,
            button1_text VARCHAR(120) NULL,
            button2_text VARCHAR(120) NULL,
            button3_text VARCHAR(120) NULL,
            course_scope ENUM('introduction','graduation_project','both') NOT NULL DEFAULT 'both',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            updated_by INT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _head_notification_attachment_select_fields(cursor):
    if _head_db_column_exists(cursor, "notifications", "attachment_name"):
        return "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"
    return "NULL AS attachment_name, NULL AS attachment_mime, 0 AS has_attachment"


def _head_notification_can_reply_select_field(cursor):
    if _head_db_column_exists(cursor, "notifications", "can_reply"):
        return "COALESCE(n.can_reply, 1) AS can_reply"
    return "1 AS can_reply"


def _head_notification_row_to_json(row):
    if not row:
        return row
    clean = dict(row)
    if clean.get("created_at") is not None:
        clean["created_at"] = str(clean["created_at"])
    clean["is_read"] = bool(clean.get("is_read"))
    clean["can_reply"] = bool(clean.get("can_reply", True))
    clean["course_scope"] = clean.get("course_scope") or "both"
    clean["has_attachment"] = bool(clean.get("has_attachment"))
    if not clean["has_attachment"]:
        clean["attachment_name"] = None
        clean["attachment_mime"] = None
    clean.pop("attachment_data", None)
    return clean



def _head_active_semester_by_course(cursor, course_code):
    """Return the active semester for one course code."""
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


def _head_course_from_scope(course_scope):
    if course_scope == "introduction":
        return "COMP4200"
    if course_scope == "graduation_project":
        return "COMP4300"
    return None


def _head_coordinator_user_ids_for_scope(cursor, course_scope):
    """
    Return the coordinator(s) for the selected course.
    For COMP4300 this returns the single coordinator assigned to the COMP4300 active semester.
    For COMP4200 this returns the coordinator assigned to the COMP4200 active semester.
    For both, it returns all active coordinators.
    """
    course_code = _head_course_from_scope(course_scope)
    if course_code and _head_table_exists(cursor, "coordinator_assignments"):
        semester = _head_active_semester_by_course(cursor, course_code)
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

    cursor.execute("SELECT user_id FROM users WHERE role = 'coordinator' AND is_active = TRUE ORDER BY user_id LIMIT %s", (1 if course_scope in {"introduction", "graduation_project"} else 1000,))
    return [r["user_id"] for r in cursor.fetchall()]


def _head_comp4200_section_recipients(cursor, section_id=None):
    if not (_head_table_exists(cursor, "student_distribution_sections") and _head_table_exists(cursor, "section_students")):
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


def _head_comp4300_project_recipients(cursor, project_id=None):
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

def _head_reply_permission_check(cursor, original_notification_id, reply_to_user_id, current_user_id):
    """
    Return (allowed, error_message). A reply is allowed only when the original
    inbox message belongs to the current user and has can_reply = 1.
    """
    has_can_reply = _head_db_column_exists(cursor, "notifications", "can_reply")
    can_reply_expr = "COALESCE(can_reply, 1)" if has_can_reply else "1"

    if original_notification_id:
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
            (original_notification_id, current_user_id, reply_to_user_id),
        )
        if cursor.fetchone():
            return True, ""
        return False, "Replies are disabled for this message."

    # Backward-compatible fallback for older frontends that only send sender_id.
    # It still refuses replies when no replyable received message exists.
    cursor.execute(
        f"""
        SELECT notification_id
        FROM notifications
        WHERE recipient_id = %s
          AND sender_id = %s
          AND {can_reply_expr} = 1
        ORDER BY created_at DESC, notification_id DESC
        LIMIT 1
        """,
        (current_user_id, reply_to_user_id),
    )
    if cursor.fetchone():
        return True, ""
    return False, "Replies are disabled for this message."


def _head_notification_recipients(cursor, scope, value=None, course_scope="both"):
    scope = (scope or "").strip()
    course_scope = (course_scope or "both").strip()

    if scope == "coordinators":
        return _head_coordinator_user_ids_for_scope(cursor, course_scope)

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
            return _head_comp4300_project_recipients(cursor, project_id)
        section_id = str(value).replace("s:", "", 1)
        return _head_comp4200_section_recipients(cursor, section_id)

    if scope == "all_sections":
        recipients = []
        if course_scope in {"introduction", "both"}:
            recipients.extend(_head_comp4200_section_recipients(cursor))
        if course_scope in {"graduation_project", "both"}:
            recipients.extend(_head_comp4300_project_recipients(cursor))
        return sorted(set(recipients))

    if scope == "reply":
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND is_active = TRUE", (value,))
        return [r["user_id"] for r in cursor.fetchall()]

    return []


@head_bp.route("/api/notifications/options", methods=["GET"])
@login_required(role="head_of_department")
def api_head_notification_options():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # One coordinator per active course when assigned; keeps COMP4300 from showing extra coordinators.
        coordinator_rows = []
        for course_scope, course_code in (("introduction", "COMP4200"), ("graduation_project", "COMP4300")):
            semester = _head_active_semester_by_course(cursor, course_code)
            if semester and _head_table_exists(cursor, "coordinator_assignments"):
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
        if _head_table_exists(cursor, "student_distribution_sections") and _head_table_exists(cursor, "section_students"):
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
        return jsonify({
            "heads": [],
            "coordinators": coordinator_rows,
            "doctors": doctors,
            "students": students,
            "sections": sections,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/notifications/inbox", methods=["GET"])
@login_required(role="head_of_department")
def api_head_notifications_inbox():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_head_notification_schema(cursor)
        db.commit()
        attachment_fields = _head_notification_attachment_select_fields(cursor)
        can_reply_field = _head_notification_can_reply_select_field(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.notification_type, n.title, n.message,
                   n.course_scope, n.related_project_id, n.is_read, n.created_at,
                   n.sender_id AS sender_user_id,
                   sender.full_name AS sender_name, sender.role AS sender_role,
                   {can_reply_field},
                   {attachment_fields}
            FROM notifications n
            LEFT JOIN users sender ON sender.user_id = n.sender_id
            WHERE n.recipient_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_head_notification_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"notifications": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/notifications/sent", methods=["GET"])
@login_required(role="head_of_department")
def api_head_notifications_sent():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_head_notification_schema(cursor)
        db.commit()
        attachment_fields = _head_notification_attachment_select_fields(cursor)
        can_reply_field = _head_notification_can_reply_select_field(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.title, n.message, n.notification_type,
                   n.course_scope, n.is_read, n.created_at,
                   n.recipient_id AS recipient_user_id,
                   recipient.full_name AS recipient_name, recipient.role AS recipient_role,
                   {can_reply_field},
                   {attachment_fields}
            FROM notifications n
            JOIN users recipient ON recipient.user_id = n.recipient_id
            WHERE n.sender_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_head_notification_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"sent": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/notifications/send", methods=["POST"])
@login_required(role="head_of_department")
def api_head_notifications_send():
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
    can_reply = str(data.get("can_reply", "1")).lower() in ("1", "true", "on", "yes")
    reply_to_notification_id = data.get("reply_to_notification_id") or data.get("notification_id")
    course_scope = (data.get("course_scope") or "both").strip()

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

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_head_notification_schema(cursor)
        db.commit()

        sender_id = session.get("user_id")
        if scope == "reply":
            try:
                reply_to_user_id = int(value)
            except (TypeError, ValueError):
                cursor.close()
                db.close()
                return jsonify({"error": "Invalid reply receiver."}), 400

            allowed, error_message = _head_reply_permission_check(
                cursor,
                reply_to_notification_id,
                reply_to_user_id,
                sender_id,
            )
            if not allowed:
                cursor.close()
                db.close()
                return jsonify({"error": error_message}), 403

            # Replies remain replyable by default, so the conversation can continue.
            can_reply = True

        recipients = _head_notification_recipients(cursor, scope, value, course_scope)
        recipients = sorted({int(r) for r in recipients if int(r) != int(sender_id)})
        if not recipients:
            cursor.close()
            db.close()
            return jsonify({"error": "No recipients found for this choice."}), 404

        notification_type = _head_safe_notification_type(cursor, "urgent_alert" if urgent else "system")
        for recipient_id in recipients:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read, can_reply,
                     attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE, %s, %s, %s, %s)
                """,
                (
                    recipient_id,
                    sender_id,
                    notification_type,
                    title,
                    message,
                    course_scope,
                    1 if can_reply else 0,
                    attachment_name,
                    attachment_mime,
                    attachment_data,
                ),
            )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": f"Message sent successfully to {len(recipients)} recipient(s).", "sent_count": len(recipients)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
@login_required(role="head_of_department")
def api_head_notification_mark_read(notification_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE notifications SET is_read = TRUE WHERE notification_id = %s AND recipient_id = %s",
            (notification_id, session.get("user_id")),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Notification marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required(role="head_of_department")
def api_head_notifications_mark_all_read():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("UPDATE notifications SET is_read = TRUE WHERE recipient_id = %s", (session.get("user_id"),))
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "All messages marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/notifications/<int:notification_id>/attachment", methods=["GET"])
@login_required(role="head_of_department")
def api_head_notification_attachment(notification_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        if not _head_db_column_exists(cursor, "notifications", "attachment_data"):
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
            (notification_id, session.get("user_id"), session.get("user_id")),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if not row or not row.get("attachment_data"):
            return jsonify({"error": "Attachment not found."}), 404
        filename = secure_filename(row.get("attachment_name") or "attachment") or "attachment"
        mimetype = row.get("attachment_mime") or "application/octet-stream"
        return Response(row["attachment_data"], mimetype=mimetype, headers={"Content-Disposition": f"attachment; filename={filename}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/notifications/unread-count", methods=["GET"])
def api_head_notifications_unread_count():
    if "user_id" not in session or session.get("role") != "head_of_department":
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


@head_bp.route("/api/important-notice", methods=["GET"])
@login_required(role="head_of_department")
def api_head_important_notice_get():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_head_notification_schema(cursor)
        db.commit()
        cursor.execute(
            """
            SELECT notice_id, title, body, highlight_text, button1_text, button2_text, button3_text,
                   course_scope, is_active, updated_at
            FROM system_notices
            WHERE is_active = TRUE
            ORDER BY updated_at DESC, notice_id DESC
            LIMIT 1
            """
        )
        notice = cursor.fetchone()
        if notice and notice.get("updated_at") is not None:
            notice["updated_at"] = str(notice["updated_at"])
        cursor.close()
        db.close()
        return jsonify({"notice": notice})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@head_bp.route("/api/important-notice", methods=["POST"])
@login_required(role="head_of_department")
def api_head_important_notice_save():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    highlight_text = (data.get("highlight_text") or "").strip() or None
    button1_text = (data.get("button1_text") or "").strip() or None
    button2_text = (data.get("button2_text") or "").strip() or None
    button3_text = (data.get("button3_text") or "").strip() or None
    course_scope = (data.get("course_scope") or "both").strip()

    if course_scope not in {"introduction", "graduation_project", "both"}:
        return jsonify({"error": "Please choose the course scope."}), 400
    if not title:
        return jsonify({"error": "Please write the notice title."}), 400
    if not body:
        return jsonify({"error": "Please write the notice body."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_head_notification_schema(cursor)
        cursor.execute("UPDATE system_notices SET is_active = FALSE WHERE is_active = TRUE")
        cursor.execute(
            """
            INSERT INTO system_notices
                (title, body, highlight_text, button1_text, button2_text, button3_text,
                 course_scope, is_active, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            """,
            (title, body, highlight_text, button1_text, button2_text, button3_text, course_scope, session.get("user_id")),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Important notice updated successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

