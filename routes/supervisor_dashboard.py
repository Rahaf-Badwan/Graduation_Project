from flask import Blueprint, render_template, session, redirect, url_for
from functools import wraps
from datetime import date, datetime
from db import get_db
from semester_lifecycle import auto_rollover_semesters

supervisor_dashboard_bp = Blueprint("supervisor_dashboard", __name__)

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


def _current_project_year_semesters(cursor, faculty_id):
    cursor.execute(
        """
        SELECT DISTINCT s.semester_id, s.academic_year, s.semester_number, s.course_code, s.start_date
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE p.supervisor_id = %s
          AND s.is_active = TRUE
          AND s.start_date IS NOT NULL
          AND s.end_date IS NOT NULL
          AND CURDATE() BETWEEN s.start_date AND s.end_date
        ORDER BY s.start_date DESC, s.semester_id DESC
        """,
        (faculty_id,),
    )
    anchors = cursor.fetchall()

    if not anchors:
        cursor.execute(
            """
            SELECT DISTINCT s.semester_id, s.academic_year, s.semester_number, s.course_code, s.start_date
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE p.supervisor_id = %s
              AND s.is_active = TRUE
            ORDER BY s.semester_id DESC
            """,
            (faculty_id,),
        )
        anchors = cursor.fetchall()

    if not anchors:
        cursor.execute(
            """
            SELECT DISTINCT s.semester_id, s.academic_year, s.semester_number, s.course_code, s.start_date
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE p.supervisor_id = %s
              AND COALESCE(p.status, '') NOT IN ('archived', 'archive', 'draft', 'cancelled', 'rejected')
              AND EXISTS (
                    SELECT 1
                    FROM project_members pm
                    WHERE pm.project_id = p.project_id
              )
            ORDER BY COALESCE(s.start_date, '1900-01-01') DESC, s.semester_id DESC
            LIMIT 1
            """,
            (faculty_id,),
        )
        latest = cursor.fetchone()
        anchors = [latest] if latest else []

    if not anchors:
        return []

    term_pairs = sorted({
        (row["academic_year"], row["semester_number"])
        for row in anchors
        if row.get("academic_year") and row.get("semester_number") is not None
    })
    if not term_pairs:
        return anchors

    term_filters = " OR ".join(
        ["(academic_year = %s AND semester_number = %s)"] * len(term_pairs)
    )
    params = []
    for academic_year, semester_number in term_pairs:
        params.extend([academic_year, semester_number])

    cursor.execute(
        f"""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE ({term_filters})
          AND course_code IN ('COMP4200', 'COMP4300')
        ORDER BY academic_year DESC, semester_number DESC, semester_id DESC
        """,
        tuple(params),
    )
    semesters = cursor.fetchall()
    if not semesters:
        return anchors

    anchor_ids = {row["semester_id"] for row in anchors if row.get("semester_id")}
    semesters.sort(
        key=lambda row: (
            0 if row.get("semester_id") in anchor_ids else 1,
            -int(row.get("semester_id") or 0),
        )
    )
    return semesters


def _semester_ids(semesters):
    return [row["semester_id"] for row in semesters if row.get("semester_id")]


def _promotion_source_filter(cursor, alias="p"):
    if not _table_exists(cursor, "project_course_promotions"):
        return ""
    return f"""
          AND NOT EXISTS (
              SELECT 1 FROM project_course_promotions pcp
              WHERE pcp.source_project_id = {alias}.project_id
          )
    """


