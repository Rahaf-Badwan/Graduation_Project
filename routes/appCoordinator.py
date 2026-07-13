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
import os
import random
import re
import zipfile
import bcrypt
from collections import defaultdict
from datetime import datetime, timedelta

from werkzeug.utils import secure_filename

from db import get_db
from auth import login_required
from ai_engine import search_uploaded_semantic
from routes.project_cleanup import clear_supervisor_project_workspace
from semester_lifecycle import auto_rollover_semesters

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


def _parse_client_datetime(value):
    """Parse datetime-local and ISO-8601 values into server-local naive time."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Missing date/time")

    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Invalid date/time format") from exc

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


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


def _get_active_semester_for_committee_scope(cursor, course_scope):
    course_code = "COMP4200" if course_scope == "introduction" else "COMP4300"
    semester = _get_active_semester_by_course(cursor, course_code)
    if semester:
        return semester
    return _get_active_semester(cursor)


def _get_active_semester_by_course(cursor, course_code):
    try:
        auto_rollover_semesters(cursor)
    except Exception:
        pass

    # Keep this helper safe even before running the migration.
    has_distribution_open = _db_column_exists(cursor, "semesters", "distribution_open")
    has_opened_at = _db_column_exists(cursor, "semesters", "distribution_opened_at")
    has_closed_at = _db_column_exists(cursor, "semesters", "distribution_closed_at")
    has_close_at = _db_column_exists(cursor, "semesters", "distribution_close_at")
    has_course_code = _db_column_exists(cursor, "semesters", "course_code")
    has_start_date = _db_column_exists(cursor, "semesters", "start_date")
    has_end_date = _db_column_exists(cursor, "semesters", "end_date")

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
    semester_order = (
        "start_date DESC, semester_id DESC" if has_start_date else "semester_id DESC"
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
        ORDER BY {semester_order}
        LIMIT 1
        """, tuple(params))
    semester = cursor.fetchone()
    if semester:
        return semester

    if has_course_code and has_start_date and has_end_date:
        cursor.execute(f"""
            SELECT {', '.join(fields)}
            FROM semesters
            WHERE course_code = %s
              AND (start_date IS NULL OR start_date <= CURDATE())
              AND (end_date IS NULL OR end_date >= CURDATE())
            ORDER BY {semester_order}
            LIMIT 1
            """, (course_code,))
        semester = cursor.fetchone()
        if semester:
            return semester

    if has_course_code:
        cursor.execute(f"""
            SELECT {', '.join(fields)}
            FROM semesters
            WHERE course_code = %s
            ORDER BY {semester_order}
            LIMIT 1
            """, (course_code,))
        return cursor.fetchone()

    return None


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


def _faculty_supervised_group_counts(cursor, faculty_id):
    counts = {
        "project_groups": 0,
        "section_groups": 0,
        "total_groups": 0,
    }

    if not faculty_id:
        return counts

    if _table_exists(cursor, "projects"):
        if _table_exists(cursor, "project_members"):
            cursor.execute(
                """
                SELECT COUNT(DISTINCT p.project_id) AS cnt
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.project_id
                WHERE p.supervisor_id = %s
                """,
                (faculty_id,),
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM projects
                WHERE supervisor_id = %s
                """,
                (faculty_id,),
            )
        row = cursor.fetchone() or {}
        counts["project_groups"] = int(row.get("cnt") or 0)

    if _table_exists(cursor, "student_distribution_sections"):
        if _table_exists(cursor, "section_students"):
            cursor.execute(
                """
                SELECT COUNT(DISTINCT sec.section_id) AS cnt
                FROM student_distribution_sections sec
                JOIN section_students ss ON ss.section_id = sec.section_id
                WHERE sec.supervisor_id = %s
                """,
                (faculty_id,),
            )
        else:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM student_distribution_sections
                WHERE supervisor_id = %s
                """,
                (faculty_id,),
            )
        row = cursor.fetchone() or {}
        counts["section_groups"] = int(row.get("cnt") or 0)

    if _table_exists(cursor, "committee_plan_members") and _table_exists(cursor, "committee_plans"):
        cursor.execute(
            """
            SELECT COUNT(DISTINCT cpm.plan_id) AS cnt
            FROM committee_plan_members cpm
            JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
            WHERE cpm.faculty_id = %s
              AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
            """,
            (faculty_id,),
        )
        row = cursor.fetchone() or {}
        committee_plans = int(row.get("cnt") or 0)
        if committee_plans > 0:
            counts["project_groups"] += committee_plans
            counts["section_groups"] += committee_plans

    counts["total_groups"] = counts["project_groups"] + counts["section_groups"]
    return counts


