from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    session,
    render_template,
    jsonify,
    Response,
)
import csv
import io
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta

from werkzeug.utils import secure_filename

from db import get_db
from auth import login_required
from ai_engine import search_uploaded_semantic

coordinator_bp = Blueprint("coordinator_bp", __name__)


# ─── Helpers ─────────────────────────────────────────────────────────────
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


def _json_safe_value(value):
    if isinstance(value, set):
        return ", ".join(sorted(str(v) for v in value))
    if isinstance(value, list):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe_value(v) for k, v in value.items()}
    return value


def _json_safe_rows(rows):
    return [_json_safe_value(row) for row in rows]


def _get_active_semester(cursor):
    # Keep this helper safe even before running the migration.
    has_distribution_open = _db_column_exists(cursor, "semesters", "distribution_open")
    has_opened_at = _db_column_exists(cursor, "semesters", "distribution_opened_at")
    has_closed_at = _db_column_exists(cursor, "semesters", "distribution_closed_at")
    has_close_at = _db_column_exists(cursor, "semesters", "distribution_close_at")
    has_course_code = _db_column_exists(cursor, "semesters", "course_code")

    fields = ["semester_id", "academic_year", "semester_number"]
    fields.append("course_code" if has_course_code else "'COMP4200' AS course_code")
    fields.append(
        "COALESCE(distribution_open, 0) AS distribution_open"
        if has_distribution_open
        else "0 AS distribution_open"
    )
    fields.append(
        "distribution_opened_at" if has_opened_at else "NULL AS distribution_opened_at"
    )
    fields.append(
        "distribution_closed_at" if has_closed_at else "NULL AS distribution_closed_at"
    )
    fields.append(
        "distribution_close_at" if has_close_at else "NULL AS distribution_close_at"
    )

    cursor.execute(f"""
        SELECT {', '.join(fields)}
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
        """)
    return cursor.fetchone()


def _get_active_comp4200_semester(cursor):
    return _get_active_semester_by_course(cursor, "COMP4200")


def _get_active_semester_by_course(cursor, course_code):
    # Keep this helper safe even before running the migration.
    has_distribution_open = _db_column_exists(cursor, "semesters", "distribution_open")
    has_opened_at = _db_column_exists(cursor, "semesters", "distribution_opened_at")
    has_closed_at = _db_column_exists(cursor, "semesters", "distribution_closed_at")
    has_close_at = _db_column_exists(cursor, "semesters", "distribution_close_at")
    has_course_code = _db_column_exists(cursor, "semesters", "course_code")

    fields = ["semester_id", "academic_year", "semester_number"]
    fields.append("course_code" if has_course_code else f"'{course_code}' AS course_code")
    fields.append(
        "COALESCE(distribution_open, 0) AS distribution_open"
        if has_distribution_open
        else "0 AS distribution_open"
    )
    fields.append(
        "distribution_opened_at" if has_opened_at else "NULL AS distribution_opened_at"
    )
    fields.append(
        "distribution_closed_at" if has_closed_at else "NULL AS distribution_closed_at"
    )
    fields.append(
        "distribution_close_at" if has_close_at else "NULL AS distribution_close_at"
    )

    where = "is_active = TRUE"
    params = []
    if has_course_code:
        where += " AND course_code = %s"
        params.append(course_code)

    cursor.execute(f"""
        SELECT {', '.join(fields)}
        FROM semesters
        WHERE {where}
        ORDER BY semester_id DESC
        LIMIT 1
        """, tuple(params))
    return cursor.fetchone()


def _get_anchor_semester_for_year(cursor, academic_year):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number
        FROM semesters
        WHERE academic_year = %s
        ORDER BY semester_number ASC, semester_id ASC
        LIMIT 1
        """,
        (academic_year,),
    )
    return cursor.fetchone()


def _db_column_exists(cursor, table_name, column_name):
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
    row = cursor.fetchone() or {}
    return int(row.get("cnt") or 0) > 0


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    row = cursor.fetchone() or {}
    return int(row.get("cnt") or 0) > 0


def _notification_enum_values(cursor):
    """Return allowed values from notifications.notification_type ENUM. Empty list means non-ENUM or missing."""
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
    column_type = row.get("column_type") or row.get("COLUMN_TYPE") or ""

    if not str(column_type).lower().startswith("enum("):
        return []

    raw = str(column_type)[5:-1]
    values = []
    current = ""
    in_quote = False
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


def _safe_notification_type(cursor, requested_type="system"):
    """Avoid MySQL 1265 Data truncated when notification_type ENUM does not contain the requested value."""
    allowed = _notification_enum_values(cursor)

    if not allowed:
        return requested_type or "system"

    if requested_type in allowed:
        return requested_type

    for fallback in ("system", "info", "message", "deadline_reminder", "urgent_alert", "alert"):
        if fallback in allowed:
            return fallback

    return allowed[0]


def _insert_notification(
    cursor,
    recipient_id,
    sender_id,
    notification_type,
    title,
    message,
    related_project_id=None,
    course_scope="both",
):
    notification_type = _safe_notification_type(cursor, notification_type)

    if _db_column_exists(cursor, "notifications", "course_scope"):
        cursor.execute(
            """
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type, title, message,
                 course_scope, related_project_id, is_read)
            VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE)
            """,
            (
                recipient_id,
                sender_id,
                notification_type,
                title,
                message,
                course_scope,
                related_project_id,
            ),
        )
    else:
        cursor.execute(
            """
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type, title, message,
                 related_project_id, is_read)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
            """,
            (
                recipient_id,
                sender_id,
                notification_type,
                title,
                message,
                related_project_id,
            ),
        )


def _project_student_user_ids(cursor, project_id):
    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM project_members pm
        JOIN students st ON st.student_id = pm.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE pm.project_id = %s
          AND u.role = 'student'
          AND u.is_active = TRUE
        """,
        (project_id,),
    )
    return [row["user_id"] for row in cursor.fetchall()]


def _deliverable_student_user_ids(cursor, semester_id, course_scope):
    if course_scope == "graduation_project":
        cursor.execute(
            """
            SELECT DISTINCT u.user_id
            FROM projects p
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE p.semester_id = %s
              AND u.role = 'student'
              AND u.is_active = TRUE
            """,
            (semester_id,),
        )
        return [row["user_id"] for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM student_course_results scr
        JOIN students st ON st.student_id = scr.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE scr.semester_id = %s
          AND u.role = 'student'
          AND u.is_active = TRUE
        """,
        (semester_id,),
    )
    recipients = [row["user_id"] for row in cursor.fetchall()]
    if recipients:
        return recipients

    cursor.execute("""
        SELECT user_id
        FROM users
        WHERE role = 'student' AND is_active = TRUE
        """)
    return [row["user_id"] for row in cursor.fetchall()]



def _comp4200_student_user_ids_for_semester(cursor, semester_id=None):
    """
    Return active student user IDs that belong to COMP4200 / Project Introduction.

    The function is defensive because different APMS database versions store the
    COMP4200 enrollment in different places. It tries the most specific sources
    first, then falls back safely.
    """
    recipients = []

    # Best source: student_course_results table, when it exists.
    if _table_exists(cursor, "student_course_results"):
        conditions = ["u.role = 'student'", "u.is_active = TRUE"]
        params = []

        if semester_id and _db_column_exists(cursor, "student_course_results", "semester_id"):
            conditions.append("scr.semester_id = %s")
            params.append(semester_id)

        if _db_column_exists(cursor, "student_course_results", "course_code"):
            conditions.append("scr.course_code = 'COMP4200'")
        elif _db_column_exists(cursor, "student_course_results", "course_scope"):
            conditions.append("scr.course_scope = 'introduction'")

        cursor.execute(
            f"""
            SELECT DISTINCT u.user_id
            FROM student_course_results scr
            JOIN students st ON st.student_id = scr.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE {' AND '.join(conditions)}
            """,
            tuple(params),
        )
        recipients = [row["user_id"] for row in cursor.fetchall()]

    if recipients:
        return recipients

    # Some versions store course data directly on students.
    if _table_exists(cursor, "students"):
        student_conditions = ["u.role = 'student'", "u.is_active = TRUE"]
        params = []

        if _db_column_exists(cursor, "students", "course_code"):
            student_conditions.append("st.course_code = 'COMP4200'")
        elif _db_column_exists(cursor, "students", "course_scope"):
            student_conditions.append("st.course_scope = 'introduction'")
        else:
            student_conditions = []

        if student_conditions:
            cursor.execute(
                f"""
                SELECT DISTINCT u.user_id
                FROM students st
                JOIN users u ON u.user_id = st.user_id
                WHERE {' AND '.join(student_conditions)}
                """,
                tuple(params),
            )
            recipients = [row["user_id"] for row in cursor.fetchall()]

    if recipients:
        return recipients

    # If COMP4200 sections already exist, notify their students only.
    if _table_exists(cursor, "student_distribution_sections") and _table_exists(cursor, "section_students"):
        cursor.execute(
            """
            SELECT DISTINCT u.user_id
            FROM section_students ss
            JOIN students st ON st.student_id = ss.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE u.role = 'student'
              AND u.is_active = TRUE
            """
        )
        recipients = [row["user_id"] for row in cursor.fetchall()]

    if recipients:
        return recipients

    # Last fallback for older schemas that cannot distinguish courses.
    # This keeps the page working, but the UI and API still label the window as COMP4200 only.
    cursor.execute(
        """
        SELECT user_id
        FROM users
        WHERE role = 'student' AND is_active = TRUE
        """
    )
    return [row["user_id"] for row in cursor.fetchall()]


def _active_distribution_is_open(semester):
    if not semester:
        return False
    if not bool(semester.get("distribution_open") or 0):
        return False
    close_at = semester.get("distribution_close_at")
    if close_at and datetime.now() >= close_at:
        return False
    return True


def _faculty_load_snapshot(cursor, faculty_id, academic_year, anchor_semester_id=None):
    if anchor_semester_id is None:
        anchor = _get_anchor_semester_for_year(cursor, academic_year)
        anchor_semester_id = anchor["semester_id"] if anchor else None

    has_grad_hours = _db_column_exists(
        cursor, "faculty_load_settings", "graduation_project_hours"
    )
    wanted_hours = 0.0

    if anchor_semester_id and _table_exists(cursor, "faculty_load_settings"):
        select_field = (
            "COALESCE(graduation_project_hours, 0) AS graduation_project_hours"
            if has_grad_hours
            else "0 AS graduation_project_hours"
        )
        cursor.execute(
            f"""
            SELECT {select_field}
            FROM faculty_load_settings
            WHERE faculty_id = %s AND semester_id = %s
            LIMIT 1
            """,
            (faculty_id, anchor_semester_id),
        )
        row = cursor.fetchone()
        if row:
            wanted_hours = float(row.get("graduation_project_hours") or 0)

    cursor.execute(
        """
        SELECT
            COUNT(DISTINCT p.project_id) AS project_groups,
            COUNT(DISTINCT pm.student_id) AS project_students
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        WHERE p.supervisor_id = %s
          AND s.academic_year = %s
        """,
        (faculty_id, academic_year),
    )
    project_row = cursor.fetchone() or {}

    project_groups = int(project_row.get("project_groups") or 0)
    project_students = int(project_row.get("project_students") or 0)

    intro_sections = 0
    intro_students = 0

    if (
        _table_exists(cursor, "student_distribution_sections")
        and _table_exists(cursor, "section_students")
    ):
        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT sec.section_id) AS intro_sections,
                COUNT(DISTINCT ss.student_id) AS intro_students
            FROM student_distribution_sections sec
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            WHERE sec.supervisor_id = %s
            """,
            (faculty_id,),
        )
        intro_row = cursor.fetchone() or {}
        intro_sections = int(intro_row.get("intro_sections") or 0)
        intro_students = int(intro_row.get("intro_students") or 0)

    graduation_used_hours = project_students * 0.5
    introduction_used_hours = intro_students * 0.5

    used_hours = graduation_used_hours + introduction_used_hours
    remaining_hours = wanted_hours - used_hours

    if wanted_hours <= 0:
        status = "Not Set"
    elif remaining_hours < 0:
        status = "Over Wanted Hours"
    elif remaining_hours < 0.5:
        status = "Full"
    else:
        status = "Available"

    return {
        "graduation_project_hours": wanted_hours,
        "wanted_hours": wanted_hours,
        "project_groups": project_groups,
        "project_students": project_students,
        "intro_sections": intro_sections,
        "intro_students": intro_students,
        "supervised_groups": project_groups + intro_sections,
        "supervised_students": project_students + intro_students,
        "graduation_used_hours": graduation_used_hours,
        "introduction_used_hours": introduction_used_hours,
        "used_hours": used_hours,
        "student_load_hours": used_hours,
        "remaining_hours": remaining_hours,
        "status": status,
        "can_take_one_student": remaining_hours >= 0.5,
        # legacy keys kept so older JS does not break
        "base_hours": 0.0,
        "max_hours": wanted_hours,
        "employment_type": "graduation_projects_only",
        "extra_bonus": 0.0,
        "assigned_courses": "",
        "total_year_hours": used_hours,
    }


def fetch_supervisors():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    active_semester = _get_active_semester(cursor)
    academic_year = active_semester["academic_year"] if active_semester else None
    anchor = (
        _get_anchor_semester_for_year(cursor, academic_year) if academic_year else None
    )
    anchor_semester_id = anchor["semester_id"] if anchor else None

    cursor.execute("""
        SELECT f.faculty_id, u.full_name
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
        ORDER BY u.full_name
        """)
    rows = cursor.fetchall()

    result = []
    for row in rows:
        snapshot = (
            _faculty_load_snapshot(
                cursor, row["faculty_id"], academic_year, anchor_semester_id
            )
            if academic_year
            else {
                "supervised_groups": 0,
                "wanted_hours": 0.0,
                "used_hours": 0.0,
                "remaining_hours": 0.0,
                "status": "Not Set",
                "can_take_one_student": False,
            }
        )
        result.append(
            {
                "faculty_id": row["faculty_id"],
                "full_name": row["full_name"],
                "assigned_projects": snapshot["supervised_groups"],
                "wanted_hours": snapshot["wanted_hours"],
                "used_hours": snapshot["used_hours"],
                "current_hours": snapshot["used_hours"],
                "max_hours": snapshot["wanted_hours"],
                "remaining_hours": snapshot["remaining_hours"],
                "status": snapshot["status"],
                "can_take_one_student": snapshot["can_take_one_student"],
            }
        )

    cursor.close()
    db.close()
    return result


# ─── Coordinator Pages ───────────────────────────────────────────────────
COORDINATOR_PAGES = {
    "dashboard": "coordinator/index.html",
    "registration": "coordinator/registration.html",
    "hours": "coordinator/hours.html",
    "review": "coordinator/review.html",
    "committee": "coordinator/committee.html",
    "evaluation": "coordinator/evaluation.html",
    "lectures": "coordinator/lectures.html",
    "sections": "coordinator/sections.html",
    "exams": "coordinator/exams.html",
    "search": "shared/archive_search.html",
    "notifs": "coordinator/notifs.html",
    "ai": "shared/ai.html",
    "profile": "coordinator/profile.html",
}


@coordinator_bp.route("/coordinator/")
@coordinator_bp.route("/coordinator/dashboard")
@login_required(role="coordinator")
def coordinator_dashboard():
    return render_template("coordinator/index.html")