def _current_semester_deadlines(cursor, faculty_id):
    active_project_filter = """
        SELECT p.project_id
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE p.supervisor_id = %s
          AND s.is_active = TRUE
          AND COALESCE(p.status, '') NOT IN ('archived', 'archive', 'draft', 'cancelled')
    """
    active_semester_filter = """
        SELECT DISTINCT p.semester_id
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE p.supervisor_id = %s
          AND s.is_active = TRUE
          AND p.semester_id IS NOT NULL
          AND COALESCE(p.status, '') NOT IN ('archived', 'archive', 'draft', 'cancelled')
    """

    cursor.execute(
        f"""
        SELECT d.deadline_type, d.deadline_date, d.description,
               DATEDIFF(d.deadline_date, CURDATE()) AS days_left
        FROM deadlines d
        WHERE d.semester_id IN ({active_semester_filter})
          AND (d.project_id IS NULL OR d.project_id IN ({active_project_filter}))
        ORDER BY d.deadline_date ASC
        """,
        (faculty_id, faculty_id),
    )
    rows = cursor.fetchall()

    deliverables_exists = _table_exists(cursor, "coordinator_deliverables")
    due_expr = None
    if deliverables_exists:
        has_due_date = _column_exists(cursor, "coordinator_deliverables", "due_date")
        has_due_at = _column_exists(cursor, "coordinator_deliverables", "due_at")
        if has_due_date and has_due_at:
            due_expr = "COALESCE(cd.due_date, DATE(cd.due_at))"
        elif has_due_date:
            due_expr = "cd.due_date"
        elif has_due_at:
            due_expr = "DATE(cd.due_at)"

    if deliverables_exists and due_expr:
        publish_filter = (
            "AND COALESCE(cd.is_published, 0) = 1"
            if _column_exists(cursor, "coordinator_deliverables", "is_published")
            else ""
        )
        cursor.execute(
            f"""
            SELECT CONCAT('coordinator_deliverable_', cd.deliverable_id) AS deadline_type,
                   {due_expr} AS deadline_date,
                   CONCAT('Assignment: ', cd.title) AS description,
                   DATEDIFF({due_expr}, CURDATE()) AS days_left
            FROM coordinator_deliverables cd
            WHERE cd.semester_id IN ({active_semester_filter})
              AND {due_expr} IS NOT NULL
              {publish_filter}
            ORDER BY {due_expr} ASC
            """,
            (faculty_id,),
        )
        rows.extend(cursor.fetchall())

    unique = {}
    for row in rows:
        key = (row.get("deadline_date"), row.get("description") or row.get("deadline_type"))
        if key not in unique:
            unique[key] = row

    today = date.today()

    def sort_key(item):
        deadline_date = item.get("deadline_date")
        if isinstance(deadline_date, datetime):
            deadline_date = deadline_date.date()
        if not deadline_date:
            return (2, date.max)
        if deadline_date >= today:
            return (0, deadline_date)
        return (1, date.max.toordinal() - deadline_date.toordinal())

    return sorted(
        unique.values(),
        key=sort_key,
    )[:4]