def _coordinator_supervisor_access(cursor, user_id):
    cursor.execute(
        """
        SELECT f.faculty_id, u.full_name
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE f.user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )
    faculty = cursor.fetchone()
    if not faculty:
        return {
            "faculty": None,
            "counts": _faculty_supervised_group_counts(cursor, None),
            "can_switch": False,
        }

    counts = _faculty_supervised_group_counts(cursor, faculty.get("faculty_id"))
    return {
        "faculty": faculty,
        "counts": counts,
        "can_switch": counts["total_groups"] > 0,
    }


def _ensure_faculty_load_submission_columns(cursor):
    if not _table_exists(cursor, "faculty_load_settings"):
        return
    required_columns = {
        "introduction_hours_submitted": (
            "ALTER TABLE faculty_load_settings "
            "ADD COLUMN introduction_hours_submitted TINYINT(1) NOT NULL DEFAULT 0"
        ),
        "graduation_hours_submitted": (
            "ALTER TABLE faculty_load_settings "
            "ADD COLUMN graduation_hours_submitted TINYINT(1) NOT NULL DEFAULT 0"
        ),
    }
    for column, ddl in required_columns.items():
        if not _db_column_exists(cursor, "faculty_load_settings", column):
            cursor.execute(ddl)


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
    try:
        notification_type = _safe_notification_type(cursor, notification_type)
        has_course_scope = _db_column_exists(cursor, "notifications", "course_scope")
        has_can_reply = _db_column_exists(cursor, "notifications", "can_reply")

        if has_course_scope and has_can_reply:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read, can_reply)
                VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, FALSE)
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
        elif has_course_scope:
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
        elif has_can_reply:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     related_project_id, is_read, can_reply)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE, FALSE)
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
    except Exception:
        return False

    return True


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
        recipients = set()

        if _table_exists(cursor, "student_course_results"):
            cursor.execute(
                """
                SELECT DISTINCT u.user_id
                FROM student_course_results scr
                JOIN students st ON st.student_id = scr.student_id
                JOIN users u ON u.user_id = st.user_id
                WHERE scr.status = 'passed'
                  AND scr.promoted_to_semester_id = %s
                  AND u.role = 'student'
                  AND u.is_active = TRUE
                """,
                (semester_id,),
            )
            recipients.update(row["user_id"] for row in cursor.fetchall())

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
        recipients.update(row["user_id"] for row in cursor.fetchall())
        return sorted(recipients)

    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM student_course_results scr
        JOIN students st ON st.student_id = scr.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE scr.semester_id = %s
          AND NOT (
              scr.status = 'passed'
              AND (
                  scr.promoted_to_semester_id IS NOT NULL
                  OR scr.promoted_at IS NOT NULL
              )
          )
          AND u.role = 'student'
          AND u.is_active = TRUE
        """,
        (semester_id,),
    )
    recipients = [row["user_id"] for row in cursor.fetchall()]
    if recipients:
        return recipients

    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM users u
        JOIN students st ON st.user_id = u.user_id
        WHERE u.role = 'student'
          AND u.is_active = TRUE
          AND NOT EXISTS (
              SELECT 1
              FROM student_course_results scr
              WHERE scr.student_id = st.student_id
                AND scr.status = 'passed'
                AND (
                    scr.promoted_to_semester_id IS NOT NULL
                    OR scr.promoted_at IS NOT NULL
                )
          )
        """
    )
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


def _faculty_load_snapshot(
    cursor,
    faculty_id,
    academic_year,
    anchor_semester_id=None,
    course_code="COMP4300",
):
    if anchor_semester_id is None:
        anchor = _get_anchor_semester_for_year(cursor, academic_year)
        anchor_semester_id = anchor["semester_id"] if anchor else None

    _ensure_faculty_load_submission_columns(cursor)

    course_code = course_code if course_code in {"COMP4200", "COMP4300"} else "COMP4300"
    requested_column = (
        "introduction_project_hours"
        if course_code == "COMP4200"
        else "graduation_project_hours"
    )
    submitted_column = (
        "introduction_hours_submitted"
        if course_code == "COMP4200"
        else "graduation_hours_submitted"
    )
    has_requested_column = _db_column_exists(
        cursor, "faculty_load_settings", requested_column
    )
    has_submitted_column = _db_column_exists(
        cursor, "faculty_load_settings", submitted_column
    )
    settings_semester_id = anchor_semester_id
    if academic_year:
        cursor.execute(
            """
            SELECT semester_id
            FROM semesters
            WHERE academic_year = %s
              AND course_code = %s
            ORDER BY semester_number DESC, semester_id DESC
            LIMIT 1
            """,
            (academic_year, course_code),
        )
        settings_semester = cursor.fetchone()
        if settings_semester:
            settings_semester_id = settings_semester["semester_id"]

    wanted_hours = 0.0

    if settings_semester_id and _table_exists(cursor, "faculty_load_settings"):
        select_field = (
            f"COALESCE({requested_column}, 0) AS requested_hours"
            if has_requested_column
            else "0 AS requested_hours"
        )
        submitted_field = (
            f"COALESCE({submitted_column}, 0) AS hours_submitted"
            if has_submitted_column
            else "0 AS hours_submitted"
        )
        cursor.execute(
            f"""
            SELECT {select_field}, {submitted_field}
            FROM faculty_load_settings
            WHERE faculty_id = %s AND semester_id = %s
            LIMIT 1
            """,
            (faculty_id, settings_semester_id),
        )
        row = cursor.fetchone()
        if row:
            wanted_hours = float(row.get("requested_hours") or 0)
            hours_submitted = bool(row.get("hours_submitted"))
        else:
            hours_submitted = False
    else:
        hours_submitted = False

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
          AND s.course_code = %s
        """,
        (faculty_id, academic_year, course_code),
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

    if course_code == "COMP4200":
        effective_intro_students = intro_students if intro_sections else project_students
        effective_intro_groups = intro_sections if intro_sections else project_groups
        graduation_used_hours = 0.0
        introduction_used_hours = effective_intro_students * 0.5
        supervised_groups = effective_intro_groups
        supervised_students = effective_intro_students
    else:
        graduation_used_hours = project_students * 0.5
        introduction_used_hours = 0.0
        supervised_groups = project_groups
        supervised_students = project_students

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
        "introduction_project_hours": wanted_hours,
        "wanted_hours": wanted_hours,
        "hours_submitted": hours_submitted,
        "course_code": course_code,
        "project_groups": project_groups,
        "project_students": project_students,
        "intro_sections": intro_sections,
        "intro_students": intro_students,
        "supervised_groups": supervised_groups,
        "supervised_students": supervised_students,
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

    active_semester = _get_active_comp4200_semester(cursor)
    academic_year = active_semester["academic_year"] if active_semester else None
    anchor_semester_id = active_semester["semester_id"] if active_semester else None

    cursor.execute("""
        SELECT f.faculty_id, u.full_name, u.role
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
                cursor,
                row["faculty_id"],
                academic_year,
                anchor_semester_id,
                "COMP4200",
            )
            if academic_year
            else {
                "supervised_groups": 0,
                "wanted_hours": 0.0,
                "hours_submitted": False,
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
                "role": row.get("role") or "supervisor",
                "is_load_exempt": row.get("role") in {"coordinator", "head_of_department"},
                "assigned_projects": snapshot["supervised_groups"],
                "wanted_hours": snapshot["wanted_hours"],
                "hours_submitted": snapshot["hours_submitted"],
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
def _faculty_assignment_role(cursor, faculty_id):
    cursor.execute(
        """
        SELECT u.role
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE f.faculty_id = %s
        LIMIT 1
        """,
        (faculty_id,),
    )
    row = cursor.fetchone() or {}
    return row.get("role") or "supervisor"


def _faculty_load_exempt_for_assignment(cursor, faculty_id):
    return _faculty_assignment_role(cursor, faculty_id) in {
        "coordinator",
        "head_of_department",
    }


COORDINATOR_PAGES = {
    "dashboard": "coordinator/index.html",
    "registration": "coordinator/registration.html",
    "hours": "coordinator/hours.html",
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
    """Dashboard counters for the coordinator.

    Counts are based on the active academic term and the real COMP4200/COMP4300
    groups only. Groups already marked as succeeded are hidden from coordinator
    active counters because they were sent to Head approval.
    """
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)
        db.commit()

        semester = _get_active_semester(cursor)
        if not semester:
            cursor.execute(
                f"""
                SELECT s.semester_id, s.academic_year, s.semester_number, s.course_code,
                       COALESCE(s.distribution_open, 0) AS distribution_open,
                       s.distribution_opened_at,
                       s.distribution_closed_at,
                       s.distribution_close_at
                FROM projects p
                JOIN semesters s ON s.semester_id = p.semester_id
                WHERE {_ci('s.course_code')} IN ({_lit('COMP4200')}, {_lit('COMP4300')})
                  AND EXISTS (
                        SELECT 1
                        FROM project_members pmx
                        WHERE pmx.project_id = p.project_id
                  )
                  AND {_ci('p.status')} IN (
                        {_lit('submitted')}, {_lit('under_review')},
                        {_lit('needs_revision')}, {_lit('committee_evaluation')}
                  )
                  AND {_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}
                  AND {_COORDINATOR_PROJECT_NOT_SUCCEEDED_SQL}
                ORDER BY s.start_date DESC, s.semester_id DESC
                LIMIT 1
                """
            )
            semester = cursor.fetchone()
        academic_year = semester.get("academic_year") if semester else None
        semester_number = semester.get("semester_number") if semester else None

        base_where_parts = [
            f"{_ci('s.course_code')} IN ({_lit('COMP4200')}, {_lit('COMP4300')})",
            "EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)",
            f"{_ci('p.status')} <> {_lit('solo_pending')}",
            f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}",
            _COORDINATOR_PROJECT_NOT_SUCCEEDED_SQL,
        ]
        base_params = []
        if academic_year:
            base_where_parts.append("CONVERT(s.academic_year USING utf8mb4) COLLATE utf8mb4_unicode_ci = CONVERT(%s USING utf8mb4) COLLATE utf8mb4_unicode_ci")
            base_params.append(academic_year)
        if semester_number:
            base_where_parts.append("s.semester_number = %s")
            base_params.append(semester_number)

        where = "WHERE " + " AND ".join(base_where_parts)
        params = tuple(base_params)

        cursor.execute(
            f"""
            SELECT
                COUNT(DISTINCT CASE
                    WHEN {_ci('p.status')} IN (
                        {_lit('submitted')}, {_lit('under_review')},
                        {_lit('needs_revision')}, {_lit('committee_evaluation')}
                    )
                    THEN p.project_id
                END) AS total_projects,
                COUNT(DISTINCT CASE
                    WHEN {_ci('p.status')} IN (
                        {_lit('submitted')}, {_lit('under_review')},
                        {_lit('needs_revision')}, {_lit('committee_evaluation')},
                        {_lit('accepted')}
                    )
                    THEN p.project_id
                END) AS visible_groups,
                COUNT(DISTINCT CASE
                    WHEN {_ci('p.status')} IN (
                        {_lit('submitted')}, {_lit('under_review')},
                        {_lit('needs_revision')}, {_lit('committee_evaluation')},
                        {_lit('accepted')}, {_lit('archived')}, {_lit('rejected')}
                    )
                    THEN p.project_id
                END) AS workflow_total,
                SUM(CASE WHEN {_ci('p.status')} IN ({_lit('submitted')}, {_lit('under_review')}, {_lit('needs_revision')}) THEN 1 ELSE 0 END) AS awaiting_review,
                SUM(CASE WHEN {_ci('p.status')} = {_lit('committee_evaluation')} THEN 1 ELSE 0 END) AS under_evaluation,
                SUM(CASE WHEN {_ci('p.status')} IN ({_lit('accepted')}, {_lit('archived')}) THEN 1 ELSE 0 END) AS accepted,
                SUM(CASE WHEN {_ci('p.status')} = {_lit('rejected')} THEN 1 ELSE 0 END) AS rejected
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            {where}
            """,
            params,
        )
        stats = cursor.fetchone() or {}

        cursor.execute(
            f"""
            SELECT p.status, COUNT(DISTINCT p.project_id) AS count
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            {where}
            GROUP BY p.status
            ORDER BY count DESC
            """,
            params,
        )
        by_status = cursor.fetchall()

        cursor.execute(
            f"""
            SELECT p.project_type, COUNT(DISTINCT p.project_id) AS count
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
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
                   COALESCE(GROUP_CONCAT(stu.full_name ORDER BY pm.is_primary_contact DESC, stu.full_name SEPARATOR ', '), '') AS team_members
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
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

        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT pm.student_id) AS active_students
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            {where}
            """,
            params,
        )
        students_row = cursor.fetchone() or {}

        sections_count = int(stats.get("visible_groups") or 0)

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
            "web": int(archive_type_row.get("web") or 0),
            "mobile": int(archive_type_row.get("mobile") or 0),
            "ai": int(archive_type_row.get("ai") or 0),
            "software_engineering": int(archive_type_row.get("software_engineering") or 0),
            "security": int(archive_type_row.get("security") or 0),
            "databases": int(archive_type_row.get("databases") or 0),
            "other": int(archive_type_row.get("other") or 0),
            "_total": int(archive_type_row.get("total_archived") or 0),
        }

        cursor.close()
        db.close()

        return jsonify(
            _json_safe_value(
                {
                    "semester": semester or {},
                    "distribution_open": _active_distribution_is_open(semester),
                    "stats": {
                        "active_projects": int(stats.get("total_projects") or 0),
                        "total_projects": int(stats.get("visible_groups") or 0),
                        "visible_groups": int(stats.get("visible_groups") or 0),
                        "workflow_total": int(stats.get("workflow_total") or 0),
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
            lecture_time TIME NULL,
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
    if not _db_column_exists(cursor, "coordinator_lectures", "lecture_time"):
        cursor.execute(
            "ALTER TABLE coordinator_lectures ADD COLUMN lecture_time TIME NULL AFTER lecture_date"
        )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coordinator_lecture_recipients (
            lecture_id INT NOT NULL,
            student_id INT NOT NULL,
            notified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lecture_id, student_id),
            FOREIGN KEY (lecture_id) REFERENCES coordinator_lectures(lecture_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coordinator_lecture_attendance (
            lecture_id INT NOT NULL,
            student_id INT NOT NULL,
            attendance_status ENUM('present','absent') NOT NULL,
            marked_by INT NULL,
            marked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lecture_id, student_id),
            FOREIGN KEY (lecture_id) REFERENCES coordinator_lectures(lecture_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            FOREIGN KEY (marked_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
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
        if key == "lecture_time" and value is not None:
            row[key] = str(value)[:5]
        elif hasattr(value, "isoformat"):
            row[key] = value.isoformat()
        elif isinstance(value, float):
            row[key] = round(value, 2)
    return row


def _required_coordinator_lecture_schedule(data):
    lecture_date = (data.get("lecture_date") or "").strip()
    lecture_time = (data.get("lecture_time") or "").strip()
    if not lecture_date:
        raise ValueError("Lecture date is required before sending the lecture.")
    if not lecture_time:
        raise ValueError("Lecture time is required before sending the lecture.")
    try:
        parsed_date = datetime.strptime(lecture_date, "%Y-%m-%d").date()
        parsed_time = datetime.strptime(lecture_time, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("Lecture date or time is invalid.") from exc
    if datetime.combine(parsed_date, parsed_time) <= datetime.now():
        raise ValueError("Lecture date and time must be in the future.")
    return lecture_date, lecture_time


def _student_user_ids_by_student_id(cursor, student_ids):
    if not student_ids:
        return {}
    placeholders = ",".join(["%s"] * len(student_ids))
    cursor.execute(
        f"""
        SELECT st.student_id, u.user_id
        FROM students st
        JOIN users u ON u.user_id = st.user_id
        WHERE st.student_id IN ({placeholders})
          AND u.role = 'student'
          AND u.is_active = TRUE
        """,
        tuple(student_ids),
    )
    return {int(row["student_id"]): int(row["user_id"]) for row in cursor.fetchall()}


def _notify_coordinator_absences(cursor, lecture, newly_absent_student_ids):
    user_ids = _student_user_ids_by_student_id(cursor, newly_absent_student_ids)
    if not user_ids:
        return 0

    lecture_time = str(lecture.get("lecture_time") or "")[:5] or "the scheduled time"
    message = (
        f"You have an absence recorded for \"{lecture.get('title') or 'Lecture'}\" "
        f"on {lecture.get('lecture_date') or 'the scheduled date'} at {lecture_time}. "
        "Please contact the course coordinator if this is incorrect."
    )
    sent = 0
    for recipient_id in user_ids.values():
        _insert_notification(
            cursor,
            recipient_id,
            session.get("user_id"),
            "urgent_alert",
            "You have an absence",
            message,
            None,
            lecture.get("course_scope") or "both",
        )
        sent += 1
    return sent


def _snapshot_coordinator_lecture_recipients(cursor, lecture_id, user_ids):
    cursor.execute(
        "DELETE FROM coordinator_lecture_recipients WHERE lecture_id = %s",
        (lecture_id,),
    )
    if user_ids:
        placeholders = ",".join(["%s"] * len(user_ids))
        cursor.execute(
            f"""
            INSERT IGNORE INTO coordinator_lecture_recipients (lecture_id, student_id)
            SELECT %s, st.student_id
            FROM students st
            WHERE st.user_id IN ({placeholders})
            """,
            (lecture_id, *user_ids),
        )
    cursor.execute(
        """
        DELETE cla
        FROM coordinator_lecture_attendance cla
        LEFT JOIN coordinator_lecture_recipients clr
          ON clr.lecture_id = cla.lecture_id AND clr.student_id = cla.student_id
        WHERE cla.lecture_id = %s AND clr.student_id IS NULL
        """,
        (lecture_id,),
    )


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
                       lecture_date, lecture_time, week_label, status, created_at, updated_at
                FROM coordinator_lectures
                WHERE semester_id IN ({placeholders})
                ORDER BY course_scope, COALESCE(lecture_date, '9999-12-31'), lecture_id
                """,
                tuple(semester_ids),
            )
        else:
            cursor.execute("""
                SELECT lecture_id, semester_id, course_scope, title, description,
                       lecture_date, lecture_time, week_label, status, created_at, updated_at
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
        try:
            lecture_date, lecture_time = _required_coordinator_lecture_schedule(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        semester = _semester_for_course_scope(cursor, course_scope)
        semester_id = semester["semester_id"] if semester else None

        cursor.execute(
            """
            INSERT INTO coordinator_lectures
                (semester_id, course_scope, title, description, lecture_date, lecture_time, week_label, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
            (
                semester_id,
                course_scope,
                title,
                data.get("description") or None,
                lecture_date,
                lecture_time,
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
            _snapshot_coordinator_lecture_recipients(cursor, lecture_id, recipients)
            scope_label = "Project Introduction" if course_scope == "introduction" else "Graduation Project"
            details = (data.get("description") or "").strip()
            message = "\n".join((
                f"Lecture: {title}",
                f"Course: {scope_label}",
                f"Date: {lecture_date}",
                f"Time: {lecture_time}",
                f"Week: {(data.get('week_label') or '').strip() or 'Not specified'}",
                f"Status: {status.replace('_', ' ').title()}",
                f"Details: {details or 'No additional details.'}",
            ))

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
        try:
            lecture_date, lecture_time = _required_coordinator_lecture_schedule(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        cursor.execute(
            """
            SELECT lecture_id, semester_id, course_scope, title, lecture_date, lecture_time
            FROM coordinator_lectures
            WHERE lecture_id = %s
            """,
            (lecture_id,),
        )
        lecture = cursor.fetchone()
        if not lecture:
            cursor.close()
            db.close()
            return jsonify({"error": "Lecture not found."}), 404

        old_lecture_date = lecture.get("lecture_date")
        old_lecture_time = lecture.get("lecture_time")
        cursor.execute(
            """
            UPDATE coordinator_lectures
            SET lecture_date = %s,
                lecture_time = %s,
                status = 'scheduled'
            WHERE lecture_id = %s
            """,
            (lecture_date, lecture_time, lecture_id),
        )

        sent_count = 0
        if (
            lecture.get("semester_id")
            and lecture_date
            and (
                str(old_lecture_date or "") != str(lecture_date)
                or str(old_lecture_time or "")[:5] != str(lecture_time)
            )
        ):
            recipients = sorted(
                set(
                    _deliverable_student_user_ids(
                        cursor,
                        lecture.get("semester_id"),
                        lecture.get("course_scope") or "introduction",
                    )
                )
            )
            cursor.execute(
                "SELECT COUNT(*) AS total FROM coordinator_lecture_recipients WHERE lecture_id = %s",
                (lecture_id,),
            )
            if int((cursor.fetchone() or {}).get("total") or 0) == 0:
                _snapshot_coordinator_lecture_recipients(cursor, lecture_id, recipients)
            course_scope = lecture.get("course_scope") or "introduction"
            scope_label = (
                "Project Introduction"
                if course_scope == "introduction"
                else "Graduation Project"
            )
            message = "\n".join((
                f"Lecture: {lecture.get('title')}",
                f"Course: {scope_label}",
                f"Date: {lecture_date}",
                f"Time: {lecture_time}",
                "Status: Scheduled",
                "Details: The lecture date and time were confirmed by the course coordinator.",
            ))
            for recipient_id in recipients:
                _insert_notification(
                    cursor,
                    recipient_id,
                    session.get("user_id"),
                    "system",
                    f'Lecture Date Confirmed: {lecture.get("title")}',
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
                "message": f"Lecture date and time updated. {sent_count} student notification(s) sent.",
                "notifications_sent": sent_count,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/lectures/<int:lecture_id>", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_update_lecture(lecture_id):
    try:
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Lecture title is required."}), 400

        status = (
            data.get("status")
            if data.get("status") in ("scheduled", "completed", "cancelled")
            else "scheduled"
        )
        description = (data.get("description") or "").strip() or None
        try:
            lecture_date, lecture_time = _required_coordinator_lecture_schedule(data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        week_label = (data.get("week_label") or "").strip() or None

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)
        cursor.execute(
            """
            SELECT lecture_id, semester_id, course_scope, title, description,
                   lecture_date, lecture_time, week_label, status
            FROM coordinator_lectures
            WHERE lecture_id = %s
            """,
            (lecture_id,),
        )
        lecture = cursor.fetchone()
        if not lecture:
            cursor.close()
            db.close()
            return jsonify({"error": "Lecture not found."}), 404

        changed = any(
            (
                str(lecture.get("title") or "") != title,
                str(lecture.get("description") or "") != str(description or ""),
                str(lecture.get("lecture_date") or "") != str(lecture_date or ""),
                str(lecture.get("lecture_time") or "")[:5] != str(lecture_time),
                str(lecture.get("week_label") or "") != str(week_label or ""),
                str(lecture.get("status") or "") != status,
            )
        )

        cursor.execute(
            """
            UPDATE coordinator_lectures
            SET title = %s,
                description = %s,
                lecture_date = %s,
                lecture_time = %s,
                week_label = %s,
                status = %s
            WHERE lecture_id = %s
            """,
            (title, description, lecture_date, lecture_time, week_label, status, lecture_id),
        )

        sent_count = 0
        if changed and lecture.get("semester_id"):
            course_scope = lecture.get("course_scope") or "introduction"
            recipients = sorted(
                set(
                    _deliverable_student_user_ids(
                        cursor, lecture.get("semester_id"), course_scope
                    )
                )
            )
            _snapshot_coordinator_lecture_recipients(cursor, lecture_id, recipients)
            scope_label = (
                "Project Introduction"
                if course_scope == "introduction"
                else "Graduation Project"
            )
            message = "\n".join((
                f"Lecture: {title}",
                f"Course: {scope_label}",
                f"Date: {lecture_date}",
                f"Time: {lecture_time}",
                f"Week: {week_label or 'Not specified'}",
                f"Status: {status.replace('_', ' ').title()}",
                f"Details: {description or 'No additional details.'}",
            ))
            for recipient_id in recipients:
                _insert_notification(
                    cursor,
                    recipient_id,
                    session.get("user_id"),
                    "system",
                    f"Lecture Updated: {title}",
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
                "message": (
                    f"Lecture updated successfully. {sent_count} student notification(s) sent."
                    if changed
                    else "No lecture changes to save."
                ),
                "notifications_sent": sent_count,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _coordinator_attendance_lecture(cursor, lecture_id):
    cursor.execute(
        """
        SELECT lecture_id, semester_id, course_scope, title, lecture_date, lecture_time,
               CASE
                   WHEN lecture_time IS NULL THEN lecture_date < CURDATE()
                   ELSE TIMESTAMP(lecture_date, lecture_time) <= NOW()
               END AS has_started
        FROM coordinator_lectures
        WHERE lecture_id = %s
        LIMIT 1
        """,
        (lecture_id,),
    )
    return cursor.fetchone()


def _ensure_coordinator_lecture_recipient_snapshot(cursor, lecture):
    cursor.execute(
        "SELECT COUNT(*) AS total FROM coordinator_lecture_recipients WHERE lecture_id = %s",
        (lecture["lecture_id"],),
    )
    if int((cursor.fetchone() or {}).get("total") or 0) > 0:
        return
    recipients = _deliverable_student_user_ids(
        cursor,
        lecture.get("semester_id"),
        lecture.get("course_scope") or "introduction",
    )
    _snapshot_coordinator_lecture_recipients(
        cursor, lecture["lecture_id"], sorted(set(recipients))
    )


@coordinator_bp.route("/api/coordinator/lectures/<int:lecture_id>/attendance", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_lecture_attendance(lecture_id):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        _ensure_lecture_tables(cursor)
        lecture = _coordinator_attendance_lecture(cursor, lecture_id)
        if not lecture:
            return jsonify({"error": "Lecture not found."}), 404
        if not lecture.get("has_started"):
            return jsonify({"error": "Attendance opens after the lecture date and time."}), 400
        _ensure_coordinator_lecture_recipient_snapshot(cursor, lecture)
        cursor.execute(
            """
            SELECT st.student_id, u.full_name, u.university_id,
                   cla.attendance_status
            FROM coordinator_lecture_recipients clr
            JOIN students st ON st.student_id = clr.student_id
            JOIN users u ON u.user_id = st.user_id
            LEFT JOIN coordinator_lecture_attendance cla
              ON cla.lecture_id = clr.lecture_id
             AND cla.student_id = clr.student_id
            WHERE clr.lecture_id = %s
            ORDER BY u.full_name
            """,
            (lecture_id,),
        )
        students = cursor.fetchall()
        db.commit()
        return jsonify({"lecture_id": lecture_id, "title": lecture["title"], "students": students})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); db.close()


@coordinator_bp.route("/api/coordinator/lectures/<int:lecture_id>/attendance", methods=["POST"])
@login_required(role="coordinator")
def api_save_coordinator_lecture_attendance(lecture_id):
    data = request.get_json(silent=True) or {}
    attendance = data.get("attendance") or []
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        _ensure_lecture_tables(cursor)
        lecture = _coordinator_attendance_lecture(cursor, lecture_id)
        if not lecture:
            return jsonify({"error": "Lecture not found."}), 404
        if not lecture.get("has_started"):
            return jsonify({"error": "Attendance opens after the lecture date and time."}), 400
        _ensure_coordinator_lecture_recipient_snapshot(cursor, lecture)
        cursor.execute(
            "SELECT student_id FROM coordinator_lecture_recipients WHERE lecture_id = %s",
            (lecture_id,),
        )
        allowed_ids = {int(row["student_id"]) for row in cursor.fetchall()}
        if allowed_ids:
            placeholders = ",".join(["%s"] * len(allowed_ids))
            cursor.execute(
                f"""
                SELECT student_id, attendance_status
                FROM coordinator_lecture_attendance
                WHERE lecture_id = %s
                  AND student_id IN ({placeholders})
                """,
                (lecture_id, *sorted(allowed_ids)),
            )
            previous_status = {
                int(row["student_id"]): (row.get("attendance_status") or "").lower()
                for row in cursor.fetchall()
            }
        else:
            previous_status = {}
        cleaned = []
        for row in attendance:
            try:
                student_id = int(row.get("student_id"))
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid student in attendance list."}), 400
            status = (row.get("status") or "").strip().lower()
            if student_id not in allowed_ids or status not in {"present", "absent"}:
                return jsonify({"error": "Attendance can only be recorded for notified students."}), 400
            cleaned.append((student_id, status))
        if allowed_ids and {student_id for student_id, _ in cleaned} != allowed_ids:
            return jsonify({"error": "Mark every notified student as present or absent."}), 400
        for student_id, status in cleaned:
            cursor.execute(
                """
                INSERT INTO coordinator_lecture_attendance
                    (lecture_id, student_id, attendance_status, marked_by, marked_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    attendance_status = VALUES(attendance_status),
                    marked_by = VALUES(marked_by),
                    marked_at = NOW()
                """,
                (lecture_id, student_id, status, session.get("user_id")),
            )
        notified = _notify_coordinator_absences(
            cursor,
            lecture,
            [
                student_id
                for student_id, status in cleaned
                if status == "absent" and previous_status.get(student_id) != "absent"
            ],
        )
        db.commit()
        return jsonify({"message": f"Attendance saved for {len(cleaned)} student(s). Absence notifications sent: {notified}."})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close(); db.close()



@coordinator_bp.route("/api/coordinator/lectures/reset-scheduled", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_reset_scheduled_lectures():
    """Delete scheduled lectures for one course without touching completed/cancelled lectures."""
    try:
        data = request.get_json(silent=True) or {}
        course_scope = (
            data.get("course_scope")
            if data.get("course_scope") in ("introduction", "graduation_project")
            else "introduction"
        )

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_lecture_tables(cursor)

        semester = _semester_for_course_scope(cursor, course_scope)
        params = [course_scope]
        semester_filter = ""
        if semester:
            semester_filter = " AND semester_id = %s"
            params.append(semester["semester_id"])

        cursor.execute(
            f"""
            DELETE FROM coordinator_lectures
            WHERE course_scope = %s
              AND status = 'scheduled'
              {semester_filter}
            """,
            tuple(params),
        )
        deleted_count = cursor.rowcount

        db.commit()
        cursor.close()
        db.close()

        course_label = "COMP4200" if course_scope == "introduction" else "COMP4300"
        return jsonify(
            {
                "message": f"Restart done. Deleted {deleted_count} scheduled lecture(s) for {course_label}.",
                "deleted_count": deleted_count,
            }
        )
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
            SELECT deliverable_id, published_at
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
        was_published = bool((existing or {}).get("published_at"))
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
            notification_title = (
                "COMP4300 Final Submission Republished"
                if was_published
                else "COMP4300 Final Submission Published"
            )
            msg = (
                (
                    f"COMP4300 final submission was republished: {title}. "
                    if was_published
                    else f"COMP4300 final submission is now open: {title}. "
                )
                + f"Starts: {start_at.strftime('%Y-%m-%d %H:%M')}. "
                f"Deadline: {due_at.strftime('%Y-%m-%d %H:%M')}. "
                "Open it from your student timeline."
            )
            for recipient_id in recipients:
                _insert_notification(
                    cursor,
                    recipient_id,
                    session.get("user_id"),
                    "deadline_reminder",
                    notification_title,
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


def _ensure_milestone_storage_columns(cursor):
    if not _table_exists(cursor, "milestone_submissions"):
        return
    try:
        cursor.execute(
            "ALTER TABLE milestone_submissions MODIFY COLUMN file_data LONGBLOB NULL"
        )
    except Exception:
        pass
    if not _db_column_exists(cursor, "milestone_submissions", "file_path"):
        cursor.execute(
            "ALTER TABLE milestone_submissions ADD COLUMN file_path VARCHAR(600) NULL"
        )



def _ci(expr):
    return f"CONVERT({expr} USING utf8mb4) COLLATE utf8mb4_unicode_ci"


def _lit(value):
    return f"'{value}' COLLATE utf8mb4_unicode_ci"


_COORDINATOR_PROJECT_SUBMISSION_CLOSED_SQL = f"""
    (
        EXISTS (
            SELECT 1
            FROM deadlines d
            WHERE d.semester_id = s.semester_id
              AND {_ci("d.deadline_type")} = {_lit("file_submission")}
              AND (d.project_id IS NULL OR d.project_id = p.project_id)
              AND d.deadline_date < CURDATE()
        )
        OR (
            {_ci("s.course_code")} = {_lit("COMP4300")}
            AND EXISTS (
                SELECT 1
                FROM coordinator_deliverables cd_final
                WHERE cd_final.semester_id = s.semester_id
                  AND {_ci("cd_final.course_scope")} = {_lit("graduation_project")}
                  AND {_ci("cd_final.title")} = {_lit("Graduation Project Final Submission")}
                  AND cd_final.is_published = TRUE
                  AND cd_final.due_at < NOW()
            )
        )
    )
"""


_COORDINATOR_MILESTONE_SUBMISSION_CLOSED_SQL = """
    ti.due_date IS NOT NULL
    AND TIMESTAMP(
        ti.due_date,
        COALESCE(NULLIF(TRIM(ti.due_time), ''), '23:59:59')
    ) < NOW()
"""


_COORDINATOR_DELIVERABLE_SUBMISSION_CLOSED_SQL = """
    COALESCE(cd.due_at, TIMESTAMP(cd.due_date, '23:59:59')) IS NOT NULL
    AND COALESCE(cd.due_at, TIMESTAMP(cd.due_date, '23:59:59')) < NOW()
"""


_COORDINATOR_PROJECT_NOT_SUCCEEDED_SQL = f"""
    NOT EXISTS (
        SELECT 1
        FROM section_completion_status scs_hide
        WHERE scs_hide.reference_id = p.project_id
          AND {_ci("scs_hide.status")} = {_lit("succeeded")}
          AND (
              (
                  {_ci("s.course_code")} = {_lit("COMP4300")}
                  AND {_ci("scs_hide.course_scope")} = {_lit("graduation_project")}
              )
              OR
              (
                  {_ci("s.course_code")} = {_lit("COMP4200")}
                  AND {_ci("scs_hide.course_scope")} = {_lit("introduction")}
              )
          )
    )
"""

_COORDINATOR_MILESTONE_PROJECT_NOT_SUCCEEDED_SQL = f"""
    (
        ms.project_id IS NULL
        OR NOT EXISTS (
            SELECT 1
            FROM section_completion_status scs_hide
            WHERE scs_hide.reference_id = ms.project_id
              AND {_ci("scs_hide.status")} = {_lit("succeeded")}
              AND {_ci("scs_hide.course_scope")} = {_lit("introduction")}
        )
    )
"""

_COORDINATOR_DELIVERABLE_PROJECT_NOT_SUCCEEDED_SQL = f"""
    (
        cds.project_id IS NULL
        OR NOT EXISTS (
            SELECT 1
            FROM section_completion_status scs_hide
            WHERE scs_hide.reference_id = cds.project_id
              AND {_ci("scs_hide.status")} = {_lit("succeeded")}
              AND {_ci("scs_hide.course_scope")} = {_ci("cd.course_scope")}
        )
    )
"""


@coordinator_bp.route("/api/coordinator/submission-files", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_submission_files():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)
        db.commit()
        semester = _get_active_semester(cursor)
        academic_year = semester.get("academic_year") if semester else None

        files = []

        if _table_exists(cursor, "project_files"):
            params = []
            where = """
                WHERE COALESCE(CONVERT(pf.upload_status USING utf8mb4) COLLATE utf8mb4_unicode_ci, 'uploaded' COLLATE utf8mb4_unicode_ci) = 'uploaded' COLLATE utf8mb4_unicode_ci
                  AND """ + _COORDINATOR_PROJECT_SUBMISSION_CLOSED_SQL + """
                  AND """ + _COORDINATOR_PROJECT_NOT_SUCCEEDED_SQL
            if academic_year:
                where += " AND CONVERT(s.academic_year USING utf8mb4) COLLATE utf8mb4_unicode_ci = CONVERT(%s USING utf8mb4) COLLATE utf8mb4_unicode_ci"
                params.append(academic_year)

            cursor.execute(
                f"""
                SELECT pf.file_id, pf.project_id, pf.file_type, pf.file_name,
                       pf.file_path, pf.file_size_mb, pf.uploaded_at,
                       pf.file_data IS NOT NULL AS has_file_data,
                       p.title AS project_title, p.project_type,
                       s.course_code,
                       COALESCE(
                           (
                               SELECT cd.title
                               FROM coordinator_deliverables cd
                               WHERE cd.semester_id = s.semester_id
                                 AND CONVERT(cd.course_scope USING utf8mb4) COLLATE utf8mb4_unicode_ci = 'graduation_project' COLLATE utf8mb4_unicode_ci
                                 AND CONVERT(cd.title USING utf8mb4) COLLATE utf8mb4_unicode_ci = 'Graduation Project Final Submission' COLLATE utf8mb4_unicode_ci
                                 AND cd.is_published = TRUE
                               ORDER BY cd.deliverable_id DESC
                               LIMIT 1
                           ),
                           'Project File Submission'
                       ) AS submission_title,
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
                         p.title, p.project_type, s.semester_id, s.course_code
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
                        "submission_title": row.get("submission_title")
                        or "Project File Submission",
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
            duplicate_project_report_filter = ""
            if _table_exists(cursor, "project_files"):
                duplicate_project_report_filter = """
                     AND NOT (
                         EXISTS (
                             SELECT 1
                             FROM project_files pf_dup
                             WHERE pf_dup.project_id = ms.project_id
                               AND pf_dup.file_type = 'final_report'
                               AND (
                                     COALESCE(pf_dup.upload_status, 'uploaded') = 'uploaded'
                                     OR pf_dup.uploaded_at IS NOT NULL
                                     OR pf_dup.file_data IS NOT NULL
                                     OR COALESCE(pf_dup.file_path, '') <> ''
                                   )
                         )
                         AND (
                               LOWER(COALESCE(ms.file_name, '')) LIKE '%%final%%'
                               OR LOWER(COALESCE(ti.milestone_label, ti.title, '')) LIKE '%%final%%'
                               OR LOWER(COALESCE(ti.milestone_label, ti.title, '')) LIKE '%%graduation%%'
                             )
                     )
                """
            where = (
                """WHERE CONVERT(ms.submitted_to USING utf8mb4) COLLATE utf8mb4_unicode_ci IN ('coordinator' COLLATE utf8mb4_unicode_ci, 'both' COLLATE utf8mb4_unicode_ci)
                     AND """
                + _COORDINATOR_MILESTONE_SUBMISSION_CLOSED_SQL
                + duplicate_project_report_filter
                + """
                     AND """
                + _COORDINATOR_MILESTONE_PROJECT_NOT_SUCCEEDED_SQL
            )
            if academic_year:
                where += " AND CONVERT(s.academic_year USING utf8mb4) COLLATE utf8mb4_unicode_ci = CONVERT(%s USING utf8mb4) COLLATE utf8mb4_unicode_ci"
                params.append(academic_year)

            cursor.execute(
                f"""
                SELECT ms.submission_id, ms.item_id, ms.project_id, ms.file_name,
                       ms.file_path, ms.file_size_mb, ms.submitted_to, ms.submitted_at,
                       ti.due_date,
                       ti.title AS milestone_title,
                       ti.milestone_label,
                       p.title AS project_title,
                       u.full_name AS submitted_by,
                       sup_u.full_name AS supervisor_name,
                       (
                           SELECT GROUP_CONCAT(
                               tm_u.full_name
                               ORDER BY tm_pm.is_primary_contact DESC, tm_u.full_name
                               SEPARATOR ', '
                           )
                           FROM project_members tm_pm
                           JOIN students tm_st ON tm_st.student_id = tm_pm.student_id
                           JOIN users tm_u ON tm_u.user_id = tm_st.user_id
                           WHERE tm_pm.project_id = ms.project_id
                       ) AS team_members,
                       ms.file_data IS NOT NULL AS has_file_data
                FROM milestone_submissions ms
                JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
                JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
                JOIN semesters s ON s.semester_id = tl.semester_id
                JOIN students st ON st.student_id = ms.student_id
                JOIN users u ON u.user_id = st.user_id
                LEFT JOIN projects p ON p.project_id = ms.project_id
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
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
                        "supervisor_name": row.get("supervisor_name") or "",
                        "team_members": row.get("team_members") or "",
                        "submitted_by": row.get("submitted_by") or "Unknown student",
                        "file_name": row.get("file_name") or "Open file",
                        "file_path": row.get("file_path") or "",
                        "file_size_mb": float(row.get("file_size_mb") or 0),
                        "uploaded_at": _format_submission_datetime(uploaded_at),
                        "sort_at": uploaded_at,
                        "submitted_to": row.get("submitted_to") or "supervisor",
                        "download_url": (
                            f"/api/coordinator/milestone-submissions/{row.get('submission_id')}/download"
                            if row.get("has_file_data") or row.get("file_path")
                            else ""
                        ),
                    }
                )

        if _table_exists(cursor, "coordinator_deliverable_submissions"):
            params = []
            where = (
                "WHERE "
                + _COORDINATOR_DELIVERABLE_SUBMISSION_CLOSED_SQL
                + " AND "
                + _COORDINATOR_DELIVERABLE_PROJECT_NOT_SUCCEEDED_SQL
            )
            if academic_year:
                where += " AND CONVERT(s.academic_year USING utf8mb4) COLLATE utf8mb4_unicode_ci = CONVERT(%s USING utf8mb4) COLLATE utf8mb4_unicode_ci"
                params.append(academic_year)

            cursor.execute(
                f"""
                SELECT cds.submission_id, cds.project_id, cds.file_name, cds.file_path,
                       cds.file_size_mb, cds.submitted_at,
                       cds.file_data IS NOT NULL AS has_file_data,
                       cd.title AS deliverable_title,
                       cd.course_scope,
                       p.title AS project_title,
                       u.full_name AS submitted_by,
                       sup_u.full_name AS supervisor_name,
                       (
                           SELECT GROUP_CONCAT(
                               tm_u.full_name
                               ORDER BY tm_pm.is_primary_contact DESC, tm_u.full_name
                               SEPARATOR ', '
                           )
                           FROM project_members tm_pm
                           JOIN students tm_st ON tm_st.student_id = tm_pm.student_id
                           JOIN users tm_u ON tm_u.user_id = tm_st.user_id
                           WHERE tm_pm.project_id = cds.project_id
                       ) AS team_members
                FROM coordinator_deliverable_submissions cds
                JOIN coordinator_deliverables cd
                  ON cd.deliverable_id = cds.deliverable_id
                LEFT JOIN semesters s ON s.semester_id = cd.semester_id
                JOIN students st ON st.student_id = cds.student_id
                JOIN users u ON u.user_id = st.user_id
                LEFT JOIN projects p ON p.project_id = cds.project_id
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
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
                        "supervisor_name": row.get("supervisor_name") or "",
                        "team_members": row.get("team_members") or "",
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
        _ensure_section_results_schema(cursor)
        db.commit()

        cursor.execute(
            f"""
            SELECT pf.file_name, pf.file_path, pf.file_data, pf.file_mime
            FROM project_files pf
            JOIN projects p ON p.project_id = pf.project_id
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE pf.file_id = %s
              AND COALESCE(CONVERT(pf.upload_status USING utf8mb4) COLLATE utf8mb4_unicode_ci, 'uploaded' COLLATE utf8mb4_unicode_ci) = 'uploaded' COLLATE utf8mb4_unicode_ci
              AND {_COORDINATOR_PROJECT_SUBMISSION_CLOSED_SQL}
              AND {_COORDINATOR_PROJECT_NOT_SUCCEEDED_SQL}
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


@coordinator_bp.route("/api/coordinator/projects/<int:project_id>/files/download-all")
@login_required(role="coordinator")
def api_coordinator_download_project_files(project_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)
        db.commit()
        cursor.execute(
            f"""
            SELECT p.title AS project_title, pf.file_id, pf.file_name, pf.file_data
            FROM project_files pf
            JOIN projects p ON p.project_id = pf.project_id
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE pf.project_id = %s
              AND COALESCE(CONVERT(pf.upload_status USING utf8mb4) COLLATE utf8mb4_unicode_ci, 'uploaded' COLLATE utf8mb4_unicode_ci) = 'uploaded' COLLATE utf8mb4_unicode_ci
              AND pf.file_data IS NOT NULL
              AND {_COORDINATOR_PROJECT_SUBMISSION_CLOSED_SQL}
              AND {_COORDINATOR_PROJECT_NOT_SUCCEEDED_SQL}
            ORDER BY pf.file_type, pf.file_id
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        if not rows:
            return jsonify({"error": "No downloadable files found for this project."}), 404

        archive = io.BytesIO()
        used_names = set()
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for row in rows:
                original_name = secure_filename(row.get("file_name") or "")
                file_name = original_name or f"project_file_{row['file_id']}"
                if file_name in used_names:
                    stem, extension = os.path.splitext(file_name)
                    file_name = f"{stem}_{row['file_id']}{extension}"
                used_names.add(file_name)
                zip_file.writestr(file_name, bytes(row["file_data"]))

        archive.seek(0)
        project_name = secure_filename(rows[0].get("project_title") or "")
        archive_name = f"{project_name or f'project_{project_id}'}_files.zip"
        return Response(
            archive.getvalue(),
            mimetype="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{archive_name}"'},
        )
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
        _ensure_section_results_schema(cursor)
        db.commit()
        cursor.execute(
            f"""
            SELECT ms.file_name, ms.file_path, ms.file_data, ms.file_mime
            FROM milestone_submissions ms
            JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
            WHERE ms.submission_id = %s
              AND CONVERT(ms.submitted_to USING utf8mb4) COLLATE utf8mb4_unicode_ci IN ('coordinator' COLLATE utf8mb4_unicode_ci, 'both' COLLATE utf8mb4_unicode_ci)
              AND {_COORDINATOR_MILESTONE_SUBMISSION_CLOSED_SQL}
              AND NOT EXISTS (
                  SELECT 1
                  FROM section_completion_status scs_hide
                  WHERE scs_hide.reference_id = ms.project_id
                    AND CONVERT(scs_hide.status USING utf8mb4) COLLATE utf8mb4_unicode_ci = 'succeeded' COLLATE utf8mb4_unicode_ci
                    AND CONVERT(scs_hide.course_scope USING utf8mb4) COLLATE utf8mb4_unicode_ci = 'introduction' COLLATE utf8mb4_unicode_ci
              )
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
                    "Content-Disposition": f'attachment; filename="{row.get("file_name") or "timeline-submission"}"'
                },
            )
        if row.get("file_path"):
            return _download_static_path(row.get("file_path"))
        return jsonify({"error": "File content not found."}), 404
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
        _ensure_section_results_schema(cursor)
        db.commit()
        cursor.execute(
            f"""
            SELECT cds.file_name, cds.file_path, cds.file_data, cds.file_mime
            FROM coordinator_deliverable_submissions cds
            JOIN coordinator_deliverables cd
              ON cd.deliverable_id = cds.deliverable_id
            WHERE cds.submission_id = %s
              AND {_COORDINATOR_DELIVERABLE_SUBMISSION_CLOSED_SQL}
              AND NOT EXISTS (
                  SELECT 1
                  FROM section_completion_status scs_hide
                  WHERE scs_hide.reference_id = cds.project_id
                    AND CONVERT(scs_hide.status USING utf8mb4) COLLATE utf8mb4_unicode_ci = 'succeeded' COLLATE utf8mb4_unicode_ci
                    AND CONVERT(scs_hide.course_scope USING utf8mb4) COLLATE utf8mb4_unicode_ci = CONVERT(cd.course_scope USING utf8mb4) COLLATE utf8mb4_unicode_ci
              )
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
    """Add notification messaging columns when the database has not been migrated yet."""
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
    if not _db_column_exists(cursor, "notifications", "can_reply"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN can_reply TINYINT(1) NOT NULL DEFAULT 0 AFTER is_read"
        )
    if not _db_column_exists(cursor, "notifications", "message_origin"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN message_origin ENUM('dynamic','manual','reply') NOT NULL DEFAULT 'dynamic' AFTER can_reply"
        )


def _notification_attachment_select_fields(cursor):
    """Return safe SELECT fields for attachment metadata and reply policy."""
    attachment_fields = "NULL AS attachment_name, NULL AS attachment_mime, 0 AS has_attachment"
    if _db_column_exists(cursor, "notifications", "attachment_name"):
        attachment_fields = "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"

    reply_field = "0 AS can_reply"
    if _db_column_exists(cursor, "notifications", "can_reply"):
        reply_field = (
            "CASE WHEN n.message_origin IN ('manual', 'reply') "
            "THEN COALESCE(n.can_reply, 0) ELSE 0 END AS can_reply"
        )

    return f"{attachment_fields}, {reply_field}"


def _notification_row_to_json(row):
    """Convert MySQL notification rows to safe JSON values."""
    if not row:
        return row
    clean = dict(row)
    if clean.get("created_at") is not None:
        clean["created_at"] = str(clean["created_at"])
    clean["is_read"] = bool(clean.get("is_read"))
    clean["can_reply"] = bool(clean.get("can_reply", 0))
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


def _student_user_rows_by_course(cursor, course_code):
    """
    Return active student rows for a course.
    COMP4300 is detected mainly from real graduation projects/project_members.
    COMP4200 is detected from student_course_results or sections.
    """
    course_code = (course_code or "").strip().upper()
    rows_by_user = {}

    def add_rows(rows):
        for row in rows:
            user_id = row.get("user_id")
            if user_id and user_id not in rows_by_user:
                rows_by_user[user_id] = row

    # Source 1: students that are members of projects in the selected course semester.
    if _table_exists(cursor, "projects") and _table_exists(cursor, "project_members"):
        has_course_code = _db_column_exists(cursor, "semesters", "course_code")
        if has_course_code:
            cursor.execute(
                """
                SELECT DISTINCT st.student_id, u.user_id, u.full_name, u.university_id,
                       %s AS course_code
                FROM projects p
                JOIN semesters s ON s.semester_id = p.semester_id
                JOIN project_members pm ON pm.project_id = p.project_id
                JOIN students st ON st.student_id = pm.student_id
                JOIN users u ON u.user_id = st.user_id
                WHERE s.course_code = %s
                  AND u.role = 'student'
                  AND u.is_active = TRUE
                ORDER BY u.full_name
                """,
                (course_code, course_code),
            )
            add_rows(cursor.fetchall())

    # Source 2: student_course_results for databases that track enrollment/promotion there.
    if _table_exists(cursor, "student_course_results"):
        if _db_column_exists(cursor, "student_course_results", "course_code"):
            cursor.execute(
                """
                SELECT DISTINCT st.student_id, u.user_id, u.full_name, u.university_id,
                       %s AS course_code
                FROM student_course_results scr
                JOIN students st ON st.student_id = scr.student_id
                JOIN users u ON u.user_id = st.user_id
                WHERE scr.course_code = %s
                  AND u.role = 'student'
                  AND u.is_active = TRUE
                ORDER BY u.full_name
                """,
                (course_code, course_code),
            )
            add_rows(cursor.fetchall())
        elif _db_column_exists(cursor, "student_course_results", "semester_id"):
            cursor.execute(
                """
                SELECT DISTINCT st.student_id, u.user_id, u.full_name, u.university_id,
                       %s AS course_code
                FROM student_course_results scr
                JOIN semesters s ON s.semester_id = scr.semester_id
                JOIN students st ON st.student_id = scr.student_id
                JOIN users u ON u.user_id = st.user_id
                WHERE s.course_code = %s
                  AND u.role = 'student'
                  AND u.is_active = TRUE
                ORDER BY u.full_name
                """,
                (course_code, course_code),
            )
            add_rows(cursor.fetchall())

            if course_code == "COMP4300" and _db_column_exists(cursor, "student_course_results", "promoted_to_semester_id"):
                cursor.execute(
                    """
                    SELECT DISTINCT st.student_id, u.user_id, u.full_name, u.university_id,
                           'COMP4300' AS course_code
                    FROM student_course_results scr
                    JOIN semesters promoted_sem ON promoted_sem.semester_id = scr.promoted_to_semester_id
                    JOIN students st ON st.student_id = scr.student_id
                    JOIN users u ON u.user_id = st.user_id
                    WHERE promoted_sem.course_code = 'COMP4300'
                      AND scr.status = 'passed'
                      AND u.role = 'student'
                      AND u.is_active = TRUE
                    ORDER BY u.full_name
                    """
                )
                add_rows(cursor.fetchall())

    # Source 3: COMP4200 sections.
    if course_code == "COMP4200" and _table_exists(cursor, "student_distribution_sections") and _table_exists(cursor, "section_students"):
        cursor.execute(
            """
            SELECT DISTINCT st.student_id, u.user_id, u.full_name, u.university_id,
                   'COMP4200' AS course_code
            FROM section_students ss
            JOIN students st ON st.student_id = ss.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE u.role = 'student'
              AND u.is_active = TRUE
            ORDER BY u.full_name
            """
        )
        add_rows(cursor.fetchall())

    return sorted(rows_by_user.values(), key=lambda r: (r.get("full_name") or "").lower())


def _student_user_ids_by_course(cursor, course_code):
    return [row["user_id"] for row in _student_user_rows_by_course(cursor, course_code)]


def _all_active_student_rows(cursor):
    cursor.execute(
        """
        SELECT st.student_id, u.user_id, u.full_name, u.university_id,
               NULL AS course_code
        FROM students st
        JOIN users u ON u.user_id = st.user_id
        WHERE u.role = 'student'
          AND u.is_active = TRUE
        ORDER BY u.full_name
        """
    )
    return cursor.fetchall()


def _all_active_student_user_ids(cursor):
    return [row["user_id"] for row in _all_active_student_rows(cursor)]



def _comp4300_project_recipients(cursor, project_id=None):
    """Return students and supervisor user IDs for COMP4300 projects."""
    if not (_table_exists(cursor, "projects") and _table_exists(cursor, "project_members")):
        return []

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
              AND us.role = 'student'
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

def _notification_recipients(cursor, scope, value=None, course_scope="both"):
    """Return user_ids for the coordinator selected target."""
    scope = (scope or "").strip()
    course_scope = (course_scope or "both").strip()

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

    if scope in {"all_students", "students"}:
        if course_scope == "graduation_project":
            return _student_user_ids_by_course(cursor, "COMP4300")
        if course_scope == "introduction":
            return _student_user_ids_by_course(cursor, "COMP4200")
        return _all_active_student_user_ids(cursor)

    if scope == "comp4200_students":
        return _student_user_ids_by_course(cursor, "COMP4200")

    if scope == "comp4300_students":
        return _student_user_ids_by_course(cursor, "COMP4300")

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
        # For COMP4300 the "section" selector contains projects with values like p:12.
        if course_scope == "graduation_project" or str(value or "").startswith("p:"):
            project_id = str(value or "").replace("p:", "", 1)
            return _comp4300_project_recipients(cursor, project_id)

        section_id = str(value or "").replace("s:", "", 1)
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
            (section_id, section_id),
        )
        return [r["recipient_id"] for r in cursor.fetchall()]

    if scope == "all_sections":
        recipients = []
        if course_scope in {"introduction", "both"}:
            if _table_exists(cursor, "student_distribution_sections") and _table_exists(cursor, "section_students"):
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
                recipients.extend([r["recipient_id"] for r in cursor.fetchall()])
        if course_scope in {"graduation_project", "both"}:
            recipients.extend(_comp4300_project_recipients(cursor))
        return sorted(set(recipients))

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

    if scope == "all_users":
        cursor.execute(
            """
            SELECT user_id
            FROM users
            WHERE is_active = TRUE
              AND role IN ('student', 'supervisor', 'coordinator', 'head_of_department')
              AND user_id <> %s
            ORDER BY role, full_name
            """,
            (session.get("user_id"),),
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

        students = _all_active_student_rows(cursor)
        comp4200_students = _student_user_rows_by_course(cursor, "COMP4200")
        comp4300_students = _student_user_rows_by_course(cursor, "COMP4300")
        _ensure_comp4200_section_schema(cursor)

        sections = []
        if _table_exists(cursor, "student_distribution_sections") and _table_exists(
            cursor, "section_students"
        ):
            cursor.execute("""
                SELECT CONCAT('s:', sec.section_id) AS section_key,
                       sec.section_id,
                       COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS section_name,
                       'introduction' AS course_scope,
                       'COMP4200' AS course_code,
                       u_sup.full_name AS supervisor_name,
                       COUNT(DISTINCT ss.student_id) AS students_count
                FROM student_distribution_sections sec
                LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
                LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
                JOIN faculty f ON f.faculty_id = sec.supervisor_id
                JOIN users u_sup ON u_sup.user_id = f.user_id
                LEFT JOIN section_students ss ON ss.section_id = sec.section_id
                GROUP BY sec.section_id, sec.section_name, p_intro.title, u_sup.full_name
                ORDER BY section_name
                """)
            sections.extend(cursor.fetchall())

        if _table_exists(cursor, "projects") and _table_exists(cursor, "project_members"):
            cursor.execute("""
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
                """)
            sections.extend(cursor.fetchall())

        cursor.close()
        db.close()
        return jsonify(
            {
                "heads": heads,
                "doctors": doctors,
                "students": students,
                "comp4200_students": comp4200_students,
                "comp4300_students": comp4300_students,
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
        _ensure_notification_attachment_columns(cursor)
        db.commit()
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
        _ensure_notification_attachment_columns(cursor)
        db.commit()
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


@coordinator_bp.route("/api/coordinator/notifications/supervisor-activity", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_supervisor_activity():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notification_attachment_columns(cursor)
        _ensure_comp4200_section_schema(cursor)
        intro_semester = _get_active_semester_by_course(cursor, "COMP4200")
        if intro_semester and intro_semester.get("semester_id"):
            _committee_sync_comp4200_project_sections(cursor, intro_semester["semester_id"])
        db.commit()

        has_message_origin = _db_column_exists(cursor, "notifications", "message_origin")
        manual_filter = "AND n.message_origin IN ('manual', 'reply')" if has_message_origin else ""

        cursor.execute(
            f"""
            SELECT
                'message' AS activity_type,
                MIN(n.notification_id) AS activity_id,
                n.title,
                n.message,
                COALESCE(n.course_scope, 'both') AS course_scope,
                sender.full_name AS supervisor_name,
                sender.user_id AS supervisor_user_id,
                COUNT(DISTINCT n.recipient_id) AS recipient_count,
                GROUP_CONCAT(DISTINCT recipient.full_name ORDER BY recipient.full_name SEPARATOR ', ') AS recipient_names,
                MAX(n.created_at) AS activity_at
            FROM notifications n
            JOIN users sender ON sender.user_id = n.sender_id
            JOIN users recipient ON recipient.user_id = n.recipient_id
            WHERE sender.role = 'supervisor'
              AND recipient.role = 'student'
              {manual_filter}
            GROUP BY
                n.sender_id, n.title, n.message, COALESCE(n.course_scope, 'both'),
                sender.full_name, sender.user_id,
                DATE_FORMAT(n.created_at, '%Y-%m-%d %H:%i:%s')
            ORDER BY activity_at DESC
            LIMIT 80
            """
        )
        activities = []
        for row in cursor.fetchall():
            row["activity_at"] = str(row.get("activity_at") or "")
            row["recipient_count"] = int(row.get("recipient_count") or 0)
            activities.append(row)

        if _table_exists(cursor, "supervisor_lectures"):
            lecture_recipient_count = (
                """
                (
                    SELECT COUNT(*)
                    FROM supervisor_lecture_recipients slr
                    WHERE slr.lecture_id = sl.lecture_id
                ) AS recipient_count
                """
                if _table_exists(cursor, "supervisor_lecture_recipients")
                else "0 AS recipient_count"
            )
            cursor.execute(
                f"""
                SELECT
                    'lecture' AS activity_type,
                    sl.lecture_id AS activity_id,
                    sl.title,
                    COALESCE(sl.description, '') AS message,
                    sl.course_scope,
                    u.full_name AS supervisor_name,
                    u.user_id AS supervisor_user_id,
                    COALESCE(
                        CASE
                            WHEN sl.target_kind = 'all' THEN 'All assigned students'
                            WHEN sl.target_kind = 'section' THEN COALESCE(NULLIF(p_sec.title, ''), sec.section_name)
                            WHEN sl.target_kind = 'project' THEN COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id))
                            ELSE NULL
                        END,
                        'Assigned students'
                    ) AS target_name,
                    sl.lecture_date,
                    sl.lecture_time,
                    sl.week_label,
                    sl.status,
                    sl.created_at AS activity_at,
                    {lecture_recipient_count}
                FROM supervisor_lectures sl
                JOIN faculty f ON f.faculty_id = sl.supervisor_id
                JOIN users u ON u.user_id = f.user_id
                LEFT JOIN student_distribution_sections sec
                  ON sl.target_kind = 'section' AND sec.section_id = sl.target_id
                LEFT JOIN comp4200_project_sections cps_sec
                  ON sl.target_kind = 'section' AND cps_sec.section_id = sec.section_id
                LEFT JOIN projects p_sec
                  ON sl.target_kind = 'section' AND p_sec.project_id = cps_sec.project_id
                LEFT JOIN projects p
                  ON sl.target_kind = 'project' AND p.project_id = sl.target_id
                ORDER BY sl.created_at DESC, sl.lecture_id DESC
                LIMIT 80
                """
            )
            for row in cursor.fetchall():
                for key in ("activity_at", "lecture_date", "lecture_time"):
                    if row.get(key) is not None:
                        row[key] = str(row[key])
                row["recipient_count"] = int(row.get("recipient_count") or 0)
                activities.append(row)

        activities.sort(key=lambda item: str(item.get("activity_at") or ""), reverse=True)
        cursor.close()
        db.close()
        return jsonify({"activity": activities[:120]})
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
    allow_reply = str(data.get("allow_reply") or "1").lower() in ("1", "true", "on", "yes")
    reply_to_notification_id = data.get("reply_to_notification_id")
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
        sender_id = session.get("user_id")

        if scope == "reply":
            if not reply_to_notification_id:
                cursor.close()
                db.close()
                return jsonify({"error": "This reply cannot be sent because the original message was not identified."}), 400
            cursor.execute(
                """
                SELECT n.notification_id, n.sender_id, COALESCE(n.can_reply, 0) AS can_reply
                FROM notifications n
                WHERE n.notification_id = %s
                  AND n.recipient_id = %s
                  AND n.sender_id = %s
                  AND n.message_origin IN ('manual', 'reply')
                LIMIT 1
                """,
                (reply_to_notification_id, sender_id, value),
            )
            original_message = cursor.fetchone()
            if not original_message:
                cursor.close()
                db.close()
                return jsonify({"error": "Original message was not found for this reply."}), 404
            if not bool(original_message.get("can_reply", 0)):
                cursor.close()
                db.close()
                return jsonify({"error": "Replies are disabled for this message."}), 403

        recipients = _notification_recipients(cursor, scope, value, course_scope)
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
                     course_scope, related_project_id, is_read, can_reply,
                     message_origin, attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE, %s, %s, %s, %s, %s)
                """,
                (
                    recipient_id,
                    sender_id,
                    notification_type,
                    title,
                    message,
                    course_scope,
                    1 if allow_reply else 0,
                    "reply" if scope == "reply" else "manual",
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
            semester_id INT NOT NULL,
            title VARCHAR(180) NOT NULL DEFAULT 'Project Introduction Timeline',
            note TEXT NULL,
            is_published BOOLEAN NOT NULL DEFAULT FALSE,
            published_at DATETIME NULL,
            created_by INT NULL,
            owner_role VARCHAR(20) NOT NULL DEFAULT 'coordinator',
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE SET NULL,
            INDEX idx_comp4200_timeline_owner (semester_id, owner_role, created_by)
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

    # Timelines used to be globally unique per semester. Supervisors now own an
    # independent timeline, while the coordinator timeline remains department-wide.
    if not _db_column_exists(cursor, "comp4200_timelines", "owner_role"):
        cursor.execute(
            "ALTER TABLE comp4200_timelines ADD COLUMN owner_role VARCHAR(20) NOT NULL DEFAULT 'coordinator' AFTER created_by"
        )
    # MySQL may use the old UNIQUE(semester_id) index to enforce the semester
    # foreign key. Create a non-unique replacement before dropping that unique
    # index, otherwise MySQL raises error 1553.
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'comp4200_timelines'
          AND INDEX_NAME = 'idx_comp4200_timelines_semester_fk'
        """
    )
    if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
        cursor.execute(
            "CREATE INDEX idx_comp4200_timelines_semester_fk ON comp4200_timelines (semester_id)"
        )
    cursor.execute(
        """
        SELECT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'comp4200_timelines'
          AND COLUMN_NAME = 'semester_id'
          AND NON_UNIQUE = 0
          AND INDEX_NAME <> 'PRIMARY'
        """
    )
    for row in cursor.fetchall():
        index_name = row.get("INDEX_NAME") or row.get("index_name")
        if index_name and str(index_name).replace("_", "").isalnum():
            cursor.execute(f"ALTER TABLE comp4200_timelines DROP INDEX `{index_name}`")
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'comp4200_timelines'
          AND INDEX_NAME = 'idx_comp4200_timeline_owner'
        """
    )
    if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
        cursor.execute(
            "CREATE INDEX idx_comp4200_timeline_owner ON comp4200_timelines (semester_id, owner_role, created_by)"
        )


def _get_or_create_intro_timeline(cursor, semester_id, user_id=None, owner_role="coordinator"):
    _ensure_intro_timeline_tables(cursor)
    cursor.execute(
        """
        SELECT timeline_id, semester_id, title, note, is_published, published_at, updated_at
        FROM comp4200_timelines
        WHERE semester_id = %s
          AND owner_role = %s
          AND (%s = 'coordinator' OR created_by = %s)
        LIMIT 1
        """,
        (semester_id, owner_role, owner_role, user_id),
    )
    timeline = cursor.fetchone()
    if timeline:
        return timeline
    cursor.execute(
        """
        INSERT INTO comp4200_timelines (semester_id, title, note, created_by, owner_role)
        VALUES (%s, 'Project Introduction Timeline', 'Timeline for COMP4200 students.', %s, %s)
        """,
        (semester_id, user_id, owner_role),
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
        "owner_role": owner_role,
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
        submitted_to = (item.get("submitted_to") or "coordinator").strip().lower()
        if submitted_to not in ("coordinator", "both"):
            submitted_to = "coordinator"

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
                "submitted_to": submitted_to,
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
                        item.get("submitted_to", "coordinator"),
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
                        item.get("submitted_to", "coordinator"),
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
        was_published = bool(timeline.get("published_at"))
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
        notification_title = (
            "Project Introduction Timeline Republished"
            if was_published
            else "Project Introduction Timeline Published"
        )
        msg = (
            "The coordinator republished the Project Introduction timeline. "
            "Open Student Timeline to view the updated milestones and deadlines."
            if was_published
            else "The coordinator published the Project Introduction timeline. "
            "Open Student Timeline to view all milestones and deadlines."
        )
        notification_count = 0
        for uid in recipients:
            _insert_notification(
                cursor,
                uid,
                session.get("user_id"),
                "deadline_reminder",
                notification_title,
                msg,
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
                close_at = _parse_client_datetime(close_at_raw)
            except ValueError:
                cursor.close()
                db.close()
                return (
                    jsonify({"error": "Please enter a valid close date and time."}),
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
                       GROUP_CONCAT(u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
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
              AND p.status <> 'solo_pending'
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_course_promotions pcp
                  WHERE pcp.source_project_id = p.project_id
              )
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
            WHERE u.role = 'student'
              AND u.is_active = TRUE
              AND EXISTS (
                SELECT 1
                FROM student_course_results scr
                WHERE scr.student_id = st.student_id
                  AND scr.semester_id = %s
                  AND COALESCE(scr.status, 'pending') <> 'passed'
                  AND scr.promoted_to_semester_id IS NULL
                  AND scr.promoted_at IS NULL
            )
            AND EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN projects p ON p.project_id = pm.project_id
                WHERE pm.student_id = st.student_id
                  AND p.semester_id = %s
                  AND p.status = 'solo_pending'
            )
            AND NOT EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN projects p ON p.project_id = pm.project_id
                WHERE pm.student_id = st.student_id
                  AND p.semester_id = %s
                  AND p.status <> 'solo_pending'
            )
            AND NOT EXISTS (
                SELECT 1
                FROM section_students ss
                WHERE ss.student_id = st.student_id
            )
            ORDER BY u.full_name
            """,
            (
                semester["semester_id"],
                semester["semester_id"],
                semester["semester_id"],
            ),
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


@coordinator_bp.route("/api/coordinator/delete-group/<int:project_id>", methods=["DELETE"])
@login_required(role="coordinator")
def api_delete_group(project_id):
    """Remove a COMP4200 group entirely so its students can re-register."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Confirm the project belongs to an active COMP4200 semester
        cursor.execute(
            """
            SELECT p.project_id
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
                             AND s.course_code = 'COMP4200'
            WHERE p.project_id = %s
            LIMIT 1
            """,
            (project_id,),
        )
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "Group not found or not a COMP4200 group."}), 404

        # Clean up records not covered by CASCADE
        for tbl_col in [
            ("notifications", "project_id"),
            ("deadlines", "project_id"),
            ("project_report_readers", "project_id"),
        ]:
            tbl, col = tbl_col
            try:
                cursor.execute(f"DELETE FROM `{tbl}` WHERE `{col}` = %s", (project_id,))
            except Exception:
                pass  # table may not exist

        try:
            cursor.execute(
                "DELETE FROM section_completion_status WHERE course_scope = 'introduction' AND reference_id = %s",
                (project_id,),
            )
        except Exception:
            pass

        # Delete the project — CASCADE handles project_members, project_files,
        # project_progress, project_lifecycle
        cursor.execute("DELETE FROM projects WHERE project_id = %s", (project_id,))

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Group deleted. Students can now re-register."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/assign-group-supervisor", methods=["POST"])
@login_required(role="coordinator")
def api_assign_group_supervisor():
    data = request.get_json(silent=True) or {}

    def assignment_notice(message, **extra):
        payload = {
            "ok": False,
            "message": message,
            "needs_attention": True,
        }
        payload.update(extra)
        return jsonify(payload), 200

    project_id = data.get("project_id")
    supervisor_id = data.get("supervisor_id")

    if not project_id or not supervisor_id:
        return assignment_notice("Please choose a group and supervisor before saving.")
    if not str(project_id).isdigit() or not str(supervisor_id).isdigit():
        return assignment_notice("Invalid group or supervisor selection.")

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT p.project_id,
                   p.semester_id,
                   p.title,
                   p.supervisor_id,
                   s.course_code,
                   s.academic_year,
                   old_sup.full_name AS old_supervisor_name,
                   COUNT(DISTINCT pm.student_id) AS member_count
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN faculty old_f ON old_f.faculty_id = p.supervisor_id
            LEFT JOIN users old_sup ON old_sup.user_id = old_f.user_id
            WHERE p.project_id = %s
            GROUP BY p.project_id, p.semester_id, p.title, p.supervisor_id, s.course_code, s.academic_year, old_sup.full_name
            """,
            (project_id,),
        )
        project = cursor.fetchone()

        if not project:
            cursor.close()
            db.close()
            return jsonify({"error": "Project not found."}), 404

        course_code = project.get("course_code") or "COMP4200"
        active_semester = _get_active_semester_by_course(cursor, course_code)
        anchor_semester_id = (
            active_semester["semester_id"]
            if active_semester
            else project.get("semester_id")
        )

        if str(project.get("supervisor_id") or "") == str(supervisor_id):
            cursor.close()
            db.close()
            return assignment_notice(
                "Supervisor is already assigned to this group.",
                already_assigned=True,
            )

        required_students = int(project.get("member_count") or 0)
        if required_students <= 0:
            required_students = 1

        snapshot = _faculty_load_snapshot(
            cursor,
            int(supervisor_id),
            project.get("academic_year") or (active_semester or {}).get("academic_year"),
            anchor_semester_id,
            course_code,
        )
        required_hours = required_students * 0.5
        load_exempt = _faculty_load_exempt_for_assignment(cursor, int(supervisor_id))

        if not load_exempt and snapshot["remaining_hours"] < required_hours:
            cursor.close()
            db.close()
            return assignment_notice(
                f"This doctor cannot take this project. "
                f"Required load: {required_hours:.1f} hour(s), "
                f"remaining load: {snapshot['remaining_hours']:.1f} hour(s)."
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
        title = "Supervisor Changed" if changed else "Project Approved and Supervisor Assigned"
        if changed:
            message = (
                f"Your project supervisor has been changed"
                f"{f' from {old_name}' if old_name else ''} to {new_name}."
            )
        else:
            message = (
                f"Your project has been approved. {new_name} has been assigned "
                "as your project supervisor. Your student workspace is now available."
            )
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
                "introduction",
            )
            sent_count += 1

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "ok": True,
                "message": f"Supervisor assigned successfully. {sent_count} student notification(s) sent."
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500




def _next_comp4200_group_name(cursor, semester_id):
    """
    Generate the next COMP4200 group name automatically.

    Example:
    Existing groups: Group 01, Group 02, Group 10
    Next group:      Group 11

    This is calculated in Python instead of REGEXP_SUBSTR so it works on
    more MySQL versions.
    """
    if not semester_id:
        return "Group 01"

    if _db_column_exists(cursor, "projects", "group_name"):
        cursor.execute(
            """
            SELECT COALESCE(NULLIF(group_name, ''), CONCAT('Group ', project_id)) AS group_name
            FROM projects
            WHERE semester_id = %s
              AND status <> 'solo_pending'
            """,
            (semester_id,),
        )
    else:
        cursor.execute(
            """
            SELECT CONCAT('Group ', project_id) AS group_name
            FROM projects
            WHERE semester_id = %s
              AND status <> 'solo_pending'
            """,
            (semester_id,),
        )

    max_no = 0
    for row in cursor.fetchall():
        name = str(row.get("group_name") or "")
        match = re.search(r"(\d+)", name)
        if match:
            max_no = max(max_no, int(match.group(1)))

    return f"Group {max_no + 1:02d}"


@coordinator_bp.route("/api/coordinator/next-group-name", methods=["GET"])
@login_required(role="coordinator")
def api_next_comp4200_group_name():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_comp4200_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"ok": False, "error": "No active COMP4200 semester found."}), 400

        group_name = _next_comp4200_group_name(cursor, semester["semester_id"])

        cursor.close()
        db.close()

        return jsonify({
            "ok": True,
            "group_name": group_name
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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

    if not supervisor_id:
        return jsonify({"error": "Supervisor is required."}), 400

    if len(student_ids) == 0:
        return jsonify({"error": "Please choose at least 1 student."}), 400

    if len(student_ids) > 3:
        return jsonify({"error": "A group can contain at most 3 students."}), 400

    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_comp4200_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester found."}), 400

        if not section_name:
            section_name = _next_comp4200_group_name(cursor, semester["semester_id"])

        cursor.execute(
            """
            SELECT project_id
            FROM projects
            WHERE semester_id = %s
              AND status <> 'solo_pending'
              AND LOWER(TRIM(COALESCE(NULLIF(group_name, ''), CONCAT('Group ', project_id)))) =
                  LOWER(TRIM(%s))
            LIMIT 1
            """,
            (semester["semester_id"], section_name),
        )
        if cursor.fetchone():
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "This group name already exists. Please choose another name."
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
            "COMP4200",
        )
        required_hours = len(student_ids) * 0.5
        load_exempt = _faculty_load_exempt_for_assignment(cursor, int(supervisor_id))

        if not load_exempt and snapshot["remaining_hours"] < required_hours:
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
              AND u.role = 'student'
              AND u.is_active = TRUE
              AND EXISTS (
                  SELECT 1
                  FROM student_course_results scr
                  WHERE scr.student_id = st.student_id
                    AND scr.semester_id = %s
                    AND COALESCE(scr.status, 'pending') <> 'passed'
                    AND scr.promoted_to_semester_id IS NULL
                    AND scr.promoted_at IS NULL
              )
              AND EXISTS (
                  SELECT 1
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                  WHERE pm.student_id = st.student_id
                    AND p.semester_id = %s
                    AND p.status = 'solo_pending'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                  WHERE pm.student_id = st.student_id
                    AND p.semester_id = %s
                    AND p.status <> 'solo_pending'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM section_students ss
                  WHERE ss.student_id = st.student_id
              )
        """
        params = tuple(student_ids) + (
            semester["semester_id"],
            semester["semester_id"],
            semester["semester_id"],
        )
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
            INSERT INTO projects
                (group_name, title, project_type, semester_id, supervisor_id,
                 status, submission_date)
            VALUES (%s, '', '', %s, %s, 'submitted', CURDATE())
            """,
            (section_name, semester["semester_id"], supervisor_id),
        )
        project_id = cursor.lastrowid

        for index, sid in enumerate(student_ids):
            cursor.execute(
                """
                DELETE p
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.project_id
                WHERE pm.student_id = %s
                  AND p.semester_id = %s
                  AND p.status = 'solo_pending'
                """,
                (sid, semester["semester_id"]),
            )
            cursor.execute(
                """
                INSERT INTO project_members
                    (project_id, student_id, is_primary_contact)
                VALUES (%s, %s, %s)
                """,
                (project_id, sid, index == 0),
            )

        _ensure_comp4200_section_schema(cursor)
        _committee_sync_comp4200_project_sections(cursor, semester["semester_id"])

        cursor.execute(
            """
            SELECT u.full_name
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s
            LIMIT 1
            """,
            (supervisor_id,),
        )
        supervisor = cursor.fetchone() or {}
        supervisor_name = supervisor.get("full_name") or "your assigned supervisor"
        team_names = ", ".join(student["full_name"] for student in students)
        notification_message = (
            f"You have been added to {section_name}. "
            f"Your supervisor is {supervisor_name}. "
            f"Team members: {team_names}."
        )

        for recipient_id in _project_student_user_ids(cursor, project_id):
            _insert_notification(
                cursor,
                recipient_id,
                session.get("user_id"),
                "supervisor_assigned",
                "Project Team and Supervisor Assignment",
                notification_message,
                project_id,
                "introduction",
            )

        db.commit()
        cursor.close()
        db.close()

        return jsonify(
            {"message": f"{section_name} created successfully.", "project_id": project_id, "group_name": section_name}
        )

    except Exception as e:
        if db:
            db.rollback()
        if cursor:
            cursor.close()
        if db:
            db.close()
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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_course_promotions (
            promotion_id INT PRIMARY KEY AUTO_INCREMENT,
            source_project_id INT NOT NULL,
            promoted_project_id INT NOT NULL,
            promoted_to_semester_id INT NOT NULL,
            promoted_by INT NULL,
            promoted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_project_course_promotion_source (source_project_id),
            UNIQUE KEY uq_project_course_promotion_target (promoted_project_id),
            FOREIGN KEY (source_project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (promoted_project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (promoted_to_semester_id) REFERENCES semesters(semester_id) ON DELETE RESTRICT,
            FOREIGN KEY (promoted_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
    _ensure_milestone_storage_columns(cursor)


def _sync_comp4200_group_student_results(cursor, project_id, status, notes, updated_by):
    """
    Coordinator marks are requests.
    COMP4200 students become passed/promoted only after Head approval, so a
    coordinator "succeeded" mark remains pending here.
    """
    if not _table_exists(cursor, "student_course_results"):
        return 0

    student_status = {
        "pending": "pending",
        "succeeded": "pending",
        "not_succeeded": "failed",
    }[status]

    cursor.execute(
        """
        INSERT INTO student_course_results
            (student_id, semester_id, status, updated_by, notes)
        SELECT DISTINCT pm.student_id, p.semester_id, %s, %s, %s
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        JOIN project_members pm ON pm.project_id = p.project_id
        WHERE p.project_id = %s
          AND sem.course_code = 'COMP4200'
        ON DUPLICATE KEY UPDATE
            status = IF(student_course_results.promoted_at IS NULL, VALUES(status), student_course_results.status),
            updated_by = IF(student_course_results.promoted_at IS NULL, VALUES(updated_by), student_course_results.updated_by),
            notes = IF(student_course_results.promoted_at IS NULL, VALUES(notes), student_course_results.notes),
            updated_at = CURRENT_TIMESTAMP
        """,
        (student_status, updated_by, notes, project_id),
    )
    return cursor.rowcount



def _notify_heads_section_success_request(cursor, course_scope, project_id, coordinator_id):
    """Notify all active Heads that a section/group success needs approval."""
    course_code = "COMP4200" if course_scope == "introduction" else "COMP4300"
    course_title = (
        "Project Introduction — COMP4200"
        if course_scope == "introduction"
        else "Graduation Project — COMP4300"
    )

    has_group_name = _db_column_exists(cursor, "projects", "group_name")
    group_name_expr = (
        "COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id))"
        if has_group_name
        else "CONCAT('Group ', p.project_id)"
    )
    group_name_group_by = ", p.group_name" if has_group_name else ""

    cursor.execute(
        f"""
        SELECT
            {group_name_expr} AS group_name,
            COALESCE(NULLIF(p.title, ''), {group_name_expr}) AS project_title,
            COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
            GROUP_CONCAT(u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', ') AS students
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        JOIN project_members pm ON pm.project_id = p.project_id
        JOIN students st ON st.student_id = pm.student_id
        JOIN users u_st ON u_st.user_id = st.user_id
        LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
        WHERE p.project_id = %s
          AND CONVERT(sem.course_code USING utf8mb4) COLLATE utf8mb4_unicode_ci = CONVERT(%s USING utf8mb4) COLLATE utf8mb4_unicode_ci
        GROUP BY p.project_id, p.title{group_name_group_by}, u_sup.full_name
        LIMIT 1
        """,
        (project_id, course_code),
    )
    project = cursor.fetchone() or {}

    cursor.execute(
        """
        SELECT user_id
        FROM users
        WHERE role = 'head_of_department'
          AND is_active = TRUE
        """
    )
    heads = cursor.fetchall()

    title = f"{course_code} Success Approval Required"
    message = (
        f"The coordinator marked {project.get('group_name') or 'a group'} as succeeded "
        f"in {course_title}. Please review and approve the result. "
        f"Project: {project.get('project_title') or '-'}. "
        f"Supervisor: {project.get('supervisor_name') or 'Not assigned'}. "
        f"Students: {project.get('students') or 'No students'}."
    )

    sent_count = 0
    for head in heads:
        _insert_notification(
            cursor,
            head["user_id"],
            coordinator_id,
            "system",
            title,
            message,
            project_id,
            course_scope,
        )
        sent_count += 1

    return sent_count



def _sql_value_for_copy(value):
    """Convert mysql-connector SET values and date/time values into insert-safe values."""
    if isinstance(value, set):
        return ",".join(sorted(str(v) for v in value))
    return value


def _get_comp4300_promotion_semester(cursor, academic_year=None):
    """Return the target COMP4300 semester used when a COMP4200 group succeeds."""
    if academic_year:
        cursor.execute(
            """
            SELECT semester_id, academic_year, semester_number, course_code
            FROM semesters
            WHERE course_code = 'COMP4300'
              AND academic_year = %s
            ORDER BY is_active DESC, semester_id DESC
            LIMIT 1
            """,
            (academic_year,),
        )
        semester = cursor.fetchone()
        if semester:
            return semester

    semester = _get_active_semester_by_course(cursor, "COMP4300")
    if semester:
        return semester

    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE course_code = 'COMP4300'
        ORDER BY semester_id DESC
        LIMIT 1
        """
    )
    return cursor.fetchone()


def _copy_project_optional_rows_to_promoted_project(cursor, source_project_id, promoted_project_id):
    """Copy only project rows that should continue with the group in COMP4300."""
    # COMP4300 gets the same team/project identity, but its submission workspace
    # must start empty. Do not copy COMP4200 files, progress, or lifecycle rows.

    if _table_exists(cursor, "supervisor_notes"):
        cursor.execute(
            """
            INSERT INTO supervisor_notes
                (project_id, supervisor_id, note_text, urgency)
            SELECT %s, supervisor_id, note_text, urgency
            FROM supervisor_notes
            WHERE project_id = %s
            """,
            (promoted_project_id, source_project_id),
        )

    if _table_exists(cursor, "project_report_readers"):
        cursor.execute(
            """
            INSERT IGNORE INTO project_report_readers
                (project_id, faculty_id, reader_order)
            SELECT %s, faculty_id, reader_order
            FROM project_report_readers
            WHERE project_id = %s
            """,
            (promoted_project_id, source_project_id),
        )



def _ensure_committee_continuation_schema(cursor):
    """Allow a promoted COMP4300 project to keep the same committee used in COMP4200."""
    if not _table_exists(cursor, "committee_plans"):
        return False

    if not _db_column_exists(cursor, "committee_plans", "source_intro_plan_id"):
        cursor.execute(
            "ALTER TABLE committee_plans ADD COLUMN source_intro_plan_id INT NULL AFTER course_scope"
        )

    if not _table_exists(cursor, "committee_plan_projects"):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS committee_plan_projects (
                cpp_id INT PRIMARY KEY AUTO_INCREMENT,
                plan_id INT NOT NULL,
                project_id INT NOT NULL,
                slot_order INT NOT NULL,
                slot_start TIME NOT NULL,
                slot_end TIME NOT NULL,
                UNIQUE KEY uq_plan_project (plan_id, project_id),
                FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    if not _table_exists(cursor, "committee_plan_members"):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS committee_plan_members (
                id INT PRIMARY KEY AUTO_INCREMENT,
                plan_id INT NOT NULL,
                faculty_id INT NOT NULL,
                role ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member',
                UNIQUE KEY uq_plan_faculty (plan_id, faculty_id),
                FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
                FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    if not _table_exists(cursor, "project_report_readers"):
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS project_report_readers (
                id INT PRIMARY KEY AUTO_INCREMENT,
                project_id INT NOT NULL,
                faculty_id INT NOT NULL,
                reader_order TINYINT NOT NULL,
                UNIQUE KEY uq_project_reader_order (project_id, reader_order),
                UNIQUE KEY uq_project_reader_faculty (project_id, faculty_id),
                FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
    return True


def _copy_intro_committee_to_comp4300(cursor, source_project_id, promoted_project_id, promoted_by=None):
    """
    Keep the same discussion committee when a COMP4200 group becomes a COMP4300 project.

    COMP4200 committees are linked through comp4200_project_sections -> committee_plan_sections.
    COMP4300 committees are linked through committee_plan_projects. This function creates/reuses
    a COMP4300 committee plan copied from the original COMP4200 committee and links the promoted
    project to it, with the same doctors, responsible doctor, room, date, and time slot.
    """
    if not _ensure_committee_continuation_schema(cursor):
        return {"copied": False, "reason": "committee tables do not exist"}

    required_tables = [
        "comp4200_project_sections",
        "committee_plan_sections",
        "committee_plans",
        "committee_plan_members",
        "committee_plan_projects",
    ]
    if any(not _table_exists(cursor, table) for table in required_tables):
        return {"copied": False, "reason": "missing committee link tables"}

    cursor.execute(
        """
        SELECT
            cp.*,
            cps.slot_order,
            cps.slot_start,
            cps.slot_end
        FROM comp4200_project_sections cps_link
        JOIN committee_plan_sections cps ON cps.section_id = cps_link.section_id
        JOIN committee_plans cp ON cp.plan_id = cps.plan_id
        WHERE cps_link.project_id = %s
          AND COALESCE(cp.course_scope, 'introduction') = 'introduction'
          AND cp.status <> 'cancelled'
        ORDER BY cp.plan_id DESC
        LIMIT 1
        """,
        (source_project_id,),
    )
    intro_plan = cursor.fetchone()
    if not intro_plan:
        return {"copied": False, "reason": "source COMP4200 group has no committee"}

    cursor.execute(
        """
        SELECT cp.plan_id
        FROM committee_plan_projects cpp
        JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
        WHERE cpp.project_id = %s
          AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
          AND cp.status <> 'cancelled'
        LIMIT 1
        """,
        (promoted_project_id,),
    )
    existing_link = cursor.fetchone()
    if existing_link:
        return {"copied": False, "plan_id": existing_link["plan_id"], "reason": "promoted project already has committee"}

    cursor.execute(
        """
        SELECT plan_id
        FROM committee_plans
        WHERE source_intro_plan_id = %s
          AND COALESCE(course_scope, 'graduation_project') = 'graduation_project'
          AND status <> 'cancelled'
        ORDER BY plan_id DESC
        LIMIT 1
        """,
        (intro_plan["plan_id"],),
    )
    target = cursor.fetchone()
    target_plan_id = target.get("plan_id") if target else None

    if not target_plan_id:
        target_name = intro_plan.get("committee_name") or f"Committee {intro_plan['plan_id']}"
        if "COMP4200" in target_name:
            target_name = target_name.replace("COMP4200", "COMP4300")
        elif "Introduction" in target_name:
            target_name = target_name.replace("Introduction", "Graduation")
        else:
            target_name = f"{target_name} — COMP4300"

        columns = [
            "committee_name",
            "course_scope",
            "source_intro_plan_id",
            "discussion_date",
            "start_time",
            "end_time",
            "room_id",
            "responsible_faculty_id",
            "status",
            "created_by",
        ]
        values = [
            target_name,
            "graduation_project",
            intro_plan["plan_id"],
            intro_plan.get("discussion_date"),
            intro_plan.get("start_time"),
            intro_plan.get("end_time"),
            intro_plan.get("room_id"),
            intro_plan.get("responsible_faculty_id"),
            "scheduled",
            promoted_by or intro_plan.get("created_by"),
        ]
        if _db_column_exists(cursor, "committee_plans", "academic_year"):
            columns.insert(3, "academic_year")
            values.insert(3, intro_plan.get("academic_year"))

        placeholders = ", ".join(["%s"] * len(values))
        cursor.execute(
            f"INSERT INTO committee_plans ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(values),
        )
        target_plan_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT IGNORE INTO committee_plan_members (plan_id, faculty_id, role)
            SELECT %s, faculty_id, role
            FROM committee_plan_members
            WHERE plan_id = %s
            """,
            (target_plan_id, intro_plan["plan_id"]),
        )

    cursor.execute(
        """
        INSERT IGNORE INTO committee_plan_projects
            (plan_id, project_id, slot_order, slot_start, slot_end)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            target_plan_id,
            promoted_project_id,
            intro_plan.get("slot_order") or 1,
            intro_plan.get("slot_start") or intro_plan.get("start_time"),
            intro_plan.get("slot_end") or intro_plan.get("end_time"),
        ),
    )

    cursor.execute(
        "UPDATE projects SET status = 'committee_evaluation' WHERE project_id = %s",
        (promoted_project_id,),
    )

    # Keep the same two report readers if COMP4200 readers were already assigned for the section.
    if _table_exists(cursor, "section_report_readers") and _table_exists(cursor, "comp4200_project_sections"):
        cursor.execute(
            """
            INSERT INTO project_report_readers (project_id, faculty_id, reader_order)
            SELECT %s, srr.faculty_id, srr.reader_order
            FROM comp4200_project_sections cps_link
            JOIN section_report_readers srr ON srr.section_id = cps_link.section_id
            WHERE cps_link.project_id = %s
            ON DUPLICATE KEY UPDATE faculty_id = VALUES(faculty_id)
            """,
            (promoted_project_id, source_project_id),
        )

    return {"copied": True, "plan_id": target_plan_id, "source_intro_plan_id": intro_plan["plan_id"]}


def _promote_comp4200_group_to_comp4300(cursor, source_project_id, promoted_by=None):
    """
    When a COMP4200 group succeeds, create its continuation in COMP4300.

    The new COMP4300 project keeps the same group name, title, students,
    supervisor, and preferences. Student submissions are not copied; the source
    COMP4200 row is kept for history, but project_course_promotions hides it
    from active COMP4200 coordinator lists.
    """
    _ensure_section_results_schema(cursor)

    cursor.execute(
        """
        SELECT p.*, sem.academic_year, sem.semester_id AS source_semester_id
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE p.project_id = %s
          AND sem.course_code = 'COMP4200'
          AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.project_id)
        LIMIT 1
        """,
        (source_project_id,),
    )
    source_project = cursor.fetchone()
    if not source_project:
        raise ValueError("COMP4200 project/group was not found or has no students.")

    cursor.execute(
        """
        SELECT promoted_project_id
        FROM project_course_promotions
        WHERE source_project_id = %s
        LIMIT 1
        """,
        (source_project_id,),
    )
    existing = cursor.fetchone()
    if existing:
        return {
            "promoted_project_id": existing["promoted_project_id"],
            "created": False,
            "students_copied": 0,
        }

    target_semester = _get_comp4300_promotion_semester(
        cursor, source_project.get("academic_year")
    )
    if not target_semester:
        raise ValueError("No COMP4300 semester found. Create/activate a COMP4300 semester first.")

    copy_columns = []
    copy_values = []

    for column in [
        "group_name",
        "title",
        "title_en",
        "abstract",
        "keywords",
        "project_type",
        "supervisor_id",
        "preferred_supervisor_1",
        "preferred_supervisor_2",
        "preferred_supervisor_3",
        "coordinator_notes",
    ]:
        if _db_column_exists(cursor, "projects", column):
            copy_columns.append(column)
            copy_values.append(_sql_value_for_copy(source_project.get(column)))

    copy_columns.extend(["semester_id", "status", "submission_date"])
    copy_values.extend([target_semester["semester_id"], "submitted", datetime.now().date()])

    placeholders = ", ".join(["%s"] * len(copy_values))
    cursor.execute(
        f"""
        INSERT INTO projects ({', '.join(copy_columns)})
        VALUES ({placeholders})
        """,
        tuple(copy_values),
    )
    promoted_project_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT IGNORE INTO project_members
            (project_id, student_id, is_primary_contact)
        SELECT %s, student_id, is_primary_contact
        FROM project_members
        WHERE project_id = %s
        """,
        (promoted_project_id, source_project_id),
    )
    students_copied = cursor.rowcount

    _copy_project_optional_rows_to_promoted_project(
        cursor, source_project_id, promoted_project_id
    )
    committee_continuation = _copy_intro_committee_to_comp4300(
        cursor, source_project_id, promoted_project_id, promoted_by
    )

    cursor.execute(
        """
        INSERT INTO project_course_promotions
            (source_project_id, promoted_project_id, promoted_to_semester_id, promoted_by, promoted_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (
            source_project_id,
            promoted_project_id,
            target_semester["semester_id"],
            promoted_by,
        ),
    )

    if _table_exists(cursor, "student_course_results"):
        cursor.execute(
            """
            INSERT INTO student_course_results
                (student_id, semester_id, status, updated_by, notes,
                 promoted_to_semester_id, promoted_by, promoted_at)
            SELECT DISTINCT pm.student_id, %s, 'passed', %s,
                   'Automatically promoted to COMP4300 after group success.',
                   %s, %s, NOW()
            FROM project_members pm
            WHERE pm.project_id = %s
            ON DUPLICATE KEY UPDATE
                status = 'passed',
                updated_by = VALUES(updated_by),
                promoted_to_semester_id = VALUES(promoted_to_semester_id),
                promoted_by = VALUES(promoted_by),
                promoted_at = COALESCE(student_course_results.promoted_at, NOW()),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                source_project.get("source_semester_id"),
                promoted_by,
                target_semester["semester_id"],
                promoted_by,
                source_project_id,
            ),
        )

    group_name = source_project.get("group_name") or source_project.get("title") or f"Group {source_project_id}"
    notification_message = (
        f"Your COMP4200 group ({group_name}) succeeded and was moved to COMP4300. "
        "The same students and supervisor were kept for the graduation project."
    )

    for recipient_id in _project_student_user_ids(cursor, source_project_id):
        _insert_notification(
            cursor,
            recipient_id,
            promoted_by,
            "status_changed",
            "Moved to COMP4300",
            notification_message,
            promoted_project_id,
            "graduation_project",
        )

    supervisor_user_id = None
    if source_project.get("supervisor_id"):
        cursor.execute(
            """
            SELECT u.user_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s
              AND u.is_active = TRUE
            LIMIT 1
            """,
            (source_project.get("supervisor_id"),),
        )
        supervisor = cursor.fetchone()
        supervisor_user_id = supervisor.get("user_id") if supervisor else None

    if supervisor_user_id:
        _insert_notification(
            cursor,
            supervisor_user_id,
            promoted_by,
            "status_changed",
            "COMP4200 Group Promoted to COMP4300",
            f"{group_name} was moved to COMP4300 with the same students under your supervision.",
            promoted_project_id,
            "graduation_project",
        )

    return {
        "promoted_project_id": promoted_project_id,
        "created": True,
        "students_copied": students_copied,
        "committee_continuation": committee_continuation,
    }



def _placeholder_list(values):
    return ",".join(["%s"] * len(values))


def _delete_table_where(cursor, table_name, where_sql, params=()):
    if not _table_exists(cursor, table_name):
        return 0
    cursor.execute(f"DELETE FROM `{table_name}` WHERE {where_sql}", tuple(params))
    return cursor.rowcount


def _delete_scoped_reference_rows(cursor, table_name, course_scope, reference_id):
    if not _table_exists(cursor, table_name):
        return 0
    if (
        _db_column_exists(cursor, table_name, "course_scope")
        and _db_column_exists(cursor, table_name, "reference_id")
    ):
        return _delete_table_where(
            cursor,
            table_name,
            "course_scope = %s AND reference_id = %s",
            (course_scope, reference_id),
        )
    if _db_column_exists(cursor, table_name, "project_id"):
        return _delete_table_where(cursor, table_name, "project_id = %s", (reference_id,))
    return 0


def _reset_failed_comp4200_group(cursor, project_id, notes=None, updated_by=None):
    """Return failed COMP4200 students to a clean registration/workspace state."""
    cursor.execute(
        """
        SELECT p.project_id, p.semester_id
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE p.project_id = %s
          AND sem.course_code = 'COMP4200'
        LIMIT 1
        """,
        (project_id,),
    )
    project = cursor.fetchone()
    if not project:
        return {"students_reset": 0, "deleted_project": False}

    cursor.execute(
        """
        SELECT DISTINCT st.student_id, st.user_id
        FROM project_members pm
        JOIN students st ON st.student_id = pm.student_id
        WHERE pm.project_id = %s
        """,
        (project_id,),
    )
    members = cursor.fetchall()
    student_ids = [row["student_id"] for row in members if row.get("student_id")]
    user_ids = [row["user_id"] for row in members if row.get("user_id")]

    if student_ids and _table_exists(cursor, "milestone_submissions"):
        placeholders = _placeholder_list(student_ids)
        cursor.execute(
            f"""
            DELETE FROM milestone_submissions
            WHERE project_id = %s
               OR student_id IN ({placeholders})
            """,
            (project_id, *student_ids),
        )

    if student_ids and _table_exists(cursor, "coordinator_deliverable_submissions"):
        placeholders = _placeholder_list(student_ids)
        cursor.execute(
            f"""
            DELETE FROM coordinator_deliverable_submissions
            WHERE project_id = %s
               OR student_id IN ({placeholders})
            """,
            (project_id, *student_ids),
        )

    if user_ids and _table_exists(cursor, "notifications"):
        placeholders = _placeholder_list(user_ids)
        parts = [
            f"recipient_id IN ({placeholders})",
            f"sender_id IN ({placeholders})",
        ]
        params = [*user_ids, *user_ids]
        if _db_column_exists(cursor, "notifications", "related_project_id"):
            parts.append("related_project_id = %s")
            params.append(project_id)
        if _db_column_exists(cursor, "notifications", "project_id"):
            parts.append("project_id = %s")
            params.append(project_id)
        cursor.execute(f"DELETE FROM notifications WHERE {' OR '.join(parts)}", tuple(params))
    elif _table_exists(cursor, "notifications"):
        parts = []
        params = []
        if _db_column_exists(cursor, "notifications", "related_project_id"):
            parts.append("related_project_id = %s")
            params.append(project_id)
        if _db_column_exists(cursor, "notifications", "project_id"):
            parts.append("project_id = %s")
            params.append(project_id)
        if parts:
            cursor.execute(f"DELETE FROM notifications WHERE {' OR '.join(parts)}", tuple(params))

    if student_ids:
        placeholders = _placeholder_list(student_ids)
        if _table_exists(cursor, "student_course_results"):
            failure_note = (
                notes
                or "You did not pass COMP4200. Please register again to start a new attempt."
            )
            cursor.execute(
                f"""
                INSERT INTO student_course_results
                    (student_id, semester_id, status, updated_by, notes)
                SELECT DISTINCT pm.student_id, p.semester_id, 'failed', %s, %s
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.project_id
                WHERE p.project_id = %s
                  AND pm.student_id IN ({placeholders})
                ON DUPLICATE KEY UPDATE
                    status = IF(student_course_results.promoted_at IS NULL, 'failed', student_course_results.status),
                    updated_by = IF(student_course_results.promoted_at IS NULL, VALUES(updated_by), student_course_results.updated_by),
                    notes = IF(student_course_results.promoted_at IS NULL, VALUES(notes), student_course_results.notes),
                    promoted_to_semester_id = IF(student_course_results.promoted_at IS NULL, NULL, student_course_results.promoted_to_semester_id),
                    promoted_by = IF(student_course_results.promoted_at IS NULL, NULL, student_course_results.promoted_by),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (updated_by, failure_note, project_id, *student_ids),
            )
        _delete_table_where(
            cursor,
            "student_groups",
            f"student_id IN ({placeholders})",
            tuple(student_ids),
        )

    for table_name in ("evaluation_windows", "evaluation_grade_tasks", "evaluation_scores"):
        _delete_scoped_reference_rows(cursor, table_name, "introduction", project_id)
    _delete_table_where(
        cursor,
        "section_completion_status",
        "course_scope = 'introduction' AND reference_id = %s",
        (project_id,),
    )

    for table_name in (
        "deadlines",
        "project_report_readers",
        "supervisor_assignments",
        "project_course_promotions",
    ):
        if table_name == "project_course_promotions":
            _delete_table_where(
                cursor,
                table_name,
                "source_project_id = %s OR promoted_project_id = %s",
                (project_id, project_id),
            )
        else:
            _delete_table_where(cursor, table_name, "project_id = %s", (project_id,))

    cursor.execute("DELETE FROM projects WHERE project_id = %s", (project_id,))
    return {"students_reset": len(student_ids), "deleted_project": cursor.rowcount > 0}


def _reset_failed_comp4300_project(cursor, project_id, notes=None, marked_by=None):
    """Reset a failed COMP4300 workspace while keeping team, supervisor, challenges, and feedback."""
    cursor.execute(
        """
        SELECT p.project_id, p.semester_id, p.title, p.supervisor_id
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE p.project_id = %s
          AND sem.course_code = 'COMP4300'
        LIMIT 1
        """,
        (project_id,),
    )
    project = cursor.fetchone()
    if not project:
        return {"students_reset": 0, "notifications_sent": 0, "kept_team": True}

    cursor.execute(
        """
        SELECT DISTINCT st.student_id, st.user_id
        FROM project_members pm
        JOIN students st ON st.student_id = pm.student_id
        WHERE pm.project_id = %s
        """,
        (project_id,),
    )
    members = cursor.fetchall()
    student_ids = [row["student_id"] for row in members if row.get("student_id")]
    user_ids = [row["user_id"] for row in members if row.get("user_id")]

    if student_ids and _table_exists(cursor, "milestone_submissions"):
        placeholders = _placeholder_list(student_ids)
        cursor.execute(
            f"""
            DELETE FROM milestone_submissions
            WHERE project_id = %s
               OR student_id IN ({placeholders})
            """,
            (project_id, *student_ids),
        )

    if student_ids and _table_exists(cursor, "coordinator_deliverable_submissions"):
        placeholders = _placeholder_list(student_ids)
        cursor.execute(
            f"""
            DELETE FROM coordinator_deliverable_submissions
            WHERE project_id = %s
               OR student_id IN ({placeholders})
            """,
            (project_id, *student_ids),
        )

    _delete_table_where(cursor, "project_files", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "project_progress", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "project_lifecycle", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "deadlines", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "coordinator_decisions", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "final_decisions", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "supervisor_notes", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "committees", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "project_report_readers", "project_id = %s", (project_id,))
    _delete_table_where(cursor, "committee_plan_projects", "project_id = %s", (project_id,))

    for table_name in ("evaluation_windows", "evaluation_grade_tasks", "evaluation_scores", "evaluation_final_results"):
        _delete_scoped_reference_rows(cursor, table_name, "graduation_project", project_id)

    if user_ids and _table_exists(cursor, "notifications"):
        placeholders = _placeholder_list(user_ids)
        parts = [
            f"recipient_id IN ({placeholders})",
            f"sender_id IN ({placeholders})",
        ]
        params = [*user_ids, *user_ids]
        if _db_column_exists(cursor, "notifications", "related_project_id"):
            parts.append("related_project_id = %s")
            params.append(project_id)
        if _db_column_exists(cursor, "notifications", "project_id"):
            parts.append("project_id = %s")
            params.append(project_id)
        cursor.execute(f"DELETE FROM notifications WHERE {' OR '.join(parts)}", tuple(params))

    update_parts = ["status = 'submitted'"]
    if _db_column_exists(cursor, "projects", "final_score"):
        update_parts.append("final_score = NULL")
    if _db_column_exists(cursor, "projects", "files_count"):
        update_parts.append("files_count = 0")
    if _db_column_exists(cursor, "projects", "coordinator_notes"):
        update_parts.append("coordinator_notes = NULL")
    if _db_column_exists(cursor, "projects", "rejection_reason"):
        update_parts.append("rejection_reason = NULL")
    cursor.execute(
        f"UPDATE projects SET {', '.join(update_parts)} WHERE project_id = %s",
        (project_id,),
    )

    notification_title = "COMP4300 Result: Not Succeeded"
    notification_message = (
        "Your COMP4300 graduation project was marked as not succeeded. "
        "Your team and supervisor remain assigned, and your project workspace has been reset for a new attempt. "
        "Your previous challenges and feedback remain available."
    )
    if notes:
        notification_message += f" Coordinator note: {notes}"

    notifications_sent = 0
    for recipient_id in sorted(set(user_ids)):
        _insert_notification(
            cursor,
            recipient_id,
            marked_by,
            "status_changed",
            notification_title,
            notification_message,
            project_id,
            "graduation_project",
        )
        notifications_sent += 1

    return {
        "students_reset": len(student_ids),
        "notifications_sent": notifications_sent,
        "kept_team": True,
        "kept_supervisor": True,
    }


@coordinator_bp.route("/api/coordinator/section-results", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_section_results():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)

        intro_semester = _get_active_semester_by_course(cursor, "COMP4200")
        grad_semester = _get_active_semester_by_course(cursor, "COMP4300")

        group_name_select = (
            "COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id))"
            if _db_column_exists(cursor, "projects", "group_name")
            else "CONCAT('Group ', p.project_id)"
        )

        sync_intro_params = []
        sync_intro_where_parts = [
            f"{_ci('sem.course_code')} = {_lit('COMP4200')}",
            "EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)",
            "NOT EXISTS (SELECT 1 FROM project_course_promotions pcp WHERE pcp.source_project_id = p.project_id)",
            f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}",
            f"{_ci('p.title')} NOT LIKE {_lit('COMP4300 Graduation Project%')}",
        ]
        if intro_semester:
            sync_intro_where_parts.append("p.semester_id = %s")
            sync_intro_params.append(intro_semester["semester_id"])

        cursor.execute(
            f"""
            INSERT IGNORE INTO section_completion_status
                (course_scope, reference_id, status)
            SELECT 'introduction', p.project_id, 'pending'
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            WHERE {" AND ".join(sync_intro_where_parts)}
            """,
            tuple(sync_intro_params),
        )

        sync_grad_params = []
        sync_grad_where_parts = [
            f"{_ci('sem.course_code')} = {_lit('COMP4300')}",
            "EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)",
            f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}",
        ]
        if grad_semester:
            sync_grad_where_parts.append("p.semester_id = %s")
            sync_grad_params.append(grad_semester["semester_id"])

        cursor.execute(
            f"""
            INSERT IGNORE INTO section_completion_status
                (course_scope, reference_id, status)
            SELECT 'graduation_project', p.project_id, 'pending'
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            WHERE {" AND ".join(sync_grad_where_parts)}
            """,
            tuple(sync_grad_params),
        )
        db.commit()

        # Project Introduction groups are saved from the COMP4200 registration page
        # in projects + project_members, not in student_distribution_sections.
        intro_where_parts = [f"{_ci('sem.course_code')} = {_lit('COMP4200')}"]
        intro_params_list = []
        if intro_semester:
            intro_where_parts.append("p.semester_id = %s")
            intro_params_list.append(intro_semester["semester_id"])
        intro_where_parts.append("EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)")
        intro_where_parts.append("NOT EXISTS (SELECT 1 FROM project_course_promotions pcp WHERE pcp.source_project_id = p.project_id)")
        intro_where_parts.append(f"{_ci('scs.status')} <> {_lit('succeeded')}")
        intro_where_parts.append(f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}")
        intro_where_parts.append(f"{_ci('p.title')} NOT LIKE {_lit('COMP4300 Graduation Project%')}")
        intro_where = "WHERE " + " AND ".join(intro_where_parts)

        cursor.execute(
            f"""
            SELECT p.project_id AS reference_id,
                   {group_name_select} AS section_name,
                   p.title AS project_title,
                   'introduction' AS course_scope,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(GROUP_CONCAT(u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT pm.student_id) AS student_count,
                   p.status AS project_status,
                   scs.status AS result_status,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
            JOIN section_completion_status scs
              ON {_ci('scs.course_scope')} = {_lit('introduction')} AND scs.reference_id = p.project_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            {intro_where}
            GROUP BY p.project_id, p.title, p.status, u_sup.full_name,
                     scs.status, scs.notes, scs.marked_at, u_mark.full_name
            HAVING student_count > 0
            ORDER BY p.project_id DESC
            """,
            tuple(intro_params_list),
        )
        introduction_sections = cursor.fetchall()

        # Graduation Project groups come from real COMP4300 projects only.
        grad_where_parts = [f"{_ci('sem.course_code')} = {_lit('COMP4300')}"]
        grad_params_list = []
        if grad_semester:
            grad_where_parts.append("p.semester_id = %s")
            grad_params_list.append(grad_semester["semester_id"])
        grad_where_parts.append("EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)")
        grad_where_parts.append(f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}")
        grad_where_parts.append(f"{_ci('scs.status')} <> {_lit('succeeded')}")
        grad_where = "WHERE " + " AND ".join(grad_where_parts)

        cursor.execute(
            f"""
            SELECT p.project_id AS reference_id,
                   {group_name_select} AS section_name,
                   p.title AS project_title,
                   'graduation_project' AS course_scope,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(GROUP_CONCAT(u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students,
                   COUNT(DISTINCT pm.student_id) AS student_count,
                   p.status AS project_status,
                   scs.status AS result_status,
                   scs.notes,
                   scs.marked_at,
                   u_mark.full_name AS marked_by_name
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u_st ON u_st.user_id = st.user_id
            LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
            JOIN section_completion_status scs
              ON {_ci('scs.course_scope')} = {_lit('graduation_project')} AND scs.reference_id = p.project_id
            LEFT JOIN users u_mark ON u_mark.user_id = scs.marked_by
            {grad_where}
            GROUP BY p.project_id, p.title, p.status, u_sup.full_name,
                     scs.status, scs.notes, scs.marked_at, u_mark.full_name
            HAVING student_count > 0
            ORDER BY p.project_id DESC
            """,
            tuple(grad_params_list),
        )
        graduation_sections = cursor.fetchall()

        # Keep the summary cumulative even after a succeeded COMP4200 group is
        # promoted and hidden from the active Introduction list.
        intro_stats_where_parts = [
            f"{_ci('sem.course_code')} = {_lit('COMP4200')}",
            "EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)",
            f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}",
            f"{_ci('p.title')} NOT LIKE {_lit('COMP4300 Graduation Project%')}",
        ]
        intro_stats_params = []
        if intro_semester:
            intro_stats_where_parts.append("p.semester_id = %s")
            intro_stats_params.append(intro_semester["semester_id"])
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT p.project_id) AS total,
                   COUNT(DISTINCT CASE
                       WHEN {_ci('scs.status')} = {_lit('succeeded')} THEN p.project_id
                   END) AS succeeded
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            LEFT JOIN section_completion_status scs
              ON {_ci('scs.course_scope')} = {_lit('introduction')}
             AND scs.reference_id = p.project_id
            WHERE {" AND ".join(intro_stats_where_parts)}
            """,
            tuple(intro_stats_params),
        )
        introduction_stats = cursor.fetchone() or {}

        grad_stats_where_parts = [
            f"{_ci('sem.course_code')} = {_lit('COMP4300')}",
            "EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)",
            f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}",
        ]
        grad_stats_params = []
        if grad_semester:
            grad_stats_where_parts.append("p.semester_id = %s")
            grad_stats_params.append(grad_semester["semester_id"])
        cursor.execute(
            f"""
            SELECT COUNT(DISTINCT p.project_id) AS total,
                   COUNT(DISTINCT CASE
                       WHEN {_ci('scs.status')} = {_lit('succeeded')} THEN p.project_id
                   END) AS succeeded
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            LEFT JOIN section_completion_status scs
              ON {_ci('scs.course_scope')} = {_lit('graduation_project')}
             AND scs.reference_id = p.project_id
            WHERE {" AND ".join(grad_stats_where_parts)}
            """,
            tuple(grad_stats_params),
        )
        graduation_stats = cursor.fetchone() or {}

        cursor.close()
        db.close()
        return jsonify(
            _json_safe_value(
                {
                    "semester": intro_semester or grad_semester or {},
                    "introduction_sections": introduction_sections,
                    "graduation_sections": graduation_sections,
                    "stats": {
                        # visible/waiting groups in the coordinator page
                        "introduction_total": len(introduction_sections),
                        "graduation_total": len(graduation_sections),
                        # groups already sent to Head approval
                        "introduction_succeeded": introduction_stats.get("succeeded", 0),
                        "graduation_succeeded": graduation_stats.get("succeeded", 0),
                    },
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
            jsonify({"error": "status must be pending, succeeded, or not_succeeded"}),
            400,
        )
    if not reference_id:
        return jsonify({"error": "reference_id is required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)

        expected_course_code = "COMP4200" if course_scope == "introduction" else "COMP4300"
        cursor.execute(
            """
            SELECT p.project_id
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            WHERE p.project_id = %s
              AND CONVERT(sem.course_code USING utf8mb4) COLLATE utf8mb4_unicode_ci = CONVERT(%s USING utf8mb4) COLLATE utf8mb4_unicode_ci
              AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.project_id)
            LIMIT 1
            """,
            (reference_id, expected_course_code),
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
        reset_info = None
        promotion_info = None
        head_notifications = 0

        if course_scope == "introduction" and status == "not_succeeded":
            reset_info = _reset_failed_comp4200_group(
                cursor,
                reference_id,
                notes=notes,
                updated_by=session.get("user_id"),
            )
        elif course_scope == "graduation_project" and status == "not_succeeded":
            reset_info = _reset_failed_comp4300_project(
                cursor,
                reference_id,
                notes=notes,
                marked_by=session.get("user_id"),
            )
        elif course_scope == "introduction":
            _sync_comp4200_group_student_results(
                cursor,
                reference_id,
                status,
                notes,
                session.get("user_id"),
            )

        if status == "succeeded":
            head_notifications = _notify_heads_section_success_request(
                cursor,
                course_scope,
                reference_id,
                session.get("user_id"),
            )

        db.commit()
        cursor.close()
        db.close()
        if reset_info:
            scope_label = "Section" if course_scope == "introduction" else "Project"
            return jsonify(
                {
                    "message": (
                        f"{scope_label} marked not succeeded. "
                        f"{reset_info['students_reset']} student(s) reset to a clean workspace."
                    ),
                    "reset": reset_info,
                }
            )

        if status == "succeeded":
            message = (
                "Success request sent to Head of Department for approval. "
                "This item is now hidden from the coordinator active list."
            )
        else:
            message = "Section result saved successfully."

        return jsonify({"message": message, "head_notifications": head_notifications})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/section-results/succeed-all", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_succeed_all_section_results():
    """Mark all visible COMP4200 groups and COMP4300 project groups as succeeded."""
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "all").strip()

    if course_scope not in {"all", "introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be all, introduction, or graduation_project."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_section_results_schema(cursor)

        intro_ids = []
        grad_ids = []

        if course_scope in {"all", "introduction"}:
            intro_semester = _get_active_semester_by_course(cursor, "COMP4200")
            intro_where_parts = [f"{_ci('sem.course_code')} = {_lit('COMP4200')}"]
            intro_params_list = []
            if intro_semester:
                intro_where_parts.append("p.semester_id = %s")
                intro_params_list.append(intro_semester["semester_id"])
            intro_where_parts.append("EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)")
            intro_where_parts.append("NOT EXISTS (SELECT 1 FROM project_course_promotions pcp WHERE pcp.source_project_id = p.project_id)")
            intro_where_parts.append(f"NOT EXISTS (SELECT 1 FROM section_completion_status scs WHERE {_ci('scs.course_scope')} = {_lit('introduction')} AND scs.reference_id = p.project_id AND {_ci('scs.status')} = {_lit('succeeded')})")
            intro_where_parts.append(f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}")
            intro_where_parts.append(f"{_ci('p.title')} NOT LIKE {_lit('COMP4300 Graduation Project%')}")
            intro_where = "WHERE " + " AND ".join(intro_where_parts)
            cursor.execute(
                f"""
                SELECT DISTINCT p.project_id AS reference_id
                FROM projects p
                JOIN semesters sem ON sem.semester_id = p.semester_id
                {intro_where}
                ORDER BY p.project_id DESC
                """,
                tuple(intro_params_list),
            )
            intro_ids = [row["reference_id"] for row in cursor.fetchall()]

        if course_scope in {"all", "graduation_project"}:
            grad_semester = _get_active_semester_by_course(cursor, "COMP4300")
            grad_where_parts = [f"{_ci('sem.course_code')} = {_lit('COMP4300')}"]
            grad_params_list = []
            if grad_semester:
                grad_where_parts.append("p.semester_id = %s")
                grad_params_list.append(grad_semester["semester_id"])
            grad_where_parts.append("EXISTS (SELECT 1 FROM project_members pmx WHERE pmx.project_id = p.project_id)")
            grad_where_parts.append(f"{_ci('p.title')} NOT LIKE {_lit('Committee Demo%')}")
            grad_where_parts.append(f"NOT EXISTS (SELECT 1 FROM section_completion_status scs WHERE {_ci('scs.course_scope')} = {_lit('graduation_project')} AND scs.reference_id = p.project_id AND {_ci('scs.status')} = {_lit('succeeded')})")
            grad_where = "WHERE " + " AND ".join(grad_where_parts)
            cursor.execute(
                f"""
                SELECT DISTINCT p.project_id AS reference_id
                FROM projects p
                JOIN semesters sem ON sem.semester_id = p.semester_id
                {grad_where}
                ORDER BY p.project_id DESC
                """,
                tuple(grad_params_list),
            )
            grad_ids = [row["reference_id"] for row in cursor.fetchall()]

        notes = (data.get("notes") or "Marked succeeded by coordinator bulk action.").strip() or None
        marked_by = session.get("user_id")

        head_notification_count = 0

        def mark_rows(scope, ids):
            nonlocal head_notification_count
            count = 0
            for reference_id in ids:
                cursor.execute(
                    """
                    INSERT INTO section_completion_status
                        (course_scope, reference_id, status, notes, marked_by, marked_at)
                    VALUES (%s, %s, 'succeeded', %s, %s, NOW())
                    ON DUPLICATE KEY UPDATE
                        status = 'succeeded',
                        notes = VALUES(notes),
                        marked_by = VALUES(marked_by),
                        marked_at = NOW(),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (scope, reference_id, notes, marked_by),
                )
                count += 1
                if scope == "introduction":
                    _sync_comp4200_group_student_results(
                        cursor,
                        reference_id,
                        "succeeded",
                        notes,
                        marked_by,
                    )
                head_notification_count += _notify_heads_section_success_request(
                    cursor,
                    scope,
                    reference_id,
                    marked_by,
                )
            return count

        intro_count = mark_rows("introduction", intro_ids)
        grad_count = mark_rows("graduation_project", grad_ids)

        db.commit()
        cursor.close()
        db.close()

        total = intro_count + grad_count
        return jsonify(
            {
                "message": (
                    f"Successfully sent {total} success request(s) to Head of Department. "
                    "They are now hidden from the coordinator active list."
                ),
                "updated": total,
                "introduction_updated": intro_count,
                "graduation_updated": grad_count,
                "head_notifications": head_notification_count,
            }
        )
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
    _ensure_comp4200_section_schema(cursor)
    cursor.execute("""
        SELECT COALESCE(NULLIF(p_intro.title, ''), s.section_name) AS section_name,
               u.full_name AS supervisor_name,
               s.created_at,
               COALESCE(GROUP_CONCAT(us.full_name ORDER BY us.full_name SEPARATOR ', '), '') AS assigned_students
        FROM student_distribution_sections s
        LEFT JOIN comp4200_project_sections cps ON cps.section_id = s.section_id
        LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
        JOIN faculty f ON f.faculty_id = s.supervisor_id
        JOIN users u ON u.user_id = f.user_id
        LEFT JOIN section_students ss ON ss.section_id = s.section_id
        LEFT JOIN students st ON st.student_id = ss.student_id
        LEFT JOIN users us ON us.user_id = st.user_id
        GROUP BY s.section_id, s.section_name, p_intro.title, u.full_name, s.created_at
        ORDER BY section_name
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
                    "hours_submitted": snapshot["hours_submitted"],
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

        _ensure_faculty_load_submission_columns(cursor)

        cursor.execute(
            """
            SELECT semester_id
            FROM semesters
            WHERE academic_year = %s
              AND course_code = 'COMP4300'
            ORDER BY semester_number DESC, semester_id DESC
            LIMIT 1
            """,
            (active_semester["academic_year"],),
        )
        settings_semester = cursor.fetchone() or anchor_semester

        cursor.execute(
            """
            INSERT INTO faculty_load_settings
                (faculty_id, semester_id, graduation_project_hours, graduation_hours_submitted, updated_by)
            VALUES (%s, %s, %s, 1, %s)
            ON DUPLICATE KEY UPDATE
                graduation_project_hours = VALUES(graduation_project_hours),
                graduation_hours_submitted = 1,
                updated_by = VALUES(updated_by)
            """,
            (
                faculty_id,
                settings_semester["semester_id"],
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

        files_count_select = (
            """
            (
                SELECT COUNT(DISTINCT pf.file_id)
                FROM project_files pf
                WHERE pf.project_id = p.project_id
                  AND COALESCE(CONVERT(pf.upload_status USING utf8mb4) COLLATE utf8mb4_unicode_ci, 'uploaded' COLLATE utf8mb4_unicode_ci) = 'uploaded' COLLATE utf8mb4_unicode_ci
            ) AS files_count
            """
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
                        stu.full_name
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
        _ensure_section_results_schema(cursor)
        db.commit()

        if not _table_exists(cursor, "project_files"):
            cursor.close()
            db.close()
            return jsonify({"files": []})

        cursor.execute(
            f"""
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
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE pf.project_id = %s
              AND COALESCE(CONVERT(pf.upload_status USING utf8mb4) COLLATE utf8mb4_unicode_ci, 'uploaded' COLLATE utf8mb4_unicode_ci) = 'uploaded' COLLATE utf8mb4_unicode_ci
              AND {_COORDINATOR_PROJECT_SUBMISSION_CLOSED_SQL}
              AND {_COORDINATOR_PROJECT_NOT_SUCCEEDED_SQL}
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



def _committee_time_to_minutes(value):
    """Convert a HH:MM / TIME value to minutes after midnight."""
    if value is None:
        return 0
    if hasattr(value, "hour") and hasattr(value, "minute"):
        return int(value.hour) * 60 + int(value.minute)
    text = str(value).strip()
    if not text:
        return 0
    # MySQL TIME may arrive as HH:MM:SS.
    parts = text.split(":")
    try:
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return 0


def _committee_time_ranges_overlap(start1, end1, start2, end2):
    """Return True when two committee time ranges overlap."""
    s1 = _committee_time_to_minutes(start1)
    e1 = _committee_time_to_minutes(end1)
    s2 = _committee_time_to_minutes(start2)
    e2 = _committee_time_to_minutes(end2)
    return s1 < e2 and s2 < e1


def _committee_faculty_has_db_time_conflict(
    cursor,
    faculty_id,
    discussion_date,
    start_time,
    end_time,
    exclude_plan_id=None,
):
    """Check if a doctor already has an active committee that overlaps this time."""
    params = [faculty_id, discussion_date, end_time, start_time]
    exclude_sql = ""
    if exclude_plan_id:
        exclude_sql = " AND cp.plan_id <> %s"
        params.append(exclude_plan_id)

    cursor.execute(
        f"""
        SELECT cp.plan_id
        FROM committee_plan_members cpm
        JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
        WHERE cpm.faculty_id = %s
          AND cp.discussion_date = %s
          AND cp.status IN ('draft', 'scheduled', 'in_progress')
          AND cp.start_time < %s
          AND cp.end_time > %s
          {exclude_sql}
        LIMIT 1
        """,
        tuple(params),
    )
    return cursor.fetchone() is not None


def _committee_faculty_has_generated_time_conflict(
    faculty_id,
    discussion_date,
    start_time,
    end_time,
    generated_faculty_slots=None,
):
    """Check conflicts against committees generated in the current request before DB commit."""
    for slot in generated_faculty_slots or []:
        if str(slot.get("discussion_date")) != str(discussion_date):
            continue
        if int(faculty_id) not in {int(x) for x in slot.get("faculty_ids", set())}:
            continue
        if _committee_time_ranges_overlap(start_time, end_time, slot.get("start_time"), slot.get("end_time")):
            return True
    return False


def _committee_faculty_has_any_time_conflict(
    cursor,
    faculty_id,
    discussion_date,
    start_time,
    end_time,
    generated_faculty_slots=None,
    exclude_plan_id=None,
):
    return _committee_faculty_has_db_time_conflict(
        cursor,
        faculty_id,
        discussion_date,
        start_time,
        end_time,
        exclude_plan_id=exclude_plan_id,
    ) or _committee_faculty_has_generated_time_conflict(
        faculty_id,
        discussion_date,
        start_time,
        end_time,
        generated_faculty_slots=generated_faculty_slots,
    )


def _committee_conflicting_faculty_ids(
    cursor,
    faculty_ids,
    discussion_date,
    start_time,
    end_time,
    generated_faculty_slots=None,
    exclude_plan_id=None,
):
    conflicts = set()
    for faculty_id in faculty_ids or []:
        if faculty_id is None:
            continue
        if _committee_faculty_has_any_time_conflict(
            cursor,
            int(faculty_id),
            discussion_date,
            start_time,
            end_time,
            generated_faculty_slots=generated_faculty_slots,
            exclude_plan_id=exclude_plan_id,
        ):
            conflicts.add(int(faculty_id))
    return conflicts


def _committee_fetch_supervising_faculty_ids(cursor, semester_id=None, course_scope=None):
    """Return active faculty ids that actually supervise groups/projects."""
    role_filter = ("supervisor", "coordinator", "head_of_department")
    supervisor_ids = set()

    if course_scope in (None, "introduction"):
        if semester_id and course_scope == "introduction":
            _committee_sync_comp4200_project_sections(cursor, semester_id)

        params = []
        semester_filter = ""
        if semester_id and course_scope == "introduction":
            semester_filter = """
              AND (
                  EXISTS (
                      SELECT 1
                      FROM comp4200_project_sections cps
                      JOIN projects p ON p.project_id = cps.project_id
                      JOIN semesters sem ON sem.semester_id = p.semester_id
                      WHERE cps.section_id = sec.section_id
                        AND sem.semester_id = %s
                        AND sem.course_code = 'COMP4200'
                  )
                  OR NOT EXISTS (
                      SELECT 1
                      FROM comp4200_project_sections cps
                      WHERE cps.section_id = sec.section_id
                  )
              )
            """
            params.append(semester_id)

        cursor.execute(
            f"""
            SELECT DISTINCT sec.supervisor_id AS faculty_id
            FROM student_distribution_sections sec
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE sec.supervisor_id IS NOT NULL
              AND u.is_active = TRUE
              AND u.role IN ({",".join(["%s"] * len(role_filter))})
              {semester_filter}
            """,
            tuple(role_filter) + tuple(params),
        )
        supervisor_ids.update(int(row["faculty_id"]) for row in cursor.fetchall() if row.get("faculty_id"))

        params = list(role_filter)

        cursor.execute(
            f"""
            SELECT DISTINCT p.supervisor_id AS faculty_id
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE p.supervisor_id IS NOT NULL
              AND u.is_active = TRUE
              AND u.role IN ({",".join(["%s"] * len(role_filter))})
            """,
            tuple(params),
        )
        supervisor_ids.update(int(row["faculty_id"]) for row in cursor.fetchall() if row.get("faculty_id"))

    if course_scope in (None, "graduation_project"):
        params = list(role_filter)

        cursor.execute(
            f"""
            SELECT DISTINCT p.supervisor_id AS faculty_id
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users u ON u.user_id = f.user_id
            WHERE p.supervisor_id IS NOT NULL
              AND u.is_active = TRUE
              AND u.role IN ({",".join(["%s"] * len(role_filter))})
            """,
            tuple(params),
        )
        supervisor_ids.update(int(row["faculty_id"]) for row in cursor.fetchall() if row.get("faculty_id"))

    return supervisor_ids


def _committee_fetch_faculty_pool(cursor, supervisor_faculty_ids=None):
    """Return active faculty available for committee generation.

    Important for the requested committee rule:
    - Projects are grouped by their own supervisors and a supervisor
      bucket is never split across two committees.
    - A committee still has exactly 4 doctors.
    - The remaining seats may be filled by active doctors even if they do
      not supervise a project in that committee.

    Therefore this function intentionally loads all active faculty accounts
    that can serve on committees. The optional supervisor_faculty_ids is kept
    only for backward compatibility with older calls.
    """
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
        row["faculty_id"] = int(row["faculty_id"])
        row["specialization"] = row.get("specialization") or "General"
        groups[row["specialization"]].append(row)

    for spec in groups:
        groups[spec].sort(
            key=lambda r: (
                int(r.get("active_committee_count") or 0),
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
            "Not enough available supervisors to create another committee. "
            "A supervisor cannot be assigned to more than one active committee."
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
                "Not enough available supervisors to create another committee. "
                "A supervisor cannot be assigned to more than one active committee."
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
            "Check that the supervisor has a faculty record, an active user account, and is assigned to a group/project."
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
            "You need at least 4 active group supervisors in the faculty table: the project supervisor plus 3 committee members."
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
            "Could not create a complete committee. Please add at least 3 active supervisors beside the project supervisor."
        )

    return chosen_members



def _committee_flat_faculty_pool(groups):
    """Return all faculty members from the grouped faculty pool as a flat list."""
    result = []
    for members in groups.values():
        for member in members:
            item = dict(member)
            item["faculty_id"] = int(item["faculty_id"])
            item["specialization"] = item.get("specialization") or "General"
            result.append(item)
    return result


def _committee_pick_members_for_supervisors(
    groups,
    supervisor_ids,
    used_faculty_ids=None,
    rotation_index=0,
    reserved_supervisor_ids=None,
    unavailable_faculty_ids=None,
):
    """Pick exactly 4 doctors for one committee.

    Final committee rule requested by the user:
    - A committee has exactly 4 doctors.
    - A committee may contain more than one project/section for the same doctor.
    - All projects/sections supervised by a doctor must stay in the same committee.
    - The same doctor must not appear in another generated committee.
    - A doctor may be a committee member even if they do not have a project in
      that committee, but we must not use another eligible project supervisor as
      a filler because that would put the doctor in committee A while their
      projects are assigned to committee B.
    """
    used_faculty_ids = {int(x) for x in (used_faculty_ids or set()) if x is not None}
    unavailable_faculty_ids = {int(x) for x in (unavailable_faculty_ids or set()) if x is not None}
    reserved_supervisor_ids = {int(x) for x in (reserved_supervisor_ids or set()) if x is not None}

    clean_supervisor_ids = []
    for sid in supervisor_ids or []:
        if sid is None:
            continue
        sid = int(sid)
        if sid not in clean_supervisor_ids:
            clean_supervisor_ids.append(sid)

    if not clean_supervisor_ids:
        raise ValueError("Every committee item must have an assigned supervisor.")

    if len(clean_supervisor_ids) > 4:
        raise ValueError(
            "One committee cannot contain items from more than 4 different supervisors "
            "because the committee has exactly 4 doctors."
        )

    all_faculty = _committee_flat_faculty_pool(groups)
    faculty_by_id = {int(member["faculty_id"]): member for member in all_faculty}

    chosen_members = []
    chosen_ids = set()

    # Required members: supervisors of the projects/sections in this committee.
    for supervisor_id in clean_supervisor_ids:
        if supervisor_id in used_faculty_ids:
            raise ValueError(
                "A project/section supervisor is already used in another generated committee. "
                "All projects for the same supervisor must stay in one committee."
            )
        if supervisor_id in unavailable_faculty_ids:
            raise ValueError(
                "A project/section supervisor already has another committee at this time. "
                "The system will try another time slot."
            )

        supervisor = faculty_by_id.get(supervisor_id)
        if not supervisor:
            raise ValueError(
                "A project/section supervisor is not available for committee generation. "
                "Check that every supervisor has a faculty record and an active user account."
            )

        item = dict(supervisor)
        item["faculty_id"] = int(item["faculty_id"])
        item["specialization"] = item.get("specialization") or "General"
        item["role"] = "supervisor"
        chosen_members.append(item)
        chosen_ids.add(supervisor_id)

    if len(chosen_members) == 4:
        return chosen_members

    # Fill the remaining seats. A filler doctor must not be:
    # - already chosen,
    # - used in another generated committee,
    # - unavailable at the same time,
    # - a supervisor whose eligible projects are reserved for another committee.
    filler_candidates = []
    chosen_specs = {m.get("specialization") or "General" for m in chosen_members}
    for member in all_faculty:
        fid = int(member["faculty_id"])
        if fid in chosen_ids:
            continue
        if fid in used_faculty_ids:
            continue
        if fid in unavailable_faculty_ids:
            continue
        if fid in reserved_supervisor_ids and fid not in clean_supervisor_ids:
            continue
        item = dict(member)
        item["faculty_id"] = fid
        item["specialization"] = item.get("specialization") or "General"
        item["role"] = "member"
        filler_candidates.append(item)

    def filler_sort_key(member):
        spec = member.get("specialization") or "General"
        return (
            spec in chosen_specs,
            int(member.get("active_committee_count") or 0),
            -int(member.get("years_experience") or 0),
            member.get("full_name") or "",
        )

    for member in sorted(filler_candidates, key=filler_sort_key):
        if len(chosen_members) == 4:
            break
        chosen_members.append(member)
        chosen_ids.add(int(member["faculty_id"]))
        chosen_specs.add(member.get("specialization") or "General")

    if len(chosen_members) < 4:
        raise ValueError(
            "Could not create a 4-doctor committee without repeating doctors or splitting a supervisor's projects. "
            "Add more active doctors, reduce simultaneous committees, or use fewer committees."
        )

    return chosen_members


def _committee_build_supervisor_project_groups(eligible_projects, projects_per_committee, max_committees=None):
    """Group eligible items by supervisor without splitting any supervisor.

    Final requested behavior:
    - Distribution is supervisor-bucket based, not project-by-project.
    - If Dr. X has several eligible projects/sections, all of them are placed
      in the same committee.
    - A committee may include multiple projects for the same supervisor.
    - A committee may include doctors as members even if they have no item
      inside it.
    - A doctor must not appear in more than one generated committee.
    - projects_per_committee is a preferred target, not a reason to split a
      supervisor bucket or create more committees than the available doctors can
      support. If needed, the function merges supervisor buckets and allows a
      committee to exceed the preferred project count so generation does not
      fail with Committee 5/6 simply because filler doctors ran out.
    """
    preferred_limit = max(1, int(projects_per_committee or 1))
    max_project_supervisors_per_committee = 4

    buckets = defaultdict(list)
    for project in eligible_projects:
        supervisor_id = project.get("supervisor_id")
        if supervisor_id is None:
            continue
        item = dict(project)
        item["supervisor_id"] = int(supervisor_id)
        buckets[int(supervisor_id)].append(item)

    supervisor_ids = sorted(
        buckets.keys(),
        key=lambda sid: (-len(buckets[sid]), str(sid)),
    )

    if not supervisor_ids:
        return []

    min_required_committees = math.ceil(len(supervisor_ids) / max_project_supervisors_per_committee)
    if max_committees is not None and int(max_committees) < min_required_committees:
        raise ValueError(
            f"Not enough active doctors to generate valid committees. "
            f"There are {len(supervisor_ids)} different project supervisors, so at least "
            f"{min_required_committees} committee(s) are required, but the available doctors can "
            f"support only {int(max_committees)} committee(s) with 4 doctors each."
        )

    target_group_count = None
    if max_committees is not None:
        target_group_count = max(min_required_committees, min(int(max_committees), len(supervisor_ids)))

    groups = []
    used_supervisors = set()

    for sid in supervisor_ids:
        if sid in used_supervisors:
            continue

        current_supervisors = [sid]
        current_projects = list(buckets[sid])
        used_supervisors.add(sid)

        for other_sid in supervisor_ids:
            if other_sid in used_supervisors:
                continue
            if len(current_supervisors) >= max_project_supervisors_per_committee:
                break

            remaining_supervisors_after_skip = len([x for x in supervisor_ids if x not in used_supervisors and x != other_sid])
            groups_after_current = len(groups) + 1
            minimum_groups_needed_after_current = math.ceil(remaining_supervisors_after_skip / max_project_supervisors_per_committee)
            must_pack_to_fit_available_doctors = (
                target_group_count is not None
                and groups_after_current + minimum_groups_needed_after_current > target_group_count
            )

            other_bucket = buckets[other_sid]
            would_exceed_limit = len(current_projects) + len(other_bucket) > preferred_limit

            if would_exceed_limit and not must_pack_to_fit_available_doctors:
                continue

            current_supervisors.append(other_sid)
            current_projects.extend(other_bucket)
            used_supervisors.add(other_sid)

        groups.append({
            "supervisor_ids": sorted(current_supervisors),
            "projects": current_projects,
        })

    # Final safety pass: if the preferred project limit created too many groups
    # for the number of available doctors, merge later groups into earlier groups
    # while keeping at most 4 different project supervisors per committee.
    if target_group_count is not None:
        changed = True
        while len(groups) > target_group_count and changed:
            changed = False
            for i in range(len(groups)):
                if changed:
                    break
                for j in range(len(groups) - 1, i, -1):
                    merged_supervisors = sorted(set(groups[i]["supervisor_ids"]) | set(groups[j]["supervisor_ids"]))
                    if len(merged_supervisors) <= max_project_supervisors_per_committee:
                        groups[i]["supervisor_ids"] = merged_supervisors
                        groups[i]["projects"].extend(groups[j]["projects"])
                        del groups[j]
                        changed = True
                        break

    return groups

def _ensure_comp4200_section_schema(cursor):
    """Create the COMP4200 section mirror used by supervisor tools."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS student_distribution_sections (
            section_id INT PRIMARY KEY AUTO_INCREMENT,
            section_name VARCHAR(100) NOT NULL,
            supervisor_id INT NOT NULL,
            entered_by INT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supervisor_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
            FOREIGN KEY (entered_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS section_students (
            id INT PRIMARY KEY AUTO_INCREMENT,
            section_id INT NOT NULL,
            student_id INT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_section_student (section_id, student_id),
            FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS comp4200_project_sections (
            project_id INT PRIMARY KEY,
            section_id INT NOT NULL UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _committee_ensure_course_schema(cursor):
    """Keep committee tables compatible with both COMP4200 and COMP4300."""
    _ensure_comp4200_section_schema(cursor)

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
    try:
        semester = _get_active_semester_by_course(cursor, "COMP4200")
        if semester and semester.get("semester_id"):
            _committee_sync_comp4200_project_sections(cursor, semester["semester_id"])
    except Exception:
        pass


def _committee_sync_comp4200_project_sections(cursor, semester_id=None):
    """Mirror real COMP4200 project groups into section tables used by committees."""
    if not semester_id:
        return

    cursor.execute(
        """
        SELECT
            p.project_id,
            LEFT(COALESCE(NULLIF(p.title, ''), NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id)), 100) AS section_name,
            p.supervisor_id
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE sem.semester_id = %s
          AND sem.course_code = 'COMP4200'
          AND p.supervisor_id IS NOT NULL
          AND p.status IN ('submitted', 'under_review', 'needs_revision', 'committee_evaluation')
          AND COALESCE(p.title, '') NOT LIKE 'Committee Demo%%'
          AND COALESCE(p.title, '') NOT LIKE 'COMP4300 Graduation Project%%'
          AND EXISTS (
              SELECT 1
              FROM project_members pmx
              WHERE pmx.project_id = p.project_id
          )
        ORDER BY p.project_id
        """,
        (semester_id,),
    )
    projects = cursor.fetchall()

    for project in projects:
        project_id = int(project["project_id"])
        section_name = project.get("section_name") or f"Group {project_id}"
        supervisor_id = int(project["supervisor_id"])

        cursor.execute(
            """
            SELECT section_id
            FROM comp4200_project_sections
            WHERE project_id = %s
            LIMIT 1
            """,
            (project_id,),
        )
        link = cursor.fetchone()

        if link:
            section_id = int(link["section_id"])
            cursor.execute(
                """
                UPDATE student_distribution_sections
                SET section_name = %s, supervisor_id = %s
                WHERE section_id = %s
                """,
                (section_name, supervisor_id, section_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO student_distribution_sections (section_name, supervisor_id, entered_by)
                VALUES (%s, %s, %s)
                """,
                (section_name, supervisor_id, session.get("user_id")),
            )
            section_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO comp4200_project_sections (project_id, section_id)
                VALUES (%s, %s)
                """,
                (project_id, section_id),
            )

        cursor.execute("DELETE FROM section_students WHERE section_id = %s", (section_id,))
        cursor.execute(
            """
            INSERT IGNORE INTO section_students (section_id, student_id)
            SELECT %s, pm.student_id
            FROM project_members pm
            WHERE pm.project_id = %s
            """,
            (section_id, project_id),
        )


def _committee_fetch_eligible_projects(
    cursor,
    semester_id=None,
    course_scope="graduation_project",
    include_assigned=False,
):
    _committee_ensure_course_schema(cursor)

    if course_scope == "introduction":
        _committee_sync_comp4200_project_sections(cursor, semester_id)
        assigned_filter = ""
        if not include_assigned:
            assigned_filter = """
            AND NOT EXISTS (
                SELECT 1
                FROM committee_plan_sections cps
                JOIN committee_plans cp ON cp.plan_id = cps.plan_id
                WHERE cps.section_id = sec.section_id
                  AND cp.status <> 'cancelled'
                  AND cp.course_scope = 'introduction'
            )
            """
        cursor.execute(
            f"""
            SELECT
                sec.section_id AS project_id,
                sec.section_id AS section_id,
                COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS title,
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
            LEFT JOIN comp4200_project_sections cps_title ON cps_title.section_id = sec.section_id
            LEFT JOIN projects p_intro ON p_intro.project_id = cps_title.project_id
            JOIN faculty sup_f ON sup_f.faculty_id = sec.supervisor_id
            JOIN users sup_u ON sup_u.user_id = sup_f.user_id
            JOIN section_students ss ON ss.section_id = sec.section_id
            JOIN students st ON st.student_id = ss.student_id
            JOIN users stu_u ON stu_u.user_id = st.user_id
            WHERE 1 = 1
              {assigned_filter}
            GROUP BY sec.section_id, sec.section_name, sec.supervisor_id,
                     p_intro.title, sup_u.full_name, sup_f.specialization
            HAVING COUNT(DISTINCT ss.student_id) > 0
            ORDER BY sec.supervisor_id ASC, title
            """
        )
        sections = cursor.fetchall()
        random.shuffle(sections)
        return sections

    assigned_filter = ""
    if not include_assigned:
        assigned_filter = """
          AND NOT EXISTS (
              SELECT 1
              FROM committee_plan_projects cpp
              JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
              WHERE cpp.project_id = p.project_id
                AND cp.status <> 'cancelled'
                AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
          )
        """
    cursor.execute(
        f"""
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
                GROUP_CONCAT(u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
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
          AND sem.course_code = 'COMP4300'
          AND p.supervisor_id IS NOT NULL
          AND p.status IN ('submitted', 'under_review', 'needs_revision', 'committee_evaluation')
          AND EXISTS (
              SELECT 1
              FROM project_members pmx
              WHERE pmx.project_id = p.project_id
          )
          {assigned_filter}
        GROUP BY p.project_id, p.title, p.status, p.project_type,
                 p.supervisor_id, sup_u.full_name, sup_f.specialization
        ORDER BY p.supervisor_id ASC, p.project_id DESC
        """,
        (semester_id,),
    )
    projects = cursor.fetchall()
    random.shuffle(projects)
    return projects


def _committee_no_eligible_reason(cursor, semester_id, course_scope):
    if course_scope == "introduction":
        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT p.project_id) AS real_items,
                SUM(CASE WHEN cps.section_id IS NOT NULL THEN 1 ELSE 0 END) AS assigned_items
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN comp4200_project_sections cps_link ON cps_link.project_id = p.project_id
            LEFT JOIN committee_plan_sections cps ON cps.section_id = cps_link.section_id
            LEFT JOIN committee_plans cp
              ON cp.plan_id = cps.plan_id
             AND cp.status <> 'cancelled'
             AND cp.course_scope = 'introduction'
            WHERE sem.semester_id = %s
              AND sem.course_code = 'COMP4200'
              AND p.supervisor_id IS NOT NULL
              AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.project_id)
            """,
            (semester_id,),
        )
        row = cursor.fetchone() or {}
        if int(row.get("real_items") or 0) and int(row.get("assigned_items") or 0) >= int(row.get("real_items") or 0):
            return (
                "All eligible COMP4200 sections already have committees. "
                "Open Generated/Current Committees, or use Reset & Redistribute to rebuild them."
            )
        return "No COMP4200 sections with students and assigned supervisors are ready for committee generation."

    cursor.execute(
        """
        SELECT
            COUNT(DISTINCT CASE WHEN p.title LIKE 'Committee Demo%%' THEN p.project_id END) AS demo_projects,
            COUNT(DISTINCT CASE WHEN pm.project_id IS NULL AND p.title NOT LIKE 'Committee Demo%%' THEN p.project_id END) AS no_student_projects,
            COUNT(DISTINCT CASE WHEN p.status = 'archived' AND pm.project_id IS NOT NULL THEN p.project_id END) AS archived_real_projects,
            COUNT(DISTINCT CASE WHEN p.supervisor_id IS NULL AND pm.project_id IS NOT NULL THEN p.project_id END) AS no_supervisor_projects,
            COUNT(DISTINCT CASE WHEN cpp.project_id IS NOT NULL THEN p.project_id END) AS assigned_projects
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        LEFT JOIN (
            SELECT DISTINCT project_id
            FROM project_members
        ) pm ON pm.project_id = p.project_id
        LEFT JOIN committee_plan_projects cpp ON cpp.project_id = p.project_id
        LEFT JOIN committee_plans cp
          ON cp.plan_id = cpp.plan_id
         AND cp.status <> 'cancelled'
         AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
        WHERE sem.semester_id = %s
          AND sem.course_code = 'COMP4300'
        """,
        (semester_id,),
    )
    row = cursor.fetchone() or {}
    reasons = []
    if int(row.get("archived_real_projects") or 0):
        reasons.append(f"{int(row.get('archived_real_projects') or 0)} real project(s) are archived")
    if int(row.get("no_student_projects") or 0):
        reasons.append(f"{int(row.get('no_student_projects') or 0)} project(s) have no students")
    if int(row.get("demo_projects") or 0):
        reasons.append(f"{int(row.get('demo_projects') or 0)} demo project(s) are ignored")
    if int(row.get("no_supervisor_projects") or 0):
        reasons.append(f"{int(row.get('no_supervisor_projects') or 0)} project(s) have no supervisor")
    if int(row.get("assigned_projects") or 0):
        reasons.append(f"{int(row.get('assigned_projects') or 0)} project(s) already have committees")

    detail = "; ".join(reasons) if reasons else "no submitted COMP4300 projects with students were found"
    return f"No eligible COMP4300 projects available for committee generation: {detail}."


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
        HAVING projects_count > 0
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
    try:
        cursor.execute(
            """
            SELECT COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS section_name,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name
            FROM student_distribution_sections sec
            LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
            LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
            LEFT JOIN faculty f ON f.faculty_id = sec.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
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
                f"You have been assigned to section: {section.get('section_name')}\n"
                f"Supervisor: {section.get('supervisor_name') or 'Not assigned'}\n"
                f"Section students: {', '.join(all_names)}\n"
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
    except Exception:
        return 0


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


def _committee_item_kind(course_scope):
    return "Section" if course_scope == "introduction" else "Project"


def _committee_reader_names(item):
    readers = []
    if item.get("reader1_name"):
        readers.append(f"{item['reader1_name']} (Report reader 1)")
    if item.get("reader2_name"):
        readers.append(f"{item['reader2_name']} (Report reader 2)")
    return ", ".join(readers) if readers else "Not assigned yet"


def _committee_faculty_role_for_item(member, item):
    faculty_id = int(member.get("faculty_id") or 0)
    supervisor_id = int(item.get("supervisor_id") or 0)
    roles = []

    if faculty_id == supervisor_id or member.get("role") == "supervisor":
        roles.append("Supervisor")
    if item.get("reader1_id") and faculty_id == int(item["reader1_id"]):
        roles.append("Report reader 1")
    if item.get("reader2_id") and faculty_id == int(item["reader2_id"]):
        roles.append("Report reader 2")

    if not roles:
        return "Discussion member only"

    roles.append("Discussion member")
    return " + ".join(roles)


def _committee_members_for_item_lines(members, item):
    lines = []
    for member in members:
        name = member.get("full_name") or "Doctor"
        role = _committee_faculty_role_for_item(member, item)
        lines.append(f"- {name}: {role}")
    return "\n".join(lines) if lines else "- No committee members assigned yet"


def _committee_faculty_item_lines(member, items, course_scope):
    item_label = _committee_item_kind(course_scope)
    lines = []
    for item in items:
        role = _committee_faculty_role_for_item(member, item)
        team_members = item.get("team_members") or "Not listed yet"
        supervisor_name = item.get("supervisor_name") or "Not assigned"
        readers = _committee_reader_names(item)
        lines.append(
            f"- {item.get('slot_start')}-{item.get('slot_end')} | "
            f"{item_label}: {item.get('title') or item_label} | "
            f"Students: {team_members} | "
            f"Supervisor: {supervisor_name} | "
            f"Your role: {role} | "
            f"Readers: {readers}"
        )
    return "\n".join(lines) if lines else "No items assigned."


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


def _committee_notification_summary(cursor, plan_id):
    """Return committee plan, members, items, and readable labels for notifications."""
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
    items = _committee_fetch_projects_for_plan(cursor, plan_id)
    members_line = ", ".join([m.get("full_name") or "Doctor" for m in members]) or "-"
    return plan, members, items, members_line


def _committee_send_notifications(cursor, plan_id, sender_id):
    """Notify committee doctors and students with per-item duties after generation."""
    plan, members, items, members_line = _committee_notification_summary(cursor, plan_id)
    if not plan:
        return 0

    sent = 0
    course_scope = plan.get("course_scope") or "graduation_project"
    course_label = (
        "COMP4200 Project Introduction"
        if course_scope == "introduction"
        else "COMP4300 Graduation Project"
    )
    faculty_user_ids = _faculty_user_id_map(cursor, [m["faculty_id"] for m in members])

    committee_title = plan.get("committee_name") or "Committee"
    date_value = plan.get("discussion_date") or "Not scheduled"
    plan_time_value = f"{plan.get('start_time') or '--:--'} - {plan.get('end_time') or '--:--'}"
    room_line = plan.get("room_name") or "Not assigned"

    for member in members:
        user_id = faculty_user_ids.get(int(member["faculty_id"]))
        if not user_id:
            continue

        faculty_message = (
            f"You have been assigned to {committee_title}.\n"
            f"Course: {course_label}\n"
            f"Date: {date_value}\n"
            f"Time: {plan_time_value}\n"
            f"Room: {room_line}\n"
            f"Committee members: {members_line}\n\n"
            f"Your schedule and duties:\n"
            f"{_committee_faculty_item_lines(member, items, course_scope)}"
        )
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

    for item in items:
        item_label = "section" if course_scope == "introduction" else "project"
        student_message = (
            f"Your {course_label} discussion committee has been scheduled.\n"
            f"{item_label.title()}: {item.get('title') or item_label.title()}\n"
            f"Date: {date_value}\n"
            f"Time: {item.get('slot_start') or '--:--'} - {item.get('slot_end') or '--:--'}\n"
            f"Room: {room_line}\n"
            f"Students: {item.get('team_members') or 'Not listed yet'}\n"
            f"Report readers: {_committee_reader_names(item)}\n"
            f"Committee members and roles:\n{_committee_members_for_item_lines(members, item)}"
        )

        if course_scope == "introduction":
            recipients = _section_student_user_ids(cursor, item.get("section_id") or item.get("project_id"))
            related_project_id = None
        else:
            recipients = _project_student_user_ids(cursor, item["project_id"])
            related_project_id = item["project_id"]

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
                COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS title,
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
            LEFT JOIN comp4200_project_sections cps_title ON cps_title.section_id = sec.section_id
            LEFT JOIN projects p_intro ON p_intro.project_id = cps_title.project_id
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
                     sec.section_id, sec.section_name, p_intro.title, sec.supervisor_id, sup_u.full_name,
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
                GROUP_CONCAT(u.full_name ORDER BY pm.is_primary_contact DESC, u.full_name SEPARATOR ', '),
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


def _committee_fetch_faculty_options(cursor):
    """Return active faculty who actually supervise groups/projects."""
    supervising_faculty_ids = _committee_fetch_supervising_faculty_ids(cursor)
    if not supervising_faculty_ids:
        return []

    placeholders = ",".join(["%s"] * len(supervising_faculty_ids))
    cursor.execute("""
        SELECT
            f.faculty_id,
            u.full_name,
            f.specialization,
            COALESCE(f.years_experience, 0) AS years_experience
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE f.faculty_id IN ({placeholders})
          AND u.role IN ('supervisor', 'coordinator', 'head_of_department')
          AND u.is_active = TRUE
        ORDER BY u.full_name ASC
    """.format(placeholders=placeholders), tuple(sorted(supervising_faculty_ids)))
    return cursor.fetchall()


def _committee_dashboard_payload(cursor):
    _committee_ensure_course_schema(cursor)
    _committee_ensure_report_readers_table(cursor)
    intro_semester = _get_active_semester_for_committee_scope(cursor, "introduction")
    grad_semester = _get_active_semester_for_committee_scope(cursor, "graduation_project")

    eligible_projects = []
    if intro_semester:
        eligible_projects.extend(
            _committee_fetch_eligible_projects(cursor, intro_semester["semester_id"], "introduction")
        )
    if grad_semester:
        eligible_projects.extend(
            _committee_fetch_eligible_projects(cursor, grad_semester["semester_id"], "graduation_project")
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
        FROM committee_plans cp
        WHERE (
            COALESCE(cp.course_scope, 'graduation_project') = 'introduction'
            AND EXISTS (
                SELECT 1 FROM committee_plan_sections cps WHERE cps.plan_id = cp.plan_id
            )
        ) OR (
            COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
            AND EXISTS (
                SELECT 1 FROM committee_plan_projects cpp WHERE cpp.plan_id = cp.plan_id
            )
        )
        """)
    stat_row = cursor.fetchone() or {}

    current_committees = [
        {
            "plan_id": p["plan_id"],
            "committee_name": p["committee_name"],
            "course_scope": p.get("course_scope") or "graduation_project",
            "discussion_date": p["discussion_date"],
            "start_time": p["start_time"],
            "end_time": p.get("end_time"),
            "room_name": p["room_name"],
            "status": p["status"],
            "projects_count": p["projects_count"],
            "responsible_faculty_id": p.get("responsible_faculty_id"),
            "responsible_name": p["responsible_name"],
            "supervisor_faculty_id": p.get("supervisor_faculty_id") or p.get("responsible_faculty_id"),
            "supervisor_name": p.get("supervisor_name") or p.get("responsible_name"),
            "members": p.get("members", []),
            "projects": p.get("projects", []),
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
        "faculty_options": _committee_fetch_faculty_options(cursor),
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
    active_semester = _get_active_semester_for_committee_scope(cursor, course_scope)
    if not active_semester:
        course_code = "COMP4200" if course_scope == "introduction" else "COMP4300"
        raise ValueError(f"No active {course_code} semester found.")

    _committee_ensure_course_schema(cursor)

    _committee_seed_rooms(cursor)

    eligible_projects = _committee_fetch_eligible_projects(
        cursor,
        active_semester["semester_id"],
        course_scope,
        include_assigned=clear_existing,
    )
    if not eligible_projects:
        label = "COMP4200 sections" if course_scope == "introduction" else "COMP4300 projects"
        if not clear_existing:
            assigned_items = _committee_fetch_eligible_projects(
                cursor,
                active_semester["semester_id"],
                course_scope,
                include_assigned=True,
            )
            if assigned_items:
                raise ValueError(
                    f"All eligible {label} already have committees. "
                    "Open Generated/Current Committees, or use Reset & Redistribute to rebuild them."
                )
        raise ValueError(_committee_no_eligible_reason(cursor, active_semester["semester_id"], course_scope))

    if clear_existing:
        _committee_delete_active_plans(cursor, course_scope)

    supervising_faculty_ids = _committee_fetch_supervising_faculty_ids(
        cursor,
        active_semester["semester_id"],
        course_scope,
    )
    faculty_groups = _committee_fetch_faculty_pool(cursor, supervising_faculty_ids)

    # We need 4 active group supervisors total. Different majors are preferred later inside
    # _committee_pick_members_for_supervisor(), but they are NOT required.
    # This avoids blocking generation when the department has fewer than 4 majors.
    total_active_doctors = sum(len(members) for members in faculty_groups.values())
    if total_active_doctors < 4:
        raise ValueError(
            "At least 4 active group supervisors are required to generate committees."
        )

    cursor.execute("""
        SELECT room_id, room_name
        FROM discussion_rooms
        WHERE is_active = 1
        ORDER BY sort_order ASC, room_name ASC
        """)
    rooms = cursor.fetchall()

    eligible_with_supervisors = []
    all_supervisor_ids = set()
    for project in eligible_projects:
        supervisor_id = project.get("supervisor_id")
        if supervisor_id:
            project = dict(project)
            project["supervisor_id"] = int(supervisor_id)
            eligible_with_supervisors.append(project)
            all_supervisor_ids.add(int(supervisor_id))

    if not eligible_with_supervisors:
        raise ValueError(
            "No eligible items with assigned supervisors were found. "
            "Assign a supervisor before generating committees."
        )

    # Build committees so each committee can include projects/sections from
    # multiple supervisors, and every supervisor in the committee has their own
    # item inside that same committee.
    max_committees_supported_by_doctors = total_active_doctors // 4
    committee_groups = _committee_build_supervisor_project_groups(
        eligible_with_supervisors,
        projects_per_committee,
        max_committees=max_committees_supported_by_doctors,
    )
    committee_count = len(committee_groups)

    if len(rooms) < committee_count:
        raise ValueError(
            f"Not enough rooms. Required rooms: {committee_count}, available rooms: {len(rooms)}."
        )

    used_faculty_ids = set()
    reserved_supervisor_ids = set(all_supervisor_ids)
    all_faculty_ids = {
        int(member["faculty_id"])
        for members in faculty_groups.values()
        for member in members
        if member.get("faculty_id") is not None
    }
    generated_faculty_slots = []
    course_label = "COMP4200" if course_scope == "introduction" else "COMP4300"

    for idx, committee_group in enumerate(committee_groups):
        chunk = committee_group["projects"]
        supervisor_ids = committee_group.get("supervisor_ids") or []
        supervisor_id = int(supervisor_ids[0]) if supervisor_ids else None

        if not chunk:
            continue

        committee_duration_minutes = max(30, ((len(chunk) - 1) * 40) + 30)
        members = None
        committee_start_time = None
        last_slot_end = None
        unavailable_faculty_ids = set()

        # Committees can run in parallel only when their doctors do not overlap.
        # If a required supervisor or selected member already has a committee at the
        # requested time, move this committee forward by 40 minutes and try again.
        max_attempts = max(36, len(committee_groups) * 8)
        for attempt in range(max_attempts):
            candidate_start = _committee_time_add(start_time, attempt * 40)
            candidate_end = _committee_time_add(candidate_start, committee_duration_minutes)

            supervisor_conflicts = _committee_conflicting_faculty_ids(
                cursor,
                supervisor_ids,
                discussion_date,
                candidate_start,
                candidate_end,
                generated_faculty_slots=generated_faculty_slots,
            )
            if supervisor_conflicts:
                continue

            unavailable_faculty_ids = _committee_conflicting_faculty_ids(
                cursor,
                all_faculty_ids,
                discussion_date,
                candidate_start,
                candidate_end,
                generated_faculty_slots=generated_faculty_slots,
            )

            try:
                candidate_members = _committee_pick_members_for_supervisors(
                    faculty_groups,
                    supervisor_ids,
                    used_faculty_ids,
                    idx + attempt,
                    reserved_supervisor_ids,
                    unavailable_faculty_ids=unavailable_faculty_ids,
                )
            except ValueError:
                continue

            member_ids = [int(member["faculty_id"]) for member in candidate_members]
            member_conflicts = _committee_conflicting_faculty_ids(
                cursor,
                member_ids,
                discussion_date,
                candidate_start,
                candidate_end,
                generated_faculty_slots=generated_faculty_slots,
            )
            if member_conflicts:
                continue

            members = candidate_members
            committee_start_time = candidate_start
            last_slot_end = candidate_end
            break

        if members is None or committee_start_time is None or last_slot_end is None:
            raise ValueError(
                f"Could not schedule {course_label} Committee {idx + 1}. "
                "This usually means the selected date/time already has active committees for one of the required doctors, "
                "or there are not enough unused active doctors to keep every committee at exactly 4 members. "
                "Try Reset & Redistribute, choose another date/time, or increase Projects Per Committee so fewer committees are needed."
            )

        room = rooms[idx]
        committee_name = f"{course_label} Committee {idx + 1}"

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
                    committee_start_time,
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
                    committee_start_time,
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
                (plan_id, member["faculty_id"], "supervisor" if int(member["faculty_id"]) in {int(x) for x in supervisor_ids} else "member"),
            )

        for slot_index, project in enumerate(chunk, start=1):
            slot_start = _committee_time_add(committee_start_time, (slot_index - 1) * 40)
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
        # Readers are selected from the other supervisors in the same committee,
        # excluding the project/section supervisor.
        if '_committee_auto_assign_readers' in globals():
            _committee_auto_assign_readers(cursor, plan_id, chunk, members, course_scope)
        if '_committee_send_notifications' in globals():
            _committee_send_notifications(cursor, plan_id, session.get("user_id"))

        generated_faculty_slots.append({
            "faculty_ids": {int(member["faculty_id"]) for member in members},
            "discussion_date": discussion_date,
            "start_time": committee_start_time,
            "end_time": last_slot_end,
        })

        for member in members:
            used_faculty_ids.add(int(member["faculty_id"]))

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
                COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS section_name,
                sec.supervisor_id,
                u_sup.full_name AS supervisor_name,
                COUNT(DISTINCT ss.student_id) AS student_count,
                COALESCE(
                    GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '),
                    ''
                ) AS assigned_students
            FROM student_distribution_sections sec
            LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
            LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users u_st ON u_st.user_id = st.user_id
            GROUP BY sec.section_id, sec.section_name, p_intro.title, sec.supervisor_id, u_sup.full_name
            ORDER BY section_name
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

        active_semester = _get_active_comp4200_semester(cursor)

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
              AND u.role = 'student'
              AND u.is_active = TRUE
              AND EXISTS (
                  SELECT 1
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                  WHERE pm.student_id = st.student_id
                    AND p.semester_id = %s
                    AND p.status = 'solo_pending'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM project_members pm
                  JOIN projects p ON p.project_id = pm.project_id
                  WHERE pm.student_id = st.student_id
                    AND p.semester_id = %s
                    AND p.status <> 'solo_pending'
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM section_students ss
                  WHERE ss.student_id = st.student_id
              )
        """, tuple(student_ids) + (
            active_semester["semester_id"],
            active_semester["semester_id"],
        ))

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

        try:
            if _table_exists(cursor, "comp4200_project_sections"):
                cursor.execute(
                    """
                    SELECT project_id
                    FROM comp4200_project_sections
                    WHERE section_id = %s
                    LIMIT 1
                    """,
                    (section_id,),
                )
                link = cursor.fetchone()
                if link and link.get("project_id"):
                    project_id = int(link["project_id"])
                    for student_id in student_ids:
                        cursor.execute(
                            """
                            DELETE p
                            FROM projects p
                            JOIN project_members pm ON pm.project_id = p.project_id
                            WHERE pm.student_id = %s
                              AND p.semester_id = %s
                              AND p.status = 'solo_pending'
                            """,
                            (student_id, active_semester["semester_id"]),
                        )
                        cursor.execute(
                            """
                            INSERT IGNORE INTO project_members
                                (project_id, student_id, is_primary_contact)
                            VALUES (%s, %s, 0)
                            """,
                            (project_id, student_id),
                        )
        except Exception:
            pass

        try:
            _notify_section_students(cursor, section_id, session.get("user_id"))
        except Exception:
            pass

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


@coordinator_bp.route("/api/coordinator/groups-with-space", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_groups_with_space():
    """Return submitted project groups that have fewer than 3 members (for adding solo students)."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_comp4200_semester(cursor)
        if not semester:
            cursor.close(); db.close()
            return jsonify({"groups": []})

        group_name_expr = (
            "COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id))"
            if _db_column_exists(cursor, "projects", "group_name")
            else "CONCAT('Group ', p.project_id)"
        )

        cursor.execute(f"""
            SELECT p.project_id,
                   {group_name_expr} AS group_name,
                   p.title,
                   p.supervisor_id,
                   u_sup.role AS supervisor_role,
                   GROUP_CONCAT(u.full_name ORDER BY pm.is_primary_contact DESC SEPARATOR ', ') AS team_members,
                   COUNT(pm.student_id) AS member_count
            FROM projects p
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
            WHERE p.semester_id = %s
              AND p.status = 'submitted'
            GROUP BY p.project_id, p.title, p.supervisor_id, u_sup.role
            HAVING member_count < 3
            ORDER BY p.project_id DESC
        """, (semester["semester_id"],))

        groups = cursor.fetchall()
        anchor = _get_anchor_semester_for_year(cursor, semester["academic_year"])
        anchor_semester_id = anchor["semester_id"] if anchor else None
        for group in groups:
            supervisor_id = group.get("supervisor_id")
            if supervisor_id:
                snapshot = _faculty_load_snapshot(
                    cursor,
                    int(supervisor_id),
                    semester["academic_year"],
                    anchor_semester_id,
                    "COMP4200",
                )
                group["supervisor_wanted_hours"] = snapshot["wanted_hours"]
                group["supervisor_remaining_hours"] = snapshot["remaining_hours"]
                load_exempt = group.get("supervisor_role") in {
                    "coordinator",
                    "head_of_department",
                }
                group["supervisor_can_take_one_student"] = (
                    load_exempt
                    or (snapshot["wanted_hours"] > 0 and snapshot["remaining_hours"] >= 0.5)
                )
            else:
                group["supervisor_wanted_hours"] = 0.0
                group["supervisor_remaining_hours"] = 0.0
                group["supervisor_can_take_one_student"] = False
        cursor.close(); db.close()
        return jsonify({"groups": groups})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/groups/add-student", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_add_student_to_group():
    """Add unassigned solo student(s) to an existing submitted project group."""
    data = request.get_json(silent=True) or {}
    project_id = data.get("project_id")
    student_ids = data.get("student_ids") or []

    if not project_id or not student_ids:
        return jsonify({"error": "project_id and student_ids are required."}), 400

    try:
        project_id = int(project_id)
        student_ids = sorted({int(student_id) for student_id in student_ids})
    except Exception:
        return jsonify({"error": "Invalid project or student id."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        semester = _get_active_comp4200_semester(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active COMP4200 semester found."}), 400

        # Verify the target is an active COMP4200 submitted group.
        cursor.execute(
            """
            SELECT project_id, status, semester_id, supervisor_id
            FROM projects
            WHERE project_id = %s
              AND semester_id = %s
              AND status = 'submitted'
            """,
            (project_id, semester["semester_id"]),
        )
        project = cursor.fetchone()
        if not project:
            cursor.close(); db.close()
            return jsonify({"error": "Active COMP4200 submitted group not found."}), 400

        if not project.get("supervisor_id"):
            cursor.close()
            db.close()
            return jsonify({"error": "This group has no supervisor assigned."}), 400

        # Check current member count
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM project_members WHERE project_id = %s", (project_id,)
        )
        current_count = cursor.fetchone()["cnt"]

        if current_count + len(student_ids) > 3:
            cursor.close(); db.close()
            return jsonify({"error": f"Adding {len(student_ids)} student(s) would exceed 3 members."}), 400

        anchor = _get_anchor_semester_for_year(cursor, semester["academic_year"])
        anchor_semester_id = anchor["semester_id"] if anchor else None
        snapshot = _faculty_load_snapshot(
            cursor,
            int(project["supervisor_id"]),
            semester["academic_year"],
            anchor_semester_id,
            "COMP4200",
        )
        required_hours = len(student_ids) * 0.5
        load_exempt = _faculty_load_exempt_for_assignment(
            cursor,
            int(project["supervisor_id"]),
        )
        if (
            not load_exempt
            and (snapshot["wanted_hours"] <= 0 or snapshot["remaining_hours"] < required_hours)
        ):
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": (
                            f"This group's supervisor is not available for more students. "
                            f"Required load: {required_hours:.1f} hour(s), "
                            f"remaining load: {snapshot['remaining_hours']:.1f} hour(s)."
                        )
                    }
                ),
                400,
            )

        existing_member_user_ids = _project_student_user_ids(cursor, project_id)
        added = []
        for student_id in student_ids:
            # Only a student who explicitly registered solo can be moved into a group.
            cursor.execute("""
                SELECT p.project_id
                FROM projects p
                JOIN project_members pm ON pm.project_id = p.project_id
                JOIN students st ON st.student_id = pm.student_id
                JOIN users u ON u.user_id = st.user_id
                WHERE pm.student_id = %s
                  AND p.semester_id = %s
                  AND p.status = 'solo_pending'
                  AND u.role = 'student'
                  AND u.is_active = TRUE
                  AND NOT EXISTS (
                      SELECT 1
                      FROM section_students ss
                      WHERE ss.student_id = pm.student_id
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM project_members other_pm
                      JOIN projects other_p ON other_p.project_id = other_pm.project_id
                      WHERE other_pm.student_id = pm.student_id
                        AND other_p.semester_id = p.semester_id
                        AND other_p.status <> 'solo_pending'
                  )
                LIMIT 1
            """, (student_id, project["semester_id"]))
            solo = cursor.fetchone()
            if not solo:
                db.rollback()
                cursor.close()
                db.close()
                return jsonify({"error": "One or more selected students are not waiting as solo registrations."}), 400

            cursor.execute(
                "DELETE FROM projects WHERE project_id = %s AND status = 'solo_pending'",
                (solo["project_id"],),
            )

            cursor.execute(
                "INSERT INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, 0)",
                (project_id, student_id),
            )
            added.append(student_id)

        _ensure_comp4200_section_schema(cursor)
        _committee_sync_comp4200_project_sections(cursor, semester["semester_id"])

        group_name_expr = (
            "COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id))"
            if _db_column_exists(cursor, "projects", "group_name")
            else "CONCAT('Group ', p.project_id)"
        )
        cursor.execute(
            f"""
            SELECT {group_name_expr} AS group_name,
                   p.title,
                   COALESCE(u_sup.full_name, 'Not assigned yet') AS supervisor_name,
                   COALESCE(
                       GROUP_CONCAT(
                           u_student.full_name
                           ORDER BY pm.is_primary_contact DESC, u_student.full_name
                           SEPARATOR ', '
                       ),
                       ''
                   ) AS team_members
            FROM projects p
            LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u_student ON u_student.user_id = st.user_id
            WHERE p.project_id = %s
            GROUP BY p.project_id, p.title, u_sup.full_name
            """,
            (project_id,),
        )
        group = cursor.fetchone() or {}
        group_name = group.get("group_name") or f"Group {project_id}"
        project_title = group.get("title") or "Not specified"
        supervisor_name = group.get("supervisor_name") or "Not assigned yet"
        team_members = group.get("team_members") or "Not listed yet"

        placeholders = ",".join(["%s"] * len(added))
        cursor.execute(
            f"""
            SELECT u.user_id, u.full_name
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.student_id IN ({placeholders})
            """,
            tuple(added),
        )
        added_students = cursor.fetchall()
        added_names = ", ".join(student["full_name"] for student in added_students)

        for student in added_students:
            _insert_notification(
                cursor,
                student["user_id"],
                session.get("user_id"),
                "system",
                "You Have Been Added to a Project Team",
                (
                    f"You have been added to team: {group_name}.\n"
                    f"Project: {project_title}.\n"
                    f"Supervisor: {supervisor_name}.\n"
                    f"Team members: {team_members}."
                ),
                project_id,
                "introduction",
            )

        joined_verb = "has" if len(added_students) == 1 else "have"
        for recipient_id in existing_member_user_ids:
            _insert_notification(
                cursor,
                recipient_id,
                session.get("user_id"),
                "system",
                "New Team Member Added",
                (
                    f"{added_names} {joined_verb} been added to your team: {group_name}.\n"
                    f"Project: {project_title}.\n"
                    f"Supervisor: {supervisor_name}.\n"
                    f"Team members: {team_members}."
                ),
                project_id,
                "introduction",
            )

        db.commit()
        cursor.close(); db.close()
        return jsonify({"ok": True, "message": f"Added {len(added)} student(s) to the group successfully."})
    except Exception as e:
        try:
            db.rollback()
            cursor.close()
            db.close()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


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
                COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS section_name,
                sec.supervisor_id,
                u.full_name AS supervisor_name
            FROM student_distribution_sections sec
            LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
            LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
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
    try:
        projects_per_committee = int(data.get("projects_per_committee") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Projects/sections per committee must be a number."}), 400

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

    db = None
    cursor = None
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
    except ValueError as e:
        message = str(e)
        if (
            cursor
            and db
            and (
                message.startswith("No eligible ")
                or "already have committees" in message
            )
        ):
            payload = _committee_dashboard_payload(cursor)
            payload["message"] = message
            payload["warning"] = True
            db.commit()
            cursor.close()
            db.close()
            return jsonify(_json_safe_value(payload))
        if db:
            db.rollback()
        if cursor:
            cursor.close()
        if db:
            db.close()
        return jsonify({"error": message}), 400
    except Exception as e:
        if db:
            db.rollback()
        if cursor:
            cursor.close()
        if db:
            db.close()
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/committee-reset", methods=["POST"])
@login_required(role="coordinator")
def api_committee_reset():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "graduation_project").strip()
    discussion_date = (data.get("discussion_date") or "").strip()
    start_time = (data.get("start_time") or "").strip()
    try:
        projects_per_committee = int(data.get("projects_per_committee") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Projects/sections per committee must be a number."}), 400

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

    db = None
    cursor = None
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
    except ValueError as e:
        message = str(e)
        if (
            cursor
            and db
            and (
                message.startswith("No eligible ")
                or "already have committees" in message
            )
        ):
            payload = _committee_dashboard_payload(cursor)
            payload["message"] = message
            payload["warning"] = True
            db.commit()
            cursor.close()
            db.close()
            return jsonify(_json_safe_value(payload))
        if db:
            db.rollback()
        if cursor:
            cursor.close()
        if db:
            db.close()
        return jsonify({"error": message}), 400
    except Exception as e:
        if db:
            db.rollback()
        if cursor:
            cursor.close()
        if db:
            db.close()
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
            SELECT cpm.faculty_id, cpm.role
            FROM committee_plan_members cpm
            JOIN faculty f ON f.faculty_id = cpm.faculty_id
            JOIN users u ON u.user_id = f.user_id
            WHERE cpm.plan_id = %s
              AND cpm.faculty_id = %s
              AND u.role IN ('supervisor', 'coordinator', 'head_of_department')
              AND u.is_active = TRUE
            """,
            (plan_id, faculty_id),
        )
        member_row = cursor.fetchone()
        if not member_row:
            cursor.close()
            db.close()
            return jsonify({"error": "Responsible supervisor must be one of the committee members."}), 400

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
        # If the selected responsible supervisor is the item supervisor, keep role='supervisor'
        # and rely on committee_plans.responsible_faculty_id to mark them responsible.
        # Otherwise mark the selected non-supervisor member as responsible.
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
            "eligible_sections_4200": _json_safe_rows(payload.get("eligible_sections_4200", [])),
            "eligible_projects_4300": _json_safe_rows(payload.get("eligible_projects_4300", [])),
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
        return jsonify({"error": "Reader 1 and Reader 2 must be different supervisors."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _committee_ensure_report_readers_table(cursor)

        cursor.execute(
            """
            SELECT cpp.project_id, p.supervisor_id
            FROM committee_plan_projects cpp
            JOIN projects p ON p.project_id = cpp.project_id
            WHERE cpp.plan_id = %s AND cpp.project_id = %s
            """,
            (plan_id, project_id),
        )
        project_row = cursor.fetchone()
        if not project_row:
            cursor.close()
            db.close()
            return jsonify({"error": "This project does not belong to this committee."}), 404

        supervisor_id = int(project_row.get("supervisor_id") or 0)
        if reader1_id == supervisor_id or reader2_id == supervisor_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Report readers must be different from the project supervisor."}), 400

        placeholders = "%s,%s"
        cursor.execute(
            f"""
            SELECT cpm.faculty_id
            FROM committee_plan_members cpm
            JOIN faculty f ON f.faculty_id = cpm.faculty_id
            JOIN users u ON u.user_id = f.user_id
            WHERE cpm.plan_id = %s
              AND cpm.faculty_id IN ({placeholders})
              AND u.role IN ('supervisor', 'coordinator', 'head_of_department')
              AND u.is_active = TRUE
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


@coordinator_bp.route(
    "/api/coordinator/committee/<int:plan_id>/section/<int:section_id>/readers",
    methods=["POST"],
)
@login_required(role="coordinator")
def api_committee_save_section_readers(plan_id, section_id):
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
        return jsonify({"error": "Reader 1 and Reader 2 must be different supervisors."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _committee_ensure_report_readers_table(cursor)

        cursor.execute(
            """
            SELECT cps.section_id, sec.supervisor_id
            FROM committee_plan_sections cps
            JOIN student_distribution_sections sec ON sec.section_id = cps.section_id
            WHERE cps.plan_id = %s AND cps.section_id = %s
            """,
            (plan_id, section_id),
        )
        section_row = cursor.fetchone()
        if not section_row:
            cursor.close()
            db.close()
            return jsonify({"error": "This section does not belong to this committee."}), 404

        supervisor_id = int(section_row.get("supervisor_id") or 0)
        if reader1_id == supervisor_id or reader2_id == supervisor_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Report readers must be different from the section supervisor."}), 400

        cursor.execute(
            """
            SELECT cpm.faculty_id
            FROM committee_plan_members cpm
            JOIN faculty f ON f.faculty_id = cpm.faculty_id
            JOIN users u ON u.user_id = f.user_id
            WHERE cpm.plan_id = %s
              AND cpm.faculty_id IN (%s, %s)
              AND u.role IN ('supervisor', 'coordinator', 'head_of_department')
              AND u.is_active = TRUE
            """,
            (plan_id, reader1_id, reader2_id),
        )
        found = {int(row["faculty_id"]) for row in cursor.fetchall()}
        if reader1_id not in found or reader2_id not in found:
            cursor.close()
            db.close()
            return jsonify({"error": "Report readers must be selected from this committee members."}), 400

        cursor.execute("DELETE FROM section_report_readers WHERE section_id = %s", (section_id,))
        cursor.execute(
            """
            INSERT INTO section_report_readers (section_id, faculty_id, reader_order)
            VALUES (%s, %s, 1), (%s, %s, 2)
            """,
            (section_id, reader1_id, section_id, reader2_id),
        )

        db.commit()
        payload = _committee_dashboard_payload(cursor)
        cursor.close()
        db.close()

        return jsonify({
            "message": "Section report readers saved successfully.",
            "plans": _json_safe_rows(payload["plans"]),
            "current_committees": _json_safe_rows(payload["current_committees"]),
            "eligible_projects": _json_safe_rows(payload["eligible_projects"]),
            "eligible_sections_4200": _json_safe_rows(payload.get("eligible_sections_4200", [])),
            "eligible_projects_4300": _json_safe_rows(payload.get("eligible_projects_4300", [])),
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_final_results (
            result_id INT PRIMARY KEY AUTO_INCREMENT,
            course_scope ENUM('introduction','graduation_project') NOT NULL,
            reference_id INT NOT NULL,
            report_score DECIMAL(6,2) NULL,
            supervisor_score DECIMAL(6,2) NULL,
            coordinator_score DECIMAL(6,2) NULL,
            discussion_score DECIMAL(6,2) NULL,
            committee_score DECIMAL(6,2) NULL,
            final_score DECIMAL(6,2) NULL,
            decision ENUM('pending','accepted','rejected','archived') NOT NULL DEFAULT 'pending',
            notes TEXT NULL,
            workflow_status ENUM('draft','sent_to_supervisor','sent_to_head','published_to_students') NOT NULL DEFAULT 'draft',
            sent_by_coordinator INT NULL,
            sent_to_supervisor_at DATETIME NULL,
            supervisor_id INT NULL,
            supervisor_sent_by INT NULL,
            supervisor_sent_to_head_at DATETIME NULL,
            head_published_by INT NULL,
            head_published_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_eval_final_reference (course_scope, reference_id),
            INDEX idx_eval_final_workflow (workflow_status),
            INDEX idx_eval_final_supervisor (supervisor_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    if not _db_column_exists(cursor, "evaluation_final_results", "coordinator_score"):
        cursor.execute(
            """
            ALTER TABLE evaluation_final_results
            ADD COLUMN coordinator_score DECIMAL(6,2) NULL AFTER supervisor_score
            """
        )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_student_scores (
            score_id INT PRIMARY KEY AUTO_INCREMENT,
            course_scope ENUM('introduction','graduation_project') NOT NULL,
            reference_id INT NOT NULL,
            student_id INT NOT NULL,
            report_score DECIMAL(6,2) NULL,
            supervisor_score DECIMAL(6,2) NULL,
            coordinator_score DECIMAL(6,2) NULL,
            discussion_score DECIMAL(6,2) NULL,
            committee_score DECIMAL(6,2) NULL,
            calculated_final_score DECIMAL(6,2) NULL,
            final_score DECIMAL(6,2) NULL,
            manual_override BOOLEAN NOT NULL DEFAULT FALSE,
            decision ENUM('pending','accepted','rejected','archived') NOT NULL DEFAULT 'pending',
            notes TEXT NULL,
            updated_by INT NULL,
            synced_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_eval_student_score (course_scope, reference_id, student_id),
            INDEX idx_eval_student_score_ref (course_scope, reference_id),
            INDEX idx_eval_student_score_student (student_id),
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    student_score_columns = {
        "report_score": "ALTER TABLE evaluation_student_scores ADD COLUMN report_score DECIMAL(6,2) NULL AFTER student_id",
        "supervisor_score": "ALTER TABLE evaluation_student_scores ADD COLUMN supervisor_score DECIMAL(6,2) NULL AFTER report_score",
        "coordinator_score": "ALTER TABLE evaluation_student_scores ADD COLUMN coordinator_score DECIMAL(6,2) NULL AFTER supervisor_score",
        "discussion_score": "ALTER TABLE evaluation_student_scores ADD COLUMN discussion_score DECIMAL(6,2) NULL AFTER coordinator_score",
        "committee_score": "ALTER TABLE evaluation_student_scores ADD COLUMN committee_score DECIMAL(6,2) NULL AFTER discussion_score",
        "calculated_final_score": "ALTER TABLE evaluation_student_scores ADD COLUMN calculated_final_score DECIMAL(6,2) NULL AFTER committee_score",
        "final_score": "ALTER TABLE evaluation_student_scores ADD COLUMN final_score DECIMAL(6,2) NULL AFTER calculated_final_score",
        "manual_override": "ALTER TABLE evaluation_student_scores ADD COLUMN manual_override BOOLEAN NOT NULL DEFAULT FALSE AFTER final_score",
        "decision": "ALTER TABLE evaluation_student_scores ADD COLUMN decision ENUM('pending','accepted','rejected','archived') NOT NULL DEFAULT 'pending' AFTER manual_override",
        "notes": "ALTER TABLE evaluation_student_scores ADD COLUMN notes TEXT NULL AFTER decision",
        "updated_by": "ALTER TABLE evaluation_student_scores ADD COLUMN updated_by INT NULL AFTER notes",
        "synced_at": "ALTER TABLE evaluation_student_scores ADD COLUMN synced_at DATETIME NULL AFTER updated_by",
    }
    for column_name, alter_sql in student_score_columns.items():
        if not _db_column_exists(cursor, "evaluation_student_scores", column_name):
            cursor.execute(alter_sql)

    _ensure_evaluation_student_task_score_schema(cursor)


def _ensure_evaluation_student_task_score_schema(cursor):
    """Create/repair the per-student marks table used by doctors and coordinator."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_student_task_scores (
            id INT PRIMARY KEY AUTO_INCREMENT,
            task_id INT NOT NULL,
            student_id INT NOT NULL,
            mark DECIMAL(6,2) NULL,
            notes TEXT NULL,
            is_submitted BOOLEAN NOT NULL DEFAULT FALSE,
            submitted_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_eval_task_student (task_id, student_id),
            INDEX idx_eval_task_student_task (task_id),
            INDEX idx_eval_task_student_student (student_id),
            FOREIGN KEY (task_id) REFERENCES evaluation_grade_tasks(task_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    repair_columns = {
        "mark": "ALTER TABLE evaluation_student_task_scores ADD COLUMN mark DECIMAL(6,2) NULL AFTER student_id",
        "notes": "ALTER TABLE evaluation_student_task_scores ADD COLUMN notes TEXT NULL AFTER mark",
        "is_submitted": "ALTER TABLE evaluation_student_task_scores ADD COLUMN is_submitted BOOLEAN NOT NULL DEFAULT FALSE AFTER notes",
        "submitted_at": "ALTER TABLE evaluation_student_task_scores ADD COLUMN submitted_at DATETIME NULL AFTER is_submitted",
    }
    for column_name, alter_sql in repair_columns.items():
        if not _db_column_exists(cursor, "evaluation_student_task_scores", column_name):
            cursor.execute(alter_sql)


def _ensure_student_course_results_score_schema(cursor):
    if not _table_exists(cursor, "student_course_results"):
        return False
    if not _db_column_exists(cursor, "student_course_results", "final_score"):
        cursor.execute(
            """
            ALTER TABLE student_course_results
            ADD COLUMN final_score DECIMAL(6,2) NULL AFTER status
            """
        )
    return True


def _sync_comp4300_project_course_results(cursor, project_id, status, final_score, notes, updated_by):
    if not _ensure_student_course_results_score_schema(cursor):
        return 0

    cursor.execute(
        """
        INSERT INTO student_course_results
            (student_id, semester_id, status, final_score, updated_by, notes)
        SELECT DISTINCT pm.student_id, p.semester_id, %s, %s, %s,
               COALESCE(%s, 'COMP4300 final grade saved.')
        FROM projects p
        JOIN project_members pm ON pm.project_id = p.project_id
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE p.project_id = %s
          AND sem.course_code = 'COMP4300'
        ON DUPLICATE KEY UPDATE
            status = VALUES(status),
            final_score = VALUES(final_score),
            updated_by = VALUES(updated_by),
            notes = VALUES(notes),
            updated_at = CURRENT_TIMESTAMP
        """,
        (status, final_score, updated_by, notes, project_id),
    )
    return cursor.rowcount


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
    # COMP4200: two report readers + coordinator + supervisor + four discussion members.
    # COMP4300: two report readers + supervisor + four committee members.
    return 8 if course_scope == "introduction" else 7


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



def _evaluation_current_coordinator_faculty_id(cursor):
    """Return faculty_id for the logged-in coordinator so they can enter /10 coordinator mark."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    cursor.execute(
        """
        SELECT f.faculty_id
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.user_id = %s
          AND u.role IN ('coordinator', 'supervisor', 'head_of_department')
          AND u.is_active = TRUE
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone() or {}
    return row.get("faculty_id")

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


def _evaluation_committee_setup_for_item(cursor, course_scope, reference_id):
    """
    Return the exact committee setup for one evaluation item.

    This function is intentionally strict:
    - The item must belong to a committee plan.
    - The committee must have a responsible doctor selected.
    - Reader 1 and Reader 2 must be saved from the Committee page.
    - Readers must be committee members and must not be the item supervisor.
    - Evaluation tasks are built only from this returned setup.
    """
    _committee_ensure_course_schema(cursor)
    _committee_ensure_report_readers_table(cursor)

    reference_id = int(reference_id)

    if course_scope == "graduation_project":
        cursor.execute(
            """
            SELECT
                cp.plan_id,
                cp.committee_name,
                COALESCE(cp.course_scope, 'graduation_project') AS course_scope,
                cp.responsible_faculty_id,
                p.project_id AS reference_id,
                p.title,
                p.supervisor_id,
                sup_u.full_name AS supervisor_name
            FROM committee_plan_projects cpp
            JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
            JOIN projects p ON p.project_id = cpp.project_id
            LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
            LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
            WHERE cpp.project_id = %s
              AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
              AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
            ORDER BY cp.plan_id DESC
            LIMIT 1
            """,
            (reference_id,),
        )
        item = cursor.fetchone()
        reader_table = "project_report_readers"
        reader_key = "project_id"
        reader_component = "grad_report_reader"
        supervisor_component = "grad_supervisor"
        committee_component = "grad_committee_member"
        item_label = "project"
    else:
        cursor.execute(
            """
            SELECT
                cp.plan_id,
                cp.committee_name,
                COALESCE(cp.course_scope, 'introduction') AS course_scope,
                cp.responsible_faculty_id,
                sec.section_id AS reference_id,
                COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS title,
                sec.supervisor_id,
                sup_u.full_name AS supervisor_name
            FROM committee_plan_sections cps
            JOIN committee_plans cp ON cp.plan_id = cps.plan_id
            JOIN student_distribution_sections sec ON sec.section_id = cps.section_id
            LEFT JOIN comp4200_project_sections cps_title ON cps_title.section_id = sec.section_id
            LEFT JOIN projects p_intro ON p_intro.project_id = cps_title.project_id
            LEFT JOIN faculty sup_f ON sup_f.faculty_id = sec.supervisor_id
            LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
            WHERE cps.section_id = %s
              AND COALESCE(cp.course_scope, 'introduction') = 'introduction'
              AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
            ORDER BY cp.plan_id DESC
            LIMIT 1
            """,
            (reference_id,),
        )
        item = cursor.fetchone()
        reader_table = "section_report_readers"
        reader_key = "section_id"
        reader_component = "intro_report_reader"
        supervisor_component = "intro_supervisor"
        committee_component = "intro_discussion_member"
        item_label = "section"

    if not item:
        return {
            "ok": False,
            "error": f"Create/generate a committee for this {item_label} first.",
            "status": 400,
        }

    plan_id = item.get("plan_id")
    supervisor_id = item.get("supervisor_id")
    responsible_id = item.get("responsible_faculty_id")

    if not supervisor_id:
        return {
            "ok": False,
            "error": f"This {item_label} has no supervisor assigned.",
            "status": 400,
        }

    cursor.execute(
        """
        SELECT DISTINCT cpm.faculty_id, cpm.role, u.full_name
        FROM committee_plan_members cpm
        JOIN faculty f ON f.faculty_id = cpm.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE cpm.plan_id = %s
        ORDER BY
            CASE
                WHEN cpm.role = 'supervisor' THEN 0
                WHEN cpm.faculty_id = %s THEN 1
                ELSE 2
            END,
            u.full_name
        """,
        (plan_id, responsible_id),
    )
    members = cursor.fetchall()
    member_ids = [int(row["faculty_id"]) for row in members if row.get("faculty_id")]
    member_id_set = set(member_ids)

    if len(member_id_set) < 4:
        return {
            "ok": False,
            "error": "This committee must have 4 committee supervisors before opening evaluation.",
            "status": 400,
        }

    if int(supervisor_id) not in member_id_set:
        return {
            "ok": False,
            "error": "The item supervisor is not inside the selected committee. Regenerate/fix the committee first.",
            "status": 400,
        }

    if not responsible_id:
        return {
            "ok": False,
            "error": "Choose and save the Responsible Supervisor from the Committee page before opening grade entry.",
            "status": 400,
        }

    responsible_id = int(responsible_id)
    if responsible_id not in member_id_set:
        return {
            "ok": False,
            "error": "Responsible Supervisor must be one of this committee members.",
            "status": 400,
        }

    cursor.execute(
        f"""
        SELECT rr.faculty_id, rr.reader_order, u.full_name
        FROM {reader_table} rr
        JOIN faculty f ON f.faculty_id = rr.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE rr.{reader_key} = %s
        ORDER BY rr.reader_order ASC, rr.id ASC
        LIMIT 2
        """,
        (reference_id,),
    )
    readers = cursor.fetchall()
    reader_ids = [int(row["faculty_id"]) for row in readers if row.get("faculty_id")]

    if len(reader_ids) != 2 or len(set(reader_ids)) != 2:
        return {
            "ok": False,
            "error": "Choose and save Reader 1 and Reader 2 from the Committee page before opening grade entry.",
            "status": 400,
        }

    invalid_readers = [fid for fid in reader_ids if fid not in member_id_set]
    if invalid_readers:
        return {
            "ok": False,
            "error": "Reader 1 and Reader 2 must be selected from this same committee members.",
            "status": 400,
        }

    if int(supervisor_id) in set(reader_ids):
        return {
            "ok": False,
            "error": "Reader 1 and Reader 2 must be different from the item supervisor.",
            "status": 400,
        }

    return {
        "ok": True,
        "plan": item,
        "plan_id": int(plan_id),
        "title": item.get("title"),
        "supervisor_id": int(supervisor_id),
        "responsible_id": responsible_id,
        "members": members,
        "member_ids": member_ids,
        "reader_ids": reader_ids,
        "reader_component": reader_component,
        "supervisor_component": supervisor_component,
        "committee_component": committee_component,
    }


def _evaluation_autocreate_tasks(cursor, course_scope, reference_id, created_by=None):
    """
    Rebuild grade tasks from the CURRENT Committee page setup only.

    This fixes the mismatch where Evaluation could keep old doctors or choose
    fallback readers. On every Open Grade Entry action, old rows for this item
    are deleted, then new rows are created from:
    - saved committee members for the same plan_id
    - saved Reader 1 + Reader 2 for this exact project/section
    - the real supervisor of this exact project/section
    """
    setup = _evaluation_committee_setup_for_item(cursor, course_scope, reference_id)
    if not setup.get("ok"):
        raise ValueError(setup.get("error") or "Committee setup is incomplete.")

    reference_id = int(reference_id)

    # Once marks exist, never rebuild the task rows from the committee page.
    # Rebuilding at that point can erase submitted grades.
    cursor.execute(
        """
        SELECT evaluator_faculty_id
        FROM evaluation_grade_tasks
        WHERE course_scope = %s
          AND reference_id = %s
          AND (is_submitted = TRUE OR mark IS NOT NULL)
        """,
        (course_scope, reference_id),
    )
    submitted_faculty_ids = {
        int(row["evaluator_faculty_id"])
        for row in cursor.fetchall()
        if row.get("evaluator_faculty_id")
    }
    if submitted_faculty_ids:
        return submitted_faculty_ids

    # Critical: remove old/wrong rows first so Evaluation cannot display doctors
    # from an older committee or old reader assignment.
    cursor.execute(
        """
        DELETE FROM evaluation_grade_tasks
        WHERE course_scope = %s
          AND reference_id = %s
        """,
        (course_scope, reference_id),
    )

    created_faculty_ids = set()

    for fid in setup["reader_ids"]:
        _evaluation_insert_task(cursor, course_scope, reference_id, setup["reader_component"], fid, created_by)
        created_faculty_ids.add(int(fid))

    _evaluation_insert_task(cursor, course_scope, reference_id, setup["supervisor_component"], setup["supervisor_id"], created_by)
    created_faculty_ids.add(int(setup["supervisor_id"]))

    if course_scope == "introduction":
        coordinator_faculty_id = _evaluation_current_coordinator_faculty_id(cursor)
        if coordinator_faculty_id:
            _evaluation_insert_task(cursor, course_scope, reference_id, "intro_coordinator", coordinator_faculty_id, created_by)
            created_faculty_ids.add(int(coordinator_faculty_id))

    # The discussion/committee supervisors are exactly the committee members saved
    # for the current plan. No random doctors, no old tasks, no fallback.
    for fid in setup["member_ids"]:
        _evaluation_insert_task(cursor, course_scope, reference_id, setup["committee_component"], fid, created_by)
        created_faculty_ids.add(int(fid))

    return created_faculty_ids

def _evaluation_cleanup_tasks(cursor, course_scope, reference_id):
    """
    Remove old/wrong evaluation rows created by earlier versions.
    Important fixes:
    - COMP4200 keeps exactly one coordinator /10 grade task.
    - The real section supervisor must only have the supervisor component.
    - Keep only 2 report readers and 4 discussion/committee members.
    """
    reference_id = int(reference_id)

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
        "intro_coordinator": 1,
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
    task_ids = []
    for row in rows:
        row["task_id"] = int(row.get("task_id") or 0)
        row["max_mark"] = float(row.get("max_mark") or 0)
        row["mark"] = None if row.get("mark") is None else float(row.get("mark") or 0)
        row["is_submitted"] = bool(row.get("is_submitted"))
        row["shared_mark"] = row.get("component") in ("intro_report_reader", "grad_report_reader")
        row["student_marks"] = []
        if row.get("submitted_at") is not None:
            row["submitted_at"] = str(row["submitted_at"])
        if row["task_id"]:
            task_ids.append(row["task_id"])

    if task_ids and _table_exists(cursor, "evaluation_student_task_scores"):
        placeholders = ",".join(["%s"] * len(task_ids))
        cursor.execute(
            f"""
            SELECT ests.task_id, ests.student_id, ests.mark, ests.notes,
                   ests.is_submitted, ests.submitted_at,
                   u.full_name AS student_name, u.university_id, u.email
            FROM evaluation_student_task_scores ests
            JOIN students st ON st.student_id = ests.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE ests.task_id IN ({placeholders})
            ORDER BY u.full_name
            """,
            tuple(task_ids),
        )
        marks_by_task = {}
        for mark_row in cursor.fetchall():
            task_id = int(mark_row.get("task_id") or 0)
            marks_by_task.setdefault(task_id, []).append({
                "student_id": int(mark_row.get("student_id") or 0),
                "student_name": mark_row.get("student_name"),
                "university_id": mark_row.get("university_id"),
                "email": mark_row.get("email"),
                "max_mark": None,
                "mark": None if mark_row.get("mark") is None else float(mark_row.get("mark") or 0),
                "notes": mark_row.get("notes") or "",
                "is_submitted": bool(mark_row.get("is_submitted")),
                "submitted_at": str(mark_row.get("submitted_at") or ""),
            })
        for row in rows:
            row["student_marks"] = marks_by_task.get(int(row.get("task_id") or 0), [])
            for mark_row in row["student_marks"]:
                mark_row["max_mark"] = row["max_mark"]

    return rows


def _evaluation_scores_from_grades(course_scope, grades):
    def grade_submitted_values(grade):
        if not grade.get("is_submitted"):
            return []
        if grade.get("mark") is not None:
            return [float(grade.get("mark") or 0)]
        if grade.get("shared_mark"):
            return []

        student_marks = [
            float(mark_row.get("mark") or 0)
            for mark_row in (grade.get("student_marks") or [])
            if mark_row.get("is_submitted") and mark_row.get("mark") is not None
        ]
        return [(sum(student_marks) / len(student_marks))] if student_marks else []

    def submitted_marks(component):
        result = []
        for grade in grades:
            if grade.get("component") != component:
                continue
            result.extend(grade_submitted_values(grade))
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
    coordinator_avg_10 = avg(submitted_marks("intro_coordinator"))
    discussion_sum_40_values = submitted_marks("intro_discussion_member")
    discussion_sum_40 = sum(discussion_sum_40_values) if discussion_sum_40_values else None

    # COMP4200 distribution stays the same and adds Coordinator /10:
    # Report /40 + Supervisor /10 + Coordinator /10 + Discussion /40 = Final /100.
    final_score = None
    if (
        report_avg_40 is not None
        and supervisor_avg_10 is not None
        and coordinator_avg_10 is not None
        and discussion_sum_40 is not None
    ):
        final_score = report_avg_40 + supervisor_avg_10 + coordinator_avg_10 + discussion_sum_40

    return {
        "report_score": round(report_avg_40, 2) if report_avg_40 is not None else None,
        "supervisor_score": round(supervisor_avg_10, 2) if supervisor_avg_10 is not None else None,
        "coordinator_score": round(coordinator_avg_10, 2) if coordinator_avg_10 is not None else None,
        "discussion_score": round(discussion_sum_40, 2) if discussion_sum_40 is not None else None,
        "committee_score": None,
        "calculated_final_score": round(final_score, 2) if final_score is not None else None,
        "final_score": round(final_score, 2) if final_score is not None else None,
    }


def _evaluation_blank_scores():
    return {
        "report_score": None,
        "supervisor_score": None,
        "coordinator_score": None,
        "discussion_score": None,
        "committee_score": None,
        "calculated_final_score": None,
        "final_score": None,
    }


def _evaluation_item_students(cursor, course_scope, reference_id):
    """Return the students that belong to one COMP4200 section or COMP4300 project."""
    reference_id = int(reference_id)

    if course_scope == "graduation_project":
        if not _table_exists(cursor, "project_members"):
            return []
        cursor.execute(
            """
            SELECT
                st.student_id,
                u.user_id,
                u.full_name AS student_name,
                u.university_id,
                u.email
            FROM project_members pm
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE pm.project_id = %s
              AND u.role = 'student'
              AND u.is_active = TRUE
            ORDER BY pm.is_primary_contact DESC, u.full_name
            """,
            (reference_id,),
        )
    else:
        if not _table_exists(cursor, "section_students"):
            return []
        cursor.execute(
            """
            SELECT DISTINCT
                st.student_id,
                u.user_id,
                u.full_name AS student_name,
                u.university_id,
                u.email
            FROM section_students ss
            JOIN students st ON st.student_id = ss.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE ss.section_id = %s
              AND u.role = 'student'
              AND u.is_active = TRUE
            ORDER BY u.full_name
            """,
            (reference_id,),
        )

    return cursor.fetchall()


def _evaluation_saved_student_scores(cursor, course_scope, reference_id):
    cursor.execute(
        """
        SELECT
            student_id, report_score, supervisor_score, coordinator_score,
            discussion_score, committee_score, calculated_final_score, final_score,
            manual_override, decision, notes, updated_at
        FROM evaluation_student_scores
        WHERE course_scope = %s
          AND reference_id = %s
        """,
        (course_scope, int(reference_id)),
    )
    return {int(row["student_id"]): row for row in cursor.fetchall()}


def _evaluation_student_component_scores(cursor, course_scope, reference_id, fallback_scores=None):
    """Return component/final scores per student.

    Report reader marks are shared for the group. Supervisor, coordinator,
    discussion and committee marks are taken per student when available.
    """
    fallback_scores = fallback_scores or _evaluation_blank_scores()
    students = _evaluation_item_students(cursor, course_scope, reference_id)
    result = {
        int(student["student_id"]): {
            "report_score": fallback_scores.get("report_score"),
            "supervisor_score": None,
            "coordinator_score": None,
            "discussion_score": None,
            "committee_score": None,
            "calculated_final_score": None,
            "final_score": None,
        }
        for student in students
    }
    if not result:
        return result

    grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
    student_ids = set(result.keys())

    def avg(values):
        values = [float(v) for v in values if v is not None]
        return (sum(values) / len(values)) if values else None

    def task_shared_values(component):
        return [g.get("mark") for g in grades if g.get("component") == component and g.get("is_submitted") and g.get("mark") is not None]

    def task_student_map(component):
        values = {student_id: [] for student_id in student_ids}
        for grade in grades:
            if grade.get("component") != component or not grade.get("is_submitted"):
                continue
            marks = grade.get("student_marks") or []
            if marks:
                for mark_row in marks:
                    student_id = int(mark_row.get("student_id") or 0)
                    if student_id in values and mark_row.get("is_submitted") and mark_row.get("mark") is not None:
                        values[student_id].append(float(mark_row.get("mark") or 0))
            elif grade.get("mark") is not None:
                # Backward-compatible fallback for old single-mark submissions.
                for student_id in values:
                    values[student_id].append(float(grade.get("mark") or 0))
        return values

    if course_scope == "graduation_project":
        report = avg(task_shared_values("grad_report_reader"))
        supervisor_by_student = task_student_map("grad_supervisor")
        committee_by_student = task_student_map("grad_committee_member")
        for student_id, row in result.items():
            supervisor = avg(supervisor_by_student.get(student_id) or [])
            committee_avg_25 = avg(committee_by_student.get(student_id) or [])
            committee_score_50 = committee_avg_25 * 2 if committee_avg_25 is not None else None
            final = None
            if report is not None and supervisor is not None and committee_score_50 is not None:
                final = report + supervisor + committee_score_50
            row.update({
                "report_score": round(report, 2) if report is not None else None,
                "supervisor_score": round(supervisor, 2) if supervisor is not None else None,
                "coordinator_score": None,
                "discussion_score": None,
                "committee_score": round(committee_score_50, 2) if committee_score_50 is not None else None,
                "calculated_final_score": round(final, 2) if final is not None else None,
                "final_score": round(final, 2) if final is not None else None,
            })
        return result

    report = avg(task_shared_values("intro_report_reader"))
    supervisor_by_student = task_student_map("intro_supervisor")
    coordinator_by_student = task_student_map("intro_coordinator")
    discussion_by_student = task_student_map("intro_discussion_member")

    # Coordinator marks are also stored in evaluation_student_scores by the coordinator page.
    saved = _evaluation_saved_student_scores(cursor, course_scope, reference_id)

    for student_id, row in result.items():
        supervisor = avg(supervisor_by_student.get(student_id) or [])
        coordinator = avg(coordinator_by_student.get(student_id) or [])
        saved_coordinator = (saved.get(student_id) or {}).get("coordinator_score")
        if saved_coordinator is not None:
            coordinator = float(saved_coordinator)
        discussion_marks = discussion_by_student.get(student_id) or []
        discussion = sum(discussion_marks) if discussion_marks else None
        final = None
        if report is not None and supervisor is not None and coordinator is not None and discussion is not None:
            final = report + supervisor + coordinator + discussion
        row.update({
            "report_score": round(report, 2) if report is not None else None,
            "supervisor_score": round(supervisor, 2) if supervisor is not None else None,
            "coordinator_score": round(coordinator, 2) if coordinator is not None else None,
            "discussion_score": round(discussion, 2) if discussion is not None else None,
            "committee_score": None,
            "calculated_final_score": round(final, 2) if final is not None else None,
            "final_score": round(final, 2) if final is not None else None,
        })
    return result


def _evaluation_student_absence_counts(cursor, course_scope, students):
    """Return absence count per student for the selected course scope."""
    counts = {}
    for student in students or []:
        if student.get("student_id") is not None:
            counts[int(student.get("student_id"))] = 0

    if not students:
        return counts

    if not (_table_exists(cursor, "coordinator_lecture_attendance") and _table_exists(cursor, "coordinator_lectures")):
        return counts

    def normalize_name(value):
        raw = str(value or "").lower()
        raw = raw.replace("comp4200", " ").replace("comp4300", " ")
        raw = raw.replace("project introduction", " ").replace("graduation project", " ")
        tokens = re.findall(r"[a-z]+|\d+", raw)
        tokens = [t for t in tokens if t not in ("comp", "4200", "4300")]
        return "".join(tokens)

    def number_key(value):
        raw = str(value or "")
        raw = raw.replace("COMP4200", " ").replace("COMP4300", " ")
        nums = [n for n in re.findall(r"\d+", raw) if n not in ("4200", "4300")]
        return nums[-1].lstrip("0") if nums else ""

    by_student_id = {}
    by_user_id = {}
    by_university_id = {}
    by_email = {}
    by_name = {}
    by_number = {}

    for student in students:
        if student.get("student_id") is None:
            continue
        sid = int(student.get("student_id"))
        by_student_id[sid] = sid
        if student.get("user_id") is not None:
            by_user_id[int(student.get("user_id"))] = sid
        if student.get("university_id"):
            by_university_id[str(student.get("university_id")).strip().lower()] = sid
        if student.get("email"):
            by_email[str(student.get("email")).strip().lower()] = sid
        name_key = normalize_name(student.get("student_name"))
        if name_key:
            by_name[name_key] = sid
        num = number_key(student.get("student_name")) or number_key(student.get("university_id"))
        if num:
            by_number[num] = sid

    try:
        cursor.execute(
            """
            SELECT
                cla.student_id AS attendance_student_id,
                st.student_id AS real_student_id,
                st.user_id,
                u.full_name,
                u.university_id,
                u.email,
                COUNT(*) AS absent_count
            FROM coordinator_lecture_attendance cla
            JOIN coordinator_lectures cl ON cl.lecture_id = cla.lecture_id
            LEFT JOIN students st ON st.student_id = cla.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            WHERE cl.course_scope = %s
              AND LOWER(COALESCE(cla.attendance_status, '')) = 'absent'
            GROUP BY cla.student_id, st.student_id, st.user_id, u.full_name, u.university_id, u.email
            """,
            (course_scope,),
        )
        absence_rows = cursor.fetchall()
    except Exception:
        return counts

    for row in absence_rows:
        matched_sid = None

        attendance_sid = row.get("attendance_student_id")
        real_sid = row.get("real_student_id")
        user_id = row.get("user_id")
        university_id = str(row.get("university_id") or "").strip().lower()
        email = str(row.get("email") or "").strip().lower()
        name_key = normalize_name(row.get("full_name"))
        num = number_key(row.get("full_name")) or number_key(row.get("university_id"))

        for candidate in (attendance_sid, real_sid):
            if candidate is not None and int(candidate) in by_student_id:
                matched_sid = by_student_id[int(candidate)]
                break
        if matched_sid is None and user_id is not None and int(user_id) in by_user_id:
            matched_sid = by_user_id[int(user_id)]
        if matched_sid is None and university_id and university_id in by_university_id:
            matched_sid = by_university_id[university_id]
        if matched_sid is None and email and email in by_email:
            matched_sid = by_email[email]
        if matched_sid is None and name_key and name_key in by_name:
            matched_sid = by_name[name_key]
        if matched_sid is None and num and num in by_number:
            matched_sid = by_number[num]

        if matched_sid is not None:
            counts[matched_sid] = int(counts.get(matched_sid, 0) or 0) + int(row.get("absent_count") or 0)

    return counts


def _evaluation_student_score_rows(cursor, course_scope, reference_id, scores=None):
    """Build the per-student grade payload used by coordinator/evaluation.html."""
    scores = scores or _evaluation_blank_scores()
    students = _evaluation_item_students(cursor, course_scope, reference_id)
    saved = _evaluation_saved_student_scores(cursor, course_scope, reference_id)
    per_student_components = _evaluation_student_component_scores(cursor, course_scope, reference_id, scores)
    absence_counts = _evaluation_student_absence_counts(cursor, course_scope, students)

    rows = []
    for student in students:
        student_id = int(student["student_id"])
        existing = saved.get(student_id) or {}
        calculated = per_student_components.get(student_id) or {}

        def pick(field):
            saved_value = existing.get(field)
            if saved_value is not None:
                return saved_value
            calculated_value = calculated.get(field)
            return calculated_value if calculated_value is not None else scores.get(field)

        calculated_final = calculated.get("calculated_final_score")
        if calculated_final is None:
            calculated_final = existing.get("calculated_final_score")
        if calculated_final is None:
            calculated_final = scores.get("calculated_final_score")

        final_score = existing.get("final_score")
        if final_score is None or not bool(existing.get("manual_override") or False):
            final_score = calculated.get("final_score") if calculated.get("final_score") is not None else final_score
        if final_score is None:
            final_score = scores.get("final_score")

        row = {
            "student_id": student_id,
            "user_id": student.get("user_id"),
            "student_name": student.get("student_name"),
            "university_id": student.get("university_id"),
            "email": student.get("email"),
            "absence_count": int(absence_counts.get(student_id, 0) or 0),
            "report_score": pick("report_score"),
            "supervisor_score": pick("supervisor_score"),
            "coordinator_score": pick("coordinator_score"),
            "discussion_score": pick("discussion_score"),
            "committee_score": pick("committee_score"),
            "calculated_final_score": calculated_final,
            "final_score": final_score,
            "manual_override": bool(existing.get("manual_override") or False),
            "decision": existing.get("decision") or "pending",
            "notes": existing.get("notes") or "",
            "updated_at": str(existing.get("updated_at") or ""),
        }

        for key in (
            "report_score", "supervisor_score", "coordinator_score",
            "discussion_score", "committee_score", "calculated_final_score", "final_score"
        ):
            if row.get(key) is not None:
                row[key] = float(row[key])

        rows.append(row)

    return rows


def _evaluation_sync_individual_student_scores(cursor, course_scope, reference_id, scores, updated_by=None, notes=None):
    """
    Store one grade row per student.

    Existing manual overrides are preserved. Component/calculated scores are
    refreshed from the per-student task marks. Report remains shared.
    """
    students = _evaluation_item_students(cursor, course_scope, reference_id)
    if not students:
        return 0

    per_student = _evaluation_student_component_scores(cursor, course_scope, reference_id, scores)
    changed = 0

    for student in students:
        student_id = int(student["student_id"])
        row = per_student.get(student_id) or scores
        final_score = row.get("final_score")
        calculated_final_score = row.get("calculated_final_score", final_score)
        cursor.execute(
            """
            INSERT INTO evaluation_student_scores
                (course_scope, reference_id, student_id, report_score, supervisor_score,
                 coordinator_score, discussion_score, committee_score, calculated_final_score,
                 final_score, manual_override, notes, updated_by, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                report_score = VALUES(report_score),
                supervisor_score = VALUES(supervisor_score),
                coordinator_score = VALUES(coordinator_score),
                discussion_score = VALUES(discussion_score),
                committee_score = VALUES(committee_score),
                calculated_final_score = VALUES(calculated_final_score),
                final_score = IF(manual_override = TRUE, final_score, VALUES(final_score)),
                notes = COALESCE(VALUES(notes), notes),
                updated_by = VALUES(updated_by),
                synced_at = NOW()
            """,
            (
                course_scope,
                int(reference_id),
                student_id,
                row.get("report_score"),
                row.get("supervisor_score"),
                row.get("coordinator_score"),
                row.get("discussion_score"),
                row.get("committee_score"),
                calculated_final_score,
                final_score,
                notes or None,
                updated_by,
            ),
        )
        changed += 1

    return changed


def _evaluation_student_final_scores_map(cursor, course_scope, reference_id, scores=None):
    rows = _evaluation_student_score_rows(cursor, course_scope, reference_id, scores)
    return {int(row["student_id"]): row.get("final_score") for row in rows}


def _evaluation_item_student_ids(cursor, course_scope, reference_id):
    return [
        int(row["student_id"])
        for row in _evaluation_item_students(cursor, course_scope, reference_id)
        if row.get("student_id") is not None
    ]


def _evaluation_mark_student_scores_decision(cursor, course_scope, reference_id, decision, updated_by=None, notes=None):
    cursor.execute(
        """
        UPDATE evaluation_student_scores
        SET decision = %s,
            notes = COALESCE(%s, notes),
            updated_by = %s
        WHERE course_scope = %s
          AND reference_id = %s
        """,
        (decision, notes, updated_by, course_scope, int(reference_id)),
    )
    return cursor.rowcount


def _sync_comp4300_project_individual_course_results(cursor, project_id, status, default_final_score, notes, updated_by, student_scores=None):
    """Sync COMP4300 course results using each student's own final score."""
    if not _ensure_student_course_results_score_schema(cursor):
        return 0

    student_scores = student_scores or {}
    cursor.execute(
        """
        SELECT DISTINCT pm.student_id, p.semester_id
        FROM projects p
        JOIN project_members pm ON pm.project_id = p.project_id
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE p.project_id = %s
          AND sem.course_code = 'COMP4300'
        """,
        (int(project_id),),
    )
    rows = cursor.fetchall()
    changed = 0
    for row in rows:
        student_id = int(row["student_id"])
        final_score = student_scores.get(student_id)
        if final_score is None:
            final_score = default_final_score
        cursor.execute(
            """
            INSERT INTO student_course_results
                (student_id, semester_id, status, final_score, updated_by, notes)
            VALUES (%s, %s, %s, %s, %s, COALESCE(%s, 'COMP4300 final grade saved.'))
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                final_score = VALUES(final_score),
                updated_by = VALUES(updated_by),
                notes = VALUES(notes),
                updated_at = CURRENT_TIMESTAMP
            """,
            (student_id, row["semester_id"], status, final_score, updated_by, notes),
        )
        changed += 1
    return changed


def _sync_comp4200_section_individual_course_results(cursor, section_id, status, default_final_score, notes, updated_by, student_scores=None):
    """Sync COMP4200 section results using each student's own final score when the table exists."""
    if not _ensure_student_course_results_score_schema(cursor):
        return 0

    semester = _get_active_comp4200_semester(cursor) or _get_active_semester(cursor)
    semester_id = semester.get("semester_id") if semester else None
    if not semester_id:
        return 0

    student_status = {
        "pending": "pending",
        "succeeded": "pending",
        "not_succeeded": "failed",
        "passed": "passed",
        "failed": "failed",
    }.get(status, "pending")

    student_scores = student_scores or {}
    students = _evaluation_item_students(cursor, "introduction", section_id)
    changed = 0
    for student in students:
        student_id = int(student["student_id"])
        final_score = student_scores.get(student_id)
        if final_score is None:
            final_score = default_final_score
        cursor.execute(
            """
            INSERT INTO student_course_results
                (student_id, semester_id, status, final_score, updated_by, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                status = IF(student_course_results.promoted_at IS NULL, VALUES(status), student_course_results.status),
                final_score = IF(student_course_results.promoted_at IS NULL, VALUES(final_score), student_course_results.final_score),
                updated_by = IF(student_course_results.promoted_at IS NULL, VALUES(updated_by), student_course_results.updated_by),
                notes = IF(student_course_results.promoted_at IS NULL, VALUES(notes), student_course_results.notes),
                updated_at = CURRENT_TIMESTAMP
            """,
            (student_id, semester_id, student_status, final_score, updated_by, notes),
        )
        changed += 1

    return changed


def _evaluation_scores_from_final_result_row(row):
    return {
        "report_score": row.get("report_score"),
        "supervisor_score": row.get("supervisor_score"),
        "coordinator_score": row.get("coordinator_score"),
        "discussion_score": row.get("discussion_score"),
        "committee_score": row.get("committee_score"),
        "calculated_final_score": row.get("final_score"),
        "final_score": row.get("final_score"),
    }


def _repair_evaluation_result_memberships(
    cursor,
    course_scope=None,
    reference_id=None,
    student_id=None,
    updated_by=None,
):
    """
    Re-sync published/final evaluation rows after students/projects are moved
    between COMP4200 sections or COMP4300 groups.

    Evaluation rows are keyed by section/project. If membership changes after a
    result was sent/published, this repair makes the current members see the
    same committee/grade state without manually republishing.
    """
    _ensure_evaluation_schema(cursor)
    _ensure_student_course_results_score_schema(cursor)

    filters = ["efr.workflow_status IN ('sent_to_supervisor','sent_to_head','published_to_students')"]
    params = []
    if course_scope:
        filters.append("efr.course_scope = %s")
        params.append(course_scope)
    if reference_id:
        filters.append("efr.reference_id = %s")
        params.append(int(reference_id))
    if student_id:
        filters.append(
            """
            (
                (efr.course_scope = 'introduction' AND EXISTS (
                    SELECT 1
                    FROM section_students ss_filter
                    WHERE ss_filter.section_id = efr.reference_id
                      AND ss_filter.student_id = %s
                ))
                OR
                (efr.course_scope = 'graduation_project' AND EXISTS (
                    SELECT 1
                    FROM project_members pm_filter
                    WHERE pm_filter.project_id = efr.reference_id
                      AND pm_filter.student_id = %s
                ))
            )
            """
        )
        params.extend([int(student_id), int(student_id)])

    cursor.execute(
        f"""
        SELECT
            efr.result_id,
            efr.course_scope,
            efr.reference_id,
            efr.report_score,
            efr.supervisor_score,
            efr.coordinator_score,
            efr.discussion_score,
            efr.committee_score,
            efr.final_score,
            efr.workflow_status,
            efr.notes
        FROM evaluation_final_results efr
        WHERE {" AND ".join(filters)}
        ORDER BY efr.result_id DESC
        """,
        tuple(params),
    )
    rows = cursor.fetchall()
    changed = 0

    for row in rows:
        scope = row.get("course_scope")
        ref_id = int(row.get("reference_id") or 0)
        final_score = row.get("final_score")
        scores = _evaluation_scores_from_final_result_row(row)
        changed += _evaluation_sync_individual_student_scores(
            cursor,
            scope,
            ref_id,
            scores,
            updated_by,
            row.get("notes"),
        )

        if row.get("workflow_status") != "published_to_students" or final_score is None:
            continue

        course_status = "passed" if float(final_score) >= 60 else "failed"
        notes = row.get("notes") or "Final grade published by Head of Department."
        student_scores = _evaluation_student_final_scores_map(cursor, scope, ref_id, scores)

        if scope == "introduction":
            changed += _sync_comp4200_section_individual_course_results(
                cursor,
                ref_id,
                course_status,
                final_score,
                notes,
                updated_by,
                student_scores,
            )
        elif scope == "graduation_project":
            changed += _sync_comp4300_project_individual_course_results(
                cursor,
                ref_id,
                course_status,
                final_score,
                notes,
                updated_by,
                student_scores,
            )

    return changed


def _evaluation_grade_completion(course_scope, grades, student_ids=None):
    expected_student_ids = {int(sid) for sid in (student_ids or []) if sid is not None}

    def grade_complete(grade):
        if not grade.get("is_submitted"):
            return False
        if grade.get("mark") is not None:
            return True
        if grade.get("shared_mark"):
            return False

        submitted_student_ids = {
            int(mark_row.get("student_id"))
            for mark_row in (grade.get("student_marks") or [])
            if mark_row.get("student_id") is not None
            and mark_row.get("is_submitted")
            and mark_row.get("mark") is not None
        }
        if expected_student_ids:
            return expected_student_ids.issubset(submitted_student_ids)
        return bool(submitted_student_ids)

    required_count = max(_evaluation_default_required_count(course_scope), len(grades))
    submitted_count = sum(1 for grade in grades if grade_complete(grade))
    complete = bool(grades) and len(grades) >= required_count and submitted_count >= required_count
    return {
        "submitted_count": submitted_count,
        "required_count": required_count,
        "grades_complete": complete,
    }


def _evaluation_window_for_item(cursor, course_scope, reference_id):
    cursor.execute(
        """
        SELECT is_open, opened_at, closed_at
        FROM evaluation_windows
        WHERE course_scope = %s AND reference_id = %s
        LIMIT 1
        """,
        (course_scope, reference_id),
    )
    return cursor.fetchone() or {}


def _evaluation_ready_for_calculation(window, completion):
    return (
        completion.get("grades_complete")
        and not bool(window.get("is_open"))
        and window.get("closed_at") is not None
    )


def _evaluation_save_final_result(cursor, course_scope, reference_id, scores, supervisor_id, sent_by, notes=None):
    cursor.execute(
        """
        SELECT result_id
        FROM evaluation_final_results
        WHERE course_scope = %s AND reference_id = %s
        LIMIT 1
        """,
        (course_scope, reference_id),
    )
    existing = cursor.fetchone()
    values = (
        scores.get("report_score"),
        scores.get("supervisor_score"),
        scores.get("coordinator_score"),
        scores.get("discussion_score"),
        scores.get("committee_score"),
        scores.get("final_score"),
        notes or None,
        sent_by,
        supervisor_id,
    )
    if existing:
        cursor.execute(
            """
            UPDATE evaluation_final_results
            SET report_score = %s,
                supervisor_score = %s,
                coordinator_score = %s,
                discussion_score = %s,
                committee_score = %s,
                final_score = %s,
                notes = %s,
                workflow_status = 'sent_to_supervisor',
                sent_by_coordinator = %s,
                sent_to_supervisor_at = NOW(),
                supervisor_id = %s
            WHERE result_id = %s
            """,
            (*values, existing["result_id"]),
        )
        return existing["result_id"]

    cursor.execute(
        """
        INSERT INTO evaluation_final_results
            (course_scope, reference_id, report_score, supervisor_score,
             coordinator_score, discussion_score, committee_score, final_score, notes,
             workflow_status, sent_by_coordinator, sent_to_supervisor_at, supervisor_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                'sent_to_supervisor', %s, NOW(), %s)
        """,
        (course_scope, reference_id, *values),
    )
    return cursor.lastrowid



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
    current_faculty_id = _evaluation_current_coordinator_faculty_id(cursor)
    for grade in grades:
        grade["is_current_user_task"] = (
            bool(current_faculty_id)
            and int(grade.get("evaluator_faculty_id") or 0) == int(current_faculty_id)
        )
    window = _evaluation_window_for_item(cursor, course_scope, reference_id)
    student_ids = _evaluation_item_student_ids(cursor, course_scope, reference_id)
    completion = _evaluation_grade_completion(course_scope, grades, student_ids)
    scores = (
        _evaluation_scores_from_grades(course_scope, grades)
        if _evaluation_ready_for_calculation(window, completion)
        else _evaluation_blank_scores()
    )

    payload = dict(base_row)
    payload.update(scores)
    is_calculated = _evaluation_ready_for_calculation(window, completion)
    student_scores = _evaluation_student_score_rows(cursor, course_scope, reference_id, scores)

    payload.update(
        {
            "is_open": bool(window.get("is_open") or False),
            "opened_at": str(window.get("opened_at") or ""),
            "closed_at": str(window.get("closed_at") or ""),
            "grades": grades,
            "student_scores": student_scores,
            "students_count": len(student_scores),
            "submitted_count": completion["submitted_count"],
            "required_count": completion["required_count"],
            "grades_complete": completion["grades_complete"],
            "is_calculated": is_calculated,
        }
    )
    return payload


@coordinator_bp.route("/api/evaluation/faculty", methods=["GET"])
@login_required(role="coordinator")
def api_evaluation_faculty_options():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        supervising_faculty_ids = _committee_fetch_supervising_faculty_ids(cursor)
        if not supervising_faculty_ids:
            cursor.close()
            db.close()
            return jsonify({"faculty": []})

        placeholders = ",".join(["%s"] * len(supervising_faculty_ids))
        cursor.execute("""
            SELECT f.faculty_id,
                   u.full_name AS name,
                   u.full_name,
                   f.specialization
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id IN ({placeholders})
              AND u.role IN ('supervisor', 'coordinator', 'head_of_department')
              AND u.is_active = TRUE
            ORDER BY u.full_name
        """.format(placeholders=placeholders), tuple(sorted(supervising_faculty_ids)))
        faculty_rows = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"faculty": _json_safe_value(faculty_rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/committee-schedule-export", methods=["GET"])
@login_required(role="coordinator")
def api_coordinator_committee_schedule_export():
    """Download the saved committee schedule as a CSV file that opens in Excel."""
    try:
        course_scope = (request.args.get("course_scope") or "all").strip()
        if course_scope not in {"all", "introduction", "graduation_project"}:
            return jsonify({"error": "Invalid course_scope."}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _committee_ensure_course_schema(cursor)
        _committee_ensure_report_readers_table(cursor)

        headers = [
            "Course",
            "Committee",
            "Discussion Date",
            "Slot Start",
            "Slot End",
            "Room",
            "Responsible Supervisor",
            "Item Type",
            "Project / Section",
            "Supervisor",
            "Students",
            "Reader 1",
            "Reader 2",
            "Committee Members",
            "Status",
        ]
        rows = []

        scope_filter_sql = ""
        params = []
        if course_scope != "all":
            scope_filter_sql = " AND COALESCE(cp.course_scope, 'graduation_project') = %s"
            params.append(course_scope)

        if _table_exists(cursor, "committee_plans") and _table_exists(cursor, "committee_plan_sections"):
            cursor.execute(
                f"""
                SELECT
                    COALESCE(cp.course_scope, 'introduction') AS course_scope,
                    cp.plan_id,
                    cp.committee_name,
                    cp.discussion_date,
                    TIME_FORMAT(cps.slot_start, '%%H:%%i') AS slot_start,
                    TIME_FORMAT(cps.slot_end, '%%H:%%i') AS slot_end,
                    COALESCE(dr.room_name, '') AS room_name,
                    COALESCE(resp_u.full_name, '') AS responsible_name,
                    COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS item_title,
                    COALESCE(sup_u.full_name, '') AS supervisor_name,
                    COALESCE(GROUP_CONCAT(DISTINCT stu_u.full_name ORDER BY stu_u.full_name SEPARATOR ', '), '') AS students,
                    COALESCE(r1_u.full_name, '') AS reader1_name,
                    COALESCE(r2_u.full_name, '') AS reader2_name,
                    COALESCE((
                        SELECT GROUP_CONCAT(DISTINCT mem_u.full_name ORDER BY mem_u.full_name SEPARATOR ', ')
                        FROM committee_plan_members cpm
                        JOIN faculty mem_f ON mem_f.faculty_id = cpm.faculty_id
                        JOIN users mem_u ON mem_u.user_id = mem_f.user_id
                        WHERE cpm.plan_id = cp.plan_id
                    ), '') AS committee_members,
                    COALESCE(cp.status, 'scheduled') AS status
                FROM committee_plan_sections cps
                JOIN committee_plans cp ON cp.plan_id = cps.plan_id
                JOIN student_distribution_sections sec ON sec.section_id = cps.section_id
                LEFT JOIN comp4200_project_sections cps_title ON cps_title.section_id = sec.section_id
                LEFT JOIN projects p_intro ON p_intro.project_id = cps_title.project_id
                LEFT JOIN discussion_rooms dr ON dr.room_id = cp.room_id
                LEFT JOIN faculty resp_f ON resp_f.faculty_id = cp.responsible_faculty_id
                LEFT JOIN users resp_u ON resp_u.user_id = resp_f.user_id
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = sec.supervisor_id
                LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
                LEFT JOIN section_students ss ON ss.section_id = sec.section_id
                LEFT JOIN students stu ON stu.student_id = ss.student_id
                LEFT JOIN users stu_u ON stu_u.user_id = stu.user_id
                LEFT JOIN section_report_readers r1 ON r1.section_id = sec.section_id AND r1.reader_order = 1
                LEFT JOIN faculty r1_f ON r1_f.faculty_id = r1.faculty_id
                LEFT JOIN users r1_u ON r1_u.user_id = r1_f.user_id
                LEFT JOIN section_report_readers r2 ON r2.section_id = sec.section_id AND r2.reader_order = 2
                LEFT JOIN faculty r2_f ON r2_f.faculty_id = r2.faculty_id
                LEFT JOIN users r2_u ON r2_u.user_id = r2_f.user_id
                WHERE COALESCE(cp.status, 'scheduled') <> 'cancelled'
                  AND COALESCE(cp.course_scope, 'introduction') = 'introduction'
                  {scope_filter_sql}
                GROUP BY cp.plan_id, cp.committee_name, cp.discussion_date, cps.slot_start, cps.slot_end,
                         dr.room_name, resp_u.full_name, sec.section_name, p_intro.title, sup_u.full_name,
                         r1_u.full_name, r2_u.full_name, cp.status, cp.course_scope
                ORDER BY cp.discussion_date DESC, cp.plan_id DESC, cps.slot_start ASC, item_title ASC
                """,
                tuple(params),
            )
            for row in cursor.fetchall():
                rows.append([
                    "COMP4200",
                    row.get("committee_name") or "",
                    row.get("discussion_date") or "",
                    row.get("slot_start") or "",
                    row.get("slot_end") or "",
                    row.get("room_name") or "",
                    row.get("responsible_name") or "",
                    "Section",
                    row.get("item_title") or "",
                    row.get("supervisor_name") or "",
                    row.get("students") or "",
                    row.get("reader1_name") or "",
                    row.get("reader2_name") or "",
                    row.get("committee_members") or "",
                    row.get("status") or "",
                ])

        params = []
        scope_filter_sql = ""
        if course_scope != "all":
            scope_filter_sql = " AND COALESCE(cp.course_scope, 'graduation_project') = %s"
            params.append(course_scope)

        if _table_exists(cursor, "committee_plans") and _table_exists(cursor, "committee_plan_projects"):
            cursor.execute(
                f"""
                SELECT
                    COALESCE(cp.course_scope, 'graduation_project') AS course_scope,
                    cp.plan_id,
                    cp.committee_name,
                    cp.discussion_date,
                    TIME_FORMAT(cpp.slot_start, '%%H:%%i') AS slot_start,
                    TIME_FORMAT(cpp.slot_end, '%%H:%%i') AS slot_end,
                    COALESCE(dr.room_name, '') AS room_name,
                    COALESCE(resp_u.full_name, '') AS responsible_name,
                    p.title AS item_title,
                    COALESCE(sup_u.full_name, '') AS supervisor_name,
                    COALESCE(GROUP_CONCAT(stu_u.full_name ORDER BY pm.is_primary_contact DESC, stu_u.full_name SEPARATOR ', '), '') AS students,
                    COALESCE(r1_u.full_name, '') AS reader1_name,
                    COALESCE(r2_u.full_name, '') AS reader2_name,
                    COALESCE((
                        SELECT GROUP_CONCAT(DISTINCT mem_u.full_name ORDER BY mem_u.full_name SEPARATOR ', ')
                        FROM committee_plan_members cpm
                        JOIN faculty mem_f ON mem_f.faculty_id = cpm.faculty_id
                        JOIN users mem_u ON mem_u.user_id = mem_f.user_id
                        WHERE cpm.plan_id = cp.plan_id
                    ), '') AS committee_members,
                    COALESCE(cp.status, 'scheduled') AS status
                FROM committee_plan_projects cpp
                JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
                JOIN projects p ON p.project_id = cpp.project_id
                LEFT JOIN discussion_rooms dr ON dr.room_id = cp.room_id
                LEFT JOIN faculty resp_f ON resp_f.faculty_id = cp.responsible_faculty_id
                LEFT JOIN users resp_u ON resp_u.user_id = resp_f.user_id
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_u ON sup_u.user_id = sup_f.user_id
                LEFT JOIN project_members pm ON pm.project_id = p.project_id
                LEFT JOIN students stu ON stu.student_id = pm.student_id
                LEFT JOIN users stu_u ON stu_u.user_id = stu.user_id
                LEFT JOIN project_report_readers r1 ON r1.project_id = p.project_id AND r1.reader_order = 1
                LEFT JOIN faculty r1_f ON r1_f.faculty_id = r1.faculty_id
                LEFT JOIN users r1_u ON r1_u.user_id = r1_f.user_id
                LEFT JOIN project_report_readers r2 ON r2.project_id = p.project_id AND r2.reader_order = 2
                LEFT JOIN faculty r2_f ON r2_f.faculty_id = r2.faculty_id
                LEFT JOIN users r2_u ON r2_u.user_id = r2_f.user_id
                WHERE COALESCE(cp.status, 'scheduled') <> 'cancelled'
                  AND COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
                  {scope_filter_sql}
                GROUP BY cp.plan_id, cp.committee_name, cp.discussion_date, cpp.slot_start, cpp.slot_end,
                         dr.room_name, resp_u.full_name, p.title, sup_u.full_name,
                         r1_u.full_name, r2_u.full_name, cp.status, cp.course_scope
                ORDER BY cp.discussion_date DESC, cp.plan_id DESC, cpp.slot_start ASC, p.title ASC
                """,
                tuple(params),
            )
            for row in cursor.fetchall():
                rows.append([
                    "COMP4300",
                    row.get("committee_name") or "",
                    row.get("discussion_date") or "",
                    row.get("slot_start") or "",
                    row.get("slot_end") or "",
                    row.get("room_name") or "",
                    row.get("responsible_name") or "",
                    "Project",
                    row.get("item_title") or "",
                    row.get("supervisor_name") or "",
                    row.get("students") or "",
                    row.get("reader1_name") or "",
                    row.get("reader2_name") or "",
                    row.get("committee_members") or "",
                    row.get("status") or "",
                ])

        cursor.close()
        db.close()

        suffix = "all" if course_scope == "all" else ("comp4200" if course_scope == "introduction" else "comp4300")
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        data = "\ufeff" + output.getvalue()
        output.close()
        return Response(
            data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=committee_schedule_{suffix}.csv"},
        )
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
        _committee_ensure_course_schema(cursor)
        _committee_ensure_report_readers_table(cursor)
        _repair_evaluation_result_memberships(
            cursor,
            course_scope=course_scope,
            updated_by=session.get("user_id"),
        )

        projects = []

        if course_scope == "introduction":
            if _table_exists(cursor, "student_distribution_sections") and _table_exists(cursor, "committee_plan_sections"):
                cursor.execute(
                    """
                    SELECT
                        sec.section_id AS project_id,
                        COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS title,
                        'introduction' AS course_scope,
                        'COMP4200' AS course_code,
                        COALESCE(cp.status, 'scheduled') AS status,
                        cp.status AS committee_status,
                        cp.plan_id,
                        cp.committee_name,
                        cp.responsible_faculty_id,
                        resp_u.full_name AS responsible_name,
                        u_sup.full_name AS supervisor_name,
                        COALESCE(GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '), '') AS students
                    FROM committee_plan_sections cps
                    JOIN committee_plans cp ON cp.plan_id = cps.plan_id
                    JOIN student_distribution_sections sec ON sec.section_id = cps.section_id
                    LEFT JOIN comp4200_project_sections cps_title ON cps_title.section_id = sec.section_id
                    LEFT JOIN projects p_intro ON p_intro.project_id = cps_title.project_id
                    JOIN faculty f_sup ON f_sup.faculty_id = sec.supervisor_id
                    JOIN users u_sup ON u_sup.user_id = f_sup.user_id
                    LEFT JOIN faculty resp_f ON resp_f.faculty_id = cp.responsible_faculty_id
                    LEFT JOIN users resp_u ON resp_u.user_id = resp_f.user_id
                    LEFT JOIN section_students ss ON ss.section_id = sec.section_id
                    LEFT JOIN students st ON st.student_id = ss.student_id
                    LEFT JOIN users u_st ON u_st.user_id = st.user_id
                    WHERE COALESCE(cp.course_scope, 'introduction') = 'introduction'
                      AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
                      AND cp.plan_id = (
                          SELECT MAX(cp2.plan_id)
                          FROM committee_plan_sections cps2
                          JOIN committee_plans cp2 ON cp2.plan_id = cps2.plan_id
                          WHERE cps2.section_id = sec.section_id
                            AND COALESCE(cp2.course_scope, 'introduction') = 'introduction'
                            AND COALESCE(cp2.status, 'scheduled') <> 'cancelled'
                      )
                    GROUP BY sec.section_id, sec.section_name, p_intro.title, cp.status, cp.plan_id, cp.committee_name,
                             cp.responsible_faculty_id, resp_u.full_name, u_sup.full_name
                    HAVING COUNT(DISTINCT ss.student_id) > 0
                    ORDER BY cp.plan_id DESC, sec.section_id DESC
                    """
                )
                projects = cursor.fetchall()
        else:
            if _table_exists(cursor, "projects") and _table_exists(cursor, "committee_plan_projects"):
                cursor.execute(
                    """
                    SELECT
                        p.project_id,
                        p.title,
                        'graduation_project' AS course_scope,
                        'COMP4300' AS course_code,
                        p.status,
                        cp.status AS committee_status,
                        cp.plan_id,
                        cp.committee_name,
                        cp.responsible_faculty_id,
                        resp_u.full_name AS responsible_name,
                        u_sup.full_name AS supervisor_name,
                        COALESCE(GROUP_CONCAT(u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '), '') AS students
                    FROM committee_plan_projects cpp
                    JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
                    JOIN projects p ON p.project_id = cpp.project_id
                    LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
                    LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
                    LEFT JOIN faculty resp_f ON resp_f.faculty_id = cp.responsible_faculty_id
                    LEFT JOIN users resp_u ON resp_u.user_id = resp_f.user_id
                    LEFT JOIN project_members pm ON pm.project_id = p.project_id
                    LEFT JOIN students st ON st.student_id = pm.student_id
                    LEFT JOIN users u_st ON u_st.user_id = st.user_id
                    WHERE COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
                      AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
                      AND p.title NOT LIKE 'Committee Demo%%'
                      AND cp.plan_id = (
                          SELECT MAX(cp2.plan_id)
                          FROM committee_plan_projects cpp2
                          JOIN committee_plans cp2 ON cp2.plan_id = cpp2.plan_id
                          WHERE cpp2.project_id = p.project_id
                            AND COALESCE(cp2.course_scope, 'graduation_project') = 'graduation_project'
                            AND COALESCE(cp2.status, 'scheduled') <> 'cancelled'
                      )
                    GROUP BY p.project_id, p.title, p.status, cp.status, cp.plan_id, cp.committee_name,
                             cp.responsible_faculty_id, resp_u.full_name, u_sup.full_name
                    ORDER BY cp.plan_id DESC, p.project_id DESC
                    """
                )
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
            cursor.execute(
                """
                SELECT sec.section_id AS project_id,
                       COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS title
                FROM student_distribution_sections sec
                LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
                LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
                WHERE sec.section_id = %s
                """,
                (reference_id,),
            )
            item = cursor.fetchone()
        if not item:
            cursor.close()
            db.close()
            return jsonify({"error": "Evaluation item not found."}), 404

        try:
            _evaluation_autocreate_tasks(cursor, course_scope, reference_id, session.get("user_id"))
        except ValueError as setup_error:
            cursor.close()
            db.close()
            return jsonify({"error": str(setup_error)}), 400

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



@coordinator_bp.route("/api/coordinator/evaluation/coordinator-mark", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_coordinator_mark():
    """Save the logged-in coordinator's COMP4200 /10 mark from the Evaluation page."""
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "introduction").strip()
    reference_id = data.get("project_id") or data.get("reference_id")
    raw_mark = data.get("mark")

    if course_scope != "introduction":
        return jsonify({"error": "Coordinator mark is only for Project Introduction — COMP4200."}), 400
    if not reference_id:
        return jsonify({"error": "project_id is required."}), 400

    try:
        mark = float(raw_mark)
    except (TypeError, ValueError):
        return jsonify({"error": "Coordinator mark must be a number."}), 400

    if mark < 0 or mark > 10:
        return jsonify({"error": "Coordinator mark must be between 0 and 10."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        coordinator_faculty_id = _evaluation_current_coordinator_faculty_id(cursor)
        if not coordinator_faculty_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Your coordinator account is not linked to a faculty record."}), 400

        cursor.execute(
            """
            SELECT is_open
            FROM evaluation_windows
            WHERE course_scope = 'introduction'
              AND reference_id = %s
            LIMIT 1
            """,
            (reference_id,),
        )
        window = cursor.fetchone() or {}
        if not bool(window.get("is_open")):
            cursor.close()
            db.close()
            return jsonify({"error": "Open grade entry first, then enter the coordinator mark."}), 400

        _evaluation_insert_task(
            cursor,
            "introduction",
            int(reference_id),
            "intro_coordinator",
            coordinator_faculty_id,
            session.get("user_id"),
        )

        cursor.execute(
            """
            UPDATE evaluation_grade_tasks
            SET mark = %s,
                is_submitted = TRUE,
                submitted_at = NOW()
            WHERE course_scope = 'introduction'
              AND reference_id = %s
              AND component = 'intro_coordinator'
              AND evaluator_faculty_id = %s
            """,
            (mark, reference_id, coordinator_faculty_id),
        )

        _evaluation_cleanup_tasks(cursor, "introduction", int(reference_id))
        grades = _evaluation_fetch_grade_rows(cursor, "introduction", int(reference_id))
        student_ids = _evaluation_item_student_ids(cursor, "introduction", int(reference_id))
        completion = _evaluation_grade_completion("introduction", grades, student_ids)
        scores = _evaluation_scores_from_grades("introduction", grades) if completion.get("grades_complete") else _evaluation_blank_scores()

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            _json_safe_value(
                {
                    "message": "Coordinator mark saved successfully.",
                    "scores": scores,
                    "grades_complete": completion.get("grades_complete"),
                    "submitted_count": completion.get("submitted_count"),
                    "required_count": completion.get("required_count"),
                }
            )
        )
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/coordinator-student-marks", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_coordinator_student_marks():
    """Save the coordinator /10 mark separately for every COMP4200 student."""
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "introduction").strip()
    reference_id = data.get("project_id") or data.get("reference_id")
    marks = data.get("marks") or []

    if course_scope != "introduction":
        return jsonify({"error": "Coordinator marks are only for Project Introduction — COMP4200."}), 400
    if not reference_id:
        return jsonify({"error": "project_id/reference_id is required."}), 400
    if not isinstance(marks, list) or not marks:
        return jsonify({"error": "Student marks are required."}), 400

    try:
        reference_id = int(reference_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid project_id/reference_id."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        _ensure_evaluation_student_task_score_schema(cursor)

        coordinator_faculty_id = _evaluation_current_coordinator_faculty_id(cursor)
        if not coordinator_faculty_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Your coordinator account is not linked to a faculty record."}), 400

        cursor.execute(
            """
            SELECT is_open
            FROM evaluation_windows
            WHERE course_scope = 'introduction'
              AND reference_id = %s
            LIMIT 1
            """,
            (reference_id,),
        )
        window = cursor.fetchone() or {}
        if not bool(window.get("is_open")):
            cursor.close()
            db.close()
            return jsonify({"error": "Open grade entry first, then enter coordinator marks."}), 400

        students = _evaluation_item_students(cursor, "introduction", reference_id)
        valid_student_ids = {int(row["student_id"]) for row in students}
        if not valid_student_ids:
            cursor.close()
            db.close()
            return jsonify({"error": "No students found for this section."}), 400

        received = {}
        for row in marks:
            try:
                student_id = int(row.get("student_id"))
                mark = float(row.get("mark"))
            except (TypeError, ValueError):
                cursor.close()
                db.close()
                return jsonify({"error": "Every coordinator mark must be a valid number."}), 400

            if student_id not in valid_student_ids:
                cursor.close()
                db.close()
                return jsonify({"error": "A submitted student does not belong to this section."}), 400
            if mark < 0 or mark > 10:
                cursor.close()
                db.close()
                return jsonify({"error": "Coordinator marks must be between 0 and 10."}), 400
            received[student_id] = mark

        missing = sorted(valid_student_ids - set(received.keys()))
        if missing:
            cursor.close()
            db.close()
            return jsonify({"error": "Please enter a coordinator mark for every student."}), 400

        _evaluation_insert_task(
            cursor,
            "introduction",
            reference_id,
            "intro_coordinator",
            coordinator_faculty_id,
            session.get("user_id"),
        )
        cursor.execute(
            """
            SELECT task_id
            FROM evaluation_grade_tasks
            WHERE course_scope = 'introduction'
              AND reference_id = %s
              AND component = 'intro_coordinator'
              AND evaluator_faculty_id = %s
            LIMIT 1
            """,
            (reference_id, coordinator_faculty_id),
        )
        task = cursor.fetchone()
        if not task:
            cursor.close()
            db.close()
            return jsonify({"error": "Coordinator evaluation task could not be created."}), 500
        task_id = int(task["task_id"])

        for student_id, mark in received.items():
            cursor.execute(
                """
                INSERT INTO evaluation_student_task_scores
                    (task_id, student_id, mark, notes, is_submitted, submitted_at)
                VALUES (%s, %s, %s, NULL, TRUE, NOW())
                ON DUPLICATE KEY UPDATE
                    mark = VALUES(mark),
                    is_submitted = TRUE,
                    submitted_at = NOW()
                """,
                (task_id, student_id, mark),
            )
            cursor.execute(
                """
                INSERT INTO evaluation_student_scores
                    (course_scope, reference_id, student_id, coordinator_score,
                     updated_by, synced_at)
                VALUES ('introduction', %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    coordinator_score = VALUES(coordinator_score),
                    updated_by = VALUES(updated_by),
                    synced_at = NOW()
                """,
                (reference_id, student_id, mark, session.get("user_id")),
            )

        average_mark = round(sum(received.values()) / len(received), 2)
        cursor.execute(
            """
            UPDATE evaluation_grade_tasks
            SET mark = %s,
                notes = %s,
                is_submitted = TRUE,
                submitted_at = NOW()
            WHERE task_id = %s
              AND evaluator_faculty_id = %s
            """,
            (
                average_mark,
                f"Coordinator per-student marks submitted for {len(received)} student(s).",
                task_id,
                coordinator_faculty_id,
            ),
        )

        _evaluation_cleanup_tasks(cursor, "introduction", reference_id)
        grades = _evaluation_fetch_grade_rows(cursor, "introduction", reference_id)
        student_ids = _evaluation_item_student_ids(cursor, "introduction", reference_id)
        completion = _evaluation_grade_completion("introduction", grades, student_ids)
        scores = _evaluation_scores_from_grades("introduction", grades) if completion.get("grades_complete") else _evaluation_blank_scores()
        student_scores = _evaluation_student_score_rows(cursor, "introduction", reference_id, scores)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(_json_safe_value({
            "message": "Coordinator marks saved successfully.",
            "average_mark": average_mark,
            "scores": scores,
            "student_scores": student_scores,
            "grades_complete": completion.get("grades_complete"),
            "submitted_count": completion.get("submitted_count"),
            "required_count": completion.get("required_count"),
        }))
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/my-task-marks", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_my_task_marks():
    """Let a coordinator submit evaluator marks for committee/reader tasks assigned to them."""
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id")
    marks = data.get("marks") or []
    shared_mark = data.get("mark")
    notes = (data.get("notes") or "").strip() or None

    if not task_id:
        return jsonify({"error": "task_id is required."}), 400

    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid task_id."}), 400

    allowed_components = {
        "intro_report_reader",
        "intro_discussion_member",
        "grad_report_reader",
        "grad_committee_member",
    }
    shared_components = {"intro_report_reader", "grad_report_reader"}

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        _ensure_evaluation_student_task_score_schema(cursor)

        current_faculty_id = _evaluation_current_coordinator_faculty_id(cursor)
        if not current_faculty_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Your coordinator account is not linked to a faculty record."}), 400

        cursor.execute(
            """
            SELECT egt.task_id, egt.course_scope, egt.reference_id, egt.component,
                   egt.max_mark, egt.evaluator_faculty_id, COALESCE(ew.is_open, FALSE) AS is_open
            FROM evaluation_grade_tasks egt
            LEFT JOIN evaluation_windows ew
              ON ew.course_scope = egt.course_scope
             AND ew.reference_id = egt.reference_id
            WHERE egt.task_id = %s
              AND egt.evaluator_faculty_id = %s
            LIMIT 1
            """,
            (task_id, current_faculty_id),
        )
        task = cursor.fetchone()
        if not task:
            cursor.close()
            db.close()
            return jsonify({"error": "This evaluation task is not assigned to your account."}), 404

        component = task.get("component")
        if component not in allowed_components:
            cursor.close()
            db.close()
            return jsonify({"error": "This task type cannot be submitted from the coordinator page."}), 400

        if not bool(task.get("is_open")):
            cursor.close()
            db.close()
            return jsonify({"error": "Grade entry is closed for this task."}), 400

        course_scope = task.get("course_scope") or "introduction"
        reference_id = int(task.get("reference_id") or 0)
        max_mark = float(task.get("max_mark") or 0)

        if component in shared_components:
            if shared_mark is None or str(shared_mark).strip() == "":
                cursor.close()
                db.close()
                return jsonify({"error": "Shared report mark is required."}), 400
            try:
                mark = float(shared_mark)
            except (TypeError, ValueError):
                cursor.close()
                db.close()
                return jsonify({"error": "Shared report mark must be a number."}), 400
            if mark < 0 or mark > max_mark:
                cursor.close()
                db.close()
                return jsonify({"error": f"Mark must be between 0 and {max_mark:g}."}), 400

            cursor.execute(
                """
                UPDATE evaluation_grade_tasks
                SET mark = %s,
                    notes = %s,
                    is_submitted = TRUE,
                    submitted_at = NOW()
                WHERE task_id = %s
                  AND evaluator_faculty_id = %s
                """,
                (mark, notes, task_id, current_faculty_id),
            )
        else:
            if not isinstance(marks, list) or not marks:
                cursor.close()
                db.close()
                return jsonify({"error": "Student marks are required."}), 400

            students = _evaluation_item_students(cursor, course_scope, reference_id)
            valid_student_ids = {int(row["student_id"]) for row in students}
            if not valid_student_ids:
                cursor.close()
                db.close()
                return jsonify({"error": "No students found for this evaluation item."}), 400

            received = {}
            for row in marks:
                try:
                    student_id = int(row.get("student_id"))
                    mark = float(row.get("mark"))
                except (TypeError, ValueError):
                    cursor.close()
                    db.close()
                    return jsonify({"error": "Every mark must be a valid number."}), 400

                if student_id not in valid_student_ids:
                    cursor.close()
                    db.close()
                    return jsonify({"error": "A submitted student does not belong to this item."}), 400
                if mark < 0 or mark > max_mark:
                    cursor.close()
                    db.close()
                    return jsonify({"error": f"Marks must be between 0 and {max_mark:g}."}), 400
                received[student_id] = {
                    "mark": mark,
                    "notes": (row.get("notes") or "").strip() or None,
                }

            missing = sorted(valid_student_ids - set(received.keys()))
            if missing:
                cursor.close()
                db.close()
                return jsonify({"error": "Please enter a mark for every student."}), 400

            for student_id, row in received.items():
                cursor.execute(
                    """
                    INSERT INTO evaluation_student_task_scores
                        (task_id, student_id, mark, notes, is_submitted, submitted_at)
                    VALUES (%s, %s, %s, %s, TRUE, NOW())
                    ON DUPLICATE KEY UPDATE
                        mark = VALUES(mark),
                        notes = VALUES(notes),
                        is_submitted = TRUE,
                        submitted_at = NOW()
                    """,
                    (task_id, student_id, row["mark"], row["notes"]),
                )

            average_mark = round(sum(row["mark"] for row in received.values()) / len(received), 2)
            cursor.execute(
                """
                UPDATE evaluation_grade_tasks
                SET mark = %s,
                    notes = %s,
                    is_submitted = TRUE,
                    submitted_at = NOW()
                WHERE task_id = %s
                  AND evaluator_faculty_id = %s
                """,
                (
                    average_mark,
                    f"Per-student marks submitted for {len(received)} student(s).",
                    task_id,
                    current_faculty_id,
                ),
            )

        _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        student_ids = _evaluation_item_student_ids(cursor, course_scope, reference_id)
        completion = _evaluation_grade_completion(course_scope, grades, student_ids)
        scores = _evaluation_scores_from_grades(course_scope, grades) if completion.get("grades_complete") else _evaluation_blank_scores()
        student_scores = _evaluation_student_score_rows(cursor, course_scope, reference_id, scores)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(_json_safe_value({
            "message": "Your evaluator marks were saved successfully.",
            "scores": scores,
            "student_scores": student_scores,
            "grades_complete": completion.get("grades_complete"),
            "submitted_count": completion.get("submitted_count"),
            "required_count": completion.get("required_count"),
        }))
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/student-score", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_student_score():
    """Save a coordinator override for one student's final evaluation score."""
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "").strip()
    reference_id = data.get("project_id") or data.get("reference_id")
    student_id = data.get("student_id")
    raw_final_score = data.get("final_score")
    notes = (data.get("notes") or "").strip() or None

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400
    if not reference_id:
        return jsonify({"error": "project_id/reference_id is required."}), 400
    if not student_id:
        return jsonify({"error": "student_id is required."}), 400

    try:
        reference_id = int(reference_id)
        student_id = int(student_id)
        final_score = float(raw_final_score)
    except (TypeError, ValueError):
        return jsonify({"error": "Student final score must be a valid number."}), 400

    if final_score < 0 or final_score > 100:
        return jsonify({"error": "Student final score must be between 0 and 100."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        student_ids = {int(row["student_id"]) for row in _evaluation_item_students(cursor, course_scope, reference_id)}
        if student_id not in student_ids:
            cursor.close()
            db.close()
            return jsonify({"error": "This student does not belong to the selected evaluation item."}), 400

        _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        student_ids = _evaluation_item_student_ids(cursor, course_scope, reference_id)
        completion = _evaluation_grade_completion(course_scope, grades, student_ids)
        window = _evaluation_window_for_item(cursor, course_scope, reference_id)

        if not _evaluation_ready_for_calculation(window, completion):
            cursor.close()
            db.close()
            return jsonify({"error": "Close + Calculate the item first, then override individual student scores."}), 400

        scores = _evaluation_scores_from_grades(course_scope, grades)
        if scores.get("final_score") is None:
            cursor.close()
            db.close()
            return jsonify({"error": "Cannot save a student score until the shared final score is calculated."}), 400

        _evaluation_sync_individual_student_scores(
            cursor,
            course_scope,
            reference_id,
            scores,
            session.get("user_id"),
            None,
        )

        cursor.execute(
            """
            INSERT INTO evaluation_student_scores
                (course_scope, reference_id, student_id, report_score, supervisor_score,
                 coordinator_score, discussion_score, committee_score, calculated_final_score,
                 final_score, manual_override, notes, updated_by, synced_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE
                report_score = VALUES(report_score),
                supervisor_score = VALUES(supervisor_score),
                coordinator_score = VALUES(coordinator_score),
                discussion_score = VALUES(discussion_score),
                committee_score = VALUES(committee_score),
                calculated_final_score = VALUES(calculated_final_score),
                final_score = VALUES(final_score),
                manual_override = TRUE,
                notes = COALESCE(VALUES(notes), notes),
                updated_by = VALUES(updated_by),
                synced_at = NOW()
            """,
            (
                course_scope,
                reference_id,
                student_id,
                scores.get("report_score"),
                scores.get("supervisor_score"),
                scores.get("coordinator_score"),
                scores.get("discussion_score"),
                scores.get("committee_score"),
                scores.get("calculated_final_score") or scores.get("final_score"),
                final_score,
                notes,
                session.get("user_id"),
            ),
        )

        student_scores = _evaluation_student_score_rows(cursor, course_scope, reference_id, scores)
        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            _json_safe_value(
                {
                    "message": "Student score saved successfully.",
                    "student_scores": student_scores,
                    "scores": scores,
                }
            )
        )
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
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
        student_ids = _evaluation_item_student_ids(cursor, course_scope, reference_id)
        completion = _evaluation_grade_completion(course_scope, grades, student_ids)
        if not completion["grades_complete"]:
            cursor.close()
            db.close()
            return jsonify({
                "error": (
                    "Cannot close and calculate yet. "
                    f"{completion['submitted_count']}/{completion['required_count']} grade marks are submitted."
                )
            }), 400

        scores = _evaluation_scores_from_grades(course_scope, grades)
        if scores.get("final_score") is None:
            cursor.close()
            db.close()
            return jsonify({"error": "Cannot calculate the final score until all required marks are submitted."}), 400

        _evaluation_sync_individual_student_scores(
            cursor,
            course_scope,
            reference_id,
            scores,
            session.get("user_id"),
            None,
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


@coordinator_bp.route("/api/coordinator/evaluation/close-all", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_close_all():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "introduction").strip()

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        _committee_ensure_course_schema(cursor)

        if course_scope == "introduction":
            cursor.execute(
                """
                SELECT DISTINCT sec.section_id AS reference_id
                FROM committee_plan_sections cps
                JOIN committee_plans cp ON cp.plan_id = cps.plan_id
                JOIN student_distribution_sections sec ON sec.section_id = cps.section_id
                WHERE COALESCE(cp.course_scope, 'introduction') = 'introduction'
                  AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
                """
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT p.project_id AS reference_id
                FROM committee_plan_projects cpp
                JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
                JOIN projects p ON p.project_id = cpp.project_id
                WHERE COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
                  AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
                """
            )

        reference_ids = [int(row["reference_id"]) for row in cursor.fetchall() if row.get("reference_id")]
        closed_count = 0
        skipped_count = 0

        for reference_id in reference_ids:
            _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
            grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
            student_ids = _evaluation_item_student_ids(cursor, course_scope, reference_id)
            completion = _evaluation_grade_completion(course_scope, grades, student_ids)
            if not completion["grades_complete"]:
                skipped_count += 1
                continue

            scores = _evaluation_scores_from_grades(course_scope, grades)
            if scores.get("final_score") is None:
                skipped_count += 1
                continue

            _evaluation_sync_individual_student_scores(
                cursor,
                course_scope,
                reference_id,
                scores,
                session.get("user_id"),
                None,
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

            if course_scope == "graduation_project" and scores.get("final_score") is not None and _db_column_exists(cursor, "projects", "final_score"):
                cursor.execute(
                    "UPDATE projects SET final_score = %s WHERE project_id = %s",
                    (scores["final_score"], reference_id),
                )

            closed_count += 1

        db.commit()
        cursor.close()
        db.close()
        message = f"Evaluation closed for {closed_count} item(s)."
        if skipped_count:
            message += f" Skipped {skipped_count} item(s) with missing marks."
        return jsonify({"message": message, "closed_count": closed_count, "skipped_count": skipped_count})
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
            cursor.execute(
                """
                SELECT sec.section_id AS reference_id,
                       COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS title
                FROM student_distribution_sections sec
                LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
                LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
                WHERE sec.section_id = %s
                """,
                (reference_id,),
            )
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
        student_ids = _evaluation_item_student_ids(cursor, course_scope, reference_id)
        completion = _evaluation_grade_completion(course_scope, grades, student_ids)
        window = _evaluation_window_for_item(cursor, course_scope, reference_id)
        if not completion["grades_complete"]:
            cursor.close()
            db.close()
            return jsonify({
                "error": (
                    "Cannot send the result yet. "
                    f"{completion['submitted_count']}/{completion['required_count']} grade marks are submitted."
                )
            }), 400
        if not _evaluation_ready_for_calculation(window, completion):
            cursor.close()
            db.close()
            return jsonify({"error": "Close + Calculate this item before sending the result."}), 400

        scores = _evaluation_scores_from_grades(course_scope, grades)
        final_score = scores.get("final_score")
        if final_score is None:
            cursor.close()
            db.close()
            return jsonify({"error": "Cannot send the result until the final score is calculated."}), 400

        label = "COMP4200" if course_scope == "introduction" else "COMP4300"
        score_text = f" Final score: {final_score}/100." if final_score is not None else " Final score is not complete yet."
        notes_text = f" Coordinator notes: {notes}" if notes else ""
        _evaluation_save_final_result(
            cursor,
            course_scope,
            reference_id,
            scores,
            supervisor.get("faculty_id"),
            session.get("user_id"),
            notes,
        )
        individual_count = _evaluation_sync_individual_student_scores(
            cursor,
            course_scope,
            reference_id,
            scores,
            session.get("user_id"),
            notes,
        )

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
        student_scores = _evaluation_student_score_rows(cursor, course_scope, reference_id, scores)
        cursor.close()
        db.close()
        return jsonify({
            "message": f"Result sent to supervisor: {supervisor.get('full_name') or 'Supervisor'}.",
            "notifications_sent": 1,
            "individual_scores_saved": individual_count,
            "scores": _json_safe_value(scores),
            "student_scores": _json_safe_value(student_scores),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/evaluation/send-all-to-supervisors", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_evaluation_send_all_to_supervisors():
    data = request.get_json(silent=True) or {}
    course_scope = (data.get("course_scope") or "introduction").strip()

    if course_scope not in {"introduction", "graduation_project"}:
        return jsonify({"error": "course_scope must be introduction or graduation_project."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        _committee_ensure_course_schema(cursor)

        if course_scope == "introduction":
            cursor.execute(
                """
                SELECT DISTINCT sec.section_id AS reference_id,
                       COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS title
                FROM committee_plan_sections cps
                JOIN committee_plans cp ON cp.plan_id = cps.plan_id
                JOIN student_distribution_sections sec ON sec.section_id = cps.section_id
                LEFT JOIN comp4200_project_sections cps_title ON cps_title.section_id = sec.section_id
                LEFT JOIN projects p_intro ON p_intro.project_id = cps_title.project_id
                WHERE COALESCE(cp.course_scope, 'introduction') = 'introduction'
                  AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
                """
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT p.project_id AS reference_id, p.title
                FROM committee_plan_projects cpp
                JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
                JOIN projects p ON p.project_id = cpp.project_id
                WHERE COALESCE(cp.course_scope, 'graduation_project') = 'graduation_project'
                  AND COALESCE(cp.status, 'scheduled') <> 'cancelled'
                """
            )

        items = [
            {
                "reference_id": int(row["reference_id"]),
                "title": row.get("title") or "Evaluation item",
            }
            for row in cursor.fetchall()
            if row.get("reference_id")
        ]

        sent_count = 0
        skipped_count = 0
        notifications_sent = 0
        individual_scores_saved = 0
        label = "COMP4200" if course_scope == "introduction" else "COMP4300"

        for item in items:
            reference_id = item["reference_id"]
            supervisor = _evaluation_reference_supervisor(cursor, course_scope, reference_id)
            if not supervisor or not supervisor.get("user_id"):
                skipped_count += 1
                continue

            _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
            grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
            student_ids = _evaluation_item_student_ids(cursor, course_scope, reference_id)
            completion = _evaluation_grade_completion(course_scope, grades, student_ids)
            window = _evaluation_window_for_item(cursor, course_scope, reference_id)
            if not _evaluation_ready_for_calculation(window, completion):
                skipped_count += 1
                continue

            scores = _evaluation_scores_from_grades(course_scope, grades)
            final_score = scores.get("final_score")
            if final_score is None:
                skipped_count += 1
                continue

            _evaluation_save_final_result(
                cursor,
                course_scope,
                reference_id,
                scores,
                supervisor.get("faculty_id"),
                session.get("user_id"),
                None,
            )
            individual_scores_saved += _evaluation_sync_individual_student_scores(
                cursor,
                course_scope,
                reference_id,
                scores,
                session.get("user_id"),
                None,
            )

            score_text = f" Final score: {final_score}/100."
            _insert_notification(
                cursor,
                supervisor["user_id"],
                session.get("user_id"),
                "system",
                f"{label} Evaluation Result Ready for Supervisor Review",
                f"The coordinator sent the evaluation result for {item.get('title') or 'this item'} to you for review."
                f"{score_text} Please review it, then send it to the Head of Department for publishing.",
                reference_id if course_scope == "graduation_project" else None,
                course_scope,
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

            sent_count += 1
            notifications_sent += 1

        db.commit()
        cursor.close()
        db.close()

        message = f"Sent {sent_count} item(s) to supervisors."
        if skipped_count:
            message += f" Skipped {skipped_count} item(s) that are not ready."
        return jsonify(
            {
                "message": message,
                "sent_count": sent_count,
                "skipped_count": skipped_count,
                "notifications_sent": notifications_sent,
                "individual_scores_saved": individual_scores_saved,
            }
        )
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
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
    if course_scope == "graduation_project" and decision == "archived":
        return jsonify({
            "error": "Only the Head of Department can archive COMP4300 projects. Mark the project as accepted/succeeded for Head approval."
        }), 403

    try:
        reference_id = int(reference_id)
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        _evaluation_cleanup_tasks(cursor, course_scope, reference_id)
        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        scores = _evaluation_scores_from_grades(course_scope, grades)
        final_score = scores.get("final_score")
        _evaluation_sync_individual_student_scores(
            cursor,
            course_scope,
            reference_id,
            scores,
            session.get("user_id"),
            notes,
        )
        student_final_scores = _evaluation_student_final_scores_map(cursor, course_scope, reference_id, scores)

        if course_scope == "graduation_project":
            new_status = "archived" if decision == "archived" else decision
            course_status = "passed" if decision in {"accepted", "archived"} else "failed"
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
            _sync_comp4300_project_individual_course_results(
                cursor,
                reference_id,
                course_status,
                final_score,
                notes,
                session.get("user_id"),
                student_final_scores,
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
            _sync_comp4200_section_individual_course_results(
                cursor,
                reference_id,
                status_value,
                final_score,
                notes,
                session.get("user_id"),
                student_final_scores,
            )

        _evaluation_mark_student_scores_decision(
            cursor,
            course_scope,
            reference_id,
            decision,
            session.get("user_id"),
            notes,
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

        if course_scope == "graduation_project" and decision == "archived":
            clear_supervisor_project_workspace(cursor, reference_id)

        db.commit()
        cursor.close()
        db.close()
        student_scores = _evaluation_student_score_rows(cursor, course_scope, reference_id, scores)
        return jsonify({
            "message": "Final evaluation saved successfully.",
            "scores": _json_safe_value(scores),
            "student_scores": _json_safe_value(student_scores),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@coordinator_bp.route("/api/coordinator/profile", methods=["GET"])
@login_required(role="coordinator")
def coordinator_profile_api():
    user_id = session.get("user_id")

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    try:
        _ensure_user_profile_extra_table(cur)
        conn.commit()

        has_office_number = _db_column_exists(cur, "faculty", "office_number")
        faculty_office_select = (
            "NULLIF(TRIM(f.office_number), '')"
            if has_office_number
            else "NULL"
        )
        office_select = (
            "COALESCE(NULLIF(TRIM(upe.office_number), ''), "
            f"{faculty_office_select}, '') AS office_number"
        )

        cur.execute(f"""
            SELECT
                u.user_id,
                u.university_id,
                u.full_name,
                u.email,
                u.avatar_initials,
                u.role,
                f.faculty_id,
                f.specialization,
                f.years_experience,
                {office_select},
                COALESCE(s.course_code, 'COMP4200') AS course_code
            FROM users u
            LEFT JOIN faculty f ON f.user_id = u.user_id
            LEFT JOIN user_profile_extra upe ON upe.user_id = u.user_id
            LEFT JOIN coordinator_assignments ca ON ca.faculty_id = f.faculty_id
            LEFT JOIN semesters s ON s.semester_id = ca.semester_id
            WHERE u.user_id = %s
            ORDER BY s.is_active DESC, ca.assigned_at DESC
            LIMIT 1
        """, (user_id,))

        profile = cur.fetchone()

        if not profile:
            return jsonify({"ok": False, "error": "Profile not found"}), 404

        supervisor_counts = _faculty_supervised_group_counts(cur, profile.get("faculty_id"))

        profile["course_label"] = "COMP4200 / COMP4300"
        profile["can_switch_to_supervisor"] = supervisor_counts["total_groups"] > 0
        profile["supervisor_group_count"] = supervisor_counts["total_groups"]
        profile["supervisor_project_group_count"] = supervisor_counts["project_groups"]
        profile["supervisor_section_group_count"] = supervisor_counts["section_groups"]

        return jsonify({
            "ok": True,
            "profile": _json_safe_value(profile)
        })

    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    finally:
        cur.close()
        conn.close()

@coordinator_bp.route("/api/coordinator/evaluation/unread-count", methods=["GET"])
def api_coordinator_evaluation_unread_count():
    # Return 0 silently if not logged in as coordinator (avoids 401 log noise from expired sessions)
    if session.get("role") != "coordinator" or "user_id" not in session:
        return jsonify({"count": 0})
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        _ensure_evaluation_schema(cursor)
        db.commit()

        cursor.execute("""
            SELECT COUNT(DISTINCT CONCAT(egt.course_scope, '-', egt.reference_id)) AS count
            FROM evaluation_grade_tasks egt
            JOIN evaluation_windows ew
              ON ew.course_scope = egt.course_scope
             AND ew.reference_id = egt.reference_id
            WHERE ew.is_open = TRUE
              AND COALESCE(egt.is_submitted, FALSE) = FALSE
        """)

        row = cursor.fetchone() or {}
        cursor.close()
        db.close()

        return jsonify({"count": int(row.get("count") or 0)})
    except Exception as e:
        return jsonify({"error": str(e), "count": 0}), 500


def _ensure_user_profile_extra_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profile_extra (
            user_id INT PRIMARY KEY,
            office_number VARCHAR(120) NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


@coordinator_bp.route("/api/coordinator/profile/update-info", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_update_profile_info():
    user_id = session.get("user_id")
    data = request.get_json(silent=True) or {}
    office_number = (data.get("office_number") or "").strip()
    years_raw = str(data.get("years_experience") or "").strip()

    if len(office_number) > 50:
        return jsonify({"error": "Office number must be 50 characters or fewer."}), 400

    if years_raw:
        try:
            years_experience = int(years_raw)
        except ValueError:
            return jsonify({"error": "Years of experience must be a whole number."}), 400
        if years_experience < 0 or years_experience > 80:
            return jsonify({"error": "Years of experience must be between 0 and 80."}), 400
    else:
        years_experience = None

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    try:
        _ensure_user_profile_extra_table(cur)
        has_office_number = _db_column_exists(cur, "faculty", "office_number")

        cur.execute(
            """
            SELECT faculty_id
            FROM faculty
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )
        faculty = cur.fetchone()
        if not faculty:
            return jsonify({"error": "Faculty profile not found."}), 404

        if has_office_number:
            cur.execute(
                """
                UPDATE faculty
                SET office_number = %s, years_experience = %s
                WHERE faculty_id = %s
                """,
                (office_number or None, years_experience, faculty["faculty_id"]),
            )
        else:
            cur.execute(
                """
                UPDATE faculty
                SET years_experience = %s
                WHERE faculty_id = %s
                """,
                (years_experience, faculty["faculty_id"]),
            )
            cur.execute(
                """
                INSERT INTO user_profile_extra (user_id, office_number)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE office_number = VALUES(office_number)
                """,
                (user_id, office_number or None),
            )

        conn.commit()
        return jsonify({"message": "Profile information updated successfully."})
    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()


@coordinator_bp.route("/api/coordinator/change-password", methods=["POST"])
@login_required(role="coordinator")
def api_coordinator_change_password():
    try:
        user_id = session.get("user_id")
        data = request.get_json(silent=True) or {}

        current_password = (data.get("current_password") or "").strip()
        new_password = (data.get("new_password") or "").strip()
        confirm_password = (data.get("confirm_password") or "").strip()

        if not current_password or not new_password or not confirm_password:
            return jsonify({"error": "Please fill in all password fields."}), 400

        if len(new_password) < 8:
            return jsonify({"error": "New password must be at least 8 characters."}), 400

        if new_password != confirm_password:
            return jsonify({"error": "New passwords do not match."}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT password_hash
            FROM users
            WHERE user_id = %s
            LIMIT 1
            """,
            (user_id,),
        )

        user = cursor.fetchone()

        if not user:
            cursor.close()
            db.close()
            return jsonify({"error": "User not found."}), 404

        stored_hash = user.get("password_hash") or ""

        if not bcrypt.checkpw(current_password.encode(), stored_hash.encode()):
            cursor.close()
            db.close()
            return jsonify({"error": "Current password is incorrect."}), 400

        new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()

        cursor.execute(
            """
            UPDATE users
            SET password_hash = %s
            WHERE user_id = %s
            """,
            (new_hash, user_id),
        )

        db.commit()
        cursor.close()
        db.close()

        return jsonify({"message": "Password updated successfully."})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@coordinator_bp.route("/coordinator/switch-to-supervisor", methods=["POST", "GET"])
@login_required(role="coordinator")
def switch_to_supervisor():
    """
    Allow a coordinator with supervised groups to view the system as supervisor.
    It keeps the original coordinator session so the user can switch back.
    """
    user_id = session.get("user_id")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    access = _coordinator_supervisor_access(cursor, user_id)
    cursor.close()
    db.close()

    if not access.get("can_switch"):
        return redirect(url_for("coordinator_bp.coordinator_page", page="profile"))

    faculty = access["faculty"]

    session["original_role"] = session.get("role")
    session["original_user_id"] = session.get("user_id")
    session["original_full_name"] = session.get("full_name")
    session["is_switched_to_supervisor"] = True

    session["role"] = "supervisor"
    session["faculty_id"] = faculty["faculty_id"]

    return redirect(url_for("supervisor_dashboard.supervisor_dashboard"))


@coordinator_bp.route("/supervisor/switch-to-coordinator", methods=["POST", "GET"])
@login_required(role="supervisor")
def switch_back_to_coordinator():
    if session.get("original_role") != "coordinator":
        return redirect(url_for("supervisor_dashboard.supervisor_dashboard"))

    original_user_id = session.get("original_user_id")
    original_full_name = session.get("original_full_name")

    session["role"] = "coordinator"
    if original_user_id:
        session["user_id"] = original_user_id
    if original_full_name:
        session["full_name"] = original_full_name

    session.pop("original_role", None)
    session.pop("original_user_id", None)
    session.pop("original_full_name", None)
    session.pop("is_switched_to_supervisor", None)
    session.pop("faculty_id", None)

    return redirect(url_for("coordinator_bp.coordinator_dashboard"))
