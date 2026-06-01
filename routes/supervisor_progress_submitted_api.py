from datetime import datetime, time
import os
import zipfile
import io

from flask import Blueprint, jsonify, request, session, Response, redirect, url_for

from auth import login_required
from db import get_db
from werkzeug.utils import secure_filename

supervisor_progress_api_bp = Blueprint("supervisor_progress_api_bp", __name__)


# ─────────────────────────────────────────────────────────────
# Generic DB helpers
# ─────────────────────────────────────────────────────────────
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


def _column_exists(cursor, table_name, column_name):
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


def _ensure_progress_tables(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS supervisor_progress_notes (
            note_id INT PRIMARY KEY AUTO_INCREMENT,
            project_id INT NOT NULL,
            supervisor_user_id INT NOT NULL,
            note_text TEXT NOT NULL,
            state ENUM('on_track','follow_up_needed','urgent') NOT NULL DEFAULT 'on_track',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_spn_project (project_id),
            INDEX idx_spn_supervisor (supervisor_user_id),
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (supervisor_user_id) REFERENCES users(user_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _dt(value, include_time=False):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M" if include_time else "%Y-%m-%d")
    text = str(value)
    return text[:16] if include_time else text[:10]


def _text_value(value):
    if isinstance(value, (set, list, tuple)):
        return ", ".join(sorted(str(item) for item in value))
    return str(value or "")


def _parse_time(value, fallback):
    value = (value or "").strip()
    if not value:
        return fallback
    try:
        hour, minute = value[:5].split(":")
        return time(int(hour), int(minute))
    except Exception:
        return fallback


def _combine_datetime(date_value, time_value=None, end_of_day=False):
    if not date_value:
        return None

    if isinstance(date_value, datetime):
        date_part = date_value.date()
    elif hasattr(date_value, "year") and hasattr(date_value, "month") and hasattr(date_value, "day"):
        date_part = date_value
    else:
        try:
            date_part = datetime.strptime(str(date_value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    fallback = time(23, 59) if end_of_day else time(0, 0)
    return datetime.combine(date_part, _parse_time(time_value, fallback))


def _status_label(status):
    labels = {
        "draft": "Draft / not submitted yet",
        "submitted": "Submitted to coordinator",
        "under_review": "Under supervisor review",
        "needs_revision": "Needs revision",
        "committee_evaluation": "In committee evaluation",
        "accepted": "Accepted",
        "rejected": "Rejected",
        "archived": "Archived",
    }
    return labels.get(status or "", status or "In progress")


def _logical_project_status(status, timeline):
    """Return a status that makes sense on the progress page.

    DB status is workflow/admin-oriented. The supervisor progress page should
    reflect student delivery status from Exam Distribution deadlines.
    """
    status = status or ""
    if status == "rejected":
        return "Rejected"
    if status == "accepted":
        return "Accepted"
    if status == "committee_evaluation":
        return "In committee evaluation"

    deadline_items = [item for item in (timeline or []) if item.get("is_deadline", True)]
    if deadline_items:
        keys = {item.get("status_key") for item in deadline_items}
        if "missing" in keys:
            return "Missing submission"
        if "submitted_late" in keys:
            return "Submitted late"
        if keys and all(k == "submitted_on_time" for k in keys):
            return "Submitted on time"
        if "pending" in keys:
            return "Waiting for submission"
        if "not_open" in keys:
            return "Not open yet"

    return _status_label(status)


# ─────────────────────────────────────────────────────────────
# Supervisor/project access
# ─────────────────────────────────────────────────────────────
def _get_supervisor_faculty_id(cursor, user_id):
    cursor.execute(
        """
        SELECT faculty_id
        FROM faculty
        WHERE user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    return row.get("faculty_id") if row else None


def _current_supervisor_faculty_id(cursor):
    """Return the faculty_id for the logged-in supervisor.

    If the coordinator switched into supervisor mode, session["faculty_id"] is
    used first. Otherwise the faculty record is resolved from faculty.user_id.
    """
    session_faculty_id = session.get("faculty_id")
    if session_faculty_id:
        try:
            return int(session_faculty_id)
        except (TypeError, ValueError):
            pass
    return _get_supervisor_faculty_id(cursor, session.get("user_id"))


def _project_access_filter(cursor):
    """Progress page should show only real/live projects owned by this supervisor.

    This intentionally does NOT use supervisor_assignments, committee members,
    archive/search sources, or imported demo projects. Those can include old
    archive/search records and would make the supervisor see projects that are
    not really assigned to them now.
    """
    filters = [
        "p.supervisor_id = %s",
        "LOWER(COALESCE(p.status, '')) NOT IN ('archived', 'archive', 'search', 'search_only', 'imported_archive')",
        "p.semester_id IS NOT NULL",
    ]

    if _table_exists(cursor, "semesters") and _column_exists(cursor, "semesters", "is_active"):
        filters.append("COALESCE(s.is_active, 0) = TRUE")

    if _table_exists(cursor, "project_members"):
        filters.append(
            """
            EXISTS (
                SELECT 1
                FROM project_members pm_real
                JOIN students st_real ON st_real.student_id = pm_real.student_id
                JOIN users u_real ON u_real.user_id = st_real.user_id
                WHERE pm_real.project_id = p.project_id
                  AND u_real.role = 'student'
                  AND u_real.is_active = TRUE
            )
            """
        )

    for col in ("is_archived", "is_archive", "is_search_only", "search_only", "archive_only", "is_imported", "is_demo"):
        if _column_exists(cursor, "projects", col):
            filters.append(f"COALESCE(p.{col}, 0) = 0")

    for col in ("archive_source", "search_source", "import_source"):
        if _column_exists(cursor, "projects", col):
            filters.append(f"(p.{col} IS NULL OR p.{col} = '')")

    return " AND ".join(filters)


def _project_access_params(cursor, faculty_id):
    return (faculty_id,)


def _submission_access_filter(cursor):
    """Allow assigned live-semester submissions, including archived final work."""
    filters = [
        "p.supervisor_id = %s",
        "p.semester_id IS NOT NULL",
    ]

    if _table_exists(cursor, "semesters") and _column_exists(cursor, "semesters", "is_active"):
        filters.append("COALESCE(s.is_active, 0) = TRUE")

    if _table_exists(cursor, "project_members"):
        filters.append(
            """
            EXISTS (
                SELECT 1
                FROM project_members pm_real
                JOIN students st_real ON st_real.student_id = pm_real.student_id
                JOIN users u_real ON u_real.user_id = st_real.user_id
                WHERE pm_real.project_id = p.project_id
                  AND u_real.role = 'student'
                  AND u_real.is_active = TRUE
            )
            """
        )

    for col in ("is_archive", "is_search_only", "search_only", "archive_only", "is_imported", "is_demo"):
        if _column_exists(cursor, "projects", col):
            filters.append(f"COALESCE(p.{col}, 0) = 0")

    for col in ("archive_source", "search_source", "import_source"):
        if _column_exists(cursor, "projects", col):
            filters.append(f"(p.{col} IS NULL OR p.{col} = '')")

    return " AND ".join(filters)


def _fetch_supervisor_projects(cursor, faculty_id):
    if not faculty_id:
        return []

    access_filter = _project_access_filter(cursor)
    params = _project_access_params(cursor, faculty_id)

    cursor.execute(
        f"""
        SELECT
            p.project_id,
            p.semester_id,
            COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS title,
            p.status,
            p.submission_date,
            p.updated_at,
            s.course_code,
            s.academic_year,
            COALESCE(
                GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '),
                ''
            ) AS members
        FROM projects p
        LEFT JOIN semesters s ON s.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u_st ON u_st.user_id = st.user_id
        WHERE {access_filter}
        GROUP BY p.project_id, p.semester_id, p.title, p.status, p.submission_date, p.updated_at, s.course_code, s.academic_year
        ORDER BY COALESCE(p.updated_at, p.submission_date) DESC, p.project_id DESC
        """,
        params,
    )
    return cursor.fetchall()


def _get_project_for_supervisor(cursor, project_id, faculty_id):
    access_filter = _project_access_filter(cursor)
    params = (project_id,) + _project_access_params(cursor, faculty_id)

    cursor.execute(
        f"""
        SELECT
            p.project_id,
            p.semester_id,
            COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS title,
            p.status,
            p.submission_date,
            p.updated_at,
            s.course_code,
            s.academic_year,
            COALESCE(
                GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY pm.is_primary_contact DESC, u_st.full_name SEPARATOR ', '),
                ''
            ) AS members
        FROM projects p
        LEFT JOIN semesters s ON s.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u_st ON u_st.user_id = st.user_id
        WHERE p.project_id = %s
          AND {access_filter}
        GROUP BY p.project_id, p.semester_id, p.title, p.status, p.submission_date, p.updated_at, s.course_code, s.academic_year
        LIMIT 1
        """,
        params,
    )
    return cursor.fetchone()


# ─────────────────────────────────────────────────────────────
# Counts and notes
# ─────────────────────────────────────────────────────────────
def _file_counts(cursor, project_id):
    result = {"total": 0, "report": 0, "code": 0, "presentation": 0, "other": 0}

    if not _table_exists(cursor, "project_files"):
        return result

    cursor.execute(
        """
        SELECT file_type, file_name
        FROM project_files
        WHERE project_id = %s
          AND (
              COALESCE(upload_status, 'uploaded') = 'uploaded'
              OR uploaded_at IS NOT NULL
              OR file_data IS NOT NULL
              OR COALESCE(file_path, '') <> ''
          )
        """,
        (project_id,),
    )

    for row in cursor.fetchall():
        result["total"] += 1
        text = f"{row.get('file_type') or ''} {row.get('file_name') or ''}".lower()
        if any(k in text for k in ("report", "final", "pdf", "document")):
            result["report"] += 1
        elif any(k in text for k in ("code", "source", "zip", "github")):
            result["code"] += 1
        elif any(k in text for k in ("presentation", "slide", "ppt")):
            result["presentation"] += 1
        else:
            result["other"] += 1

    return result


def _feedback_count(cursor, project_id, user_id):
    if not _table_exists(cursor, "feedback"):
        return 0

    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM feedback
        WHERE project_id = %s
          AND reviewer_id = %s
        """,
        (project_id, user_id),
    )
    row = cursor.fetchone() or {}
    return int(row.get("cnt") or 0)


def _latest_notes(cursor, project_id, user_id):
    _ensure_progress_tables(cursor)

    cursor.execute(
        """
        SELECT note_id, note_text, state, created_at
        FROM supervisor_progress_notes
        WHERE project_id = %s
          AND supervisor_user_id = %s
        ORDER BY created_at DESC, note_id DESC
        LIMIT 5
        """,
        (project_id, user_id),
    )

    return [
        {
            "note_id": row.get("note_id"),
            "note_text": row.get("note_text") or "",
            "state": row.get("state") or "on_track",
            "created_at": str(row.get("created_at") or ""),
        }
        for row in cursor.fetchall()
    ]


# ─────────────────────────────────────────────────────────────
# Exam Distribution driven timeline
# ─────────────────────────────────────────────────────────────
def _timeline_item_status(start_dt, due_dt, submitted_at):
    now = datetime.now()

    if submitted_at:
        if due_dt and submitted_at > due_dt:
            return "submitted_late", "late", "Submitted late"
        return "submitted_on_time", "completed", "Submitted on time"

    if start_dt and now < start_dt:
        return "not_open", "pending", "Not open yet"

    if due_dt and now > due_dt:
        return "missing", "missing", "Missing submission"

    return "pending", "in_progress", "Waiting for submission"


def _submission_status_score(status_key):
    if status_key == "submitted_on_time":
        return 1.0
    if status_key == "submitted_late":
        return 0.7
    return 0.0


def _categorize_title(title):
    text = (title or "").lower()
    if any(k in text for k in ("report", "final submission", "final", "document")):
        return "final_report"
    if any(k in text for k in ("code", "source", "github", "implementation")):
        return "source_code"
    if any(k in text for k in ("presentation", "slide", "demo")):
        return "presentation"
    return None


def _progress_from_timeline(timeline, file_counts=None, feedback_count=0, status=None):
    file_counts = file_counts or {}
    scored = [item for item in timeline if item.get("is_deadline", True)]

    if not scored:
        return _progress_values_from_files(file_counts, feedback_count, status)

    total_score = sum(_submission_status_score(item.get("status_key")) for item in scored)
    overall = round((total_score / len(scored)) * 100) if scored else 0

    category_values = {"final_report": None, "source_code": None, "presentation": None}
    for item in scored:
        category = _categorize_title(item.get("title"))
        if category and category in category_values:
            category_values[category] = max(
                category_values[category] or 0,
                round(_submission_status_score(item.get("status_key")) * 100),
            )

    return {
        "final_report": category_values["final_report"] if category_values["final_report"] is not None else (100 if file_counts.get("report") else 0),
        "source_code": category_values["source_code"] if category_values["source_code"] is not None else (100 if file_counts.get("code") else 0),
        "presentation": category_values["presentation"] if category_values["presentation"] is not None else (100 if file_counts.get("presentation") else 0),
        "overall": overall,
    }


def _progress_values_from_files(file_counts, feedback_count, status):
    report = 100 if file_counts.get("report") else 0
    code = 100 if file_counts.get("code") else 0
    presentation = 100 if file_counts.get("presentation") else 0

    if file_counts.get("total") and not any([report, code, presentation]):
        report = 60

    review_bonus = 20 if feedback_count else 0
    status_bonus = 0
    if status in {"committee_evaluation"}:
        status_bonus = 15
    elif status in {"accepted", "archived"}:
        status_bonus = 25
    elif status == "rejected":
        status_bonus = 5

    overall = round(min(100, ((report + code + presentation) / 3) * 0.75 + review_bonus + status_bonus))
    return {"final_report": report, "source_code": code, "presentation": presentation, "overall": overall}


def _intro_timeline_from_exam_distribution(cursor, project):
    if not (
        _table_exists(cursor, "comp4200_timelines")
        and _table_exists(cursor, "comp4200_timeline_items")
    ):
        return []

    semester_id = project.get("semester_id")
    cursor.execute(
        """
        SELECT timeline_id, title, note, is_published, published_at
        FROM comp4200_timelines
        WHERE semester_id = %s
          AND is_published = TRUE
        ORDER BY timeline_id DESC
        LIMIT 1
        """,
        (semester_id,),
    )
    timeline = cursor.fetchone()
    if not timeline:
        return []

    cursor.execute(
        """
        SELECT item_id, item_order, title, description, start_date, start_time,
               due_date, due_time, milestone_label, submitted_to, is_deadline
        FROM comp4200_timeline_items
        WHERE timeline_id = %s
          AND COALESCE(is_archived, FALSE) = FALSE
        ORDER BY item_order ASC, due_date ASC, item_id ASC
        """,
        (timeline["timeline_id"],),
    )
    items = cursor.fetchall()
    if not items:
        return []

    submissions = {}
    if _table_exists(cursor, "milestone_submissions"):
        item_ids = [row["item_id"] for row in items]
        placeholders = ",".join(["%s"] * len(item_ids))
        cursor.execute(
            f"""
            SELECT ms.item_id, ms.submission_id, ms.file_name, ms.submitted_at,
                   ms.submitted_to, u.full_name AS submitted_by
            FROM milestone_submissions ms
            LEFT JOIN students st ON st.student_id = ms.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            WHERE ms.project_id = %s
              AND ms.item_id IN ({placeholders})
            ORDER BY ms.submitted_at DESC, ms.submission_id DESC
            """,
            (project["project_id"], *item_ids),
        )
        for row in cursor.fetchall():
            # Keep newest submission per milestone.
            submissions.setdefault(row["item_id"], row)

    result = []
    for item in items:
        start_dt = _combine_datetime(item.get("start_date"), item.get("start_time"), end_of_day=False)
        due_dt = _combine_datetime(item.get("due_date"), item.get("due_time"), end_of_day=True)
        submission = submissions.get(item["item_id"])
        submitted_at = submission.get("submitted_at") if submission else None
        status_key, state, label = _timeline_item_status(start_dt, due_dt, submitted_at)

        due_text = _dt(due_dt, include_time=True) if due_dt else "No deadline"
        start_text = _dt(start_dt, include_time=True) if start_dt else "Open date not set"
        meta = f"{label} · Due: {due_text}"
        if submitted_at:
            meta = f"{label} · Submitted: {_dt(submitted_at, include_time=True)} · Due: {due_text}"

        note_parts = []
        if item.get("description"):
            note_parts.append(item.get("description"))
        note_parts.append(f"Window: {start_text} → {due_text}")
        if submission:
            note_parts.append(f"File: {submission.get('file_name') or 'submitted file'}")
            if submission.get("submitted_by"):
                note_parts.append(f"Submitted by: {submission.get('submitted_by')}")
        else:
            note_parts.append("No submission found for this project yet.")

        result.append(
            {
                "item_id": item.get("item_id"),
                "title": item.get("milestone_label") or item.get("title") or "Timeline item",
                "state": state,
                "status_key": status_key,
                "status_label": label,
                "meta": meta,
                "note": " | ".join([p for p in note_parts if p]),
                "deadline": _dt(due_dt, include_time=True),
                "submitted_at": _dt(submitted_at, include_time=True),
                "is_deadline": bool(item.get("is_deadline")),
                "source": "exam_distribution_comp4200",
            }
        )

    return result


def _grad_final_submission_from_exam_distribution(cursor, project):
    if not _table_exists(cursor, "coordinator_deliverables"):
        return []

    cursor.execute(
        """
        SELECT deliverable_id, title, description, start_at, due_at, status,
               is_published, published_at
        FROM coordinator_deliverables
        WHERE semester_id = %s
          AND course_scope = 'graduation_project'
          AND title = 'Graduation Project Final Submission'
          AND is_published = TRUE
        ORDER BY deliverable_id DESC
        LIMIT 1
        """,
        (project.get("semester_id"),),
    )
    window = cursor.fetchone()
    if not window:
        return []

    submission = None
    if _table_exists(cursor, "project_files"):
        cursor.execute(
            """
            SELECT pf.file_id, pf.file_name, pf.file_type, pf.uploaded_at,
                   u.full_name AS submitted_by
            FROM project_files pf
            LEFT JOIN users u ON u.user_id = pf.uploaded_by
            WHERE pf.project_id = %s
              AND COALESCE(pf.upload_status, 'uploaded') = 'uploaded'
              AND (
                    pf.file_type = 'final_report'
                    OR LOWER(COALESCE(pf.file_name, '')) LIKE '%%final%%'
                    OR LOWER(COALESCE(pf.file_name, '')) LIKE '%%report%%'
                  )
            ORDER BY pf.uploaded_at DESC, pf.file_id DESC
            LIMIT 1
            """,
            (project["project_id"],),
        )
        submission = cursor.fetchone()

    start_dt = window.get("start_at")
    due_dt = window.get("due_at")
    submitted_at = submission.get("uploaded_at") if submission else None
    status_key, state, label = _timeline_item_status(start_dt, due_dt, submitted_at)

    due_text = _dt(due_dt, include_time=True) if due_dt else "No deadline"
    start_text = _dt(start_dt, include_time=True) if start_dt else "Open date not set"
    meta = f"{label} · Due: {due_text}"
    if submitted_at:
        meta = f"{label} · Submitted: {_dt(submitted_at, include_time=True)} · Due: {due_text}"

    note_parts = []
    if window.get("description"):
        note_parts.append(window.get("description"))
    note_parts.append(f"Window: {start_text} → {due_text}")
    if submission:
        note_parts.append(f"File: {submission.get('file_name') or 'submitted file'}")
        if submission.get("submitted_by"):
            note_parts.append(f"Submitted by: {submission.get('submitted_by')}")
    else:
        note_parts.append("No final report submission found for this project yet.")

    return [
        {
            "item_id": f"grad-final-{window.get('deliverable_id')}",
            "title": window.get("title") or "Graduation Project Final Submission",
            "state": state,
            "status_key": status_key,
            "status_label": label,
            "meta": meta,
            "note": " | ".join([p for p in note_parts if p]),
            "deadline": _dt(due_dt, include_time=True),
            "submitted_at": _dt(submitted_at, include_time=True),
            "is_deadline": True,
            "source": "exam_distribution_comp4300",
        }
    ]


def _fallback_lifecycle_timeline(project, file_counts, feedback_count):
    status = project.get("status") or ""
    files_done = file_counts["total"] > 0
    review_done = feedback_count > 0
    committee_done = status in {"committee_evaluation", "accepted", "archived"}
    archived_done = status == "archived"

    return [
        {
            "title": "Registration and assignment",
            "state": "completed",
            "status_key": "submitted_on_time",
            "meta": f"Completed · {_dt(project.get('submission_date')) or 'Date not set'}",
            "note": "Fallback lifecycle is shown because no published Exam Distribution timeline was found.",
            "is_deadline": False,
            "source": "fallback",
        },
        {
            "title": "Uploaded files",
            "state": "completed" if files_done else "in_progress",
            "status_key": "submitted_on_time" if files_done else "pending",
            "meta": "Completed" if files_done else "Waiting for uploaded files",
            "note": f"Uploaded files: {file_counts['total']}",
            "is_deadline": True,
            "source": "fallback",
        },
        {
            "title": "Supervisor feedback",
            "state": "completed" if review_done else "in_progress",
            "status_key": "submitted_on_time" if review_done else "pending",
            "meta": "Feedback provided" if review_done else "Currently in progress",
            "note": f"Supervisor feedback items: {feedback_count}",
            "is_deadline": False,
            "source": "fallback",
        },
        {
            "title": "Committee evaluation",
            "state": "completed" if committee_done else "pending",
            "status_key": "submitted_on_time" if committee_done else "pending",
            "meta": _status_label(status),
            "note": "",
            "is_deadline": False,
            "source": "fallback",
        },
        {
            "title": "Results and archiving",
            "state": "completed" if archived_done else "pending",
            "status_key": "submitted_on_time" if archived_done else "pending",
            "meta": "Archived" if archived_done else "Not archived yet",
            "note": "",
            "is_deadline": False,
            "source": "fallback",
        },
    ]


def _exam_distribution_timeline(cursor, project, file_counts, feedback_count):
    course_code = (project.get("course_code") or "").upper()

    if course_code == "COMP4200":
        timeline = _intro_timeline_from_exam_distribution(cursor, project)
    elif course_code == "COMP4300":
        timeline = _grad_final_submission_from_exam_distribution(cursor, project)
    else:
        timeline = []

    if not timeline:
        return _fallback_lifecycle_timeline(project, file_counts, feedback_count), "fallback"

    return timeline, "exam_distribution"




# ─────────────────────────────────────────────────────────────
# Supervisor Submitted Files helpers
# ─────────────────────────────────────────────────────────────
def _course_label_for_code(course_code):
    if course_code == "COMP4300":
        return "Graduation Project"
    if course_code == "COMP4200":
        return "Project Introduction"
    return course_code or "Course"


def _format_submission_datetime(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M")
    return str(value)[:16]


def _download_static_path(file_path):
    clean_path = (file_path or "").replace("\\", "/").lstrip("/")
    if clean_path.startswith("static/"):
        clean_path = clean_path[len("static/"):]
    return redirect(url_for("static", filename=clean_path))


def _file_download_response(row, fallback_name="submitted-file"):
    if not row:
        return jsonify({"error": "File not found."}), 404

    if row.get("file_data"):
        return Response(
            bytes(row["file_data"]),
            mimetype=row.get("file_mime") or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{row.get("file_name") or fallback_name}"'
            },
        )

    if row.get("file_path"):
        return _download_static_path(row.get("file_path"))

    return jsonify({"error": "File content not found."}), 404


def _sort_and_clean_submission_files(files):
    files.sort(key=lambda item: item.get("sort_at") or datetime.min, reverse=True)
    for item in files:
        item.pop("sort_at", None)
    return files

# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────


@supervisor_progress_api_bp.route("/api/supervisor/progress/submissions", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_submitted_files():
    """Return only submitted files for projects owned by the logged-in supervisor."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Supervisor faculty record was not found."}), 404

        files = []
        access_filter = _submission_access_filter(cursor)
        access_params = _project_access_params(cursor, faculty_id)

        # Return ALL projects for this supervisor, even when they have no submissions.
        projects = _fetch_supervisor_projects(cursor, faculty_id)
        for project in projects:
            project["title"] = project.get("title") or f"Project {project.get('project_id')}"
            project["course_code"] = project.get("course_code") or ""
            project["course_label"] = _course_label_for_code(project.get("course_code") or "")
            project["members"] = project.get("members") or ""
            project["status"] = project.get("status") or ""
            project["submission_date"] = _dt(project.get("submission_date"))
            project["updated_at"] = _dt(project.get("updated_at"))

        # 1) COMP4300 / general project files
        if _table_exists(cursor, "project_files"):
            cursor.execute(
                f"""
                SELECT
                    pf.file_id,
                    pf.project_id,
                    pf.file_type,
                    pf.file_name,
                    pf.file_path,
                    pf.file_mime,
                    pf.file_size_mb,
                    pf.uploaded_at,
                    pf.file_data IS NOT NULL AS has_file_data,
                    p.title AS project_title,
                    p.project_type,
                    p.status AS project_status,
                    s.course_code,
                    COALESCE(u_upload.full_name, primary_user.full_name, 'Unknown student') AS submitted_by,
                    sup_user.full_name AS supervisor_name,
                    GROUP_CONCAT(DISTINCT team_user.full_name ORDER BY pm.is_primary_contact DESC, team_user.full_name SEPARATOR ', ') AS team_members
                FROM project_files pf
                JOIN projects p ON p.project_id = pf.project_id
                LEFT JOIN semesters s ON s.semester_id = p.semester_id
                LEFT JOIN users u_upload ON u_upload.user_id = pf.uploaded_by
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_user ON sup_user.user_id = sup_f.user_id
                LEFT JOIN project_members pm ON pm.project_id = p.project_id
                LEFT JOIN students team_st ON team_st.student_id = pm.student_id
                LEFT JOIN users team_user ON team_user.user_id = team_st.user_id
                LEFT JOIN project_members primary_pm
                       ON primary_pm.project_id = p.project_id
                      AND primary_pm.is_primary_contact = TRUE
                LEFT JOIN students primary_st ON primary_st.student_id = primary_pm.student_id
                LEFT JOIN users primary_user ON primary_user.user_id = primary_st.user_id
                WHERE {access_filter}
                  AND s.course_code = 'COMP4300'
                  AND (
                        COALESCE(pf.upload_status, 'uploaded') = 'uploaded'
                        OR pf.uploaded_at IS NOT NULL
                        OR pf.file_data IS NOT NULL
                        OR COALESCE(pf.file_path, '') <> ''
                      )
                GROUP BY
                    pf.file_id, pf.project_id, pf.file_type, pf.file_name,
                    pf.file_path, pf.file_mime, pf.file_size_mb, pf.uploaded_at,
                    p.title, p.project_type, p.status, s.course_code,
                    u_upload.full_name, primary_user.full_name, sup_user.full_name
                ORDER BY pf.uploaded_at DESC, pf.file_id DESC
                """,
                access_params,
            )
            for row in cursor.fetchall():
                course_code = row.get("course_code") or "COMP4300"
                uploaded_at = row.get("uploaded_at")
                files.append(
                    {
                        "source": "project",
                        "source_id": row.get("file_id"),
                        "project_id": row.get("project_id"),
                        "file_type": row.get("file_type") or "project_file",
                        "submission_title": "Project File Submission" if course_code != "COMP4300" else "Graduation Project Final Submission",
                        "course_scope": course_code,
                        "course_code": course_code,
                        "course_label": _course_label_for_code(course_code),
                        "project_title": row.get("project_title") or "Untitled Project",
                        "project_type": _text_value(row.get("project_type")),
                        "project_status": row.get("project_status") or "",
                        "supervisor_name": row.get("supervisor_name") or "",
                        "team_members": row.get("team_members") or "",
                        "submitted_by": row.get("submitted_by") or "Unknown student",
                        "file_name": row.get("file_name") or "Open file",
                        "file_path": row.get("file_path") or "",
                        "file_size_mb": float(row.get("file_size_mb") or 0),
                        "uploaded_at": _format_submission_datetime(uploaded_at),
                        "sort_at": uploaded_at,
                        "download_url": f"/api/supervisor/progress/project-files/{row.get('file_id')}/download",
                    }
                )

        # 2) COMP4200 timeline milestone submissions sent to supervisor/both
        if (
            _table_exists(cursor, "milestone_submissions")
            and _table_exists(cursor, "comp4200_timeline_items")
            and _table_exists(cursor, "comp4200_timelines")
        ):
            cursor.execute(
                f"""
                SELECT
                    ms.submission_id,
                    ms.project_id,
                    ms.file_name,
                    ms.file_mime,
                    ms.file_size_mb,
                    ms.submitted_at,
                    ms.file_data IS NOT NULL AS has_file_data,
                    ti.title AS milestone_title,
                    ti.milestone_label,
                    p.title AS project_title,
                    p.status AS project_status,
                    s.course_code,
                    u_student.full_name AS submitted_by,
                    sup_user.full_name AS supervisor_name,
                    GROUP_CONCAT(DISTINCT team_user.full_name ORDER BY pm.is_primary_contact DESC, team_user.full_name SEPARATOR ', ') AS team_members
                FROM milestone_submissions ms
                JOIN projects p ON p.project_id = ms.project_id
                LEFT JOIN semesters s ON s.semester_id = p.semester_id
                JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
                JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
                JOIN students st_submit ON st_submit.student_id = ms.student_id
                JOIN users u_student ON u_student.user_id = st_submit.user_id
                LEFT JOIN faculty sup_f ON sup_f.faculty_id = p.supervisor_id
                LEFT JOIN users sup_user ON sup_user.user_id = sup_f.user_id
                LEFT JOIN project_members pm ON pm.project_id = p.project_id
                LEFT JOIN students team_st ON team_st.student_id = pm.student_id
                LEFT JOIN users team_user ON team_user.user_id = team_st.user_id
                WHERE {access_filter}
                  AND tl.is_published = TRUE
                  AND ms.submitted_to IN ('supervisor', 'both')
                GROUP BY
                    ms.submission_id, ms.project_id, ms.file_name, ms.file_mime,
                    ms.file_size_mb, ms.submitted_at, ti.title, ti.milestone_label,
                    p.title, p.status, s.course_code, u_student.full_name, sup_user.full_name
                ORDER BY ms.submitted_at DESC, ms.submission_id DESC
                """,
                access_params,
            )
            for row in cursor.fetchall():
                uploaded_at = row.get("submitted_at")
                course_code = row.get("course_code") or "COMP4200"
                files.append(
                    {
                        "source": "timeline",
                        "source_id": row.get("submission_id"),
                        "project_id": row.get("project_id"),
                        "file_type": "timeline_submission",
                        "submission_title": row.get("milestone_label") or row.get("milestone_title") or "Timeline Submission",
                        "course_scope": course_code,
                        "course_code": course_code,
                        "course_label": _course_label_for_code(course_code),
                        "project_title": row.get("project_title") or "Untitled Project",
                        "project_status": row.get("project_status") or "",
                        "supervisor_name": row.get("supervisor_name") or "",
                        "team_members": row.get("team_members") or "",
                        "submitted_by": row.get("submitted_by") or "Unknown student",
                        "file_name": row.get("file_name") or "Open file",
                        "file_size_mb": float(row.get("file_size_mb") or 0),
                        "uploaded_at": _format_submission_datetime(uploaded_at),
                        "sort_at": uploaded_at,
                        "download_url": f"/api/supervisor/progress/milestone-submissions/{row.get('submission_id')}/download",
                    }
                )

        cursor.close()
        db.close()
        return jsonify({
            "projects": projects,
            "files": _sort_and_clean_submission_files(files)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@supervisor_progress_api_bp.route("/api/supervisor/progress/project-files/<int:file_id>/download")
@login_required(role="supervisor")
def api_supervisor_download_project_file(file_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        faculty_id = _current_supervisor_faculty_id(cursor)
        access_filter = _submission_access_filter(cursor)
        params = (file_id,) + _project_access_params(cursor, faculty_id)
        cursor.execute(
            f"""
            SELECT pf.file_name, pf.file_path, pf.file_data, pf.file_mime
            FROM project_files pf
            JOIN projects p ON p.project_id = pf.project_id
            LEFT JOIN semesters s ON s.semester_id = p.semester_id
            WHERE pf.file_id = %s
              AND {access_filter}
              AND s.course_code = 'COMP4300'
              AND (
                    COALESCE(pf.upload_status, 'uploaded') = 'uploaded'
                    OR pf.uploaded_at IS NOT NULL
                    OR pf.file_data IS NOT NULL
                    OR COALESCE(pf.file_path, '') <> ''
                  )
            LIMIT 1
            """,
            params,
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return _file_download_response(row, "project-file")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@supervisor_progress_api_bp.route("/api/supervisor/progress/milestone-submissions/<int:submission_id>/download")
@login_required(role="supervisor")
def api_supervisor_download_milestone_submission(submission_id):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        faculty_id = _current_supervisor_faculty_id(cursor)
        access_filter = _submission_access_filter(cursor)
        params = (submission_id,) + _project_access_params(cursor, faculty_id)
        cursor.execute(
            f"""
            SELECT ms.file_name, ms.file_data, ms.file_mime
            FROM milestone_submissions ms
            JOIN projects p ON p.project_id = ms.project_id
            LEFT JOIN semesters s ON s.semester_id = p.semester_id
            JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
            JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
            WHERE ms.submission_id = %s
              AND {access_filter}
              AND tl.is_published = TRUE
              AND ms.submitted_to IN ('supervisor', 'both')
            LIMIT 1
            """,
            params,
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return _file_download_response(row, "milestone-submission")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@supervisor_progress_api_bp.route("/api/supervisor/progress/projects", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_progress_projects():
    try:
        user_id = session.get("user_id")
        db = get_db()
        cursor = db.cursor(dictionary=True)

        faculty_id = _current_supervisor_faculty_id(cursor)
        projects = _fetch_supervisor_projects(cursor, faculty_id)

        for project in projects:
            project["submission_date"] = _dt(project.get("submission_date"))
            project["updated_at"] = _dt(project.get("updated_at"))

        cursor.close()
        db.close()

        return jsonify({"projects": projects})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@supervisor_progress_api_bp.route("/api/supervisor/progress/<int:project_id>", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_progress_detail(project_id):
    try:
        user_id = session.get("user_id")
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_progress_tables(cursor)

        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Supervisor faculty record was not found."}), 404

        project = _get_project_for_supervisor(cursor, project_id, faculty_id)
        if not project:
            cursor.close()
            db.close()
            return jsonify({"error": "Project not found or not assigned to you."}), 404

        file_counts = _file_counts(cursor, project_id)
        fb_count = _feedback_count(cursor, project_id, user_id)
        notes = _latest_notes(cursor, project_id, user_id)
        timeline, timeline_source = _exam_distribution_timeline(cursor, project, file_counts, fb_count)
        progress = _progress_from_timeline(timeline, file_counts, fb_count, project.get("status"))

        db.commit()
        cursor.close()
        db.close()

        return jsonify(
            {
                "project": {
                    "project_id": project.get("project_id"),
                    "title": project.get("title"),
                    "members": project.get("members") or "",
                    "status": project.get("status") or "",
                    "status_label": _logical_project_status(project.get("status"), timeline),
                    "course_code": project.get("course_code") or "",
                    "academic_year": project.get("academic_year") or "",
                    "submission_date": _dt(project.get("submission_date")),
                    "updated_at": _dt(project.get("updated_at")),
                },
                "files": file_counts,
                "feedback_count": fb_count,
                "timeline": timeline,
                "timeline_source": timeline_source,
                "progress": progress,
                "notes": notes,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@supervisor_progress_api_bp.route("/api/supervisor/progress/note", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_progress_note():
    try:
        user_id = session.get("user_id")
        data = request.get_json(silent=True) or {}

        project_id = data.get("project_id")
        note_text = (data.get("note_text") or "").strip()
        state = (data.get("state") or "on_track").strip()

        if not project_id:
            return jsonify({"error": "Please choose a project."}), 400
        if not note_text:
            return jsonify({"error": "Please write a note."}), 400
        if state not in {"on_track", "follow_up_needed", "urgent"}:
            state = "on_track"

        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_progress_tables(cursor)

        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            cursor.close()
            db.close()
            return jsonify({"error": "Supervisor faculty record was not found."}), 404

        access_filter = _project_access_filter(cursor)
        params = (project_id,) + _project_access_params(cursor, faculty_id)
        cursor.execute(
            f"""
            SELECT p.project_id
            FROM projects p
            WHERE p.project_id = %s
              AND {access_filter}
            LIMIT 1
            """,
            params,
        )
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "Project not found or not assigned to you."}), 404

        cursor.execute(
            """
            INSERT INTO supervisor_progress_notes
                (project_id, supervisor_user_id, note_text, state)
            VALUES (%s, %s, %s, %s)
            """,
            (project_id, user_id, note_text, state),
        )

        db.commit()
        cursor.close()
        db.close()

        return jsonify({"message": "Progress note saved successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