@coordinator_bp.route("/api/coordinator/dashboard-data", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_dashboard_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)
        semester_id = semester["semester_id"] if semester else None

        where = "WHERE p.semester_id = %s" if semester_id else ""
        params = (semester_id,) if semester_id else ()

        cursor.execute(
            f"""
            SELECT
                COUNT(*) AS total_projects,
                SUM(CASE WHEN p.status IN ('submitted','under_review','needs_revision') THEN 1 ELSE 0 END) AS awaiting_review,
                SUM(CASE WHEN p.status = 'committee_evaluation' THEN 1 ELSE 0 END) AS under_evaluation,
                SUM(CASE WHEN p.status IN ('accepted','archived') THEN 1 ELSE 0 END) AS accepted,
                SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) AS rejected
            FROM projects p
            {where}
            """,
            params,
        )
        stats = cursor.fetchone() or {}

        cursor.execute(
            f"""
            SELECT p.status, COUNT(*) AS count
            FROM projects p
            {where}
            GROUP BY p.status
            ORDER BY count DESC
            """,
            params,
        )
        by_status = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT p.project_type, COUNT(*) AS count
            FROM projects p
            {where}
            GROUP BY p.project_type
            ORDER BY count DESC
            LIMIT 8
            """,
            params,
        )
        by_type = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT p.project_id, p.title, p.status, p.submission_date,
                   sup.full_name AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT stu.full_name ORDER BY pm.is_primary_contact DESC, stu.full_name SEPARATOR ', '), '') AS team_members
            FROM projects p
            LEFT JOIN faculty sf ON sf.faculty_id = p.supervisor_id
            LEFT JOIN users sup ON sup.user_id = sf.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users stu ON stu.user_id = st.user_id
            {where}
            GROUP BY p.project_id, p.title, p.status, p.submission_date, sup.full_name
            ORDER BY p.updated_at DESC, p.project_id DESC
            LIMIT 5
            """,
            params,
        )
        latest_projects = cursor.fetchall()

        cursor.execute(
            """
            SELECT COUNT(*) AS committees
            FROM committee_plans
            WHERE status IN ('scheduled','draft')
            """
            if _table_exists(cursor, "committee_plans")
            else "SELECT 0 AS committees"
        )
        committees = cursor.fetchone() or {}

        # ── Active students count ──────────────────────────────────────────
        cursor.execute("""
            SELECT COUNT(*) AS active_students
            FROM users
            WHERE role = 'student' AND is_active = TRUE
        """)
        students_row = cursor.fetchone() or {}

        # ── Sections count (student_distribution_sections if table exists) ─
        sections_count = 0
        if _table_exists(cursor, "student_distribution_sections"):
            cursor.execute("""
                SELECT COUNT(*) AS total_sections
                FROM student_distribution_sections
            """)
            sections_row = cursor.fetchone() or {}
            sections_count = int(sections_row.get("total_sections") or 0)

        # ── Archived projects count per type (for Projects by Type panel) ──
        # project_type is a SET column so we use FIND_IN_SET per type
        cursor.execute("""
            SELECT
                SUM(CASE WHEN FIND_IN_SET('web',                  project_type) > 0 THEN 1 ELSE 0 END) AS web,
                SUM(CASE WHEN FIND_IN_SET('mobile',               project_type) > 0 THEN 1 ELSE 0 END) AS mobile,
                SUM(CASE WHEN FIND_IN_SET('ai',                   project_type) > 0 THEN 1 ELSE 0 END) AS ai,
                SUM(CASE WHEN FIND_IN_SET('software_engineering',  project_type) > 0 THEN 1 ELSE 0 END) AS software_engineering,
                SUM(CASE WHEN FIND_IN_SET('security',             project_type) > 0 THEN 1 ELSE 0 END) AS security,
                SUM(CASE WHEN FIND_IN_SET('databases',            project_type) > 0 THEN 1 ELSE 0 END) AS `databases`,
                SUM(CASE WHEN FIND_IN_SET('other',                project_type) > 0 THEN 1 ELSE 0 END) AS other,
                COUNT(*) AS total_archived
            FROM projects
            WHERE status = 'archived'
        """)
        archive_type_row = cursor.fetchone() or {}
        archive_by_type = {
            "web":                  int(archive_type_row.get("web")                  or 0),
            "mobile":               int(archive_type_row.get("mobile")               or 0),
            "ai":                   int(archive_type_row.get("ai")                   or 0),
            "software_engineering": int(archive_type_row.get("software_engineering") or 0),
            "security":             int(archive_type_row.get("security")             or 0),
            "databases":            int(archive_type_row.get("databases")            or 0),
            "other":                int(archive_type_row.get("other")                or 0),
            "_total":               int(archive_type_row.get("total_archived")       or 0),
        }

        cursor.close()
        db.close()

        return jsonify(
            _json_safe_value(
                {
                    "semester": semester or {},
                    "distribution_open": _active_distribution_is_open(semester),
                    "stats": {
                        "total_projects": int(stats.get("total_projects") or 0),
                        "awaiting_review": int(stats.get("awaiting_review") or 0),
                        "under_evaluation": int(stats.get("under_evaluation") or 0),
                        "accepted": int(stats.get("accepted") or 0),
                        "rejected": int(stats.get("rejected") or 0),
                        "committees": int(committees.get("committees") or 0),
                        "active_students": int(students_row.get("active_students") or 0),
                        "total_sections": sections_count,
                    },
                    "by_status": by_status,
                    "by_type": by_type,
                    "archive_by_type": archive_by_type,
                    "latest_projects": latest_projects,
                }
            )
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/coordinator/<page>")
@login_required(role="coordinator")
def coordinator_page(page):
    template = COORDINATOR_PAGES.get(page)
    if not template:
        return redirect(url_for("coordinator_bp.coordinator_dashboard"))
    return render_template(template)


# ─── Coordinator Lectures & Deliverables ─────────────────────────────────
def _ensure_lecture_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coordinator_lectures (
            lecture_id INT PRIMARY KEY AUTO_INCREMENT,
            semester_id INT NULL,
            course_scope ENUM('introduction','graduation_project') NOT NULL DEFAULT 'introduction',
            title VARCHAR(200) NOT NULL,
            description TEXT,
            lecture_date DATE NULL,
            week_label VARCHAR(80),
            status ENUM('scheduled','completed','cancelled') NOT NULL DEFAULT 'scheduled',
            created_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_coord_lectures_semester_scope (semester_id, course_scope),
            CONSTRAINT fk_coord_lectures_semester
                FOREIGN KEY (semester_id) REFERENCES semesters(semester_id)
                ON DELETE SET NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coordinator_deliverables (
            deliverable_id INT PRIMARY KEY AUTO_INCREMENT,
            semester_id INT NULL,
            course_scope ENUM('introduction','graduation_project') NOT NULL DEFAULT 'introduction',
            title VARCHAR(200) NOT NULL,
            description TEXT,
            start_at DATETIME NULL,
            due_date DATE NULL,
            due_at DATETIME NULL,
            mark_points DECIMAL(5,2) NOT NULL DEFAULT 0,
            status ENUM('not_open','open','in_progress','completed','closed') NOT NULL DEFAULT 'not_open',
            is_published TINYINT(1) NOT NULL DEFAULT 0,
            published_at DATETIME NULL,
            created_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_coord_deliverables_semester_scope (semester_id, course_scope),
            INDEX idx_coord_deliverables_window (course_scope, start_at, due_at),
            CONSTRAINT fk_coord_deliverables_semester
                FOREIGN KEY (semester_id) REFERENCES semesters(semester_id)
                ON DELETE SET NULL
        )
    """)

    # Older databases already have coordinator_deliverables without the new window columns.
    for column_name, column_sql in [
        ("start_at", "ALTER TABLE coordinator_deliverables ADD COLUMN start_at DATETIME NULL AFTER description"),
        ("due_at", "ALTER TABLE coordinator_deliverables ADD COLUMN due_at DATETIME NULL AFTER due_date"),
        ("is_published", "ALTER TABLE coordinator_deliverables ADD COLUMN is_published TINYINT(1) NOT NULL DEFAULT 0 AFTER status"),
        ("published_at", "ALTER TABLE coordinator_deliverables ADD COLUMN published_at DATETIME NULL AFTER is_published"),
    ]:
        if not _db_column_exists(cursor, "coordinator_deliverables", column_name):
            cursor.execute(column_sql)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coordinator_deliverable_submissions (
            submission_id INT PRIMARY KEY AUTO_INCREMENT,
            deliverable_id INT NOT NULL,
            student_id INT NOT NULL,
            project_id INT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_path VARCHAR(600) NULL,
            file_data LONGBLOB NULL,
            file_mime VARCHAR(120) NULL,
            file_size_mb DECIMAL(7,2) NULL,
            submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_deliverable_student (deliverable_id, student_id),
            INDEX idx_cds_project (project_id),
            FOREIGN KEY (deliverable_id) REFERENCES coordinator_deliverables(deliverable_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)




def _semester_for_course_scope(cursor, course_scope):
    """Return the active semester for the selected page/course only."""
    course_code = "COMP4300" if course_scope == "graduation_project" else "COMP4200"
    semester = _get_active_semester_by_course(cursor, course_code)
    if semester:
        return semester

    # Safe fallback for old DBs where course_code might not exist or active flags are incomplete.
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE course_code = %s
        ORDER BY semester_id DESC
        LIMIT 1
        """,
        (course_code,),
    )
    return cursor.fetchone()


def _parse_datetime_local(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        if "T" in value:
            return datetime.strptime(value[:16], "%Y-%m-%dT%H:%M")
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _format_datetime_local(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M")
    return str(value).replace(" ", "T")[:16]

def _date_to_iso(row):
    if not row:
        return row
    for key, value in list(row.items()):
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
        elif isinstance(value, float):
            row[key] = round(value, 2)
    return row


@coordinator_bp.route("/api/coordinator/lectures-data", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_lectures_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        db.commit()

        semester_intro = _semester_for_course_scope(cursor, "introduction")
        semester_grad = _semester_for_course_scope(cursor, "graduation_project")
        semester_ids = [s["semester_id"] for s in (semester_intro, semester_grad) if s]

        result = {
            "semester": {
                "introduction": _date_to_iso(semester_intro or {}),
                "graduation_project": _date_to_iso(semester_grad or {}),
            },
            "lectures": {"introduction": [], "graduation_project": []},
            "deliverables": {"introduction": [], "graduation_project": []},
        }

        if semester_ids:
            placeholders = ",".join(["%s"] * len(semester_ids))
            cursor.execute(
                f"""
                SELECT lecture_id, semester_id, course_scope, title, description,
                       lecture_date, week_label, status, created_at, updated_at
                FROM coordinator_lectures
                WHERE semester_id IN ({placeholders})
                ORDER BY course_scope, COALESCE(lecture_date, '9999-12-31'), lecture_id
                """,
                tuple(semester_ids),
            )
        else:
            cursor.execute("""
                SELECT lecture_id, semester_id, course_scope, title, description,
                       lecture_date, week_label, status, created_at, updated_at
                FROM coordinator_lectures
                ORDER BY course_scope, COALESCE(lecture_date, '9999-12-31'), lecture_id
            """)
        for row in cursor.fetchall():
            row = _date_to_iso(row)
            result["lectures"].setdefault(row.get("course_scope") or "introduction", []).append(row)

        if semester_ids:
            placeholders = ",".join(["%s"] * len(semester_ids))
            cursor.execute(
                f"""
                SELECT deliverable_id, semester_id, course_scope, title, description,
                       start_at, due_date, due_at, mark_points, status, is_published,
                       published_at, created_at, updated_at
                FROM coordinator_deliverables
                WHERE semester_id IN ({placeholders})
                ORDER BY course_scope, COALESCE(due_at, due_date, '9999-12-31'), deliverable_id
                """,
                tuple(semester_ids),
            )
        else:
            cursor.execute("""
                SELECT deliverable_id, semester_id, course_scope, title, description,
                       start_at, due_date, due_at, mark_points, status, is_published,
                       published_at, created_at, updated_at
                FROM coordinator_deliverables
                ORDER BY course_scope, COALESCE(due_at, due_date, '9999-12-31'), deliverable_id
            """)
        for row in cursor.fetchall():
            row = _date_to_iso(row)
            row["mark_points"] = float(row.get("mark_points") or 0)
            row["is_published"] = bool(row.get("is_published"))
            result["deliverables"].setdefault(row.get("course_scope") or "introduction", []).append(row)

        cursor.close()
        db.close()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/lectures", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_create_lecture():
    try:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Lecture title is required."}), 400
        course_scope = (
            data.get("course_scope")
            if data.get("course_scope") in ("introduction", "graduation_project")
            else "introduction"
        )
        status = (
            data.get("status")
            if data.get("status") in ("scheduled", "completed", "cancelled")
            else "scheduled"
        )
        lecture_date = data.get("lecture_date") or None

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        semester = _semester_for_course_scope(cursor, course_scope)
        semester_id = semester["semester_id"] if semester else None

        cursor.execute(
            """
            INSERT INTO coordinator_lectures
                (semester_id, course_scope, title, description, lecture_date, week_label, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                semester_id,
                course_scope,
                title,
                data.get("description") or None,
                lecture_date,
                data.get("week_label") or None,
                status,
                session.get("user_id"),
            ),
        )
        lecture_id = cursor.lastrowid

        # Send the lecture link/notice to the correct students immediately.
        sent_count = 0
        if semester_id:
            recipients = sorted(set(_deliverable_student_user_ids(cursor, semester_id, course_scope)))
            scope_label = "Project Introduction" if course_scope == "introduction" else "Graduation Project"
            date_text = f" Date: {lecture_date}." if lecture_date else ""
            details = (data.get("description") or "").strip()
            link_text = "Open from your student timeline: /student/timeline"
            message = f"A new lecture has been posted for {scope_label}: {title}.{date_text} {link_text}"
            if details:
                message += f" Details: {details}"

            for recipient_id in recipients:
                _insert_notification(
                    cursor,
                    recipient_id,
                    session.get("user_id"),
                    "system",
                    f"New Lecture: {title}",
                    message,
                    None,
                    course_scope,
                )
            sent_count = len(recipients)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": f"Lecture saved successfully. {sent_count} student notification(s) sent.",
                "lecture_id": lecture_id,
                "notifications_sent": sent_count,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route(
    "/api/coordinator/lectures/<int:lecture_id>/date", methods=["POST"]
)
@login_required(role="coordinator")
def api_coordinator_update_lecture_date(lecture_id):
    try:
        data = request.get_json(silent=True) or {}
        lecture_date = data.get("lecture_date") or None
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        cursor.execute(
            """
            UPDATE coordinator_lectures
            SET lecture_date = %s,
                status = CASE WHEN %s IS NULL THEN status ELSE 'scheduled' END
            WHERE lecture_id = %s
        """,
            (lecture_date, lecture_date, lecture_id),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Lecture date updated."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/deliverables", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_create_deliverable():
    try:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Deliverable title is required."}), 400
        course_scope = (
            data.get("course_scope")
            if data.get("course_scope") in ("introduction", "graduation_project")
            else "introduction"
        )
        status = (
            data.get("status")
            if data.get("status")
            in ("not_open", "open", "in_progress", "completed", "closed")
            else "not_open"
        )
        due_date = data.get("due_date") or None
        mark_points = data.get("mark_points") or 0

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        semester = _semester_for_course_scope(cursor, course_scope)
        semester_id = semester["semester_id"] if semester else None

        start_at = _parse_datetime_local(data.get("start_at"))
        due_at = _parse_datetime_local(data.get("due_at") or data.get("due_date"))
        due_date_sql = due_at.date() if due_at else due_date
        is_published = 1 if status in ("open", "in_progress", "completed") else 0

        cursor.execute(
            """
            INSERT INTO coordinator_deliverables
                (semester_id, course_scope, title, description, start_at, due_date, due_at,
                 mark_points, status, is_published, published_at, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s = 1 THEN NOW() ELSE NULL END, %s)
        """,
            (
                semester_id,
                course_scope,
                title,
                data.get("description") or None,
                start_at,
                due_date_sql,
                due_at,
                mark_points,
                status,
                is_published,
                is_published,
                session.get("user_id"),
            ),
        )
        deliverable_id = cursor.lastrowid

        if semester_id and due_date:
            cursor.execute(
                """
                INSERT INTO deadlines
                    (semester_id, project_id, deadline_type, deadline_date, description)
                VALUES (%s, NULL, %s, %s, %s)
                """,
                (
                    semester_id,
                    f"coordinator_deliverable_{deliverable_id}",
                    due_date,
                    f"Assignment: {title}",
                ),
            )

        sent_count = 0
        if semester_id:
            recipients = sorted(
                set(_deliverable_student_user_ids(cursor, semester_id, course_scope))
            )
            scope_label = (
                "Project Introduction"
                if course_scope == "introduction"
                else "Graduation Project"
            )
            due_text = f" Due date: {due_date}." if due_date else ""
            points_text = (
                f" Mark points: {float(mark_points):g}."
                if str(mark_points).strip() not in ("", "0", "0.0")
                else ""
            )
            details = (data.get("description") or "").strip()
            message = (
                f"A new assignment has been posted for {scope_label}: {title}."
                f"{due_text}{points_text}"
            )
            if details:
                message += f" Details: {details}"

            for recipient_id in recipients:
                _insert_notification(
                    cursor,
                    recipient_id,
                    session.get("user_id"),
                    "deadline_reminder" if due_date else "system",
                    f"New Assignment: {title}",
                    message,
                    None,
                    course_scope,
                )
            sent_count = len(recipients)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": f"Deliverable saved successfully. {sent_count} student notification(s) sent.",
                "deliverable_id": deliverable_id,
                "notifications_sent": sent_count,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@coordinator_bp.route("/api/coordinator/grad-final-submission", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_grad_final_submission_get():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        semester = _semester_for_course_scope(cursor, "graduation_project")
        semester_id = semester["semester_id"] if semester else None
        row = None
        if semester_id:
            cursor.execute(
                """
                SELECT deliverable_id, title, description, start_at, due_at,
                       status, is_published, published_at
                FROM coordinator_deliverables
                WHERE semester_id = %s
                  AND course_scope = 'graduation_project'
                  AND title = 'Graduation Project Final Submission'
                ORDER BY deliverable_id DESC
                LIMIT 1
                """,
                (semester_id,),
            )
            row = cursor.fetchone()
        cursor.close()
        db.close()
        if row:
            return jsonify(
                _json_safe_value(
                    {
                        "submission": {
                            "deliverable_id": row.get("deliverable_id"),
                            "title": row.get("title") or "Graduation Project Final Submission",
                            "note": row.get("description") or "",
                            "start_at": _format_datetime_local(row.get("start_at")),
                            "deadline_at": _format_datetime_local(row.get("due_at")),
                            "status": row.get("status") or "not_open",
                            "is_published": bool(row.get("is_published")),
                            "published_at": str(row.get("published_at") or ""),
                        }
                    }
                )
            )
        return jsonify({"submission": None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/grad-final-submission", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_grad_final_submission_save():
    try:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "Graduation Project Final Submission").strip()
        note = (data.get("note") or "").strip() or None
        start_at = _parse_datetime_local(data.get("start_at"))
        due_at = _parse_datetime_local(data.get("deadline_at"))
        publish = bool(data.get("publish"))

        if not title:
            return jsonify({"error": "Title is required."}), 400
        if not start_at:
            return jsonify({"error": "Start date/time is required."}), 400
        if not due_at:
            return jsonify({"error": "Final deadline is required."}), 400
        if due_at <= start_at:
            return jsonify({"error": "Final deadline must be after the start date/time."}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        semester = _semester_for_course_scope(cursor, "graduation_project")
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No COMP4300 semester found."}), 400
        semester_id = semester["semester_id"]
        status = "open" if publish else "not_open"

        cursor.execute(
            """
            SELECT deliverable_id
            FROM coordinator_deliverables
            WHERE semester_id = %s
              AND course_scope = 'graduation_project'
              AND title = 'Graduation Project Final Submission'
            ORDER BY deliverable_id DESC
            LIMIT 1
            """,
            (semester_id,),
        )
        existing = cursor.fetchone()
        if existing:
            deliverable_id = existing["deliverable_id"]
            cursor.execute(
                """
                UPDATE coordinator_deliverables
                SET title = %s,
                    description = %s,
                    start_at = %s,
                    due_date = %s,
                    due_at = %s,
                    mark_points = 5,
                    status = %s,
                    is_published = %s,
                    published_at = CASE WHEN %s = 1 THEN NOW() ELSE published_at END,
                    created_by = %s
                WHERE deliverable_id = %s
                """,
                (
                    title,
                    note,
                    start_at,
                    due_at.date(),
                    due_at,
                    status,
                    1 if publish else 0,
                    1 if publish else 0,
                    session.get("user_id"),
                    deliverable_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO coordinator_deliverables
                    (semester_id, course_scope, title, description, start_at, due_date, due_at,
                     mark_points, status, is_published, published_at, created_by)
                VALUES (%s, 'graduation_project', %s, %s, %s, %s, %s, 5, %s, %s,
                        CASE WHEN %s = 1 THEN NOW() ELSE NULL END, %s)
                """,
                (
                    semester_id,
                    title,
                    note,
                    start_at,
                    due_at.date(),
                    due_at,
                    status,
                    1 if publish else 0,
                    1 if publish else 0,
                    session.get("user_id"),
                ),
            )
            deliverable_id = cursor.lastrowid

        sent_count = 0
        if publish:
            recipients = sorted(set(_deliverable_student_user_ids(cursor, semester_id, "graduation_project")))
            msg = (
                f"COMP4300 final submission is now open: {title}. "
                f"Starts: {start_at.strftime('%Y-%m-%d %H:%M')}. "
                f"Deadline: {due_at.strftime('%Y-%m-%d %H:%M')}. "
                "Open it from your student timeline."
            )
            for recipient_id in recipients:
                _insert_notification(
                    cursor,
                    recipient_id,
                    session.get("user_id"),
                    "deadline_reminder",
                    "COMP4300 Final Submission Published",
                    msg,
                    None,
                    "graduation_project",
                )
            sent_count = len(recipients)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": "COMP4300 final submission saved." + (f" Notifications sent: {sent_count}." if publish else ""),
                "deliverable_id": deliverable_id,
                "notifications_sent": sent_count,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─── Coordinator Submission Files ────────────────────────────────────────
def _course_label_for_code(course_code):
    if course_code == "COMP4300":
        return "Graduation Project"
    if course_code == "COMP4200":
        return "Project Introduction"
    return course_code or "Course"


def _submission_datetime_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value:
            return value
    return None


def _format_submission_datetime(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)


def _download_static_path(file_path):
    clean_path = (file_path or "").replace("\\", "/").lstrip("/")
    if clean_path.startswith("static/"):
        clean_path = clean_path[len("static/") :]
    return redirect(url_for("static", filename=clean_path))


@coordinator_bp.route("/api/coordinator/submission-files", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_submission_files():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)
        academic_year = semester.get("academic_year") if semester else None

        files = []

        if _table_exists(cursor, "project_files"):
            params = []
            where = """
                WHERE COALESCE(pf.upload_status, 'uploaded') = 'uploaded'
                  AND EXISTS (
                      SELECT 1
                      FROM deadlines d
                      WHERE d.semester_id = s.semester_id
                        AND d.deadline_type = 'file_submission'
                        AND (d.project_id IS NULL OR d.project_id = p.project_id)
                        AND d.deadline_date < CURDATE()
                  )
            """
            if academic_year:
                where += " AND s.academic_year = %s"
                params.append(academic_year)

            cursor.execute(
                f"""
                SELECT pf.file_id, pf.project_id, pf.file_type, pf.file_name,
                       pf.file_path, pf.file_size_mb, pf.uploaded_at,
                       pf.file_data IS NOT NULL AS has_file_data,
                       p.title AS project_title, p.project_type,
                       s.course_code,
                       ANY_VALUE(COALESCE(u.full_name, primary_user.full_name, '')) AS submitted_by,
                       ANY_VALUE(sup_u.full_name) AS supervisor_name,
                       GROUP_CONCAT(DISTINCT tm_u.full_name ORDER BY tm_u.full_name SEPARATOR ', ') AS team_members
                FROM project_files pf
                JOIN projects p ON p.project_id = pf.project_id
                JOIN semesters s ON s.semester_id = p.semester_id
                LEFT JOIN users u ON u.user_id = pf.uploaded_by
                LEFT JOIN project_members primary_pm
                       ON primary_pm.project_id = p.project_id
                      AND primary_pm.is_primary_contact = TRUE
                LEFT JOIN students primary_st
                       ON primary_st.student_id = primary_pm.student_id
                LEFT JOIN users primary_user
                       ON primary_user.user_id = primary_st.user_id
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
                LEFT JOIN project_members tm_pm ON tm_pm.project_id = p.project_id
                LEFT JOIN students tm_st ON tm_st.student_id = tm_pm.student_id
                LEFT JOIN users tm_u ON tm_u.user_id = tm_st.user_id
                {where}
                GROUP BY pf.file_id, pf.project_id, pf.file_type, pf.file_name,
                         pf.file_path, pf.file_size_mb, pf.uploaded_at,
                         p.title, p.project_type, s.course_code
                ORDER BY pf.uploaded_at DESC, pf.file_id DESC
                """,
                tuple(params),
            )
            for row in cursor.fetchall():
                course_code = row.get("course_code") or "COMP4300"
                uploaded_at = _submission_datetime_value(row, "uploaded_at")
                files.append(
                    {
                        "source": "project",
                        "source_id": row.get("file_id"),
                        "project_id": row.get("project_id"),
                        "file_type": (row.get("file_type") or "project_file"),
                        "submission_title": (row.get("file_type") or "project_file")
                        .replace("_", " ")
                        .title(),
                        "course_scope": course_code,
                        "course_label": _course_label_for_code(course_code),
                        "project_title": row.get("project_title") or "Untitled Project",
                        "project_type": row.get("project_type") or "",
                        "supervisor_name": row.get("supervisor_name") or "",
                        "team_members": row.get("team_members") or "",
                        "submitted_by": row.get("submitted_by") or "Unknown student",
                        "file_name": row.get("file_name") or "Open file",
                        "file_path": row.get("file_path") or "",
                        "file_size_mb": float(row.get("file_size_mb") or 0),
                        "uploaded_at": _format_submission_datetime(uploaded_at),
                        "sort_at": uploaded_at,
                        "download_url": (
                            f"/api/coordinator/project-files/{row.get('file_id')}/download"
                            if row.get("has_file_data")
                            else ""
                        ),
                    }
                )

        if _table_exists(cursor, "milestone_submissions"):
            params = []
            where = """WHERE ms.submitted_to IN ('coordinator', 'both')"""
            if academic_year:
                where += " AND s.academic_year = %s"
                params.append(academic_year)

            cursor.execute(
                f"""
                SELECT ms.submission_id, ms.item_id, ms.project_id, ms.file_name,
                       ms.file_size_mb, ms.submitted_to, ms.submitted_at,
                       ti.due_date,
                       ti.title AS milestone_title,
                       ti.milestone_label,
                       p.title AS project_title,
                       u.full_name AS submitted_by,
                       ms.file_data IS NOT NULL AS has_file_data
                FROM milestone_submissions ms
                JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
                JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
                JOIN semesters s ON s.semester_id = tl.semester_id
                JOIN students st ON st.student_id = ms.student_id
                JOIN users u ON u.user_id = st.user_id
                LEFT JOIN projects p ON p.project_id = ms.project_id
                {where}
                ORDER BY ms.submitted_at DESC, ms.submission_id DESC
                """,
                tuple(params),
            )
            for row in cursor.fetchall():
                uploaded_at = _submission_datetime_value(row, "submitted_at")
                title = row.get("milestone_label") or row.get("milestone_title")
                files.append(
                    {
                        "source": "timeline",
                        "source_id": row.get("submission_id"),
                        "project_id": row.get("project_id"),
                        "submission_title": title or "Timeline Submission",
                        "course_scope": "COMP4200",
                        "course_label": "Project Introduction",
                        "project_title": row.get("project_title")
                        or "Project Introduction Timeline",
                        "submitted_by": row.get("submitted_by") or "Unknown student",
                        "file_name": row.get("file_name") or "Open file",
                        "file_path": "",
                        "file_size_mb": float(row.get("file_size_mb") or 0),
                        "uploaded_at": _format_submission_datetime(uploaded_at),
                        "sort_at": uploaded_at,
                        "submitted_to": row.get("submitted_to") or "supervisor",
                        "download_url": (
                            f"/api/coordinator/milestone-submissions/{row.get('submission_id')}/download"
                            if row.get("has_file_data")
                            else ""
                        ),
                    }
                )

        if _table_exists(cursor, "coordinator_deliverable_submissions"):
            params = []
            where = "WHERE 1=1"
            if academic_year:
                where += " AND s.academic_year = %s"
                params.append(academic_year)

            cursor.execute(
                f"""
                SELECT cds.submission_id, cds.project_id, cds.file_name, cds.file_path,
                       cds.file_size_mb, cds.submitted_at,
                       cds.file_data IS NOT NULL AS has_file_data,
                       cd.title AS deliverable_title,
                       cd.course_scope,
                       p.title AS project_title,
                       u.full_name AS submitted_by
                FROM coordinator_deliverable_submissions cds
                JOIN coordinator_deliverables cd
                  ON cd.deliverable_id = cds.deliverable_id
                LEFT JOIN semesters s ON s.semester_id = cd.semester_id
                JOIN students st ON st.student_id = cds.student_id
                JOIN users u ON u.user_id = st.user_id
                LEFT JOIN projects p ON p.project_id = cds.project_id
                {where}
                ORDER BY cds.submitted_at DESC, cds.submission_id DESC
                """,
                tuple(params),
            )
            for row in cursor.fetchall():
                uploaded_at = _submission_datetime_value(row, "submitted_at")
                course_code = (
                    "COMP4300"
                    if row.get("course_scope") == "graduation_project"
                    else "COMP4200"
                )
                files.append(
                    {
                        "source": "deliverable",
                        "source_id": row.get("submission_id"),
                        "project_id": row.get("project_id"),
                        "submission_title": row.get("deliverable_title")
                        or "Deliverable Submission",
                        "course_scope": course_code,
                        "course_label": _course_label_for_code(course_code),
                        "project_title": row.get("project_title")
                        or _course_label_for_code(course_code),
                        "submitted_by": row.get("submitted_by") or "Unknown student",
                        "file_name": row.get("file_name") or "Open file",
                        "file_path": row.get("file_path") or "",
                        "file_size_mb": float(row.get("file_size_mb") or 0),
                        "uploaded_at": _format_submission_datetime(uploaded_at),
                        "sort_at": uploaded_at,
                        "download_url": (
                            f"/api/coordinator/deliverable-submissions/{row.get('submission_id')}/download"
                            if row.get("has_file_data")
                            else ""
                        ),
                    }
                )

        cursor.close()
        db.close()

        files.sort(key=lambda item: item.get("sort_at") or datetime.min, reverse=True)
        for item in files:
            item.pop("sort_at", None)

        return jsonify({"files": _json_safe_value(files)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/project-files/<int:file_id>/download")
@login_required(role="coordinator")
def api_coordinator_download_project_file(file_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT pf.file_name, pf.file_path, pf.file_data, pf.file_mime
            FROM project_files pf
            WHERE pf.file_id = %s
              AND COALESCE(pf.upload_status, 'uploaded') = 'uploaded'
            """,
            (file_id,),
        )

        row = cursor.fetchone()

        cursor.close()
        db.close()

        if not row:
            return jsonify({"error": "File not found."}), 404

        if row.get("file_data"):
            return Response(
                bytes(row["file_data"]),
                mimetype=row.get("file_mime") or "application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{row.get("file_name") or "project-file"}"'
                },
            )

        if row.get("file_path"):
            return _download_static_path(row.get("file_path"))

        return jsonify({"error": "File content not found."}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@coordinator_bp.route(
    "/api/coordinator/milestone-submissions/<int:submission_id>/download"
)
@login_required(role="coordinator")
def api_coordinator_download_milestone_submission(submission_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT ms.file_name, ms.file_data, ms.file_mime
            FROM milestone_submissions ms
            JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
            WHERE ms.submission_id = %s
              AND ms.submitted_to IN ('coordinator', 'both')
            """,
            (submission_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()

        if not row or not row.get("file_data"):
            return jsonify({"error": "File not found."}), 404
        return Response(
            bytes(row["file_data"]),
            mimetype=row.get("file_mime") or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{row.get("file_name") or "timeline-submission"}"'
            },
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route(
    "/api/coordinator/deliverable-submissions/<int:submission_id>/download"
)
@login_required(role="coordinator")
def api_coordinator_download_deliverable_submission(submission_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT cds.file_name, cds.file_path, cds.file_data, cds.file_mime
            FROM coordinator_deliverable_submissions cds
            JOIN coordinator_deliverables cd
              ON cd.deliverable_id = cds.deliverable_id
            WHERE cds.submission_id = %s
              AND cd.due_date IS NOT NULL
              AND cd.due_date < CURDATE()
            """,
            (submission_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()

        if not row:
            return jsonify({"error": "File not found."}), 404
        if row.get("file_data"):
            return Response(
                bytes(row["file_data"]),
                mimetype=row.get("file_mime") or "application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{row.get("file_name") or "deliverable-submission"}"'
                },
            )
        if row.get("file_path"):
            return _download_static_path(row.get("file_path"))
        return jsonify({"error": "File content not found."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Coordinator Notifications / Messaging ───────────────────────────────
def _ensure_notification_attachment_columns(cursor):
    """Add attachment columns to notifications when the database has not been migrated yet."""
    if not _db_column_exists(cursor, "notifications", "attachment_name"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255) NULL"
        )
    if not _db_column_exists(cursor, "notifications", "attachment_mime"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120) NULL"
        )
    if not _db_column_exists(cursor, "notifications", "attachment_data"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_data LONGBLOB NULL"
        )


def _notification_attachment_select_fields(cursor):
    """Return safe SELECT fields for attachment metadata."""
    if _db_column_exists(cursor, "notifications", "attachment_name"):
        return "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"
    return "NULL AS attachment_name, NULL AS attachment_mime, 0 AS has_attachment"


def _notification_row_to_json(row):
    """Convert MySQL notification rows to safe JSON values."""
    if not row:
        return row
    clean = dict(row)
    if clean.get("created_at") is not None:
        clean["created_at"] = str(clean["created_at"])
    clean["is_read"] = bool(clean.get("is_read"))
    clean["course_scope"] = clean.get("course_scope") or "both"
    clean["has_attachment"] = bool(clean.get("has_attachment"))
    if not clean["has_attachment"]:
        clean["attachment_name"] = None
        clean["attachment_mime"] = None
    clean.pop("attachment_data", None)
    return clean


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    row = cursor.fetchone() or {}
    return int(row.get("cnt") or 0) > 0


def _notification_recipients(cursor, scope, value=None):
    """Return user_ids for the coordinator selected target."""
    scope = (scope or "").strip()

    if scope == "head":
        cursor.execute(
            "SELECT user_id FROM users WHERE role = 'head_of_department' AND is_active = TRUE"
        )
        return [r["user_id"] for r in cursor.fetchall()]

    if scope == "doctors":
        cursor.execute(
            "SELECT user_id FROM users WHERE role = 'supervisor' AND is_active = TRUE"
        )
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
        if not (
            _table_exists(cursor, "student_distribution_sections")
            and _table_exists(cursor, "section_students")
        ):
            return []
        cursor.execute(
            """
            SELECT DISTINCT recipient_id
            FROM (
                SELECT us.user_id AS recipient_id
                FROM student_distribution_sections sec
                JOIN section_students ss ON ss.section_id = sec.section_id
                JOIN students st ON st.student_id = ss.student_id
                JOIN users us ON us.user_id = st.user_id
                WHERE sec.section_id = %s AND us.is_active = TRUE
                UNION
                SELECT u_sup.user_id AS recipient_id
                FROM student_distribution_sections sec
                JOIN faculty f ON f.faculty_id = sec.supervisor_id
                JOIN users u_sup ON u_sup.user_id = f.user_id
                WHERE sec.section_id = %s AND u_sup.is_active = TRUE
            ) x
            """,
            (value, value),
        )
        return [r["recipient_id"] for r in cursor.fetchall()]

    if scope == "all_sections":
        if not (
            _table_exists(cursor, "student_distribution_sections")
            and _table_exists(cursor, "section_students")
        ):
            return []
        cursor.execute("""
            SELECT DISTINCT recipient_id
            FROM (
                SELECT us.user_id AS recipient_id
                FROM student_distribution_sections sec
                JOIN section_students ss ON ss.section_id = sec.section_id
                JOIN students st ON st.student_id = ss.student_id
                JOIN users us ON us.user_id = st.user_id
                WHERE us.is_active = TRUE
                UNION
                SELECT u_sup.user_id AS recipient_id
                FROM student_distribution_sections sec
                JOIN faculty f ON f.faculty_id = sec.supervisor_id
                JOIN users u_sup ON u_sup.user_id = f.user_id
                WHERE u_sup.is_active = TRUE
            ) x
            """)
        return [r["recipient_id"] for r in cursor.fetchall()]

    if scope == "reply":
        cursor.execute(
            """
            SELECT user_id
            FROM users
            WHERE user_id = %s AND is_active = TRUE
            """,
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]

    return []


@coordinator_bp.route("/api/coordinator/notifications/options", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_notification_options():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id, full_name, university_id
            FROM users
            WHERE role = 'head_of_department' AND is_active = TRUE
            ORDER BY full_name
            """)
        heads = cursor.fetchall()

        cursor.execute("""
            SELECT f.faculty_id, u.user_id, u.full_name, u.university_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE u.role = 'supervisor' AND u.is_active = TRUE
            ORDER BY u.full_name
            """)
        doctors = cursor.fetchall()

        cursor.execute("""
            SELECT st.student_id, u.user_id, u.full_name, u.university_id
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE u.role = 'student' AND u.is_active = TRUE
            ORDER BY u.full_name
            """)
        students = cursor.fetchall()

        sections = []
        if _table_exists(cursor, "student_distribution_sections") and _table_exists(
            cursor, "section_students"
        ):
            cursor.execute("""
                SELECT sec.section_id,
                       sec.section_name,
                       u_sup.full_name AS supervisor_name,
                       COUNT(ss.student_id) AS students_count
                FROM student_distribution_sections sec
                JOIN faculty f ON f.faculty_id = sec.supervisor_id
                JOIN users u_sup ON u_sup.user_id = f.user_id
                LEFT JOIN section_students ss ON ss.section_id = sec.section_id
                GROUP BY sec.section_id, sec.section_name, u_sup.full_name
                ORDER BY sec.section_id DESC
                """)
            sections = cursor.fetchall()

        cursor.close()
        db.close()
        return jsonify(
            {
                "heads": heads,
                "doctors": doctors,
                "students": students,
                "sections": sections,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/notifications/inbox", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_notifications_inbox():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        attachment_fields = _notification_attachment_select_fields(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.notification_type, n.title, n.message,
                   n.course_scope, n.related_project_id, n.is_read, n.created_at,
                   n.sender_id AS sender_user_id,
                   sender.full_name AS sender_name, sender.role AS sender_role,
                   {attachment_fields}
            FROM notifications n
            LEFT JOIN users sender ON sender.user_id = n.sender_id
            WHERE n.recipient_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_notification_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"notifications": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/notifications/sent", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_notifications_sent():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        attachment_fields = _notification_attachment_select_fields(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.title, n.message, n.notification_type,
                   n.course_scope, n.is_read, n.created_at,
                   n.recipient_id AS recipient_user_id,
                   recipient.full_name AS recipient_name, recipient.role AS recipient_role,
                   {attachment_fields}
            FROM notifications n
            JOIN users recipient ON recipient.user_id = n.recipient_id
            WHERE n.sender_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_notification_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"sent": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/notifications/send", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_notifications_send():
    is_multipart = bool(
        request.content_type and request.content_type.startswith("multipart/form-data")
    )
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
    allowed_course_scopes = {"introduction", "graduation_project", "both"}

    if course_scope not in allowed_course_scopes:
        return (
            jsonify(
                {
                    "error": "Please choose if this message is for Project Introduction, Graduation Project, or both."
                }
            ),
            400,
        )

    if not scope:
        return jsonify({"error": "Please choose who should receive the message."}), 400
    if not title:
        return jsonify({"error": "Please write a title."}), 400
    if not message:
        return jsonify({"error": "Please write a message."}), 400
    if scope in {"student", "section", "doctor", "reply"} and not value:
        return jsonify({"error": "Please choose the exact receiver."}), 400

    attachment_name = None
    attachment_mime = None
    attachment_data = None
    if uploaded_file and uploaded_file.filename:
        attachment_name = secure_filename(uploaded_file.filename) or "attachment"
        attachment_mime = uploaded_file.mimetype or "application/octet-stream"
        attachment_data = uploaded_file.read()
        max_attachment_size = 10 * 1024 * 1024
        if len(attachment_data) > max_attachment_size:
            return jsonify({"error": "Attachment must be 10 MB or smaller."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notification_attachment_columns(cursor)
        recipients = _notification_recipients(cursor, scope, value)
        sender_id = session.get("user_id")
        recipients = sorted({int(r) for r in recipients if int(r) != int(sender_id)})

        if not recipients:
            cursor.close()
            db.close()
            return jsonify({"error": "No recipients found for this choice."}), 404

        notification_type = "urgent_alert" if urgent else "system"
        notification_type = _safe_notification_type(cursor, notification_type)
        for recipient_id in recipients:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read,
                     attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE, %s, %s, %s)
                """,
                (
                    recipient_id,
                    sender_id,
                    notification_type,
                    title,
                    message,
                    course_scope,
                    attachment_name,
                    attachment_mime,
                    attachment_data,
                ),
            )

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": f"Message sent successfully to {len(recipients)} recipient(s).",
                "sent_count": len(recipients),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route(
    "/api/coordinator/notifications/<int:notification_id>/read", methods=["POST"]
)
@login_required(role="coordinator")
def api_coordinator_notification_mark_read(notification_id):
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            UPDATE notifications
            SET is_read = TRUE
            WHERE notification_id = %s AND recipient_id = %s
            """,
            (notification_id, session.get("user_id")),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Notification marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route(
    "/api/coordinator/notifications/<int:notification_id>/attachment", methods=["GET"]
)
@login_required(role="coordinator")
def api_coordinator_notification_attachment(notification_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        if not _db_column_exists(cursor, "notifications", "attachment_data"):
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

        filename = (
            secure_filename(row.get("attachment_name") or "attachment") or "attachment"
        )
        mimetype = row.get("attachment_mime") or "application/octet-stream"
        return Response(
            row["attachment_data"],
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/notifications/read-all", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_notifications_mark_all_read():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE notifications SET is_read = TRUE WHERE recipient_id = %s",
            (session.get("user_id"),),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "All notifications marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/notifications/unread-count", methods=["GET"])
def api_coordinator_notifications_unread_count():
    if "user_id" not in session or session.get("role") != "coordinator":
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
    except Exception as e:
        return jsonify({"unread": 0})


# ─── Public Important Notice ─────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/important-notice", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_important_notice_get():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT notice_id, title, body, highlight_text, button1_text, button2_text, button3_text, course_scope, is_active, updated_at
            FROM system_notices
            WHERE is_active = TRUE
            ORDER BY updated_at DESC, notice_id DESC
            LIMIT 1
            """)
        notice = cursor.fetchone()
        if notice and notice.get("updated_at") is not None:
            notice["updated_at"] = str(notice["updated_at"])
        cursor.close()
        db.close()
        return jsonify({"notice": notice})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/important-notice", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_important_notice_save():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    body = (data.get("body") or "").strip()
    highlight_text = (data.get("highlight_text") or "").strip() or None
    button1_text = (data.get("button1_text") or "").strip() or None
    button2_text = (data.get("button2_text") or "").strip() or None
    button3_text = (data.get("button3_text") or "").strip() or None
    course_scope = (data.get("course_scope") or "both").strip()
    allowed_course_scopes = {"introduction", "graduation_project", "both"}

    if course_scope not in allowed_course_scopes:
        return (
            jsonify(
                {
                    "error": "Please choose if this notice is for Project Introduction, Graduation Project, or both."
                }
            ),
            400,
        )

    if not title:
        return jsonify({"error": "Please write the notice title."}), 400
    if not body:
        return jsonify({"error": "Please write the notice body."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("UPDATE system_notices SET is_active = FALSE")
        cursor.execute(
            """
            INSERT INTO system_notices
                (title, body, highlight_text, button1_text, button2_text, button3_text, course_scope, is_active, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s)
            """,
            (
                title,
                body,
                highlight_text,
                button1_text,
                button2_text,
                button3_text,
                course_scope,
                session.get("user_id"),
            ),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Important notice updated successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── COMP4200 Introduction Timeline ─────────────────────────────────────
def _ensure_intro_timeline_tables(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comp4200_timelines (
            timeline_id INT PRIMARY KEY AUTO_INCREMENT,
            semester_id INT NOT NULL UNIQUE,
            title VARCHAR(180) NOT NULL DEFAULT 'Project Introduction Timeline',
            note TEXT NULL,
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            published_at DATETIME NULL,
            created_by INT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS comp4200_timeline_items (
            item_id INT PRIMARY KEY AUTO_INCREMENT,
            timeline_id INT NOT NULL,
            item_order INT NOT NULL DEFAULT 1,
            title VARCHAR(180) NOT NULL,
            description TEXT NULL,
            start_date DATE NULL,
            start_time VARCHAR(5) NULL,
            due_date DATE NULL,
            due_time VARCHAR(5) NULL,
            milestone_label VARCHAR(180) NULL,
            is_deadline  BOOLEAN NOT NULL DEFAULT TRUE,
            is_archived  BOOLEAN NOT NULL DEFAULT FALSE,
            submitted_to VARCHAR(20) NOT NULL DEFAULT 'supervisor',
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (timeline_id) REFERENCES comp4200_timelines(timeline_id) ON DELETE CASCADE,
            INDEX idx_comp4200_timeline_items_due (due_date),
            INDEX idx_comp4200_timeline_items_order (timeline_id, item_order)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    # Migration: add due_time if not exists
    if not _db_column_exists(cursor, "comp4200_timeline_items", "due_time"):
        cursor.execute(
            "ALTER TABLE comp4200_timeline_items ADD COLUMN due_time VARCHAR(5) NULL AFTER due_date"
        )
    # Migration: add start_time if not exists
    if not _db_column_exists(cursor, "comp4200_timeline_items", "start_time"):
        cursor.execute(
            "ALTER TABLE comp4200_timeline_items ADD COLUMN start_time VARCHAR(5) NULL AFTER start_date"
        )
    # Migration: add submitted_to if not exists
    if not _db_column_exists(cursor, "comp4200_timeline_items", "submitted_to"):
        cursor.execute(
            "ALTER TABLE comp4200_timeline_items ADD COLUMN submitted_to VARCHAR(20) NOT NULL DEFAULT 'supervisor' AFTER is_archived"
        )
    # Migration: allow due_date to be NULL (incomplete draft items)
    try:
        cursor.execute(
            "ALTER TABLE comp4200_timeline_items MODIFY COLUMN due_date DATE NULL"
        )
    except Exception:
        pass
    # Migration: add is_archived if not exists
    if not _db_column_exists(cursor, "comp4200_timeline_items", "is_archived"):
        cursor.execute(
            "ALTER TABLE comp4200_timeline_items ADD COLUMN is_archived BOOLEAN NOT NULL DEFAULT FALSE AFTER is_deadline"
        )


def _get_or_create_intro_timeline(cursor, semester_id, user_id=None):
    _ensure_intro_timeline_tables(cursor)
    cursor.execute(
        """
        SELECT timeline_id, semester_id, title, note, is_published, published_at, updated_at
        FROM comp4200_timelines
        WHERE semester_id = %s
        LIMIT 1
        """,
        (semester_id,),
    )
    timeline = cursor.fetchone()
    if timeline:
        return timeline
    cursor.execute(
        """
        INSERT INTO comp4200_timelines (semester_id, title, note, created_by)
        VALUES (%s, 'Project Introduction Timeline', 'Timeline for COMP4200 students.', %s)
        """,
        (semester_id, user_id),
    )
    timeline_id = cursor.lastrowid
    return {
        "timeline_id": timeline_id,
        "semester_id": semester_id,
        "title": "Project Introduction Timeline",
        "note": "Timeline for COMP4200 students.",
        "is_published": False,
        "published_at": None,
        "updated_at": None,
    }


def _intro_timeline_payload(cursor, semester_id, user_id=None, students_only=False):
    timeline = _get_or_create_intro_timeline(cursor, semester_id, user_id)
    if students_only and not bool(timeline.get("is_published")):
        return {"timeline": None, "items": []}
    cursor.execute(
        """
        SELECT item_id, item_order, title, description, start_date, start_time, due_date, due_time, milestone_label, submitted_to, is_deadline
        FROM comp4200_timeline_items
        WHERE timeline_id = %s
        ORDER BY item_order ASC, due_date ASC, item_id ASC
        """,
        (timeline["timeline_id"],),
    )
    items = cursor.fetchall()
    for item in items:
        item["is_deadline"] = bool(item.get("is_deadline"))
        # Recombine date+time into datetime-local format for the frontend
        due_date = str(item.get("due_date") or "")
        due_time = (item.get("due_time") or "").strip()
        if due_date and due_time:
            item["due_date"] = f"{due_date}T{due_time}"
        else:
            item["due_date"] = due_date
        start_date_v = str(item.get("start_date") or "")
        start_time_v = (item.get("start_time") or "").strip()
        if start_date_v and start_time_v:
            item["start_date"] = f"{start_date_v}T{start_time_v}"
        else:
            item["start_date"] = start_date_v
    timeline["is_published"] = bool(timeline.get("is_published"))
    return {"timeline": timeline, "items": items}


@coordinator_bp.route("/api/coordinator/intro-timeline", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_intro_timeline_get():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "introduction")
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400
        payload = _intro_timeline_payload(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.close()
        db.close()
        return jsonify(_json_safe_value(payload))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/intro-timeline", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_intro_timeline_save():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Project Introduction Timeline").strip()
    note = (data.get("note") or "").strip() or None
    items = data.get("items") or []
    if not title:
        return jsonify({"error": "Timeline title is required."}), 400
    if not items:
        return jsonify({"error": "Add at least one timeline item."}), 400

    clean_items = []
    for index, item in enumerate(items, start=1):
        item_title = (item.get("title") or "").strip()
        due_date = (item.get("due_date") or "").strip()
        is_deadline = bool(item.get("is_deadline", True))
        # Only require title (due_date is optional for unchecked draft items)
        if not item_title:
            return (
                jsonify({"error": f"Item #{index} must have a title."}),
                400,
            )
        start_date = (item.get("start_date") or "").strip() or None
        description = (item.get("description") or "").strip() or None
        milestone_label = (item.get("milestone_label") or "").strip() or None
        # Accept both YYYY-MM-DD and YYYY-MM-DDTHH:MM (datetime-local format)
        due_time = None
        if due_date and "T" in due_date:
            parts = due_date.split("T", 1)
            due_date = parts[0]
            due_time = parts[1][:5] if len(parts) > 1 else None
        start_time = None
        if start_date and "T" in start_date:
            _sp = start_date.split("T", 1)
            start_date = _sp[0]
            start_time = _sp[1][:5] if len(_sp) > 1 else None
        try:
            if start_date:
                datetime.strptime(start_date, "%Y-%m-%d")
            if due_date:
                datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError:
            return (
                jsonify(
                    {"error": f"Item #{index} has an invalid date. Use YYYY-MM-DD."}
                ),
                400,
            )
        clean_items.append(
            {
                "order": int(item.get("item_order") or index),
                "title": item_title,
                "description": description,
                "start_date": start_date,
                "start_time": start_time,
                "due_date": due_date or None,
                "due_time": due_time,
                "milestone_label": milestone_label,
                "is_deadline": is_deadline,
                "submitted_to": item.get("submitted_to") or "supervisor",
            }
        )

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "introduction")
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400
        timeline = _get_or_create_intro_timeline(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.execute(
            """
            UPDATE comp4200_timelines
            SET title = %s, note = %s, created_by = %s
            WHERE timeline_id = %s
            """,
            (title, note, session.get("user_id"), timeline["timeline_id"]),
        )
        # ── Smart upsert: UPDATE existing items (keeps item_id → submissions stay linked)
        #                INSERT truly new items
        #                Archive removed items that have submissions, delete the rest
        tid = timeline["timeline_id"]

        # Get current non-archived items keyed by item_order
        cursor.execute(
            """
            SELECT item_id, item_order
            FROM comp4200_timeline_items
            WHERE timeline_id = %s AND COALESCE(is_archived, FALSE) = FALSE
            """,
            (tid,),
        )
        existing = {row["item_order"]: row["item_id"] for row in cursor.fetchall()}
        new_orders = {item["order"] for item in clean_items}

        # Archive or delete items removed from the list
        for old_order, old_id in existing.items():
            if old_order not in new_orders:
                if _table_exists(cursor, "milestone_submissions"):
                    cursor.execute(
                        "SELECT COUNT(*) AS cnt FROM milestone_submissions WHERE item_id = %s",
                        (old_id,),
                    )
                    has_subs = int((cursor.fetchone() or {}).get("cnt") or 0) > 0
                else:
                    has_subs = False
                if has_subs:
                    cursor.execute(
                        "UPDATE comp4200_timeline_items SET is_archived = TRUE WHERE item_id = %s",
                        (old_id,),
                    )
                else:
                    cursor.execute(
                        "DELETE FROM comp4200_timeline_items WHERE item_id = %s",
                        (old_id,),
                    )

        # Upsert each item
        for item in clean_items:
            if item["order"] in existing:
                # UPDATE in-place — item_id stays the same, submissions stay linked
                cursor.execute(
                    """
                    UPDATE comp4200_timeline_items
                    SET item_order = %s, title = %s, description = %s,
                        start_date = %s, start_time = %s, due_date = %s, due_time = %s,
                        milestone_label = %s, submitted_to = %s,
                        is_deadline = %s, is_archived = FALSE
                    WHERE item_id = %s
                    """,
                    (
                        item["order"],
                        item["title"],
                        item["description"],
                        item["start_date"],
                        item.get("start_time"),
                        item["due_date"],
                        item.get("due_time"),
                        item["milestone_label"],
                        item.get("submitted_to", "supervisor"),
                        item["is_deadline"],
                        existing[item["order"]],
                    ),
                )
            else:
                # INSERT new item
                cursor.execute(
                    """
                    INSERT INTO comp4200_timeline_items
                        (timeline_id, item_order, title, description, start_date,
                         start_time, due_date, due_time, milestone_label, submitted_to, is_deadline, is_archived)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
                    """,
                    (
                        tid,
                        item["order"],
                        item["title"],
                        item["description"],
                        item["start_date"],
                        item.get("start_time"),
                        item["due_date"],
                        item.get("due_time"),
                        item["milestone_label"],
                        item.get("submitted_to", "supervisor"),
                        item["is_deadline"],
                    ),
                )
        db.commit()
        payload = _intro_timeline_payload(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.close()
        db.close()
        return jsonify(
            _json_safe_value({"message": "Timeline saved successfully.", **payload})
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/intro-timeline/publish", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_intro_timeline_publish():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "introduction")
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400
        timeline = _get_or_create_intro_timeline(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM comp4200_timeline_items WHERE timeline_id = %s",
            (timeline["timeline_id"],),
        )
        if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {"error": "Save at least one timeline item before publishing."}
                ),
                400,
            )

        cursor.execute(
            "UPDATE comp4200_timelines SET is_published = TRUE, published_at = NOW(), created_by = %s WHERE timeline_id = %s",
            (session.get("user_id"), timeline["timeline_id"]),
        )

        # Keep student dashboard deadlines synced with this timeline.
        cursor.execute(
            "DELETE FROM deadlines WHERE semester_id = %s AND deadline_type LIKE 'comp4200_timeline_%'",
            (semester["semester_id"],),
        )
        cursor.execute(
            """
            SELECT item_order, title, description, start_date, due_date, milestone_label
            FROM comp4200_timeline_items
            WHERE timeline_id = %s AND is_deadline = TRUE
            ORDER BY item_order ASC
            """,
            (timeline["timeline_id"],),
        )
        items = cursor.fetchall()
        for item in items:
            label = item.get("milestone_label") or item.get("title")
            cursor.execute(
                """
                INSERT INTO deadlines (semester_id, project_id, deadline_type, deadline_date, description)
                VALUES (%s, NULL, %s, %s, %s)
                """,
                (
                    semester["semester_id"],
                    f"comp4200_timeline_{item['item_order']}",
                    item["due_date"],
                    label,
                ),
            )

        # Notify all active students when the coordinator posts/publishes.
        cursor.execute(
            "SELECT user_id FROM users WHERE role = 'student' AND is_active = TRUE"
        )
        recipients = [
            r["user_id"]
            for r in cursor.fetchall()
            if r.get("user_id") != session.get("user_id")
        ]
        msg = "The coordinator published the Project Introduction timeline. Open Student Timeline to view all milestones and deadlines."
        notification_count = 0
        for uid in recipients:
            _insert_notification(
                cursor,
                uid,
                session.get("user_id"),
                "deadline_reminder",
                "Project Introduction Timeline Published",
                msg,
                None,
                "introduction",
            )
            notification_count += 1
            for item in items:
                label = item.get("milestone_label") or item.get("title")
                open_text = (
                    f" Opens: {item['start_date']}." if item.get("start_date") else ""
                )
                due_text = f" Deadline: {item['due_date']}."
                details = (item.get("description") or "").strip()
                item_message = (
                    f"A timeline submission has been posted: {label}."
                    f"{open_text}{due_text} Open Student Timeline to view it."
                )
                if details:
                    item_message += f" Details: {details}"
                _insert_notification(
                    cursor,
                    uid,
                    session.get("user_id"),
                    "deadline_reminder",
                    f"Timeline Submission: {label}",
                    item_message,
                    None,
                    "introduction",
                )
                notification_count += 1
        db.commit()
        payload = _intro_timeline_payload(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.close()
        db.close()
        return jsonify(
            _json_safe_value(
                {
                    "message": f"Timeline published to students and {notification_count} notification(s) sent.",
                    **payload,
                }
            )
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Distribution Window ─────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/distribution-window", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_distribution_window():
    """
    Coordinator opens/closes registration for COMP4200 only.

    Important:
    - This endpoint always reports course_scope='introduction' and course_code='COMP4200'.
    - The same semester columns are reused for the registration window, but the UI/student
      side should treat this window as Project Introduction registration only.
    """
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_comp4200_semester(cursor)

        # Auto-close when the deadline passed.
        if (
            semester
            and bool(semester.get("distribution_open") or 0)
            and semester.get("distribution_close_at")
            and datetime.now() >= semester["distribution_close_at"]
        ):
            cursor.execute(
                """
                UPDATE semesters
                SET distribution_open = 0, distribution_closed_at = NOW()
                WHERE semester_id = %s
                """,
                (semester["semester_id"],),
            )
            db.commit()
            semester = _get_active_comp4200_semester(cursor)

        cursor.close()
        db.close()

        if not semester:
            return jsonify({"error": "No active semester found."}), 400

        return jsonify(
            _json_safe_value(
                {
                    "semester_id": semester["semester_id"],
                    "academic_year": semester["academic_year"],
                    "semester_number": semester["semester_number"],
                    "course_scope": "introduction",
                    "course_code": "COMP4200",
                    "course_label": "Project Introduction",
                    "is_open": _active_distribution_is_open(semester),
                    "opened_at": semester.get("distribution_opened_at"),
                    "closed_at": semester.get("distribution_closed_at"),
                    "close_at": semester.get("distribution_close_at"),
                }
            )
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/distribution-window", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_distribution_window_update():
    """
    Open/close registration for COMP4200 students only.

    Any course_scope sent from the frontend is ignored unless it is 'introduction',
    because the registration window must not open COMP4300.
    """
    data = request.get_json(silent=True) or {}
    requested_scope = (data.get("course_scope") or "introduction").strip()

    if requested_scope not in ("", "introduction", "COMP4200"):
        return jsonify({"error": "This registration window is only for COMP4200 / Project Introduction."}), 400

    is_open = 1 if bool(data.get("is_open")) else 0
    close_at_raw = (data.get("close_at") or "").strip()

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_comp4200_semester(cursor)

        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        was_open = _active_distribution_is_open(semester)
        notification_count = 0

        if is_open:
            if not close_at_raw:
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "error": "Please choose an automatic close date/time before opening COMP4200 registration."
                        }
                    ),
                    400,
                )

            try:
                close_at = datetime.strptime(
                    close_at_raw.replace("T", " "), "%Y-%m-%d %H:%M"
                )
            except ValueError:
                cursor.close()
                db.close()
                return (
                    jsonify({"error": "Close date format must be YYYY-MM-DD HH:MM."}),
                    400,
                )

            if close_at <= datetime.now():
                cursor.close()
                db.close()
                return jsonify({"error": "Close date must be in the future."}), 400

            cursor.execute(
                """
                UPDATE semesters
                SET distribution_open = 1,
                    distribution_opened_at = NOW(),
                    distribution_closed_at = NULL,
                    distribution_close_at = %s
                WHERE semester_id = %s
                """,
                (close_at.strftime("%Y-%m-%d %H:%M:%S"), semester["semester_id"]),
            )

            message = "COMP4200 registration window opened successfully."

            if not was_open:
                recipients = [
                    uid
                    for uid in _comp4200_student_user_ids_for_semester(cursor, semester["semester_id"])
                    if uid != session.get("user_id")
                ]

                close_text = close_at.strftime("%Y-%m-%d %H:%M")
                notif_message = (
                    "COMP4200 Project Introduction registration is now open. "
                    f"Please register your section/group before {close_text}."
                )

                for recipient_id in sorted(set(recipients)):
                    _insert_notification(
                        cursor,
                        recipient_id,
                        session.get("user_id"),
                        "system",
                        "COMP4200 Registration Open",
                        notif_message,
                        None,
                        "introduction",
                    )

                notification_count = len(set(recipients))

        else:
            cursor.execute(
                """
                UPDATE semesters
                SET distribution_open = 0,
                    distribution_closed_at = NOW()
                WHERE semester_id = %s
                """,
                (semester["semester_id"],),
            )
            message = "COMP4200 registration window closed successfully."

        db.commit()
        cursor.close()
        db.close()

        if notification_count:
            message = f"{message} {notification_count} COMP4200 student notification(s) sent."

        return jsonify(
            {
                "message": message,
                "notifications_sent": notification_count,
                "course_scope": "introduction",
                "course_code": "COMP4200",
            }
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Distribution Data ───────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/distribution-data", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_distribution_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_comp4200_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        group_name_expr = (
            "COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id)) AS group_name"
            if _db_column_exists(cursor, "projects", "group_name")
            else "CONCAT('Group ', p.project_id) AS group_name"
        )

        cursor.execute(
            f"""
            SELECT
                   p.project_id,
                   {group_name_expr},
                   p.title,
                   p.status,
                   p.supervisor_id,
                   pref1.full_name AS preferred_1,
                   pref2.full_name AS preferred_2,
                   pref3.full_name AS preferred_3,
                   u_sup.full_name AS final_supervisor,
                   COALESCE(
                       GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                       ''
                   ) AS team_members,
                   COUNT(DISTINCT pm.student_id) AS member_count
            FROM projects p
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
            LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
            LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
            LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
            LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
            LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
            LEFT JOIN faculty fsup ON fsup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = fsup.user_id
            WHERE p.semester_id = %s
            GROUP BY
                p.project_id,
                p.title,
                p.status,
                p.supervisor_id,
                pref1.full_name,
                pref2.full_name,
                pref3.full_name,
                u_sup.full_name
            HAVING member_count > 0
            ORDER BY p.project_id DESC
            """,
            (semester["semester_id"],),
        )
        forms = cursor.fetchall()

        cursor.execute(
            """
            SELECT st.student_id, u.university_id, u.full_name
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE EXISTS (
                SELECT 1
                FROM student_course_results scr
                WHERE scr.student_id = st.student_id
                  AND scr.semester_id = %s
                  AND COALESCE(scr.status, 'pending') <> 'passed'
                  AND scr.promoted_to_semester_id IS NULL
                  AND scr.promoted_at IS NULL
            )
            AND NOT EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN projects p ON p.project_id = pm.project_id
                WHERE pm.student_id = st.student_id
                  AND p.semester_id = %s
            )
            AND NOT EXISTS (
                SELECT 1
                FROM section_students ss
                WHERE ss.student_id = st.student_id
            )
            ORDER BY u.full_name
            """,
            (semester["semester_id"], semester["semester_id"]),
        )
        unassigned = cursor.fetchall()

        cursor.execute("""
            SELECT s.section_id,
                   s.section_name,
                   s.entered_by,
                   s.created_at,
                   u.full_name AS supervisor_name,
                   COALESCE(GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', '), '') AS assigned_students
            FROM student_distribution_sections s
            JOIN faculty f ON f.faculty_id = s.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = s.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users us ON us.user_id = st.user_id
            GROUP BY s.section_id, s.section_name, s.entered_by, s.created_at, u.full_name
            ORDER BY s.section_id DESC
            """)
        sections = cursor.fetchall()

        cursor.close()
        db.close()

        assigned_forms = sum(1 for item in forms if item.get("final_supervisor"))

        stats = {
            "total_registered_students": len(unassigned)
            + sum(
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


@coordinator_bp.route("/api/coordinator/assign-group-supervisor", methods=["POST"])
@login_required(role="coordinator")
def api_assign_group_supervisor():
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    supervisor_id = data.get("supervisor_id")

    if not project_id or not supervisor_id:
        return jsonify({"error": "project_id and supervisor_id are required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester = _get_active_semester(cursor)
        if not active_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        anchor = _get_anchor_semester_for_year(cursor, active_semester["academic_year"])
        anchor_semester_id = anchor["semester_id"] if anchor else None

        cursor.execute(
            """
            SELECT p.project_id,
                   p.title,
                   p.supervisor_id,
                   old_sup.full_name AS old_supervisor_name,
                   COUNT(DISTINCT pm.student_id) AS member_count
            FROM projects p
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN faculty old_f ON old_f.faculty_id = p.supervisor_id
            LEFT JOIN users old_sup ON old_sup.user_id = old_f.user_id
            WHERE p.project_id = %s
            GROUP BY p.project_id, p.title, p.supervisor_id, old_sup.full_name
            """,
            (project_id,),
        )
        project = cursor.fetchone()

        if not project:
            cursor.close()
            db.close()
            return jsonify({"error": "Project not found."}), 404

        if str(project.get("supervisor_id") or "") == str(supervisor_id):
            cursor.close()
            db.close()
            return jsonify({"message": "Supervisor is already assigned to this group."})

        required_students = int(project.get("member_count") or 0)
        if required_students <= 0:
            required_students = 1

        snapshot = _faculty_load_snapshot(
            cursor,
            int(supervisor_id),
            active_semester["academic_year"],
            anchor_semester_id,
        )
        required_hours = required_students * 0.5

        if snapshot["remaining_hours"] < required_hours:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": (
                            f"This doctor cannot take this graduation project. "
                            f"Required load: {required_hours:.1f} hour(s), "
                            f"remaining load: {snapshot['remaining_hours']:.1f} hour(s)."
                        )
                    }
                ),
                400,
            )

        cursor.execute(
            "UPDATE projects SET supervisor_id = %s WHERE project_id = %s",
            (supervisor_id, project_id),
        )

        cursor.execute(
            """
            SELECT u.full_name
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s
            """,
            (supervisor_id,),
        )
        new_supervisor = cursor.fetchone() or {}
        new_name = new_supervisor.get("full_name") or "your supervisor"
        old_name = project.get("old_supervisor_name")
        changed = bool(project.get("supervisor_id"))
        title = "Supervisor Changed" if changed else "Supervisor Assigned"
        if changed:
            message = (
                f"Your project supervisor has been changed"
                f"{f' from {old_name}' if old_name else ''} to {new_name}."
            )
        else:
            message = f"{new_name} has been assigned as your project supervisor."
        if project.get("title"):
            message += f" Project: {project['title']}."

        sent_count = 0
        for recipient_id in _project_student_user_ids(cursor, project_id):
            _insert_notification(
                cursor,
                recipient_id,
                session.get("user_id"),
                "supervisor_assigned",
                title,
                message,
                project_id,
                "graduation_project",
            )
            sent_count += 1

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": f"Supervisor assigned successfully. {sent_count} student notification(s) sent."
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/add-section", methods=["POST"])
@login_required(role="coordinator")
def api_add_section():
    data = request.get_json(silent=True) or {}
    section_name = (data.get("section_name") or "").strip()
    section_name = " ".join(section_name.split())
    supervisor_id = data.get("supervisor_id")
    student_ids = data.get("student_ids") or []
    try:
        student_ids = sorted({int(sid) for sid in student_ids})
    except Exception:
        return jsonify({"error": "Invalid student id."}), 400

    if not section_name or not supervisor_id:
        return jsonify({"error": "section_name and supervisor_id are required."}), 400

    if len(student_ids) == 0:
        return jsonify({"error": "Please choose at least 1 student."}), 400

    if len(student_ids) > 3:
        return jsonify({"error": "A section can contain at most 3 students."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_comp4200_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        cursor.execute(
            """
            SELECT section_id
            FROM student_distribution_sections
            WHERE LOWER(TRIM(section_name)) = LOWER(TRIM(%s))
            LIMIT 1
            """,
            (section_name,),
        )
        if cursor.fetchone():
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "This section name already exists. Please choose another name."
                    }
                ),
                400,
            )

        anchor = _get_anchor_semester_for_year(cursor, semester["academic_year"])
        anchor_semester_id = anchor["semester_id"] if anchor else None

        snapshot = _faculty_load_snapshot(
            cursor,
            int(supervisor_id),
            semester["academic_year"],
            anchor_semester_id,
        )
        required_hours = len(student_ids) * 0.5

        if snapshot["remaining_hours"] < required_hours:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": (
                            f"This doctor cannot take more introduction students. "
                            f"Required load: {required_hours:.1f} hour(s), "
                            f"remaining load: {snapshot['remaining_hours']:.1f} hour(s)."
                        )
                    }
                ),
                400,
            )

        placeholders = ",".join(["%s"] * len(student_ids))
        query = f"""
            SELECT st.student_id, u.full_name
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.student_id IN ({placeholders})
              AND EXISTS (
                  SELECT 1
                  FROM student_course_results scr
                  WHERE scr.student_id = st.student_id
                    AND scr.semester_id = %s
                    AND COALESCE(scr.status, 'pending') <> 'passed'
                    AND scr.promoted_to_semester_id IS NULL
                    AND scr.promoted_at IS NULL
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                  WHERE pm.student_id = st.student_id
                    AND p.semester_id = %s
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM section_students ss
                  WHERE ss.student_id = st.student_id
              )
        """
        params = tuple(student_ids) + (semester["semester_id"], semester["semester_id"])
        cursor.execute(query, params)
        students = cursor.fetchall()

        if len(students) != len(student_ids):
            cursor.close()
            db.close()
            return (
                jsonify(
                    {"error": "One or more selected students are already assigned."}
                ),
                400,
            )

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
                """
                INSERT INTO section_students (section_id, student_id)
                VALUES (%s, %s)
                """,
                (section_id, sid),
            )

        _notify_section_students(cursor, section_id, session.get("user_id"))

        db.commit()
        cursor.close()
        db.close()

        return jsonify(
            {"message": "Section created successfully.", "section_id": section_id}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Coordinator Section Results ─────────────────────────────────────────
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


@coordinator_bp.route("/api/coordinator/section-results", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_section_results():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)

        semester = _get_active_semester(cursor)
        semester_id = semester["semester_id"] if semester else None

        introduction_sections = []
        if _table_exists(cursor, "student_distribution_sections") and _table_exists(
            cursor, "section_students"
        ):
            cursor.execute("""
                SELECT sec.section_id AS reference_id,
                       sec.section_name,
                       'introduction' AS course_scope,
                       u_sup.full_name AS supervisor_name,
                       COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '), '') AS students,
                       COUNT(DISTINCT st.student_id) AS student_count,
                       COALESCE(scs.status, 'pending') AS result_status,
                       scs.notes,
                       scs.marked_at,
                       u_mark.full_name AS marked_by_name
                FROM student_distribution_sections sec
                JOIN faculty f ON f.faculty_id = sec.supervisor_id
                JOIN users u_sup ON u_sup.user_id = f.user_id
                LEFT JOIN section_students ss ON ss.section_id = sec.section_id
                LEFT JOIN students st ON st.student_id = ss.student_id
                LEFT JOIN users u_st ON u_st.user_id = st.user_id
                LEFT JOIN section_completion_status scs
                  ON scs.course_scope = 'introduction' AND scs.reference_id = sec.section_id
                LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
                GROUP BY sec.section_id, sec.section_name, u_sup.full_name,
                         scs.status, scs.notes, scs.marked_at, u_mark.full_name
                ORDER BY sec.section_id DESC
                """)
            introduction_sections = cursor.fetchall()

        # Graduation Project groups must come from REAL registered projects only.
        # Do NOT read every row from projects, because the database contains demo/seed projects
        # such as "Committee Demo ..." with no students, which makes this page look wrong.
        grad_where_parts = []
        grad_params_list = []
        if semester_id:
            grad_where_parts.append("p.semester_id = %s")
            grad_params_list.append(semester_id)

        # A real graduation group must have at least one student in project_members.
        grad_where_parts.append("EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)")

        # Hide generated demo projects if they still exist in the database.
        grad_where_parts.append("p.title NOT LIKE 'Committee Demo%'")

        grad_where = "WHERE " + " AND ".join(grad_where_parts)
        grad_params = tuple(grad_params_list)

        group_name_select = (
            "COALESCE(NULLIF(p.group_name, ''), NULLIF(p.title, ''), CONCAT('Project ', p.project_id))"
            if _db_column_exists(cursor, "projects", "group_name")
            else "COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id))"
        )

        cursor.execute(
            f"""
            SELECT p.project_id AS reference_id,
                   {group_name_select} AS section_name,
                   'graduation_project' AS course_scope,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT pm.student_id) AS student_count,
                   p.status AS project_status,
                   COALESCE(scs.status, 'pending') AS result_status,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM projects p
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN section_completion_status scs
              ON scs.course_scope = 'graduation_project' AND scs.reference_id = p.project_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            {grad_where}
            GROUP BY p.project_id, p.title, p.status, u_sup.full_name,
                     scs.status, scs.notes, scs.marked_at, u_mark.full_name
            HAVING student_count > 0
            ORDER BY p.project_id DESC
            """,
            grad_params,
        )
        graduation_sections = cursor.fetchall()

        cursor.close()
        db.close()
        return jsonify(
            _json_safe_value(
                {
                    "semester": semester or {},
                    "introduction_sections": introduction_sections,
                    "graduation_sections": graduation_sections,
                }
            )
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/section-results/mark", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_mark_section_result():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "").strip()
    reference_id = data.get("reference_id")
    status = (data.get("status") or "pending").strip()
    notes = (data.get("notes") or "").strip() or None

    if course_scope not in {"introduction", "graduation_project"}:
        return (
            jsonify(
                {"error": "course_scope must be introduction or graduation_project."}
            ),
            400,
        )
    if status not in {"pending", "succeeded", "not_succeeded"}:
        return (
            jsonify({"error": "status must be pending, succeeded, or not_succeeded."}),
            400,
        )
    if not reference_id:
        return jsonify({"error": "reference_id is required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)

        if course_scope == "introduction":
            cursor.execute(
                "SELECT section_id FROM student_distribution_sections WHERE section_id = %s",
                (reference_id,),
            )
        else:
            cursor.execute(
                "SELECT project_id FROM projects WHERE project_id = %s", (reference_id,)
            )
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "Section/project not found."}), 404

        cursor.execute(
            """
            INSERT INTO section_completion_status
                (course_scope, reference_id, status, notes, marked_by, marked_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                notes = VALUES(notes),
                marked_by = VALUES(marked_by),
                marked_at = NOW(),
                updated_at = CURRENT_TIMESTAMP
            """,
            (course_scope, reference_id, status, notes, session.get("user_id")),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Section result saved successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/export-groups", methods=["GET"])
@login_required(role="coordinator")
def api_export_groups():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    semester = _get_active_semester(cursor)
    if not semester:
        cursor.close()
        db.close()
        return jsonify({"error": "No active semester found."}), 400

    group_name_expr = (
        "COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id)) AS group_name"
        if _db_column_exists(cursor, "projects", "group_name")
        else "CONCAT('Group ', p.project_id) AS group_name"
    )

    cursor.execute(
        f"""
        SELECT
               {group_name_expr},
               p.title,
               COALESCE(GROUP_CONCAT(DISTINCT u.full_name ORDER BY u.full_name SEPARATOR ', '), '') AS team_members,
               COALESCE(pref1.full_name, '') AS preferred_1,
               COALESCE(pref2.full_name, '') AS preferred_2,
               COALESCE(pref3.full_name, '') AS preferred_3,
               COALESCE(u_sup.full_name, '') AS final_supervisor,
               p.status,
               COUNT(DISTINCT pm.student_id) AS member_count
        FROM projects p
        JOIN project_members pm ON pm.project_id = p.project_id
        JOIN students st ON st.student_id = pm.student_id
        JOIN users u ON u.user_id = st.user_id
        LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
        LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
        LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
        LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
        LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
        LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
        LEFT JOIN faculty fsup ON fsup.faculty_id = p.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = fsup.user_id
        WHERE p.semester_id = %s
        GROUP BY p.project_id, p.title, pref1.full_name, pref2.full_name, pref3.full_name, u_sup.full_name, p.status
        HAVING member_count > 0
        ORDER BY p.project_id DESC
        """,
        (semester["semester_id"],),
    )
    rows = cursor.fetchall()
    cursor.close()
    db.close()

    return _csv_response(
        "student_groups.csv",
        [
            "Group",
            "Idea Title",
            "Team Members",
            "Preferred 1",
            "Preferred 2",
            "Preferred 3",
            "Final Supervisor",
            "Status",
        ],
        [
            [
                r["group_name"],
                r["title"],
                r["team_members"],
                r["preferred_1"],
                r["preferred_2"],
                r["preferred_3"],
                r["final_supervisor"],
                r["status"],
            ]
            for r in rows
        ],
    )


@coordinator_bp.route("/api/coordinator/export-sections", methods=["GET"])
@login_required(role="coordinator")
def api_export_sections():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT s.section_name, u.full_name AS supervisor_name, s.created_at,
               COALESCE(GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', '), '') AS assigned_students
        FROM student_distribution_sections s
        JOIN faculty f ON f.faculty_id = s.supervisor_id
        JOIN users u ON u.user_id = f.user_id
        LEFT JOIN section_students ss ON ss.section_id = s.section_id
        LEFT JOIN students st ON st.student_id = ss.student_id
        LEFT JOIN users us ON us.user_id = st.user_id
        GROUP BY s.section_id, s.section_name, u.full_name, s.created_at
        ORDER BY s.section_id DESC
        """)
    rows = cursor.fetchall()
    cursor.close()
    db.close()

    return _csv_response(
        "sections.csv",
        ["Section", "Supervisor", "Students", "Created At"],
        [
            [
                r["section_name"],
                r["supervisor_name"],
                r["assigned_students"],
                r["created_at"],
            ]
            for r in rows
        ],
    )


# ─── Faculty Hours ───────────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/faculty-hours-data", methods=["GET"])
@login_required(role="coordinator")
def api_faculty_hours_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester = _get_active_semester(cursor)
        if not active_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        academic_year = active_semester["academic_year"]
        anchor_semester = _get_anchor_semester_for_year(cursor, academic_year)
        if not anchor_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No academic year settings row found."}), 400

        cursor.execute("""
            SELECT f.faculty_id, u.full_name
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
            ORDER BY u.full_name
            """)
        faculty_rows = cursor.fetchall()
        result = []

        for row in faculty_rows:
            snapshot = _faculty_load_snapshot(
                cursor, row["faculty_id"], academic_year, anchor_semester["semester_id"]
            )
            result.append(
                {
                    "faculty_id": row["faculty_id"],
                    "full_name": row["full_name"],
                    "graduation_project_hours": snapshot["wanted_hours"],
                    "wanted_hours": snapshot["wanted_hours"],
                    "project_groups": snapshot["project_groups"],
                    "project_students": snapshot["project_students"],
                    "used_hours": snapshot["used_hours"],
                    "remaining_hours": snapshot["remaining_hours"],
                    "status": snapshot["status"],
                }
            )

        cursor.close()
        db.close()

        return jsonify(
            {
                "academic_year": academic_year,
                "anchor_semester_id": anchor_semester["semester_id"],
                "faculty": result,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/faculty-hours-save", methods=["POST"])
@login_required(role="coordinator")
def api_faculty_hours_save():
    try:
        data = request.get_json(silent=True) or {}
        faculty_id = data.get("faculty_id")
        graduation_project_hours = float(
            data.get("graduation_project_hours", data.get("wanted_hours", 0)) or 0
        )

        if not faculty_id:
            return jsonify({"error": "faculty_id is required."}), 400
        if graduation_project_hours < 0:
            return (
                jsonify({"error": "Graduation project hours cannot be negative."}),
                400,
            )

        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester = _get_active_semester(cursor)
        if not active_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        anchor_semester = _get_anchor_semester_for_year(
            cursor, active_semester["academic_year"]
        )
        if not anchor_semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No academic year settings row found."}), 400

        cursor.execute(
            """
            INSERT INTO faculty_load_settings
                (faculty_id, semester_id, graduation_project_hours, updated_by)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                graduation_project_hours = VALUES(graduation_project_hours),
                updated_by = VALUES(updated_by)
            """,
            (
                faculty_id,
                anchor_semester["semester_id"],
                graduation_project_hours,
                session.get("user_id"),
            ),
        )

        db.commit()
        cursor.close()
        db.close()

        return jsonify({"message": "Graduation project hours updated successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Review Submitted Projects ───────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/review-projects", methods=["GET"])
@login_required(role="coordinator")
def api_review_projects():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        # لو جدول الملفات مش موجود، خلي files_count = 0
        has_project_files = _table_exists(cursor, "project_files")

        files_join = """
            LEFT JOIN project_files pf
              ON pf.project_id = p.project_id
             AND COALESCE(pf.upload_status, 'uploaded') = 'uploaded'
        """ if has_project_files else ""

        files_count_select = (
            "COUNT(DISTINCT pf.file_id) AS files_count"
            if has_project_files
            else "0 AS files_count"
        )

        cursor.execute(
            f"""
            SELECT
                p.project_id,
                p.title,
                p.abstract,
                p.keywords,
                p.project_type,
                p.status,
                p.coordinator_notes,
                p.rejection_reason,
                p.submission_date,
                sup.full_name AS supervisor_name,
                COALESCE(
                    GROUP_CONCAT(
                        DISTINCT stu.full_name
                        ORDER BY pm.is_primary_contact DESC, stu.full_name
                        SEPARATOR ', '
                    ),
                    ''
                ) AS team_members,
                {files_count_select}
            FROM projects p
            LEFT JOIN faculty sf ON sf.faculty_id = p.supervisor_id
            LEFT JOIN users sup ON sup.user_id = sf.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users stu ON stu.user_id = st.user_id
            {files_join}
            WHERE p.semester_id = %s
              AND p.status IN (
                  'submitted',
                  'under_review',
                  'needs_revision',
                  'committee_evaluation',
                  'accepted',
                  'rejected'
              )
            GROUP BY
                p.project_id,
                p.title,
                p.abstract,
                p.keywords,
                p.project_type,
                p.status,
                p.coordinator_notes,
                p.rejection_reason,
                p.submission_date,
                sup.full_name
            ORDER BY
                FIELD(
                    p.status,
                    'submitted',
                    'under_review',
                    'needs_revision',
                    'committee_evaluation',
                    'accepted',
                    'rejected'
                ),
                p.project_id DESC
            """,
            (semester["semester_id"],),
        )

        projects = cursor.fetchall()

        review_badge_count = sum(
            1
            for project in projects
            if project.get("status") in ("submitted", "under_review", "needs_revision")
            and int(project.get("files_count") or 0) > 0
        )

        cursor.close()
        db.close()

        return jsonify(
            _json_safe_value(
                {
                    "projects": projects,
                    "review_badge_count": review_badge_count,
                }
            )
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500
@coordinator_bp.route("/api/coordinator/project-files/<int:project_id>", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_project_files(project_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if not _table_exists(cursor, "project_files"):
            cursor.close()
            db.close()
            return jsonify({"files": []})

        cursor.execute(
            """
            SELECT
                pf.file_id,
                pf.project_id,
                pf.file_type,
                pf.file_name,
                pf.file_path,
                pf.file_size_mb,
                pf.uploaded_at,
                pf.file_data IS NOT NULL AS has_file_data
            FROM project_files pf
            JOIN projects p ON p.project_id = pf.project_id
            WHERE pf.project_id = %s
              AND COALESCE(pf.upload_status, 'uploaded') = 'uploaded'
            ORDER BY pf.uploaded_at DESC, pf.file_id DESC
            """,
            (project_id,),
        )

        rows = cursor.fetchall()

        cursor.close()
        db.close()

        files = []
        for row in rows:
            file_id = row.get("file_id")
            files.append(
                {
                    "file_id": file_id,
                    "file_name": row.get("file_name") or f"File {file_id}",
                    "file_path": row.get("file_path") or "",
                    "file_type": row.get("file_type") or "",
                    "file_size_mb": float(row.get("file_size_mb") or 0),
                    "uploaded_at": str(row.get("uploaded_at") or ""),
                    "download_url": f"/api/coordinator/project-files/{file_id}/download",
                }
            )

        return jsonify({"files": _json_safe_value(files)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@coordinator_bp.route(
    "/api/coordinator/review-project/<int:project_id>", methods=["POST"]
)
@login_required(role="coordinator")
def api_review_project_decision(project_id):
    data = request.get_json(silent=True) or {}
    decision = (data.get("decision") or "").strip()
    notes = (data.get("notes") or "").strip()

    status_map = {
        "accepted": "accepted",
        "rejected": "rejected",
        "needs_revision": "needs_revision",
        "send_to_committee": "committee_evaluation",
        "under_review": "under_review",
    }
    if decision not in status_map:
        return jsonify({"error": "Invalid decision."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT project_id FROM projects WHERE project_id = %s", (project_id,)
        )
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "Project not found."}), 404

        new_status = status_map[decision]
        if decision == "rejected":
            cursor.execute(
                "UPDATE projects SET status = %s, coordinator_notes = %s, rejection_reason = %s WHERE project_id = %s",
                (new_status, notes, notes, project_id),
            )
        else:
            cursor.execute(
                "UPDATE projects SET status = %s, coordinator_notes = %s WHERE project_id = %s",
                (new_status, notes, project_id),
            )

        if _table_exists(cursor, "coordinator_decisions") and session.get("user_id"):
            decision_value = (
                decision
                if decision
                in ("accepted", "rejected", "needs_revision", "send_to_committee")
                else "needs_revision"
            )
            cursor.execute(
                """
                INSERT INTO coordinator_decisions (project_id, coordinator_id, decision, notes)
                VALUES (%s, %s, %s, %s)
                """,
                (project_id, session.get("user_id"), decision_value, notes),
            )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Project review decision saved successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Search ──────────────────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/search-meta", methods=["GET"])
@login_required(role="coordinator")
def api_search_meta():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT DISTINCT s.academic_year
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE s.academic_year IS NOT NULL
            ORDER BY s.academic_year DESC
            """)
        years = [row["academic_year"] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT DISTINCT u.full_name AS supervisor_name
            FROM projects p
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE u.full_name IS NOT NULL
            ORDER BY u.full_name
            """)
        supervisors = [row["supervisor_name"] for row in cursor.fetchall()]

        cursor.close()
        db.close()

        return jsonify({"years": years, "supervisors": supervisors})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/search-uploaded-projects", methods=["GET"])
@login_required(role="coordinator")
def api_search_uploaded_projects():
    try:
        q = (request.args.get("q") or "").strip()
        year = (request.args.get("year") or "").strip()
        project_type = (request.args.get("type") or "").strip()
        supervisor = (request.args.get("supervisor") or "").strip()
        status = (request.args.get("status") or "").strip()
        score = (request.args.get("score") or "").strip()

        results = search_uploaded_semantic(
            query=q,
            year=year,
            project_type=project_type,
            supervisor=supervisor,
            status=status,
            score=score,
            top_k=80,
        )

        return jsonify({"count": len(results), "projects": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/search-projects", methods=["GET"])
@login_required(role="coordinator")
def api_search_projects():
    try:
        q = (request.args.get("q") or "").strip()
        year = (request.args.get("year") or "").strip()
        project_type = (request.args.get("type") or "").strip()
        supervisor = (request.args.get("supervisor") or "").strip()
        status = (request.args.get("status") or "").strip()
        score = (request.args.get("score") or "").strip()

        db = get_db()
        cursor = db.cursor(dictionary=True)

        sql = """
            SELECT
                p.project_id,
                p.title,
                p.project_type,
                p.status,
                p.final_score,
                s.academic_year,
                u_sup.full_name AS supervisor_name,
                GROUP_CONCAT(u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', ') AS team_members
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            WHERE 1=1
        """
        params = []

        if q:
            sql += """
                AND (
                    p.title LIKE %s
                    OR u_sup.full_name LIKE %s
                    OR u_st.full_name LIKE %s
                )
            """
            like_q = f"%{q}%"
            params.extend([like_q, like_q, like_q])

        if year:
            sql += " AND s.academic_year = %s"
            params.append(year)

        if project_type:
            sql += " AND FIND_IN_SET(%s, p.project_type)"
            params.append(project_type)

        if supervisor:
            sql += " AND u_sup.full_name = %s"
            params.append(supervisor)

        if status:
            sql += " AND p.status = %s"
            params.append(status)

        if score == "90_plus":
            sql += " AND p.final_score >= 90"
        elif score == "75_89":
            sql += " AND p.final_score >= 75 AND p.final_score < 90"
        elif score == "below_75":
            sql += " AND p.final_score < 75"
        elif score == "no_score":
            sql += " AND p.final_score IS NULL"

        sql += """
            GROUP BY
                p.project_id,
                p.title,
                p.project_type,
                p.status,
                p.final_score,
                s.academic_year,
                u_sup.full_name
            ORDER BY p.project_id DESC
        """

        cursor.execute(sql, tuple(params))
        projects = cursor.fetchall()

        cursor.close()
        db.close()

        for project in projects:
            if isinstance(project.get("project_type"), set):
                project["project_type"] = ", ".join(sorted(project["project_type"]))

        return jsonify({"count": len(projects), "projects": projects})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Committee Scheduler Helpers ────────────────────────────────────────
def _committee_seed_rooms(cursor):
    rooms = [
        ("Room 201 — Engineering Building", 1),
        ("Room 202 — Engineering Building", 2),
        ("Room 203 — Engineering Building", 3),
        ("Room 204 — Engineering Building", 4),
        ("Lab 1 — Computer Science", 5),
        ("Lab 2 — Computer Science", 6),
        ("Hall A — New Building", 7),
        ("Hall B — New Building", 8),
    ]
    for room_name, sort_order in rooms:
        cursor.execute(
            """
            INSERT INTO discussion_rooms (room_name, sort_order, is_active)
            SELECT %s, %s, 1
            WHERE NOT EXISTS (
                SELECT 1 FROM discussion_rooms WHERE room_name = %s
            )
            """,
            (room_name, sort_order, room_name),
        )


def _committee_time_add(start_hhmm, minutes_to_add):
    dt = datetime.strptime(start_hhmm, "%H:%M")
    return (dt + timedelta(minutes=minutes_to_add)).strftime("%H:%M")


def _committee_fetch_faculty_pool(cursor):
    # Do NOT filter by active_committee_count = 0.
    # Include ALL active doctors so there are always >= 4 specialisations.
    # _committee_pick_members_for_supervisor already prefers less-loaded doctors.
    cursor.execute("""
        SELECT
            f.faculty_id,
            u.full_name,
            f.specialization,
            COALESCE(f.years_experience, 0) AS years_experience,
            (
                SELECT COUNT(DISTINCT cpm.plan_id)
                FROM committee_plan_members cpm
                JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
                WHERE cpm.faculty_id = f.faculty_id
                  AND cp.status IN ('scheduled', 'in_progress')
            ) AS active_committee_count
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
          AND u.is_active = TRUE
        ORDER BY f.specialization, u.full_name
        """)
    rows = cursor.fetchall()
    groups = defaultdict(list)
    for row in rows:
        groups[row["specialization"]].append(row)

    for spec in groups:
        groups[spec].sort(
            key=lambda r: (
                -int(r.get("years_experience") or 0),
                r.get("full_name") or "",
            )
        )
    return groups


def _committee_pick_members(groups, used_faculty_ids=None, rotation_index=0):
    if used_faculty_ids is None:
        used_faculty_ids = set()

    available_specs = []
    for spec, members in groups.items():
        free_members = [m for m in members if m["faculty_id"] not in used_faculty_ids]
        if free_members:
            available_specs.append(spec)

    if len(available_specs) < 4:
        raise ValueError(
            "Not enough available doctors to create another committee. "
            "A doctor cannot be assigned to more than one active committee."
        )

    available_specs.sort()
    rotation_index = rotation_index % len(available_specs)
    rotated_specs = available_specs[rotation_index:] + available_specs[:rotation_index]

    chosen_specs = rotated_specs[:4]
    chosen_members = []

    for spec in chosen_specs:
        members = [m for m in groups[spec] if m["faculty_id"] not in used_faculty_ids]
        members.sort(
            key=lambda r: (
                -int(r.get("years_experience") or 0),
                r.get("full_name") or "",
            )
        )
        if not members:
            raise ValueError(
                "Not enough available doctors to create another committee. "
                "A doctor cannot be assigned to more than one active committee."
            )
        chosen = members[0]
        chosen_members.append(chosen)
        used_faculty_ids.add(chosen["faculty_id"])

    return chosen_members



def _committee_find_faculty_in_groups(groups, faculty_id):
    for members in groups.values():
        for member in members:
            if int(member["faculty_id"]) == int(faculty_id):
                return member
    return None


def _committee_pick_members_for_supervisor(
    groups,
    supervisor_id,
    used_faculty_ids=None,
    rotation_index=0,
    reserved_supervisor_ids=None,
):
    """
    Build one discussion committee.

    Required: project supervisor + 3 other doctors.
    Preferred: the 3 other doctors are unused and from different majors.
    Fallback: if the database does not have enough free/different-major doctors,
    the system still generates the committee by reusing the least-loaded available
    doctors instead of stopping the coordinator with an error.
    """
    if used_faculty_ids is None:
        used_faculty_ids = set()

    used_faculty_ids = {int(x) for x in used_faculty_ids}

    supervisor = _committee_find_faculty_in_groups(groups, supervisor_id)
    if not supervisor:
        raise ValueError(
            "The project supervisor is not available for committee generation. "
            "Check that the supervisor has a faculty record and an active user account."
        )

    supervisor_id = int(supervisor_id)
    supervisor_spec = supervisor.get("specialization") or "General"

    chosen_members = [supervisor]
    chosen_ids = {supervisor_id}
    chosen_specs = {supervisor_spec}

    # Flatten all doctors except the current project supervisor.
    all_candidates = []
    for spec, members in groups.items():
        for member in members:
            fid = int(member["faculty_id"])
            if fid == supervisor_id:
                continue
            item = dict(member)
            item["specialization"] = item.get("specialization") or "General"
            all_candidates.append(item)

    if len(all_candidates) < 3:
        raise ValueError(
            "You need at least 4 doctors in the faculty table: the project supervisor plus 3 committee members."
        )

    def sort_key(member):
        fid = int(member["faculty_id"])
        return (
            fid in used_faculty_ids,                 # unused first
            int(member.get("active_committee_count") or 0),
            -int(member.get("years_experience") or 0),
            member.get("full_name") or "",
        )

    def add_from(candidates, require_new_major=False):
        nonlocal chosen_members, chosen_ids, chosen_specs
        for member in sorted(candidates, key=sort_key):
            fid = int(member["faculty_id"])
            spec = member.get("specialization") or "General"
            if fid in chosen_ids:
                continue
            if require_new_major and spec in chosen_specs:
                continue
            chosen_members.append(member)
            chosen_ids.add(fid)
            chosen_specs.add(spec)
            used_faculty_ids.add(fid)
            if len(chosen_members) == 4:
                return True
        return len(chosen_members) == 4

    # 1) Best case: unused doctors, different majors from each other/supervisor.
    unused_candidates = [m for m in all_candidates if int(m["faculty_id"]) not in used_faculty_ids]
    add_from(unused_candidates, require_new_major=True)

    # 2) If majors are limited, fill with unused doctors even if major repeats.
    if len(chosen_members) < 4:
        add_from(unused_candidates, require_new_major=False)

    # 3) Last fallback: reuse doctors from other committees to avoid blocking the workflow.
    # This is intentionally allowed only after all strict options fail.
    if len(chosen_members) < 4:
        add_from(all_candidates, require_new_major=False)

    if len(chosen_members) < 4:
        raise ValueError(
            "Could not create a complete committee. Please add at least 3 doctors beside the supervisor."
        )

    return chosen_members


def _committee_ensure_course_schema(cursor):
    """Keep committee tables compatible with both COMP4200 and COMP4300."""
    if not _db_column_exists(cursor, "committee_plans", "course_scope"):
        cursor.execute(
            "ALTER TABLE committee_plans ADD COLUMN course_scope ENUM('introduction','graduation_project') NOT NULL DEFAULT 'graduation_project' AFTER committee_name"
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS committee_plan_sections (
            id INT PRIMARY KEY AUTO_INCREMENT,
            plan_id INT NOT NULL,
            section_id INT NOT NULL,
            slot_order INT NOT NULL,
            slot_start TIME NOT NULL,
            slot_end TIME NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_committee_plan_section (plan_id, section_id),
            UNIQUE KEY uq_unique_section_committee (section_id),
            INDEX idx_committee_plan_sections_plan (plan_id),
            INDEX idx_committee_plan_sections_section (section_id),
            FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
            FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _committee_fetch_eligible_projects(cursor, semester_id=None, course_scope="graduation_project"):
    _committee_ensure_course_schema(cursor)

    if course_scope == "introduction":
        cursor.execute(
            """
            SELECT
                sec.section_id AS project_id,
                sec.section_id AS section_id,
                sec.section_name AS title,
                'submitted' AS status,
                'introduction' AS project_type,
                sec.supervisor_id,
                sup_u.full_name AS supervisor_name,
                sup_f.specialization AS supervisor_specialization,
                'introduction' AS course_scope,
                COALESCE(
                    GROUP_CONCAT(DISTINCT stu_u.full_name ORDER BY stu_u.full_name SEPARATOR ', '),
                    ''
                ) AS team_members
            FROM student_distribution_sections sec
            JOIN faculty sup_f ON sup_f.faculty_id = sec.supervisor_id
            JOIN users sup_u ON sup_u.user_id = sup_f.user_id
            JOIN section_students ss ON ss.section_id = sec.section_id
            JOIN students st ON st.student_id = ss.student_id
            JOIN users stu_u ON stu_u.user_id = st.user_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM committee_plan_sections cps
                JOIN committee_plans cp ON cp.plan_id = cps.plan_id
                WHERE cps.section_id = sec.section_id
                  AND cp.status <> 'cancelled'
                  AND cp.course_scope = 'introduction'
            )
            GROUP BY sec.section_id, sec.section_name, sec.supervisor_id,
                     sup_u.full_name, sup_f.specialization
            HAVING COUNT(DISTINCT ss.student_id) > 0
            ORDER BY sec.supervisor_id ASC, sec.section_id DESC
            """
        )
        sections = cursor.fetchall()
        random.shuffle(sections)
        return sections

    cursor.execute(
        """
        SELECT
            p.project_id,
            NULL AS section_id,
            p.title,
            p.status,
            p.project_type,
            p.supervisor_id,
            sup_u.full_name AS supervisor_name,
            sup_f.specialization AS supervisor_specialization,
            'graduation_project' AS course_scope,
            COALESCE(
                GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                ''
            ) AS team_members
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
        LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE sem.academic_year = (
              SELECT s2.academic_year
              FROM semesters s2
              WHERE s2.semester_id = %s
              LIMIT 1
          )
          AND p.supervisor_id IS NOT NULL
          AND p.status IN ('submitted', 'under_review', 'needs_revision', 'committee_evaluation')
          AND EXISTS (
              SELECT 1
              FROM project_members pmx
              WHERE pmx.project_id = p.project_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM committee_plan_projects cpp
              JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
              WHERE cpp.project_id = p.project_id
                AND cp.status <> 'cancelled'
                AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
          )
        GROUP BY p.project_id, p.title, p.status, p.project_type,
                 p.supervisor_id, sup_u.full_name, sup_f.specialization
        ORDER BY p.supervisor_id ASC, p.project_id DESC
        """,
        (semester_id,),
    )
    projects = cursor.fetchall()
    random.shuffle(projects)
    return projects


def _committee_fetch_plan_rows(cursor):
    _committee_ensure_course_schema(cursor)
    cursor.execute("""
        SELECT
            cp.plan_id,
            cp.committee_name,
            COALESCE(cp.course_scope, 'graduation_project') AS course_scope,
            cp.discussion_date,
            TIME_FORMAT(cp.start_time, '%H:%i') AS start_time,
            TIME_FORMAT(cp.end_time, '%H:%i') AS end_time,
            cp.status,
            cp.responsible_faculty_id,
            dr.room_name,
            ru.full_name AS responsible_name,
            CASE
                WHEN COALESCE(cp.course_scope, 'graduation_project') = 'introduction'
                    THEN COUNT(DISTINCT cps.section_id)
                ELSE COUNT(DISTINCT cpp.project_id)
            END AS projects_count
        FROM committee_plans cp
        LEFT JOIN discussion_rooms dr ON dr.room_id = cp.room_id
        LEFT JOIN faculty rf ON rf.faculty_id = cp.responsible_faculty_id
        LEFT JOIN users ru ON ru.user_id = rf.user_id
        LEFT JOIN committee_plan_projects cpp ON cpp.plan_id = cp.plan_id
        LEFT JOIN committee_plan_sections cps ON cps.plan_id = cp.plan_id
        GROUP BY cp.plan_id, cp.committee_name, cp.course_scope, cp.discussion_date, cp.start_time, cp.end_time,
                 cp.status, cp.responsible_faculty_id, dr.room_name, ru.full_name
        ORDER BY cp.discussion_date DESC, cp.start_time ASC, cp.plan_id DESC
        """)
    return cursor.fetchall()


def _committee_fetch_members_for_plan(cursor, plan_id, responsible_faculty_id=None):
    cursor.execute(
        """
        SELECT
            cpm.faculty_id,
            cpm.role,
            u.full_name,
            f.specialization,
            COALESCE(f.years_experience, 0) AS years_experience
        FROM committee_plan_members cpm
        JOIN faculty f ON f.faculty_id = cpm.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE cpm.plan_id = %s
        ORDER BY
            CASE
                WHEN cpm.role = 'supervisor' THEN 0
                WHEN %s IS NOT NULL AND cpm.faculty_id = %s THEN 1
                WHEN cpm.role = 'responsible' THEN 1
                ELSE 2
            END,
            u.full_name
        """,
        (plan_id, responsible_faculty_id, responsible_faculty_id),
    )
    rows = cursor.fetchall()
    result = []
    for row in rows:
        is_responsible = (
            responsible_faculty_id is not None
            and int(row["faculty_id"]) == int(responsible_faculty_id)
        )
        role = row.get("role") or "member"
        result.append(
            {
                "faculty_id": row["faculty_id"],
                "full_name": row["full_name"],
                "specialization": row["specialization"],
                "years_experience": row["years_experience"],
                "role": role,
                "is_supervisor": role == "supervisor",
                "is_responsible": is_responsible,
            }
        )
    return result


def _committee_ensure_report_readers_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS project_report_readers (
            id INT PRIMARY KEY AUTO_INCREMENT,
            project_id INT NOT NULL,
            faculty_id INT NOT NULL,
            reader_order TINYINT NOT NULL,
            assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_project_reader_order (project_id, reader_order),
            UNIQUE KEY uq_project_reader_faculty (project_id, faculty_id),
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS section_report_readers (
            id INT PRIMARY KEY AUTO_INCREMENT,
            section_id INT NOT NULL,
            faculty_id INT NOT NULL,
            reader_order TINYINT NOT NULL,
            assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_section_reader_order (section_id, reader_order),
            UNIQUE KEY uq_section_reader_faculty (section_id, faculty_id),
            FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE,
            FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _faculty_user_id_map(cursor, faculty_ids):
    """Return {faculty_id: user_id} for active faculty users."""
    faculty_ids = sorted({int(fid) for fid in faculty_ids if fid is not None})
    if not faculty_ids:
        return {}

    placeholders = ",".join(["%s"] * len(faculty_ids))
    cursor.execute(
        f"""
        SELECT f.faculty_id, u.user_id
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE f.faculty_id IN ({placeholders})
          AND u.is_active = TRUE
        """,
        tuple(faculty_ids),
    )
    return {int(row["faculty_id"]): row["user_id"] for row in cursor.fetchall()}


def _section_student_user_ids(cursor, section_id):
    """Return active student user IDs for a COMP4200 section."""
    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM section_students ss
        JOIN students st ON st.student_id = ss.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE ss.section_id = %s
          AND u.role = 'student'
          AND u.is_active = TRUE
        """,
        (section_id,),
    )
    return [row["user_id"] for row in cursor.fetchall()]


def _notify_section_students(cursor, section_id, sender_id):
    """Notify COMP4200 students about their supervisor and group/section students."""
    cursor.execute(
        """
        SELECT sec.section_name, u_sup.full_name AS supervisor_name
        FROM student_distribution_sections sec
        JOIN faculty f ON f.faculty_id = sec.supervisor_id
        JOIN users u_sup ON u_sup.user_id = f.user_id
        WHERE sec.section_id = %s
        """,
        (section_id,),
    )
    section = cursor.fetchone()
    if not section:
        return 0

    cursor.execute(
        """
        SELECT st.student_id, u.user_id, u.full_name
        FROM section_students ss
        JOIN students st ON st.student_id = ss.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE ss.section_id = %s
          AND u.role = 'student'
          AND u.is_active = TRUE
        ORDER BY u.full_name
        """,
        (section_id,),
    )
    students = cursor.fetchall()
    if not students:
        return 0

    all_names = [s["full_name"] for s in students]
    sent = 0

    for student in students:
        partners = [name for name in all_names if name != student["full_name"]]
        partners_line = ", ".join(partners) if partners else "No other students in your section yet"
        message = (
            f"You have been assigned to section: {section.get('section_name')}.\n"
            f"Supervisor: {section.get('supervisor_name') or 'Not assigned'}.\n"
            f"Section students: {', '.join(all_names)}.\n"
            f"Your partners: {partners_line}."
        )

        _insert_notification(
            cursor,
            student["user_id"],
            sender_id,
            "system",
            "Supervisor and Section Assignment",
            message,
            None,
            "introduction",
        )
        sent += 1

    return sent


def _committee_auto_assign_readers(cursor, plan_id, items, members, course_scope="graduation_project"):
    """
    Automatically choose two report readers from the three non-supervisor committee members.

    Committee rule:
    - The committee has 4 doctors: the supervisor + 3 other doctors.
    - The discussion/evaluation committee is the full 4 doctors.
    - The 2 report readers are selected only from the 3 non-supervisor doctors.
    """
    _committee_ensure_report_readers_table(cursor)

    member_ids = [int(m["faculty_id"]) for m in members if m.get("faculty_id")]
    if len(member_ids) < 2:
        return 0

    assigned = 0
    for index, item in enumerate(items):
        supervisor_id = int(item.get("supervisor_id") or 0)
        candidates = [fid for fid in member_ids if fid != supervisor_id]

        # Readers must be from the 3 non-supervisor members.
        # If old/incomplete data has fewer than two non-supervisor members, skip instead of using the supervisor.
        if len(candidates) < 2:
            continue

        shift = index % len(candidates)
        candidates = candidates[shift:] + candidates[:shift]
        reader_ids = candidates[:2]

        if reader_ids[0] == reader_ids[1]:
            continue

        if course_scope == "introduction":
            section_id = item.get("section_id") or item.get("project_id")
            if not section_id:
                continue
            section_id = int(section_id)
            cursor.execute("DELETE FROM section_report_readers WHERE section_id = %s", (section_id,))
            cursor.execute(
                """
                INSERT INTO section_report_readers (section_id, faculty_id, reader_order)
                VALUES (%s, %s, 1), (%s, %s, 2)
                """,
                (section_id, reader_ids[0], section_id, reader_ids[1]),
            )
            assigned += 1
        else:
            project_id = item.get("project_id")
            if not project_id:
                continue
            project_id = int(project_id)
            cursor.execute("DELETE FROM project_report_readers WHERE project_id = %s", (project_id,))
            cursor.execute(
                """
                INSERT INTO project_report_readers (project_id, faculty_id, reader_order)
                VALUES (%s, %s, 1), (%s, %s, 2)
                """,
                (project_id, reader_ids[0], project_id, reader_ids[1]),
            )
            assigned += 1

    return assigned


def _committee_faculty_project_summary(cursor, plan_id):
    """Build readable committee details for notifications."""
    cursor.execute(
        """
        SELECT cp.plan_id, cp.committee_name,
               COALESCE(cp.course_scope, 'graduation_project') AS course_scope,
               cp.discussion_date,
               TIME_FORMAT(cp.start_time, '%H:%i') AS start_time,
               TIME_FORMAT(cp.end_time, '%H:%i') AS end_time,
               dr.room_name
        FROM committee_plans cp
        LEFT JOIN discussion_rooms dr ON dr.room_id = cp.room_id
        WHERE cp.plan_id = %s
        """,
        (plan_id,),
    )
    plan = cursor.fetchone() or {}

    cursor.execute(
        """
        SELECT cpm.faculty_id, u.full_name, cpm.role
        FROM committee_plan_members cpm
        JOIN faculty f ON f.faculty_id = cpm.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE cpm.plan_id = %s
        ORDER BY CASE WHEN cpm.role = 'supervisor' THEN 0 ELSE 1 END, u.full_name
        """,
        (plan_id,),
    )
    members = cursor.fetchall()
    projects = _committee_fetch_projects_for_plan(cursor, plan_id)

    members_line = ", ".join([m.get("full_name") or "Doctor" for m in members]) or "—"
    project_lines = []

    for project in projects:
        readers = []
        if project.get("reader1_name"):
            readers.append(project["reader1_name"])
        if project.get("reader2_name"):
            readers.append(project["reader2_name"])
        readers_line = ", ".join(readers) if readers else "Not assigned yet"
        item_label = "Section" if plan.get("course_scope") == "introduction" else "Project"
        project_lines.append(
            f"- {item_label}: {project.get('title') or item_label} | "
            f"{project.get('slot_start')}–{project.get('slot_end')} | "
            f"Students: {project.get('team_members') or '—'} | Readers: {readers_line}"
        )

    return plan, members, projects, members_line, "\n".join(project_lines)


def _committee_send_notifications(cursor, plan_id, sender_id):
    """Notify committee doctors and students after a COMP4200/COMP4300 committee is generated."""
    plan, members, projects, members_line, project_lines = _committee_faculty_project_summary(cursor, plan_id)
    if not plan:
        return 0

    sent = 0
    course_scope = plan.get("course_scope") or "graduation_project"
    course_label = "COMP4200 Project Introduction" if course_scope == "introduction" else "COMP4300 Graduation Project"
    faculty_user_ids = _faculty_user_id_map(cursor, [m["faculty_id"] for m in members])

    committee_title = plan.get("committee_name") or "Committee"
    date_line = f"{plan.get('discussion_date')} from {plan.get('start_time')} to {plan.get('end_time')}"
    room_line = plan.get("room_name") or "Not assigned"

    faculty_message = (
        f"You have been assigned to {committee_title}.\n"
        f"Course: {course_label}\n"
        f"Date/Time: {date_line}\n"
        f"Room: {room_line}\n"
        f"Committee members: {members_line}\n\n"
        f"Items and reading assignments:\n{project_lines or 'No items.'}"
    )

    for member in members:
        user_id = faculty_user_ids.get(int(member["faculty_id"]))
        if not user_id:
            continue
        _insert_notification(
            cursor,
            user_id,
            sender_id,
            "system",
            f"{course_label} Committee Assignment",
            faculty_message,
            None,
            course_scope,
        )
        sent += 1

    for project in projects:
        item_label = "section" if course_scope == "introduction" else "project"
        student_message = (
            f"Your {course_label} discussion committee has been scheduled.\n"
            f"{item_label.title()}: {project.get('title') or item_label.title()}\n"
            f"Date/Time: {plan.get('discussion_date')} {project.get('slot_start')}–{project.get('slot_end')}\n"
            f"Room: {room_line}\n"
            f"Committee members: {members_line}"
        )

        if course_scope == "introduction":
            recipients = _section_student_user_ids(cursor, project.get("section_id") or project.get("project_id"))
            related_project_id = None
        else:
            recipients = _project_student_user_ids(cursor, project["project_id"])
            related_project_id = project["project_id"]

        for user_id in recipients:
            _insert_notification(
                cursor,
                user_id,
                sender_id,
                "system",
                f"{course_label} Discussion Scheduled",
                student_message,
                related_project_id,
                course_scope,
            )
            sent += 1

    return sent


def _committee_fetch_projects_for_plan(cursor, plan_id):
    _committee_ensure_course_schema(cursor)
    _committee_ensure_report_readers_table(cursor)

    cursor.execute(
        "SELECT COALESCE(course_scope, 'graduation_project') AS course_scope FROM committee_plans WHERE plan_id = %s",
        (plan_id,),
    )
    plan = cursor.fetchone() or {}
    course_scope = plan.get("course_scope") or "graduation_project"

    if course_scope == "introduction":
        cursor.execute(
            """
            SELECT
                cps.slot_order,
                TIME_FORMAT(cps.slot_start, '%H:%i') AS slot_start,
                TIME_FORMAT(cps.slot_end, '%H:%i') AS slot_end,
                sec.section_id AS project_id,
                sec.section_id AS section_id,
                sec.section_name AS title,
                sec.supervisor_id,
                sup_u.full_name AS supervisor_name,
                'introduction' AS course_scope,
                COALESCE(
                    GROUP_CONCAT(DISTINCT u.full_name ORDER BY u.full_name SEPARATOR ', '),
                    ''
                ) AS team_members,
                r1.faculty_id AS reader1_id,
                r1_u.full_name AS reader1_name,
                r2.faculty_id AS reader2_id,
                r2_u.full_name AS reader2_name
            FROM committee_plan_sections cps
            JOIN student_distribution_sections sec ON sec.section_id = cps.section_id
            LEFT JOIN faculty sup_f ON sup_f.faculty_id = sec.supervisor_id
            LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            LEFT JOIN section_report_readers r1
                ON r1.section_id = sec.section_id AND r1.reader_order = 1
            LEFT JOIN faculty r1_f ON r1_f.faculty_id = r1.faculty_id
            LEFT JOIN users r1_u ON r1_u.user_id = r1_f.user_id
            LEFT JOIN section_report_readers r2
                ON r2.section_id = sec.section_id AND r2.reader_order = 2
            LEFT JOIN faculty r2_f ON r2_f.faculty_id = r2.faculty_id
            LEFT JOIN users r2_u ON r2_u.user_id = r2_f.user_id
            WHERE cps.plan_id = %s
            GROUP BY cps.slot_order, cps.slot_start, cps.slot_end,
                     sec.section_id, sec.section_name, sec.supervisor_id, sup_u.full_name,
                     r1.faculty_id, r1_u.full_name, r2.faculty_id, r2_u.full_name
            ORDER BY cps.slot_order ASC
            """,
            (plan_id,),
        )
        return cursor.fetchall()

    cursor.execute(
        """
        SELECT
            cpp.slot_order,
            TIME_FORMAT(cpp.slot_start, '%H:%i') AS slot_start,
            TIME_FORMAT(cpp.slot_end, '%H:%i') AS slot_end,
            p.project_id,
            NULL AS section_id,
            p.title,
            p.supervisor_id,
            sup_u.full_name AS supervisor_name,
            'graduation_project' AS course_scope,
            COALESCE(
                GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                ''
            ) AS team_members,
            r1.faculty_id AS reader1_id,
            r1_u.full_name AS reader1_name,
            r2.faculty_id AS reader2_id,
            r2_u.full_name AS reader2_name
        FROM committee_plan_projects cpp
        JOIN projects p ON p.project_id = cpp.project_id
        LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
        LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        LEFT JOIN project_report_readers r1
            ON r1.project_id = p.project_id AND r1.reader_order = 1
        LEFT JOIN faculty r1_f ON r1_f.faculty_id = r1.faculty_id
        LEFT JOIN users r1_u ON r1_u.user_id = r1_f.user_id
        LEFT JOIN project_report_readers r2
            ON r2.project_id = p.project_id AND r2.reader_order = 2
        LEFT JOIN faculty r2_f ON r2_f.faculty_id = r2.faculty_id
        LEFT JOIN users r2_u ON r2_u.user_id = r2_f.user_id
        WHERE cpp.plan_id = %s
        GROUP BY
            cpp.slot_order, cpp.slot_start, cpp.slot_end,
            p.project_id, p.title, p.supervisor_id, sup_u.full_name,
            r1.faculty_id, r1_u.full_name, r2.faculty_id, r2_u.full_name
        ORDER BY cpp.slot_order ASC
        """,
        (plan_id,),
    )
    return cursor.fetchall()


def _committee_dashboard_payload(cursor):
    _committee_ensure_course_schema(cursor)
    _committee_ensure_report_readers_table(cursor)
    active_semester = _get_active_semester(cursor)

    eligible_projects = []
    if active_semester:
        eligible_projects.extend(
            _committee_fetch_eligible_projects(cursor, active_semester["semester_id"], "introduction")
        )
        eligible_projects.extend(
            _committee_fetch_eligible_projects(cursor, active_semester["semester_id"], "graduation_project")
        )

    plan_rows = _committee_fetch_plan_rows(cursor)
    plans = []
    for row in plan_rows:
        course_scope = row.get("course_scope") or "graduation_project"
        plans.append(
            {
                "plan_id": row["plan_id"],
                "committee_name": row["committee_name"],
                "course_scope": course_scope,
                "discussion_date": str(row["discussion_date"]),
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "room_name": row["room_name"] or "—",
                "status": row["status"],
                "responsible_faculty_id": row["responsible_faculty_id"],
                "responsible_name": row["responsible_name"],
                "supervisor_faculty_id": row["responsible_faculty_id"],
                "supervisor_name": row["responsible_name"],
                "projects_count": row["projects_count"],
                "members": _committee_fetch_members_for_plan(
                    cursor, row["plan_id"], row["responsible_faculty_id"]
                ),
                "projects": _committee_fetch_projects_for_plan(cursor, row["plan_id"]),
            }
        )

    cursor.execute("""
        SELECT
            COUNT(*) AS formed,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS ongoing_count,
            SUM(CASE WHEN status = 'scheduled' THEN 1 ELSE 0 END) AS scheduled_count,
            0 AS average_score
        FROM committee_plans
        """)
    stat_row = cursor.fetchone() or {}

    current_committees = [
        {
            "plan_id": p["plan_id"],
            "committee_name": p["committee_name"],
            "course_scope": p.get("course_scope") or "graduation_project",
            "discussion_date": p["discussion_date"],
            "start_time": p["start_time"],
            "room_name": p["room_name"],
            "status": p["status"],
            "projects_count": p["projects_count"],
            "responsible_name": p["responsible_name"],
            "supervisor_name": p.get("supervisor_name") or p.get("responsible_name"),
        }
        for p in plans
    ]

    eligible_sections_4200 = [item for item in eligible_projects if item.get("course_scope") == "introduction"]
    eligible_projects_4300 = [item for item in eligible_projects if item.get("course_scope") == "graduation_project"]

    return {
        "eligible_projects": eligible_projects,
        "eligible_sections_4200": eligible_sections_4200,
        "eligible_projects_4300": eligible_projects_4300,
        "plans": plans,
        "current_committees": current_committees,
        "stats": {
            "formed": int(stat_row.get("formed") or 0),
            "ongoing": int(stat_row.get("ongoing_count") or 0),
            "scheduled": int(stat_row.get("scheduled_count") or 0),
            "average_score": float(stat_row.get("average_score") or 0),
        },
    }


def _committee_plan_has_academic_year(cursor):
    cursor.execute("""
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'committee_plans'
          AND COLUMN_NAME = 'academic_year'
        """)
    row = cursor.fetchone() or {}
    return int(row.get("cnt") or 0) > 0


# ─── Committee Scheduler APIs ────────────────────────────────────────────


def _committee_delete_active_plans(cursor, course_scope="graduation_project"):
    _committee_ensure_course_schema(cursor)
    course_scope = course_scope if course_scope in ("introduction", "graduation_project") else "graduation_project"

    if course_scope == "graduation_project":
        cursor.execute("""
            SELECT DISTINCT cpp.project_id
            FROM committee_plan_projects cpp
            JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
            WHERE cp.status IN ('scheduled', 'in_progress')
              AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
            """)
        project_ids = [row["project_id"] for row in cursor.fetchall()]
    else:
        project_ids = []

    cursor.execute("""
        DELETE cpm
        FROM committee_plan_members cpm
        JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
          AND COALESCE(cp.course_scope, 'graduation_project') = %s
        """, (course_scope,))

    cursor.execute("""
        DELETE cpp
        FROM committee_plan_projects cpp
        JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
          AND COALESCE(cp.course_scope, 'graduation_project') = %s
        """, (course_scope,))

    cursor.execute("""
        DELETE cps
        FROM committee_plan_sections cps
        JOIN committee_plans cp ON cp.plan_id = cps.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
          AND COALESCE(cp.course_scope, 'graduation_project') = %s
        """, (course_scope,))

    cursor.execute("""
        DELETE FROM committee_plans
        WHERE status IN ('scheduled', 'in_progress')
          AND COALESCE(course_scope, 'graduation_project') = %s
        """, (course_scope,))

    if project_ids:
        placeholders = ",".join(["%s"] * len(project_ids))
        cursor.execute(
            f"""
            UPDATE projects
            SET status = 'submitted'
            WHERE project_id IN ({placeholders})
              AND status = 'committee_evaluation'
            """,
            tuple(project_ids),
        )


def _committee_generate_internal(
    db,
    cursor,
    discussion_date,
    start_time,
    projects_per_committee,
    clear_existing=False,
    course_scope="graduation_project",
):
    course_scope = course_scope if course_scope in ("introduction", "graduation_project") else "graduation_project"
    active_semester = _get_active_semester(cursor)
    if not active_semester:
        raise ValueError("No active semester found.")

    _committee_ensure_course_schema(cursor)

    if clear_existing:
        _committee_delete_active_plans(cursor, course_scope)

    _committee_seed_rooms(cursor)

    eligible_projects = _committee_fetch_eligible_projects(
        cursor, active_semester["semester_id"], course_scope
    )
    if not eligible_projects:
        label = "COMP4200 sections" if course_scope == "introduction" else "COMP4300 projects"
        raise ValueError(f"No eligible {label} available for committee generation.")

    faculty_groups = _committee_fetch_faculty_pool(cursor)

    # We need 4 active doctors total. Different majors are preferred later inside
    # _committee_pick_members_for_supervisor(), but they are NOT required.
    # This avoids blocking generation when the department has fewer than 4 majors.
    total_active_doctors = sum(len(members) for members in faculty_groups.values())
    if total_active_doctors < 4:
        raise ValueError(
            "At least 4 active doctors are required to generate committees."
        )

    cursor.execute("""
        SELECT room_id, room_name
        FROM discussion_rooms
        WHERE is_active = 1
        ORDER BY sort_order ASC, room_name ASC
        """)
    rooms = cursor.fetchall()

    projects_by_supervisor = defaultdict(list)
    for project in eligible_projects:
        supervisor_id = project.get("supervisor_id")
        if supervisor_id:
            projects_by_supervisor[int(supervisor_id)].append(project)

    if not projects_by_supervisor:
        raise ValueError(
            "No eligible items with assigned supervisors were found. "
            "Assign a supervisor before generating committees."
        )

    committee_groups = []
    for supervisor_id, supervisor_projects in projects_by_supervisor.items():
        random.shuffle(supervisor_projects)
        committee_groups.append(
            {
                "supervisor_id": supervisor_id,
                "projects": supervisor_projects,
            }
        )

    random.shuffle(committee_groups)
    committee_count = len(committee_groups)

    if len(rooms) < committee_count:
        raise ValueError(
            f"Not enough rooms. Required rooms: {committee_count}, available rooms: {len(rooms)}."
        )

    used_faculty_ids = set()
    reserved_supervisor_ids = set(projects_by_supervisor.keys())
    course_label = "COMP4200" if course_scope == "introduction" else "COMP4300"

    for idx, committee_group in enumerate(committee_groups):
        chunk = committee_group["projects"]
        supervisor_id = committee_group["supervisor_id"]

        if not chunk:
            continue

        members = _committee_pick_members_for_supervisor(
            faculty_groups,
            supervisor_id,
            used_faculty_ids,
            idx,
            reserved_supervisor_ids,
        )
        room = rooms[idx]
        supervisor_name = chunk[0].get("supervisor_name") or "Supervisor"
        committee_name = f"{course_label} Committee {idx + 1} — {supervisor_name}"
        last_slot_end = start_time

        for slot_index in range(len(chunk)):
            slot_start = _committee_time_add(start_time, slot_index * 40)
            slot_end = _committee_time_add(slot_start, 30)
            last_slot_end = slot_end

        insert_cursor = db.cursor()
        if _committee_plan_has_academic_year(cursor):
            insert_cursor.execute(
                """
                INSERT INTO committee_plans
                    (committee_name, course_scope, academic_year, discussion_date, start_time, end_time, room_id, responsible_faculty_id, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    committee_name,
                    course_scope,
                    active_semester["academic_year"],
                    discussion_date,
                    start_time,
                    last_slot_end,
                    room["room_id"],
                    supervisor_id,
                    "scheduled",
                    session.get("user_id"),
                ),
            )
        else:
            insert_cursor.execute(
                """
                INSERT INTO committee_plans
                    (committee_name, course_scope, discussion_date, start_time, end_time, room_id, responsible_faculty_id, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    committee_name,
                    course_scope,
                    discussion_date,
                    start_time,
                    last_slot_end,
                    room["room_id"],
                    supervisor_id,
                    "scheduled",
                    session.get("user_id"),
                ),
            )
        plan_id = insert_cursor.lastrowid

        for member in members:
            insert_cursor.execute(
                """
                INSERT INTO committee_plan_members (plan_id, faculty_id, role)
                VALUES (%s, %s, %s)
                """,
                (plan_id, member["faculty_id"], "supervisor" if int(member["faculty_id"]) == int(supervisor_id) else "member"),
            )

        for slot_index, project in enumerate(chunk, start=1):
            slot_start = _committee_time_add(start_time, (slot_index - 1) * 40)
            slot_end = _committee_time_add(slot_start, 30)

            if course_scope == "introduction":
                insert_cursor.execute(
                    """
                    INSERT INTO committee_plan_sections (plan_id, section_id, slot_order, slot_start, slot_end)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (plan_id, project["section_id"] or project["project_id"], slot_index, slot_start, slot_end),
                )
            else:
                insert_cursor.execute(
                    """
                    INSERT INTO committee_plan_projects (plan_id, project_id, slot_order, slot_start, slot_end)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (plan_id, project["project_id"], slot_index, slot_start, slot_end),
                )
                insert_cursor.execute(
                    "UPDATE projects SET status = 'committee_evaluation' WHERE project_id = %s",
                    (project["project_id"],),
                )

        # Both COMP4200 and COMP4300 have two report readers.
        # Readers are selected from the 3 non-supervisor committee members.
        if '_committee_auto_assign_readers' in globals():
            _committee_auto_assign_readers(cursor, plan_id, chunk, members, course_scope)
        if '_committee_send_notifications' in globals():
            _committee_send_notifications(cursor, plan_id, session.get("user_id"))

        insert_cursor.close()

    payload = _committee_dashboard_payload(cursor)
    return {
        "message": (
            f"{course_label} committees were generated successfully."
            if not clear_existing
            else f"{course_label} committees were reset and redistributed successfully."
        ),
        "plans": _json_safe_rows(payload["plans"]),
        "eligible_projects": _json_safe_rows(payload["eligible_projects"]),
        "eligible_sections_4200": _json_safe_rows(payload.get("eligible_sections_4200", [])),
        "eligible_projects_4300": _json_safe_rows(payload.get("eligible_projects_4300", [])),
        "current_committees": _json_safe_rows(payload["current_committees"]),
        "stats": _json_safe_value(payload["stats"]),
    }


@coordinator_bp.route("/api/coordinator/committee-dashboard", methods=["GET"])
@login_required(role="coordinator")
def api_committee_dashboard():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        payload = _committee_dashboard_payload(cursor)
        cursor.close()
        db.close()
        return jsonify(_json_safe_value(payload))
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ─── Coordinator Sections: list / add students / delete ──────────────────

@coordinator_bp.route("/api/coordinator/sections", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_sections_list():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if not _table_exists(cursor, "student_distribution_sections"):
            cursor.close()
            db.close()
            return jsonify({
                "ok": True,
                "sections": []
            })

        cursor.execute("""
            SELECT 
                sec.section_id,
                sec.section_name,
                sec.supervisor_id,
                u_sup.full_name AS supervisor_name,
                COUNT(DISTINCT ss.student_id) AS student_count,
                COALESCE(
                    GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '),
                    ''
                ) AS assigned_students
            FROM student_distribution_sections sec
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            GROUP BY sec.section_id, sec.section_name, sec.supervisor_id, u_sup.full_name
            ORDER BY sec.section_id DESC
        """)

        sections = cursor.fetchall()

        cursor.close()
        db.close()

        return jsonify({
            "ok": True,
            "sections": _json_safe_value(sections)
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@coordinator_bp.route("/api/coordinator/sections/add-students", methods=["POST"])
@login_required(role="coordinator")
def api_add_students_to_existing_section():
    data = request.get_json(silent=True) or {}

    section_id = data.get("section_id")
    student_ids = data.get("student_ids") or []

    if not section_id:
        return jsonify({
            "ok": False,
            "error": "Please choose a section."
        }), 400

    if not student_ids:
        return jsonify({
            "ok": False,
            "error": "Please select at least one student."
        }), 400

    try:
        section_id = int(section_id)
        student_ids = sorted({int(sid) for sid in student_ids})
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Invalid section or student id."
        }), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester = _get_active_semester(cursor)

        if not active_semester:
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "No active semester found."
            }), 400

        if not _table_exists(cursor, "student_distribution_sections"):
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "student_distribution_sections table not found."
            }), 500

        if not _table_exists(cursor, "section_students"):
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "section_students table not found."
            }), 500

        cursor.execute("""
            SELECT section_id, section_name, supervisor_id
            FROM student_distribution_sections
            WHERE section_id = %s
            LIMIT 1
        """, (section_id,))

        section = cursor.fetchone()

        if not section:
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "Section not found."
            }), 404

        cursor.execute("""
            SELECT COUNT(DISTINCT student_id) AS current_count
            FROM section_students
            WHERE section_id = %s
        """, (section_id,))

        current_count = int((cursor.fetchone() or {}).get("current_count") or 0)

        if current_count >= 3:
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "This section is already full."
            }), 400

        if current_count + len(student_ids) > 3:
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": f"This section has {current_count} student(s). You can add only {3 - current_count} more."
            }), 400

        placeholders = ",".join(["%s"] * len(student_ids))

        cursor.execute(f"""
            SELECT st.student_id, u.full_name
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.student_id IN ({placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                  WHERE pm.student_id = st.student_id
                    AND p.semester_id = %s
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM section_students ss
                  WHERE ss.student_id = st.student_id
              )
        """, tuple(student_ids) + (active_semester["semester_id"],))

        valid_students = cursor.fetchall()

        if len(valid_students) != len(student_ids):
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "One or more selected students are already assigned."
            }), 400

        for student_id in student_ids:
            cursor.execute("""
                INSERT INTO section_students (section_id, student_id)
                VALUES (%s, %s)
            """, (section_id, student_id))

        _notify_section_students(cursor, section_id, session.get("user_id"))

        db.commit()

        cursor.close()
        db.close()

        return jsonify({
            "ok": True,
            "message": "Students added to existing section successfully."
        })

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@coordinator_bp.route("/api/coordinator/sections/delete", methods=["POST"])
@login_required(role="coordinator")
def api_delete_distribution_section():
    data = request.get_json(silent=True) or {}

    section_id = data.get("section_id")

    if not section_id:
        return jsonify({
            "ok": False,
            "error": "Section ID is required."
        }), 400

    try:
        section_id = int(section_id)
    except Exception:
        return jsonify({
            "ok": False,
            "error": "Invalid section id."
        }), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if not _table_exists(cursor, "student_distribution_sections"):
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "student_distribution_sections table not found."
            }), 500

        cursor.execute("""
            SELECT 
                sec.section_id,
                sec.section_name,
                sec.supervisor_id,
                u.full_name AS supervisor_name
            FROM student_distribution_sections sec
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE sec.section_id = %s
            LIMIT 1
        """, (section_id,))

        section = cursor.fetchone()

        if not section:
            cursor.close()
            db.close()
            return jsonify({
                "ok": False,
                "error": "Section not found."
            }), 404

        student_count = 0

        if _table_exists(cursor, "section_students"):
            cursor.execute("""
                SELECT COUNT(DISTINCT student_id) AS student_count
                FROM section_students
                WHERE section_id = %s
            """, (section_id,))

            student_count = int((cursor.fetchone() or {}).get("student_count") or 0)

            cursor.execute("""
                DELETE FROM section_students
                WHERE section_id = %s
            """, (section_id,))

        if _table_exists(cursor, "section_completion_status"):
            cursor.execute("""
                DELETE FROM section_completion_status
                WHERE course_scope = 'introduction'
                  AND reference_id = %s
            """, (section_id,))

        cursor.execute("""
            DELETE FROM student_distribution_sections
            WHERE section_id = %s
        """, (section_id,))

        db.commit()

        cursor.close()
        db.close()

        removed_hours = student_count * 0.5

        return jsonify({
            "ok": True,
            "message": (
                f"Section deleted successfully. "
                f"{student_count} student(s) returned to unassigned. "
                f"Doctor load decreased by {removed_hours:g} hour(s)."
            ),
            "returned_students": student_count,
            "removed_hours": removed_hours,
            "supervisor_id": section.get("supervisor_id"),
            "supervisor_name": section.get("supervisor_name")
        })

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass

        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500
    

@coordinator_bp.route("/api/coordinator/committee-generate", methods=["POST"])
@login_required(role="coordinator")
def api_committee_generate():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "graduation_project").strip()
    discussion_date = (data.get("discussion_date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    projects_per_committee = int(data.get("projects_per_committee") or 0)

    if course_scope not in ("introduction", "graduation_project"):
        return jsonify({"error": "Invalid committee type."}), 400

    if not discussion_date or not start_time or projects_per_committee <= 0:
        return (
            jsonify(
                {
                    "error": "discussion_date, start_time, and projects_per_committee are required."
                }
            ),
            400,
        )

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        payload = _committee_generate_internal(
            db,
            cursor,
            discussion_date,
            start_time,
            projects_per_committee,
            clear_existing=False,
            course_scope=course_scope,
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/committee-reset", methods=["POST"])
@login_required(role="coordinator")
def api_committee_reset():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "graduation_project").strip()
    discussion_date = (data.get("discussion_date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    projects_per_committee = int(data.get("projects_per_committee") or 0)

    if course_scope not in ("introduction", "graduation_project"):
        return jsonify({"error": "Invalid committee type."}), 400

    if not discussion_date or not start_time or projects_per_committee <= 0:
        return (
            jsonify(
                {
                    "error": "discussion_date, start_time, and projects_per_committee are required."
                }
            ),
            400,
        )

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        payload = _committee_generate_internal(
            db,
            cursor,
            discussion_date,
            start_time,
            projects_per_committee,
            clear_existing=True,
            course_scope=course_scope,
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route(
    "/api/coordinator/committee/<int:plan_id>/responsible", methods=["POST"]
)
@login_required(role="coordinator")
def api_committee_save_responsible(plan_id):
    data = request.get_json(silent=True) or {}
    faculty_id = data.get("faculty_id")

    if not faculty_id:
        return jsonify({"error": "faculty_id is required."}), 400

    try:
        faculty_id = int(faculty_id)
    except Exception:
        return jsonify({"error": "Invalid faculty_id."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("SELECT plan_id FROM committee_plans WHERE plan_id = %s", (plan_id,))
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "Committee plan was not found."}), 404

        cursor.execute(
            """
            SELECT faculty_id, role
            FROM committee_plan_members
            WHERE plan_id = %s AND faculty_id = %s
            """,
            (plan_id, faculty_id),
        )
        member_row = cursor.fetchone()
        if not member_row:
            cursor.close()
            db.close()
            return jsonify({"error": "Responsible doctor must be one of the committee members."}), 400

        if (member_row.get("role") or "").lower() == "supervisor":
            cursor.close()
            db.close()
            return jsonify({"error": "Responsible doctor must be different from the project supervisor."}), 400

        cursor.execute(
            "UPDATE committee_plans SET responsible_faculty_id = %s WHERE plan_id = %s",
            (faculty_id, plan_id),
        )

        cursor.execute(
            """
            UPDATE committee_plan_members
            SET role = CASE
                WHEN role = 'supervisor' THEN 'supervisor'
                ELSE 'member'
            END
            WHERE plan_id = %s
            """,
            (plan_id,),
        )
        cursor.execute(
            """
            UPDATE committee_plan_members
            SET role = 'responsible'
            WHERE plan_id = %s
              AND faculty_id = %s
              AND role <> 'supervisor'
            """,
            (plan_id, faculty_id),
        )

        db.commit()
        payload = _committee_dashboard_payload(cursor)
        cursor.close()
        db.close()

        return jsonify({
            "message": "Responsible doctor saved successfully.",
            "plans": _json_safe_rows(payload["plans"]),
            "current_committees": _json_safe_rows(payload["current_committees"]),
            "eligible_projects": _json_safe_rows(payload["eligible_projects"]),
            "stats": _json_safe_value(payload["stats"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route(
    "/api/coordinator/committee/<int:plan_id>/project/<int:project_id>/readers",
    methods=["POST"],
)
@login_required(role="coordinator")
def api_committee_save_project_readers(plan_id, project_id):
    data = request.get_json(silent=True) or {}
    reader1_id = data.get("reader1_id")
    reader2_id = data.get("reader2_id")

    if not reader1_id or not reader2_id:
        return jsonify({"error": "Choose Reader 1 and Reader 2."}), 400

    try:
        reader1_id = int(reader1_id)
        reader2_id = int(reader2_id)
    except Exception:
        return jsonify({"error": "Invalid reader id."}), 400

    if reader1_id == reader2_id:
        return jsonify({"error": "Reader 1 and Reader 2 must be different doctors."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _committee_ensure_report_readers_table(cursor)

        cursor.execute(
            """
            SELECT cpp.project_id
            FROM committee_plan_projects cpp
            WHERE cpp.plan_id = %s AND cpp.project_id = %s
            """,
            (plan_id, project_id),
        )
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "This project does not belong to this committee."}), 404

        placeholders = "%s,%s"
        cursor.execute(
            f"""
            SELECT faculty_id
            FROM committee_plan_members
            WHERE plan_id = %s
              AND faculty_id IN ({placeholders})
            """,
            (plan_id, reader1_id, reader2_id),
        )
        found = {int(row["faculty_id"]) for row in cursor.fetchall()}
        if reader1_id not in found or reader2_id not in found:
            cursor.close()
            db.close()
            return jsonify({"error": "Report readers must be selected from this committee members."}), 400

        cursor.execute("DELETE FROM project_report_readers WHERE project_id = %s", (project_id,))
        cursor.execute(
            """
            INSERT INTO project_report_readers (project_id, faculty_id, reader_order)
            VALUES (%s, %s, 1), (%s, %s, 2)
            """,
            (project_id, reader1_id, project_id, reader2_id),
        )

        db.commit()
        payload = _committee_dashboard_payload(cursor)
        cursor.close()
        db.close()

        return jsonify({
            "message": "Report readers saved successfully.",
            "plans": _json_safe_rows(payload["plans"]),
            "current_committees": _json_safe_rows(payload["current_committees"]),
            "eligible_projects": _json_safe_rows(payload["eligible_projects"]),
            "stats": _json_safe_value(payload["stats"]),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ─── Coordinator Final Evaluation APIs ───────────────────────────────────
def _ensure_evaluation_schema(cursor):
    """Create evaluation tables used by coordinator/evaluation.html."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_windows (
            window_id INT PRIMARY KEY AUTO_INCREMENT,
            course_scope ENUM('introduction','graduation_project') NOT NULL,
            reference_id INT NOT NULL,
            is_open BOOLEAN NOT NULL DEFAULT FALSE,
            opened_by INT NULL,
            opened_at DATETIME NULL,
            closed_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_eval_window (course_scope, reference_id),
            INDEX idx_eval_window_scope_open (course_scope, is_open)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_grade_tasks (
            task_id INT PRIMARY KEY AUTO_INCREMENT,
            course_scope ENUM('introduction','graduation_project') NOT NULL,
            reference_id INT NOT NULL,
            component VARCHAR(60) NOT NULL,
            evaluator_faculty_id INT NOT NULL,
            max_mark DECIMAL(6,2) NOT NULL DEFAULT 0,
            mark DECIMAL(6,2) NULL,
            notes TEXT NULL,
            is_submitted BOOLEAN NOT NULL DEFAULT FALSE,
            created_by INT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            submitted_at DATETIME NULL,
            UNIQUE KEY uq_eval_task (course_scope, reference_id, component, evaluator_faculty_id),
            INDEX idx_eval_task_ref (course_scope, reference_id),
            INDEX idx_eval_task_eval (evaluator_faculty_id),
            FOREIGN KEY (evaluator_faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def _evaluation_component_max_mark(component):
    return {
        "intro_report_reader": 40.0,
        "intro_coordinator": 10.0,
        "intro_supervisor": 10.0,
        "intro_discussion_member": 10.0,
        "grad_report_reader": 30.0,
        "grad_supervisor": 20.0,
        "grad_committee_member": 25.0,
    }.get(component, 0.0)


def _evaluation_default_required_count(course_scope):
    # COMP4200: two report readers + supervisor + four discussion members.
    # Coordinator does not read/evaluate the report from this page.
    # COMP4300: two report readers + supervisor + four committee members.
    return 7 if course_scope == "introduction" else 7


def _evaluation_faculty_user_ids(cursor, faculty_ids):
    faculty_ids = sorted({int(fid) for fid in faculty_ids if fid is not None})
    if not faculty_ids:
        return {}
    placeholders = ",".join(["%s"] * len(faculty_ids))
    cursor.execute(
        f"""
        SELECT f.faculty_id, u.user_id
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE f.faculty_id IN ({placeholders})
          AND u.is_active = TRUE
        """,
        tuple(faculty_ids),
    )
    return {int(row["faculty_id"]): row["user_id"] for row in cursor.fetchall()}


def _evaluation_section_student_user_ids(cursor, section_id):
    if not (_table_exists(cursor, "section_students") and _table_exists(cursor, "student_distribution_sections")):
        return []
    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM section_students ss
        JOIN students st ON st.student_id = ss.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE ss.section_id = %s
          AND u.role = 'student'
          AND u.is_active = TRUE
        """,
        (section_id,),
    )
    return [row["user_id"] for row in cursor.fetchall()]


def _evaluation_insert_task(cursor, course_scope, reference_id, component, faculty_id, created_by=None):
    if not faculty_id:
        return False
    max_mark = _evaluation_component_max_mark(component)
    if max_mark <= 0:
        return False
    cursor.execute(
        """
        INSERT INTO evaluation_grade_tasks
            (course_scope, reference_id, component, evaluator_faculty_id, max_mark, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            max_mark = VALUES(max_mark)
        """,
        (course_scope, reference_id, component, faculty_id, max_mark, created_by),
    )
    return True


def _evaluation_autocreate_tasks(cursor, course_scope, reference_id, created_by=None):
    """
    Create grade tasks from the committee page setup.

    Committee rule used here:
    - Committee = supervisor + 3 other doctors.
    - The full committee gives discussion/committee marks.
    - The 2 report readers are chosen from the 3 non-supervisor doctors.
    - Coordinator does not read/evaluate and does not assign readers from the Evaluation page.
    """
    created_faculty_ids = set()
    _committee_ensure_report_readers_table(cursor)

    if course_scope == "graduation_project":
        cursor.execute("SELECT supervisor_id FROM projects WHERE project_id = %s", (reference_id,))
        project = cursor.fetchone() or {}
        supervisor_id = project.get("supervisor_id")

        if supervisor_id:
            _evaluation_insert_task(cursor, course_scope, reference_id, "grad_supervisor", supervisor_id, created_by)
            created_faculty_ids.add(int(supervisor_id))

        # Two report readers, selected by the committee generator from the 3 non-supervisor members.
        cursor.execute(
            """
            SELECT faculty_id
            FROM project_report_readers
            WHERE project_id = %s
            ORDER BY reader_order ASC, id ASC
            LIMIT 2
            """,
            (reference_id,),
        )
        for row in cursor.fetchall():
            fid = row.get("faculty_id")
            if fid:
                _evaluation_insert_task(cursor, course_scope, reference_id, "grad_report_reader", fid, created_by)
                created_faculty_ids.add(int(fid))

        # Full committee = supervisor + 3 doctors. All submit committee marks.
        if _table_exists(cursor, "committee_plan_projects") and _table_exists(cursor, "committee_plan_members"):
            cursor.execute(
                """
                SELECT cpm.faculty_id, MIN(COALESCE(cpm.role, 'member')) AS member_role
                FROM committee_plan_projects cpp
                JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
                JOIN committee_plan_members cpm ON cpm.plan_id = cp.plan_id
                WHERE cpp.project_id = %s
                  AND cp.status <> 'cancelled'
                  AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
                GROUP BY cpm.faculty_id
                ORDER BY MIN(CASE WHEN cpm.role = 'supervisor' THEN 0 ELSE 1 END), cpm.faculty_id
                LIMIT 4
                """,
                (reference_id,),
            )
            for row in cursor.fetchall():
                fid = row.get("faculty_id")
                if fid:
                    _evaluation_insert_task(cursor, course_scope, reference_id, "grad_committee_member", fid, created_by)
                    created_faculty_ids.add(int(fid))
    else:
        supervisor_id = None
        if _table_exists(cursor, "student_distribution_sections"):
            cursor.execute("SELECT supervisor_id FROM student_distribution_sections WHERE section_id = %s", (reference_id,))
            section = cursor.fetchone() or {}
            supervisor_id = section.get("supervisor_id")
            if supervisor_id:
                _evaluation_insert_task(cursor, course_scope, reference_id, "intro_supervisor", supervisor_id, created_by)
                created_faculty_ids.add(int(supervisor_id))

        # Two report readers from the 3 non-supervisor committee doctors.
        cursor.execute(
            """
            SELECT faculty_id
            FROM section_report_readers
            WHERE section_id = %s
            ORDER BY reader_order ASC, id ASC
            LIMIT 2
            """,
            (reference_id,),
        )
        for row in cursor.fetchall():
            fid = row.get("faculty_id")
            if fid:
                _evaluation_insert_task(cursor, course_scope, reference_id, "intro_report_reader", fid, created_by)
                created_faculty_ids.add(int(fid))

        # Full committee discussion = supervisor + 3 doctors.
        if _table_exists(cursor, "committee_plan_sections") and _table_exists(cursor, "committee_plan_members"):
            cursor.execute(
                """
                SELECT cpm.faculty_id, MIN(COALESCE(cpm.role, 'member')) AS member_role
                FROM committee_plan_sections cps
                JOIN committee_plans cp ON cp.plan_id = cps.plan_id
                JOIN committee_plan_members cpm ON cpm.plan_id = cp.plan_id
                WHERE cps.section_id = %s
                  AND cp.status <> 'cancelled'
                  AND COALESCE(cp.course_scope, 'graduation_project') = 'introduction'
                GROUP BY cpm.faculty_id
                ORDER BY MIN(CASE WHEN cpm.role = 'supervisor' THEN 0 ELSE 1 END), cpm.faculty_id
                LIMIT 4
                """,
                (reference_id,),
            )
            committee_members = cursor.fetchall()
            for row in committee_members:
                fid = row.get("faculty_id")
                if fid:
                    _evaluation_insert_task(cursor, course_scope, reference_id, "intro_discussion_member", fid, created_by)
                    created_faculty_ids.add(int(fid))

            # Fallback: if readers were not generated yet, choose first two non-supervisor members now.
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM evaluation_grade_tasks
                WHERE course_scope = 'introduction'
                  AND reference_id = %s
                  AND component = 'intro_report_reader'
                """,
                (reference_id,),
            )
            reader_count = int((cursor.fetchone() or {}).get("cnt") or 0)
            if reader_count < 2:
                fallback_readers = []
                for row in committee_members:
                    fid = row.get("faculty_id")
                    if not fid:
                        continue
                    if supervisor_id and int(fid) == int(supervisor_id):
                        continue
                    fallback_readers.append(int(fid))
                for fid in fallback_readers[:2]:
                    _evaluation_insert_task(cursor, course_scope, reference_id, "intro_report_reader", fid, created_by)
                    created_faculty_ids.add(int(fid))

    return created_faculty_ids


def _evaluation_cleanup_tasks(cursor, course_scope, reference_id):
    """
    Remove old/wrong evaluation rows created by earlier versions.
    Important fixes:
    - COMP4200 has no coordinator grade task on this coordinator page.
    - The real section supervisor must only have the supervisor component.
    - Keep only 2 report readers and 4 discussion/committee members.
    """
    reference_id = int(reference_id)

    # Coordinator task was an old mistake because it was often assigned to the supervisor.
    cursor.execute(
        """
        DELETE FROM evaluation_grade_tasks
        WHERE course_scope = %s
          AND reference_id = %s
          AND component = 'intro_coordinator'
        """,
        (course_scope, reference_id),
    )

    supervisor_id = None
    supervisor = _evaluation_reference_supervisor(cursor, course_scope, reference_id)
    if supervisor and supervisor.get("faculty_id"):
        supervisor_id = int(supervisor["faculty_id"])

    # The supervisor should not also appear as report reader/discussion/committee.
    if supervisor_id:
        wrong_components = (
            ("intro_report_reader",)
            if course_scope == "introduction"
            else ("grad_report_reader",)
        )
        placeholders = ",".join(["%s"] * len(wrong_components))
        cursor.execute(
            f"""
            DELETE FROM evaluation_grade_tasks
            WHERE course_scope = %s
              AND reference_id = %s
              AND evaluator_faculty_id = %s
              AND component IN ({placeholders})
            """,
            (course_scope, reference_id, supervisor_id, *wrong_components),
        )

    limits = {
        "intro_report_reader": 2,
        "intro_supervisor": 1,
        "intro_discussion_member": 4,
        "grad_report_reader": 2,
        "grad_supervisor": 1,
        "grad_committee_member": 4,
    }

    for component, limit in limits.items():
        if course_scope == "introduction" and not component.startswith("intro_"):
            continue
        if course_scope == "graduation_project" and not component.startswith("grad_"):
            continue
        cursor.execute(
            """
            SELECT task_id
            FROM evaluation_grade_tasks
            WHERE course_scope = %s
              AND reference_id = %s
              AND component = %s
            ORDER BY is_submitted DESC, task_id ASC
            """,
            (course_scope, reference_id, component),
        )
        ids = [int(row["task_id"]) for row in cursor.fetchall()]
        extra_ids = ids[limit:]
        if extra_ids:
            placeholders = ",".join(["%s"] * len(extra_ids))
            cursor.execute(
                f"DELETE FROM evaluation_grade_tasks WHERE task_id IN ({placeholders})",
                tuple(extra_ids),
            )


def _evaluation_fetch_grade_rows(cursor, course_scope, reference_id):
    cursor.execute(
        """
        SELECT egt.task_id, egt.course_scope, egt.reference_id, egt.component,
               egt.evaluator_faculty_id, u.full_name AS evaluator_name,
               egt.max_mark, egt.mark, egt.notes, egt.is_submitted, egt.submitted_at
        FROM evaluation_grade_tasks egt
        JOIN faculty f ON f.faculty_id = egt.evaluator_faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE egt.course_scope = %s AND egt.reference_id = %s
        ORDER BY FIELD(egt.component,
            'intro_report_reader','intro_coordinator','intro_supervisor','intro_discussion_member',
            'grad_report_reader','grad_supervisor','grad_committee_member'),
            u.full_name
        """,
        (course_scope, reference_id),
    )
    rows = cursor.fetchall()
    for row in rows:
        row["max_mark"] = float(row.get("max_mark") or 0)
        row["mark"] = None if row.get("mark") is None else float(row.get("mark") or 0)
        row["is_submitted"] = bool(row.get("is_submitted"))
        if row.get("submitted_at") is not None:
            row["submitted_at"] = str(row["submitted_at"])
    return rows


def _evaluation_scores_from_grades(course_scope, grades):
    def submitted_marks(component):
        result = []
        for grade in grades:
            if grade.get("component") != component or not grade.get("is_submitted"):
                continue
            if grade.get("mark") is None:
                continue
            result.append(float(grade.get("mark") or 0))
        return result

    def avg(values):
        return (sum(values) / len(values)) if values else None

    if course_scope == "graduation_project":
        report_avg_30 = avg(submitted_marks("grad_report_reader"))
        supervisor_avg_20 = avg(submitted_marks("grad_supervisor"))
        committee_avg_25 = avg(submitted_marks("grad_committee_member"))
        committee_score_50 = committee_avg_25 * 2 if committee_avg_25 is not None else None

        final_score = None
        if report_avg_30 is not None and supervisor_avg_20 is not None and committee_score_50 is not None:
            final_score = report_avg_30 + supervisor_avg_20 + committee_score_50

        return {
            "report_score": round(report_avg_30, 2) if report_avg_30 is not None else None,
            "supervisor_score": round(supervisor_avg_20, 2) if supervisor_avg_20 is not None else None,
            "coordinator_score": None,
            "discussion_score": None,
            "committee_score": round(committee_score_50, 2) if committee_score_50 is not None else None,
            "calculated_final_score": round(final_score, 2) if final_score is not None else None,
            "final_score": round(final_score, 2) if final_score is not None else None,
        }

    report_avg_40 = avg(submitted_marks("intro_report_reader"))
    supervisor_avg_10 = avg(submitted_marks("intro_supervisor"))
    discussion_sum_40_values = submitted_marks("intro_discussion_member")
    discussion_sum_40 = sum(discussion_sum_40_values) if discussion_sum_40_values else None

    # The coordinator is not the supervisor and should not be auto-assigned
    # a report/evaluation task. COMP4200 is calculated from the available
    # report + supervisor + discussion components (/90) and normalized to /100.
    final_score = None
    if report_avg_40 is not None and supervisor_avg_10 is not None and discussion_sum_40 is not None:
        raw_score_90 = report_avg_40 + supervisor_avg_10 + discussion_sum_40
        final_score = (raw_score_90 / 90.0) * 100.0

    return {
        "report_score": round(report_avg_40, 2) if report_avg_40 is not None else None,
        "supervisor_score": round(supervisor_avg_10, 2) if supervisor_avg_10 is not None else None,
        "coordinator_score": None,
        "discussion_score": round(discussion_sum_40, 2) if discussion_sum_40 is not None else None,
        "committee_score": None,
        "calculated_final_score": round(final_score, 2) if final_score is not None else None,
        "final_score": round(final_score, 2) if final_score is not None else None,
    }



def _evaluation_reference_supervisor(cursor, course_scope, reference_id):
    """Return the supervisor user/faculty for a section/project evaluation item."""
    if course_scope == "graduation_project":
        cursor.execute(
            """
            SELECT f.faculty_id, u.user_id, u.full_name
            FROM projects p
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE p.project_id = %s
              AND u.is_active = TRUE
            LIMIT 1
            """,
            (reference_id,),
        )
    else:
        cursor.execute(
            """
            SELECT f.faculty_id, u.user_id, u.full_name
            FROM student_distribution_sections sec
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE sec.section_id = %s
              AND u.is_active = TRUE
            LIMIT 1
            """,
            (reference_id,),
        )
    return cursor.fetchone()

def _evaluation_notify_faculty(cursor, course_scope, reference_id, title, message, sender_id):
    cursor.execute(
        """
        SELECT DISTINCT evaluator_faculty_id
        FROM evaluation_grade_tasks
        WHERE course_scope = %s AND reference_id = %s
        """,
        (course_scope, reference_id),
    )
    faculty_ids = [row["evaluator_faculty_id"] for row in cursor.fetchall()]
    user_map = _evaluation_faculty_user_ids(cursor, faculty_ids)
    sent = 0
    for user_id in user_map.values():
        if not user_id or user_id == sender_id:
            continue
        _insert_notification(cursor, user_id, sender_id, "system", title, message, None, course_scope)
        sent += 1
    return sent


def _evaluation_project_payload(cursor, course_scope, base_row):
    reference_id = base_row["project_id"]
    _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
    grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
    scores = _evaluation_scores_from_grades(course_scope, grades)

    cursor.execute(
        """
        SELECT is_open, opened_at, closed_at
        FROM evaluation_windows
        WHERE course_scope = %s AND reference_id = %s
        LIMIT 1
        """,
        (course_scope, reference_id),
    )
    window = cursor.fetchone() or {}

    submitted_count = sum(1 for grade in grades if grade.get("is_submitted"))
    required_count = max(_evaluation_default_required_count(course_scope), len(grades))

    payload = dict(base_row)
    payload.update(scores)
    payload.update(
        {
            "is_open": bool(window.get("is_open") or False),
            "opened_at": str(window.get("opened_at") or ""),
            "closed_at": str(window.get("closed_at") or ""),
            "grades": grades,
            "submitted_count": submitted_count,
            "required_count": required_count,
        }
    )
    return payload


@coordinator_bp.route("/api/evaluation/faculty", methods=["GET"])
@login_required(role="coordinator")
def api_evaluation_faculty_options():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.faculty_id,
                   u.full_name AS name,
                   u.full_name,
                   f.specialization
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
              AND u.is_active = TRUE
            ORDER BY u.full_name
        """)
        faculty_rows = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"faculty": _json_safe_value(faculty_rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/projects", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_evaluation_projects():
    try:
        course_scope = (request.args.get("course_scope") or "introduction").strip()
        if course_scope not in {"introduction", "graduation_project"}:
            return jsonify({"error": "Invalid course_scope."}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        semester = _get_active_semester(cursor)
        semester_id = semester["semester_id"] if semester else None

        projects = []
        if course_scope == "introduction":
            if _table_exists(cursor, "student_distribution_sections") and _table_exists(cursor, "section_students"):
                cursor.execute("""
                    SELECT sec.section_id AS project_id,
                           sec.section_name AS title,
                           'introduction' AS course_scope,
                           'COMP4200' AS course_code,
                           'section' AS status,
                           u_sup.full_name AS supervisor_name,
                           COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '), '') AS students
                    FROM student_distribution_sections sec
                    JOIN faculty f ON f.faculty_id = sec.supervisor_id
                    JOIN users u_sup ON u_sup.user_id = f.user_id
                    LEFT JOIN section_students ss ON ss.section_id = sec.section_id
                    LEFT JOIN students st ON st.student_id = ss.student_id
                    LEFT JOIN users u_st ON u_st.user_id = st.user_id
                    GROUP BY sec.section_id, sec.section_name, u_sup.full_name
                    HAVING COUNT(DISTINCT ss.student_id) > 0
                    ORDER BY sec.section_id DESC
                """)
                projects = cursor.fetchall()
        else:
            if not semester_id:
                cursor.close()
                db.close()
                return jsonify({"projects": []})
            cursor.execute("""
                SELECT p.project_id,
                       p.title,
                       'graduation_project' AS course_scope,
                       'COMP4300' AS course_code,
                       p.status,
                       u_sup.full_name AS supervisor_name,
                       COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students
                FROM projects p
                JOIN semesters s ON s.semester_id = p.semester_id
                JOIN project_members pm ON pm.project_id = p.project_id
                JOIN students st ON st.student_id = pm.student_id
                JOIN users u_st ON u_st.user_id = st.user_id
                LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
                LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
                WHERE p.semester_id = %s
                  AND COALESCE(s.course_code, 'COMP4300') = 'COMP4300'
                  AND p.status IN ('submitted','under_review','needs_revision','committee_evaluation','accepted','rejected','archived')
                  AND p.title NOT LIKE 'Committee Demo%%'
                GROUP BY p.project_id, p.title, p.status, u_sup.full_name
                ORDER BY FIELD(p.status,'committee_evaluation','submitted','under_review','needs_revision','accepted','archived','rejected'), p.project_id DESC
            """, (semester_id,))
            projects = cursor.fetchall()

        result = [_evaluation_project_payload(cursor, course_scope, row) for row in projects]
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"projects": _json_safe_value(result)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/open", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_open():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "").strip()
    reference_id = data.get("project_id") or data.get("reference_id")

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400
    if not reference_id:
        return jsonify({"error": "project_id/reference_id is required."}), 400

    try:
        reference_id = int(reference_id)
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        if course_scope == "graduation_project":
            cursor.execute("SELECT project_id, title FROM projects WHERE project_id = %s", (reference_id,))
            item = cursor.fetchone()
        else:
            cursor.execute("SELECT section_id AS project_id, section_name AS title FROM student_distribution_sections WHERE section_id = %s", (reference_id,))
            item = cursor.fetchone()
        if not item:
            cursor.close()
            db.close()
            return jsonify({"error": "Evaluation item not found."}), 404

        _evaluation_autocreate_tasks(cursor, course_scope, reference_id, session.get("user_id"))
        _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
        cursor.execute(
            """
            INSERT INTO evaluation_windows
                (course_scope, reference_id, is_open, opened_by, opened_at, closed_at)
            VALUES (%s, %s, TRUE, %s, NOW(), NULL)
            ON DUPLICATE KEY UPDATE
                is_open = TRUE,
                opened_by = VALUES(opened_by),
                opened_at = NOW(),
                closed_at = NULL
            """,
            (course_scope, reference_id, session.get("user_id")),
        )

        label = "COMP4200" if course_scope == "introduction" else "COMP4300"
        notifications_sent = _evaluation_notify_faculty(
            cursor,
            course_scope,
            reference_id,
            f"{label} Grade Entry Opened",
            f"Grade entry is now open for {item.get('title') or 'the assigned item'}. Please enter your mark.",
            session.get("user_id"),
        )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Grade entry opened successfully.", "notifications_sent": notifications_sent})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/assign", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_assign():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "").strip()
    reference_id = data.get("project_id") or data.get("reference_id")
    assignments = data.get("assignments") or []

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400
    if not reference_id:
        return jsonify({"error": "project_id/reference_id is required."}), 400
    if not assignments:
        return jsonify({"error": "No assignments provided."}), 400

    # Coordinator page is not allowed to manually assign report readers or committee members.
    # Readers/committee members must come from their own official screens/workflows.
    allowed_by_scope = {
        "introduction": {"intro_supervisor"},
        "graduation_project": {"grad_supervisor"},
    }

    try:
        reference_id = int(reference_id)
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        changed_faculty_ids = []
        for item in assignments:
            component = (item.get("component") or "").strip()
            faculty_id = item.get("faculty_id")
            if component not in allowed_by_scope[course_scope]:
                cursor.close()
                db.close()
                return jsonify({"error": f"Invalid component for this course: {component}"}), 400
            if not faculty_id:
                cursor.close()
                db.close()
                return jsonify({"error": "faculty_id is required for every assignment."}), 400
            faculty_id = int(faculty_id)
            _evaluation_insert_task(cursor, course_scope, reference_id, component, faculty_id, session.get("user_id"))
            changed_faculty_ids.append(faculty_id)

        label = "COMP4200" if course_scope == "introduction" else "COMP4300"
        user_map = _evaluation_faculty_user_ids(cursor, changed_faculty_ids)
        notifications_sent = 0
        for user_id in user_map.values():
            if not user_id or user_id == session.get("user_id"):
                continue
            _insert_notification(
                cursor,
                user_id,
                session.get("user_id"),
                "system",
                f"{label} Grade Task Assigned",
                "You have been assigned a grade entry task. Please open your evaluation page and submit the mark.",
                None,
                course_scope,
            )
            notifications_sent += 1

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Evaluator assignment saved successfully.", "notifications_sent": notifications_sent})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/close", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_close():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "").strip()
    reference_id = data.get("project_id") or data.get("reference_id")

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400
    if not reference_id:
        return jsonify({"error": "project_id/reference_id is required."}), 400

    try:
        reference_id = int(reference_id)
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        _evaluation_cleanup_tasks(cursor, course_scope, reference_id)

        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        scores = _evaluation_scores_from_grades(course_scope, grades)

        cursor.execute(
            """
            INSERT INTO evaluation_windows
                (course_scope, reference_id, is_open, opened_by, opened_at, closed_at)
            VALUES (%s, %s, FALSE, %s, NULL, NOW())
            ON DUPLICATE KEY UPDATE
                is_open = FALSE,
                closed_at = NOW()
            """,
            (course_scope, reference_id, session.get("user_id")),
        )

        if course_scope == "graduation_project" and scores.get("final_score") is not None and _db_column_exists(cursor, "projects", "final_score"):
            cursor.execute(
                "UPDATE projects SET final_score = %s WHERE project_id = %s",
                (scores["final_score"], reference_id),
            )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Grade entry closed and score calculated.", "scores": _json_safe_value(scores)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@coordinator_bp.route("/api/coordinator/evaluation/send-to-supervisor", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_send_to_supervisor():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "").strip()
    reference_id = data.get("project_id") or data.get("reference_id")
    notes = (data.get("notes") or "").strip()

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400
    if not reference_id:
        return jsonify({"error": "project_id/reference_id is required."}), 400

    try:
        reference_id = int(reference_id)
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        if course_scope == "graduation_project":
            cursor.execute("SELECT project_id AS reference_id, title FROM projects WHERE project_id = %s", (reference_id,))
            item = cursor.fetchone()
        else:
            cursor.execute("SELECT section_id AS reference_id, section_name AS title FROM student_distribution_sections WHERE section_id = %s", (reference_id,))
            item = cursor.fetchone()

        if not item:
            cursor.close()
            db.close()
            return jsonify({"error": "Evaluation item not found."}), 404

        supervisor = _evaluation_reference_supervisor(cursor, course_scope, reference_id)
        if not supervisor or not supervisor.get("user_id"):
            cursor.close()
            db.close()
            return jsonify({"error": "No active supervisor found for this item."}), 404

        _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        scores = _evaluation_scores_from_grades(course_scope, grades)
        final_score = scores.get("final_score")
        label = "COMP4200" if course_scope == "introduction" else "COMP4300"
        score_text = f" Final score: {final_score}/100." if final_score is not None else " Final score is not complete yet."
        notes_text = f" Coordinator notes: {notes}" if notes else ""

        _insert_notification(
            cursor,
            supervisor["user_id"],
            session.get("user_id"),
            "system",
            f"{label} Evaluation Result Ready for Supervisor Review",
            f"The coordinator sent the evaluation result for {item.get('title') or 'this item'} to you for review."
            f"{score_text} Please review it, then send it to the Head of Department for publishing."
            f"{notes_text}",
            reference_id if course_scope == "graduation_project" else None,
            course_scope,
        )

        # Keep the grade entry closed after sending to the supervisor.
        cursor.execute(
            """
            INSERT INTO evaluation_windows
                (course_scope, reference_id, is_open, opened_by, opened_at, closed_at)
            VALUES (%s, %s, FALSE, %s, NULL, NOW())
            ON DUPLICATE KEY UPDATE
                is_open = FALSE,
                closed_at = NOW()
            """,
            (course_scope, reference_id, session.get("user_id")),
        )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({
            "message": f"Result sent to supervisor: {supervisor.get('full_name') or 'Supervisor'}.",
            "notifications_sent": 1,
            "scores": _json_safe_value(scores),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/finalize", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_finalize():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "").strip()
    reference_id = data.get("project_id") or data.get("reference_id")
    decision = (data.get("decision") or "").strip()
    notes = (data.get("notes") or "").strip() or None

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400
    if not reference_id:
        return jsonify({"error": "project_id/reference_id is required."}), 400
    if decision not in {"accepted", "rejected", "archived"}:
        return jsonify({"error": "decision must be accepted, rejected, or archived."}), 400

    try:
        reference_id = int(reference_id)
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        scores = _evaluation_scores_from_grades(course_scope, grades)
        final_score = scores.get("final_score")

        if course_scope == "graduation_project":
            new_status = "archived" if decision == "archived" else decision
            if _db_column_exists(cursor, "projects", "final_score"):
                cursor.execute(
                    """
                    UPDATE projects
                    SET status = %s,
                        final_score = %s,
                        coordinator_notes = COALESCE(%s, coordinator_notes)
                    WHERE project_id = %s
                    """,
                    (new_status, final_score, notes, reference_id),
                )
            else:
                cursor.execute(
                    "UPDATE projects SET status = %s, coordinator_notes = COALESCE(%s, coordinator_notes) WHERE project_id = %s",
                    (new_status, notes, reference_id),
                )
        else:
            _ensure_section_results_schema(cursor)
            status_value = "succeeded" if decision in {"accepted", "archived"} else "not_succeeded"
            cursor.execute(
                """
                INSERT INTO section_completion_status
                    (course_scope, reference_id, status, notes, marked_by, marked_at)
                VALUES ('introduction', %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    notes = VALUES(notes),
                    marked_by = VALUES(marked_by),
                    marked_at = NOW(),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (reference_id, status_value, notes, session.get("user_id")),
            )

        cursor.execute(
            """
            INSERT INTO evaluation_windows
                (course_scope, reference_id, is_open, opened_by, opened_at, closed_at)
            VALUES (%s, %s, FALSE, %s, NULL, NOW())
            ON DUPLICATE KEY UPDATE
                is_open = FALSE,
                closed_at = NOW()
            """,
            (course_scope, reference_id, session.get("user_id")),
        )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Final evaluation saved successfully.", "scores": _json_safe_value(scores)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/profile", methods=["GET"])
@login_required(role="coordinator")
def coordinator_profile_api():
    user_id = session.get("user_id")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    try:
        has_office_number = _db_column_exists(cur, "faculty", "office_number")
        office_select = (
            "COALESCE(f.office_number, 'Science Building — 214') AS office_number"
            if has_office_number
            else "'Science Building — 214' AS office_number"
        )

        cur.execute(f"""
            SELECT
                u.user_id,
                u.full_name,
                u.email,
                u.avatar_initials,
                u.role,
                f.faculty_id,
                f.specialization,
                {office_select},
                COALESCE(s.course_code, 'COMP4200') AS course_code
            FROM users u
            LEFT JOIN faculty f ON f.user_id = u.user_id
            LEFT JOIN coordinator_assignments ca ON ca.faculty_id = f.faculty_id
            LEFT JOIN semesters s ON s.semester_id = ca.semester_id
            WHERE u.user_id = %s
            ORDER BY s.is_active DESC, ca.assigned_at DESC
            LIMIT 1
        """, (user_id,))

        profile = cur.fetchone()

        if not profile:
            return jsonify({"ok": False, "error": "Profile not found"}), 404

        cur.execute("""
            SELECT COUNT(*) AS total_projects
            FROM projects
        """)
        projects_overseen = cur.fetchone()["total_projects"] or 0

        cur.execute("""
            SELECT COUNT(*) AS accepted_projects
            FROM projects
            WHERE status IN ('accepted', 'archived')
        """)
        accepted_projects = cur.fetchone()["accepted_projects"] or 0

        cur.execute("""
            SELECT COUNT(*) AS committees_formed
            FROM committees
        """)
        committees_formed = cur.fetchone()["committees_formed"] or 0

        cur.execute("""
            SELECT ROUND(AVG(final_score), 1) AS average_score
            FROM projects
            WHERE final_score IS NOT NULL
        """)
        avg_row = cur.fetchone()
        average_score = (
            avg_row["average_score"]
            if avg_row and avg_row["average_score"] is not None
            else 0
        )

        acceptance_rate = 0
        if projects_overseen:
            acceptance_rate = round((accepted_projects / projects_overseen) * 100)

        return jsonify({
            "ok": True,
            "profile": _json_safe_value(profile),
            "stats": {
                "projects_overseen": int(projects_overseen),
                "acceptance_rate": int(acceptance_rate),
                "committees_formed": int(committees_formed),
                "average_score": float(average_score or 0)
            }
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    finally:
        cur.close()
        conn.close()


@coordinator_bp.route("/api/coordinator/profile", methods=["POST"])
@login_required(role="coordinator")
def coordinator_profile_update_api():
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip()
    office_number = (data.get("office_number") or "").strip()
    specialization = (data.get("specialization") or "").strip()

    if not full_name:
        return jsonify({"ok": False, "error": "Full name is required"}), 400

    if not email:
        return jsonify({"ok": False, "error": "Email is required"}), 400

    allowed_specs = {
        "software_engineering",
        "artificial_intelligence",
        "web_development",
        "mobile",
        "security_networks",
        "databases",
        "other"
    }

    if specialization not in allowed_specs:
        specialization = "software_engineering"

    initials = "".join([part[0].upper() for part in full_name.split()[:2] if part])[:5]

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    try:
        has_office_number = _db_column_exists(cur, "faculty", "office_number")

        cur.execute("""
            SELECT user_id
            FROM users
            WHERE email = %s AND user_id <> %s
            LIMIT 1
        """, (email, user_id))

        if cur.fetchone():
            return jsonify({"ok": False, "error": "This email is already used by another user"}), 400

        cur.execute("""
            UPDATE users
            SET full_name = %s,
                email = %s,
                avatar_initials = %s
            WHERE user_id = %s
        """, (full_name, email, initials, user_id))

        cur.execute("""
            SELECT faculty_id
            FROM faculty
            WHERE user_id = %s
            LIMIT 1
        """, (user_id,))

        faculty = cur.fetchone()

        if faculty:
            if has_office_number:
                cur.execute("""
                    UPDATE faculty
                    SET specialization = %s,
                        office_number = %s
                    WHERE user_id = %s
                """, (specialization, office_number, user_id))
            else:
                cur.execute("""
                    UPDATE faculty
                    SET specialization = %s
                    WHERE user_id = %s
                """, (specialization, user_id))

        conn.commit()

    except Exception as e:
        conn.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500

    finally:
        cur.close()
        conn.close()

    return jsonify({
        "ok": True,
        "message": "Profile updated successfully"
    })