def _supervisor_dashboard_projects(cursor, faculty_id, semester_ids):
    if not semester_ids:
        return []

    placeholders = ",".join(["%s"] * len(semester_ids))
    promotion_filter = _promotion_source_filter(cursor, "p")
    cursor.execute(f"""
        SELECT
            p.project_id,
            COALESCE(NULLIF(p.title, ''), NULLIF(p.group_name, ''), CONCAT('Project ', p.project_id)) AS title,
            p.status,
            p.final_score,
            p.group_name,
            CASE
                WHEN COALESCE(p.group_name, '') REGEXP '^Group [0-9]+$'
                    THEN CONCAT('Group ', p.project_id)
                ELSE COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id))
            END AS display_group_name,
            s.course_code,
            GREATEST(
                COALESCE(pp_overall.percentage, 0),
                CASE WHEN COALESCE(pf.has_final_report, 0) = 1 THEN 100 ELSE 0 END
            ) AS overall_progress,
            GREATEST(
                COALESCE(pp_report.percentage, 0),
                CASE WHEN COALESCE(pf.has_final_report, 0) = 1 THEN 100 ELSE 0 END
            ) AS report_progress,
            GREATEST(
                COALESCE(pp_code.percentage, 0),
                CASE WHEN COALESCE(pf.has_source_code, 0) = 1 THEN 100 ELSE 0 END
            ) AS code_progress,
            GREATEST(
                COALESCE(pp_slides.percentage, 0),
                CASE WHEN COALESCE(pf.has_presentation, 0) = 1 THEN 100 ELSE 0 END
            ) AS slides_progress,
            COALESCE(pf.has_final_report, 0) AS has_final_report,
            COALESCE(pf.has_source_code, 0) AS has_source_code,
            COALESCE(pf.has_presentation, 0) AS has_presentation,
            pf.latest_uploaded_at,
            GROUP_CONCAT(DISTINCT u.full_name ORDER BY u.full_name SEPARATOR ', ') AS students,
            COUNT(DISTINCT pm.student_id) AS team_size,
            (SELECT sn.urgency FROM supervisor_notes sn
             WHERE sn.project_id = p.project_id AND sn.supervisor_id = %s
             ORDER BY sn.created_at DESC LIMIT 1) AS urgency,
            (SELECT sn.note_text FROM supervisor_notes sn
             WHERE sn.project_id = p.project_id AND sn.supervisor_id = %s
             ORDER BY sn.created_at DESC LIMIT 1) AS last_note
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        LEFT JOIN project_progress pp_overall
               ON pp_overall.project_id = p.project_id AND pp_overall.component = 'overall'
        LEFT JOIN project_progress pp_report
               ON pp_report.project_id = p.project_id AND pp_report.component = 'final_report'
        LEFT JOIN project_progress pp_code
               ON pp_code.project_id = p.project_id AND pp_code.component = 'source_code'
        LEFT JOIN project_progress pp_slides
               ON pp_slides.project_id = p.project_id AND pp_slides.component = 'presentation'
        LEFT JOIN (
            SELECT
                project_id,
                MAX(CASE WHEN file_type = 'final_report' THEN 1 ELSE 0 END) AS has_final_report,
                MAX(CASE WHEN file_type = 'source_code' THEN 1 ELSE 0 END) AS has_source_code,
                MAX(CASE WHEN file_type = 'presentation' THEN 1 ELSE 0 END) AS has_presentation,
                MAX(uploaded_at) AS latest_uploaded_at
            FROM project_files
            WHERE (
                COALESCE(upload_status, 'uploaded') = 'uploaded'
                OR uploaded_at IS NOT NULL
                OR file_data IS NOT NULL
                OR COALESCE(file_path, '') <> ''
            )
            GROUP BY project_id
        ) pf ON pf.project_id = p.project_id
        WHERE p.supervisor_id = %s
          AND p.semester_id IN ({placeholders})
          AND LOWER(COALESCE(p.status, '')) NOT IN ('archived', 'archive', 'draft', 'cancelled', 'rejected')
          {promotion_filter}
        GROUP BY
            p.project_id, p.title, p.status, p.final_score,
            p.group_name, s.course_code,
            pp_overall.percentage, pp_report.percentage,
            pp_code.percentage, pp_slides.percentage,
            pf.has_final_report, pf.has_source_code, pf.has_presentation, pf.latest_uploaded_at
        HAVING team_size > 0
        ORDER BY
            overall_progress ASC,
            FIELD(p.status, 'needs_revision', 'under_review', 'submitted', 'committee_evaluation', 'accepted'),
            p.project_id DESC
    """, (faculty_id, faculty_id, faculty_id, *semester_ids))
    return cursor.fetchall()


def login_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if role and session.get('role') != role:
                from flask import abort
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


