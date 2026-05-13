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

    fields = ["semester_id", "academic_year", "semester_number"]
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
    used_hours = project_students * 0.5
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
        "supervised_groups": project_groups,
        "supervised_students": project_students,
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
                    },
                    "by_status": by_status,
                    "by_type": by_type,
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
            due_date DATE NULL,
            mark_points DECIMAL(5,2) NOT NULL DEFAULT 0,
            status ENUM('not_open','open','in_progress','completed','closed') NOT NULL DEFAULT 'not_open',
            created_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_coord_deliverables_semester_scope (semester_id, course_scope),
            CONSTRAINT fk_coord_deliverables_semester
                FOREIGN KEY (semester_id) REFERENCES semesters(semester_id)
                ON DELETE SET NULL
        )
    """)


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

        semester = _get_active_semester(cursor)
        semester_id = semester["semester_id"] if semester else None

        result = {
            "semester": _date_to_iso(semester or {}),
            "lectures": {"introduction": [], "graduation_project": []},
            "deliverables": {"introduction": [], "graduation_project": []},
        }

        if semester_id:
            cursor.execute(
                """
                SELECT lecture_id, semester_id, course_scope, title, description,
                       lecture_date, week_label, status, created_at, updated_at
                FROM coordinator_lectures
                WHERE semester_id = %s
                ORDER BY course_scope, COALESCE(lecture_date, '9999-12-31'), lecture_id
            """,
                (semester_id,),
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
            result["lectures"].setdefault(row["course_scope"], []).append(row)

        if semester_id:
            cursor.execute(
                """
                SELECT deliverable_id, semester_id, course_scope, title, description,
                       due_date, mark_points, status, created_at, updated_at
                FROM coordinator_deliverables
                WHERE semester_id = %s
                ORDER BY course_scope, COALESCE(due_date, '9999-12-31'), deliverable_id
            """,
                (semester_id,),
            )
        else:
            cursor.execute("""
                SELECT deliverable_id, semester_id, course_scope, title, description,
                       due_date, mark_points, status, created_at, updated_at
                FROM coordinator_deliverables
                ORDER BY course_scope, COALESCE(due_date, '9999-12-31'), deliverable_id
            """)
        for row in cursor.fetchall():
            row = _date_to_iso(row)
            row["mark_points"] = float(row.get("mark_points") or 0)
            result["deliverables"].setdefault(row["course_scope"], []).append(row)

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
        semester = _get_active_semester(cursor)
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
        db.commit()
        lecture_id = cursor.lastrowid
        cursor.close()
        db.close()
        return jsonify(
            {"message": "Lecture saved successfully.", "lecture_id": lecture_id}
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
        semester = _get_active_semester(cursor)
        semester_id = semester["semester_id"] if semester else None

        cursor.execute(
            """
            INSERT INTO coordinator_deliverables
                (semester_id, course_scope, title, description, due_date, mark_points, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                semester_id,
                course_scope,
                title,
                data.get("description") or None,
                due_date,
                mark_points,
                status,
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
        request.content_type
        and request.content_type.startswith("multipart/form-data")
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

        filename = secure_filename(row.get("attachment_name") or "attachment") or "attachment"
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
@login_required(role="coordinator")
def api_coordinator_notifications_unread_count():
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
            due_date DATE NOT NULL,
            milestone_label VARCHAR(180) NULL,
            is_deadline BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (timeline_id) REFERENCES comp4200_timelines(timeline_id) ON DELETE CASCADE,
            INDEX idx_comp4200_timeline_items_due (due_date),
            INDEX idx_comp4200_timeline_items_order (timeline_id, item_order)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


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
        SELECT item_id, item_order, title, description, start_date, due_date, milestone_label, is_deadline
        FROM comp4200_timeline_items
        WHERE timeline_id = %s
        ORDER BY item_order ASC, due_date ASC, item_id ASC
        """,
        (timeline["timeline_id"],),
    )
    items = cursor.fetchall()
    for item in items:
        item["is_deadline"] = bool(item.get("is_deadline"))
    timeline["is_published"] = bool(timeline.get("is_published"))
    return {"timeline": timeline, "items": items}


@coordinator_bp.route("/api/coordinator/intro-timeline", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_intro_timeline_get():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)
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
        if not item_title or not due_date:
            return (
                jsonify({"error": f"Item #{index} must have a title and due date."}),
                400,
            )
        start_date = (item.get("start_date") or "").strip() or None
        description = (item.get("description") or "").strip() or None
        milestone_label = (item.get("milestone_label") or "").strip() or None
        try:
            if start_date:
                datetime.strptime(start_date, "%Y-%m-%d")
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
                "due_date": due_date,
                "milestone_label": milestone_label,
                "is_deadline": bool(item.get("is_deadline", True)),
            }
        )

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)
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
        cursor.execute(
            "DELETE FROM comp4200_timeline_items WHERE timeline_id = %s",
            (timeline["timeline_id"],),
        )
        for item in clean_items:
            cursor.execute(
                """
                INSERT INTO comp4200_timeline_items
                    (timeline_id, item_order, title, description, start_date, due_date, milestone_label, is_deadline)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    timeline["timeline_id"],
                    item["order"],
                    item["title"],
                    item["description"],
                    item["start_date"],
                    item["due_date"],
                    item["milestone_label"],
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
        semester = _get_active_semester(cursor)
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
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)

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
            semester = _get_active_semester(cursor)

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
    data = request.get_json(silent=True) or {}
    is_open = 1 if bool(data.get("is_open")) else 0
    close_at_raw = (data.get("close_at") or "").strip()

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester(cursor)

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
                            "error": "Please choose an automatic close date/time before opening registration."
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
            message = "Registration window opened successfully."

            if not was_open:
                cursor.execute("""
                    SELECT user_id
                    FROM users
                    WHERE role = 'student' AND is_active = TRUE
                    """)
                recipients = [
                    row["user_id"]
                    for row in cursor.fetchall()
                    if row.get("user_id") != session.get("user_id")
                ]
                close_text = close_at.strftime("%Y-%m-%d %H:%M")
                notif_message = (
                    "Project registration is now open. "
                    f"Please register your group before {close_text}."
                )
                for recipient_id in recipients:
                    _insert_notification(
                        cursor,
                        recipient_id,
                        session.get("user_id"),
                        "system",
                        "Project Registration Open",
                        notif_message,
                        None,
                        "graduation_project",
                    )
                notification_count = len(recipients)
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
            message = "Registration window closed successfully."

        db.commit()
        cursor.close()
        db.close()
        if notification_count:
            message = f"{message} {notification_count} student notification(s) sent."
        return jsonify({"message": message, "notifications_sent": notification_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─── Distribution Data ───────────────────────────────────────────────────
@coordinator_bp.route("/api/coordinator/distribution-data", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_distribution_data():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        cursor.execute(
            """
            SELECT
                   p.project_id,
                   CONCAT('Group ', p.project_id) AS group_name,
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
                   ) AS team_members
            FROM projects p
            LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
            LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
            LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
            LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
            LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
            LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
            LEFT JOIN faculty fsup ON fsup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = fsup.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
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
            WHERE NOT EXISTS (
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
            (semester["semester_id"],),
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
    supervisor_id = data.get("supervisor_id")
    student_ids = data.get("student_ids") or []

    if not section_name or not supervisor_id:
        return jsonify({"error": "section_name and supervisor_id are required."}), 400

    if len(student_ids) == 0:
        return jsonify({"error": "Please choose at least 1 student."}), 400

    if len(student_ids) > 3:
        return jsonify({"error": "A section can contain at most 3 students."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

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
        params = tuple(student_ids) + (semester["semester_id"],)
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

        grad_where = "WHERE p.semester_id = %s" if semester_id else ""
        grad_params = (semester_id,) if semester_id else ()
        cursor.execute(
            f"""
            SELECT p.project_id AS reference_id,
                   COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS section_name,
                   'graduation_project' AS course_scope,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT st.student_id) AS student_count,
                   p.status AS project_status,
                   COALESCE(scs.status, 'pending') AS result_status,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM projects p
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN section_completion_status scs
              ON scs.course_scope = 'graduation_project' AND scs.reference_id = p.project_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            {grad_where}
            GROUP BY p.project_id, p.title, p.status, u_sup.full_name,
                     scs.status, scs.notes, scs.marked_at, u_mark.full_name
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

    cursor.execute(
        """
        SELECT
               CONCAT('Group ', p.project_id) AS group_name,
               p.title,
               COALESCE(GROUP_CONCAT(DISTINCT u.full_name ORDER BY u.full_name SEPARATOR ', '), '') AS team_members,
               COALESCE(pref1.full_name, '') AS preferred_1,
               COALESCE(pref2.full_name, '') AS preferred_2,
               COALESCE(pref3.full_name, '') AS preferred_3,
               COALESCE(u_sup.full_name, '') AS final_supervisor,
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
        LEFT JOIN faculty fsup ON fsup.faculty_id = p.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = fsup.user_id
        WHERE p.semester_id = %s
        GROUP BY p.project_id, p.title, pref1.full_name, pref2.full_name, pref3.full_name, u_sup.full_name, p.status
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

        cursor.execute(
            """
            SELECT p.project_id, p.title, p.abstract, p.keywords, p.project_type,
                   p.status, p.coordinator_notes, p.rejection_reason, p.submission_date,
                   sup.full_name AS supervisor_name,
                   COALESCE(GROUP_CONCAT(DISTINCT stu.full_name ORDER BY pm.is_primary_contact DESC, stu.full_name SEPARATOR ', '), '') AS team_members,
                   COUNT(DISTINCT pf.file_id) AS files_count
            FROM projects p
            LEFT JOIN faculty sf ON sf.faculty_id = p.supervisor_id
            LEFT JOIN users sup ON sup.user_id = sf.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users stu ON stu.user_id = st.user_id
            LEFT JOIN project_files pf ON pf.project_id = p.project_id
            WHERE p.semester_id = %s
              AND p.status IN ('submitted','under_review','needs_revision','committee_evaluation','accepted','rejected')
            GROUP BY p.project_id, p.title, p.abstract, p.keywords, p.project_type, p.status,
                     p.coordinator_notes, p.rejection_reason, p.submission_date, sup.full_name
            ORDER BY FIELD(p.status,'submitted','under_review','needs_revision','committee_evaluation','accepted','rejected'), p.project_id DESC
            """,
            (semester["semester_id"],),
        )
        projects = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify(_json_safe_value({"projects": projects}))
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
        HAVING active_committee_count = 0
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


def _committee_fetch_eligible_projects(cursor, semester_id):
    cursor.execute(
        """
        SELECT
            p.project_id,
            p.title,
            p.status,
            p.project_type,
            COALESCE(
                GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                ''
            ) AS team_members
        FROM projects p
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE p.semester_id = %s
          AND p.status IN ('submitted', 'under_review', 'needs_revision', 'committee_evaluation')
          AND NOT EXISTS (
              SELECT 1
              FROM committee_plan_projects cpp
              JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
              WHERE cpp.project_id = p.project_id
                AND cp.status <> 'cancelled'
          )
        GROUP BY p.project_id, p.title, p.status, p.project_type
        ORDER BY p.project_id DESC
        """,
        (semester_id,),
    )
    projects = cursor.fetchall()
    random.shuffle(projects)
    return projects


def _committee_fetch_plan_rows(cursor):
    cursor.execute("""
        SELECT
            cp.plan_id,
            cp.committee_name,
            cp.discussion_date,
            TIME_FORMAT(cp.start_time, '%H:%i') AS start_time,
            TIME_FORMAT(cp.end_time, '%H:%i') AS end_time,
            cp.status,
            cp.responsible_faculty_id,
            dr.room_name,
            ru.full_name AS responsible_name,
            COUNT(DISTINCT cpp.project_id) AS projects_count
        FROM committee_plans cp
        LEFT JOIN discussion_rooms dr ON dr.room_id = cp.room_id
        LEFT JOIN faculty rf ON rf.faculty_id = cp.responsible_faculty_id
        LEFT JOIN users ru ON ru.user_id = rf.user_id
        LEFT JOIN committee_plan_projects cpp ON cpp.plan_id = cp.plan_id
        GROUP BY cp.plan_id, cp.committee_name, cp.discussion_date, cp.start_time, cp.end_time,
                 cp.status, cp.responsible_faculty_id, dr.room_name, ru.full_name
        ORDER BY cp.discussion_date DESC, cp.start_time ASC, cp.plan_id DESC
        """)
    return cursor.fetchall()


def _committee_fetch_members_for_plan(cursor, plan_id, responsible_faculty_id=None):
    cursor.execute(
        """
        SELECT
            cpm.faculty_id,
            u.full_name,
            f.specialization,
            COALESCE(f.years_experience, 0) AS years_experience
        FROM committee_plan_members cpm
        JOIN faculty f ON f.faculty_id = cpm.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE cpm.plan_id = %s
        ORDER BY u.full_name
        """,
        (plan_id,),
    )
    rows = cursor.fetchall()
    result = []
    for row in rows:
        role = (
            "responsible"
            if responsible_faculty_id
            and int(row["faculty_id"]) == int(responsible_faculty_id)
            else "member"
        )
        result.append(
            {
                "faculty_id": row["faculty_id"],
                "full_name": row["full_name"],
                "specialization": row["specialization"],
                "years_experience": row["years_experience"],
                "role": role,
            }
        )
    return result


def _committee_fetch_projects_for_plan(cursor, plan_id):
    cursor.execute(
        """
        SELECT
            cpp.slot_order,
            TIME_FORMAT(cpp.slot_start, '%H:%i') AS slot_start,
            TIME_FORMAT(cpp.slot_end, '%H:%i') AS slot_end,
            p.title,
            COALESCE(
                GROUP_CONCAT(DISTINCT u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
                ''
            ) AS team_members
        FROM committee_plan_projects cpp
        JOIN projects p ON p.project_id = cpp.project_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE cpp.plan_id = %s
        GROUP BY cpp.slot_order, cpp.slot_start, cpp.slot_end, p.project_id, p.title
        ORDER BY cpp.slot_order ASC
        """,
        (plan_id,),
    )
    return cursor.fetchall()


def _committee_dashboard_payload(cursor):
    active_semester = _get_active_semester(cursor)
    eligible_projects = (
        _committee_fetch_eligible_projects(cursor, active_semester["semester_id"])
        if active_semester
        else []
    )

    plan_rows = _committee_fetch_plan_rows(cursor)
    plans = []
    for row in plan_rows:
        plans.append(
            {
                "plan_id": row["plan_id"],
                "committee_name": row["committee_name"],
                "discussion_date": str(row["discussion_date"]),
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "room_name": row["room_name"] or "—",
                "status": row["status"],
                "responsible_faculty_id": row["responsible_faculty_id"],
                "responsible_name": row["responsible_name"],
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
            "discussion_date": p["discussion_date"],
            "start_time": p["start_time"],
            "room_name": p["room_name"],
            "status": p["status"],
            "projects_count": p["projects_count"],
            "responsible_name": p["responsible_name"],
        }
        for p in plans
    ]

    return {
        "eligible_projects": eligible_projects,
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


def _committee_delete_active_plans(cursor):
    cursor.execute("""
        SELECT DISTINCT cpp.project_id
        FROM committee_plan_projects cpp
        JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
        """)
    project_ids = [row["project_id"] for row in cursor.fetchall()]

    cursor.execute("""
        DELETE cpm
        FROM committee_plan_members cpm
        JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
        """)
    cursor.execute("""
        DELETE cpp
        FROM committee_plan_projects cpp
        JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
        WHERE cp.status IN ('scheduled', 'in_progress')
        """)
    cursor.execute("""
        DELETE FROM committee_plans
        WHERE status IN ('scheduled', 'in_progress')
        """)

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
):
    active_semester = _get_active_semester(cursor)
    if not active_semester:
        raise ValueError("No active semester found.")

    if clear_existing:
        _committee_delete_active_plans(cursor)

    _committee_seed_rooms(cursor)

    eligible_projects = _committee_fetch_eligible_projects(
        cursor, active_semester["semester_id"]
    )
    if not eligible_projects:
        raise ValueError("No eligible projects available for committee generation.")

    faculty_groups = _committee_fetch_faculty_pool(cursor)
    if len([s for s, members in faculty_groups.items() if members]) < 4:
        raise ValueError(
            "At least 4 different available doctor majors are required to generate committees."
        )

    cursor.execute("""
        SELECT room_id, room_name
        FROM discussion_rooms
        WHERE is_active = 1
        ORDER BY sort_order ASC, room_name ASC
        """)
    rooms = cursor.fetchall()
    committee_count = math.ceil(len(eligible_projects) / projects_per_committee)

    available_doctors_count = sum(len(members) for members in faculty_groups.values())
    if available_doctors_count < committee_count * 4:
        raise ValueError(
            f"Not enough available doctors. Required doctors: {committee_count * 4}, "
            f"available doctors: {available_doctors_count}. "
            f"A doctor cannot be assigned to more than one active committee."
        )

    if len(rooms) < committee_count:
        raise ValueError(
            f"Not enough rooms. Required rooms: {committee_count}, available rooms: {len(rooms)}."
        )

    used_faculty_ids = set()

    for idx in range(committee_count):
        chunk = eligible_projects[
            idx * projects_per_committee : (idx + 1) * projects_per_committee
        ]
        if not chunk:
            continue

        members = _committee_pick_members(faculty_groups, used_faculty_ids, idx)
        room = rooms[idx]
        committee_name = f"Committee {idx + 1}"
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
                    (committee_name, academic_year, discussion_date, start_time, end_time, room_id, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    committee_name,
                    active_semester["academic_year"],
                    discussion_date,
                    start_time,
                    last_slot_end,
                    room["room_id"],
                    "scheduled",
                    session.get("user_id"),
                ),
            )
        else:
            insert_cursor.execute(
                """
                INSERT INTO committee_plans
                    (committee_name, discussion_date, start_time, end_time, room_id, status, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    committee_name,
                    discussion_date,
                    start_time,
                    last_slot_end,
                    room["room_id"],
                    "scheduled",
                    session.get("user_id"),
                ),
            )
        plan_id = insert_cursor.lastrowid

        for member in members:
            insert_cursor.execute(
                """
                INSERT INTO committee_plan_members (plan_id, faculty_id, role)
                VALUES (%s, %s, 'member')
                """,
                (plan_id, member["faculty_id"]),
            )

        for slot_index, project in enumerate(chunk, start=1):
            slot_start = _committee_time_add(start_time, (slot_index - 1) * 40)
            slot_end = _committee_time_add(slot_start, 30)
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

        insert_cursor.close()

    payload = _committee_dashboard_payload(cursor)
    return {
        "message": (
            "Committees were generated successfully. Projects were selected automatically and distributed randomly across committees."
            if not clear_existing
            else "Committees were reset and redistributed successfully."
        ),
        "plans": _json_safe_rows(payload["plans"]),
        "eligible_projects": _json_safe_rows(payload["eligible_projects"]),
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


@coordinator_bp.route("/api/coordinator/committee-generate", methods=["POST"])
@login_required(role="coordinator")
def api_committee_generate():
    data = request.get_json(silent=True) or {}
    discussion_date = (data.get("discussion_date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    projects_per_committee = int(data.get("projects_per_committee") or 0)

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
    discussion_date = (data.get("discussion_date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    projects_per_committee = int(data.get("projects_per_committee") or 0)

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
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT 1
            FROM committee_plan_members
            WHERE plan_id = %s AND faculty_id = %s
            LIMIT 1
            """,
            (plan_id, faculty_id),
        )
        exists = cursor.fetchone()
        if not exists:
            cursor.close()
            db.close()
            return (
                jsonify(
                    {"error": "The selected doctor is not a member of this committee."}
                ),
                400,
            )

        update_cursor = db.cursor()
        update_cursor.execute(
            "UPDATE committee_plans SET responsible_faculty_id = %s WHERE plan_id = %s",
            (faculty_id, plan_id),
        )
        update_cursor.execute(
            "UPDATE committee_plan_members SET role = 'member' WHERE plan_id = %s",
            (plan_id,),
        )
        update_cursor.execute(
            "UPDATE committee_plan_members SET role = 'responsible' WHERE plan_id = %s AND faculty_id = %s",
            (plan_id, faculty_id),
        )
        db.commit()
        update_cursor.close()

        payload = _committee_dashboard_payload(cursor)
        cursor.close()
        db.close()

        return jsonify(
            {
                "message": "Responsible doctor saved successfully.",
                "plans": _json_safe_rows(payload["plans"]),
                "current_committees": _json_safe_rows(payload["current_committees"]),
                "stats": _json_safe_value(payload["stats"]),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500