@supervisor_dashboard_bp.route('/supervisor/index', strict_slashes=False)
@supervisor_dashboard_bp.route('/supervisor/dashboard', strict_slashes=False)
@supervisor_dashboard_bp.route('/supervisor', strict_slashes=False)
@login_required(role='supervisor')
def supervisor_dashboard():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        auto_rollover_semesters(cursor)
        db.commit()
    except Exception:
        pass

    cursor.execute("SELECT faculty_id FROM faculty WHERE user_id = %s", (user_id,))
    faculty_row = cursor.fetchone()

    if not faculty_row:
        cursor.execute("""
            SELECT f.faculty_id, f.user_id, u.full_name, u.university_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE u.university_id = (
                SELECT university_id FROM users WHERE user_id = %s
            )
        """, (user_id,))
        fallback = cursor.fetchone()
        cursor.close()
        return "Supervisor not found (check console debug output)", 404

    faculty_id = faculty_row['faculty_id']
    project_year_semesters = _current_project_year_semesters(cursor, faculty_id)
    project_year_semester_ids = _semester_ids(project_year_semesters)
    dashboard_projects = _supervisor_dashboard_projects(cursor, faculty_id, project_year_semester_ids)

    total_projects = len(dashboard_projects)
    urgent_count = sum(1 for project in dashboard_projects if project.get("urgency") == "urgent")
    on_track_count = sum(
        1 for project in dashboard_projects
        if project.get("urgency") != "urgent" and int(project.get("overall_progress") or 0) >= 50
    )
    scored = [
        float(project["final_score"])
        for project in dashboard_projects
        if project.get("final_score") is not None
    ]
    avg_score = round(sum(scored) / len(scored), 1) if scored else None
    overview_projects = dashboard_projects[:3]

    deadlines = _current_semester_deadlines(cursor, faculty_id)

    semester_filter = ",".join(["%s"] * len(project_year_semester_ids))
    promotion_filter = _promotion_source_filter(cursor, "p")

    if project_year_semester_ids:
        cursor.execute(f"""
        SELECT COUNT(DISTINCT f.feedback_id) AS feedback_count
        FROM feedback f
        JOIN projects p ON p.project_id = f.project_id
        WHERE f.reviewer_id = %s
          AND p.supervisor_id = %s
          AND p.semester_id IN ({semester_filter})
          {promotion_filter}
    """, (user_id, faculty_id, *project_year_semester_ids))
        perf = cursor.fetchone() or {}
    else:
        perf = {}

    perf_total    = total_projects
    perf_feedback = perf.get('feedback_count') or 0
    progress_pct  = round(
        sum(int(project.get("overall_progress") or 0) for project in dashboard_projects) / perf_total
    ) if perf_total else 0
    feedback_pct  = round((perf_feedback / (perf_total * 3) * 100) if perf_total else 0)
    feedback_pct  = min(feedback_pct, 100)

    pending_feedback = []
    if project_year_semester_ids:
        cursor.execute(f"""
        SELECT p.project_id, p.title,
               GROUP_CONCAT(u.full_name ORDER BY u.full_name SEPARATOR ', ') AS students
        FROM projects p
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE p.supervisor_id = %s
          AND p.semester_id IN ({semester_filter})
          AND LOWER(COALESCE(p.status, '')) NOT IN ('archived','archive','draft','cancelled','rejected')
          {promotion_filter}
          AND NOT EXISTS (
              SELECT 1 FROM feedback f
              WHERE f.project_id  = p.project_id
                AND f.reviewer_id = %s
                AND f.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        )
        GROUP BY p.project_id, p.title
        LIMIT 3
    """, (faculty_id, *project_year_semester_ids, user_id))
        pending_feedback = cursor.fetchall()

    cursor.execute("""
        SELECT title, message, notification_type, is_read, created_at
        FROM notifications
        WHERE recipient_id = %s
        ORDER BY created_at DESC
        LIMIT 3
    """, (user_id,))
    notifications = cursor.fetchall()

    cursor.close()

    return render_template(
        'supervisor/index.html',
        total_projects   = total_projects,
        on_track_count   = on_track_count,
        urgent_count     = urgent_count,
        avg_score        = avg_score,
        overview_projects= overview_projects,
        deadlines        = deadlines,
        perf_total       = perf_total,
        perf_feedback    = perf_feedback,
        progress_pct     = progress_pct,
        feedback_pct     = feedback_pct,
        avg_score_perf   = avg_score,
        pending_feedback = pending_feedback,
        notifications    = notifications,
    )
