from flask import Blueprint, jsonify, session
from db import get_db
from auth import login_required
from semester_lifecycle import auto_rollover_semesters

dashboard_bp = Blueprint("dashboard_bp", __name__)


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


def _current_dashboard_semesters(cursor):
    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
          AND start_date IS NOT NULL
          AND end_date IS NOT NULL
          AND CURDATE() BETWEEN start_date AND end_date
        ORDER BY start_date DESC, semester_id DESC
    """)
    semesters = cursor.fetchall()
    if semesters:
        return _project_year_semesters(cursor, semesters)

    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
    """)
    semesters = cursor.fetchall()
    if semesters:
        return _project_year_semesters(cursor, semesters)

    return _latest_project_year_semesters(cursor)


def _latest_project_year_semesters(cursor):
    cursor.execute("""
        SELECT sem.semester_id, sem.academic_year, sem.semester_number, sem.course_code
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE sem.academic_year IS NOT NULL
          AND sem.course_code IN ('COMP4200', 'COMP4300')
          AND LOWER(COALESCE(p.status, '')) NOT IN (
                'archived', 'archive', 'draft', 'cancelled', 'rejected',
                'promoted', 'search', 'search_only', 'imported_archive',
                'solo_pending'
          )
          AND COALESCE(p.title, '') NOT LIKE 'Committee Demo%%'
          AND COALESCE(p.title, '') NOT LIKE 'COMP4300 Graduation Project%%'
        ORDER BY sem.start_date DESC, sem.semester_id DESC
        LIMIT 1
    """)
    latest = cursor.fetchone()
    return _project_year_semesters(cursor, [latest]) if latest else []


def _project_year_semesters(cursor, anchor_semesters):
    term_pairs = sorted({
        (row["academic_year"], row["semester_number"])
        for row in anchor_semesters
        if row.get("academic_year") and row.get("semester_number") is not None
    })

    if not term_pairs:
        return anchor_semesters

    term_filters = " OR ".join(
        ["(academic_year = %s AND semester_number = %s)"] * len(term_pairs)
    )
    params = []
    for academic_year, semester_number in term_pairs:
        params.extend([academic_year, semester_number])

    cursor.execute(f"""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE ({term_filters})
          AND course_code IN ('COMP4200', 'COMP4300')
        ORDER BY academic_year DESC, semester_number DESC, semester_id DESC
    """, tuple(params))
    scoped = cursor.fetchall()
    if not scoped:
        return anchor_semesters

    anchor_ids = {row["semester_id"] for row in anchor_semesters if row.get("semester_id")}
    scoped.sort(
        key=lambda row: (
            0 if row.get("semester_id") in anchor_ids else 1,
            -int(row.get("semester_id") or 0),
        )
    )
    return scoped


def _dashboard_project_scope(cursor, semesters, include_rejected=False):
    semester_ids = [row["semester_id"] for row in semesters if row.get("semester_id")]
    placeholders = ",".join(["%s"] * len(semester_ids))
    promotion_filter = ""
    if _table_exists(cursor, "project_course_promotions"):
        promotion_filter = """
          AND NOT EXISTS (
                SELECT 1
                FROM project_course_promotions pcp
                WHERE pcp.source_project_id = p.project_id
          )
        """
    rejected_status = "" if include_rejected else "'rejected',"
    sql = f"""
        FROM projects p
        WHERE p.semester_id IN ({placeholders})
          AND LOWER(COALESCE(p.status, '')) NOT IN (
                'archived', 'archive', 'draft', 'cancelled', {rejected_status}
                'promoted', 'search', 'search_only', 'imported_archive',
                'solo_pending'
          )
          AND COALESCE(p.title, '') NOT LIKE 'Committee Demo%%'
          AND COALESCE(p.title, '') NOT LIKE 'COMP4300 Graduation Project%%'
          {promotion_filter}
          AND EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users us ON us.user_id = st.user_id
                WHERE pm.project_id = p.project_id
                  AND us.is_active = TRUE
          )
    """
    return sql, tuple(semester_ids)


@dashboard_bp.route('/api/dashboard-data')
@login_required(role="head_of_department")
def api_dashboard_data():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    auto_rollover_semesters(cursor)
    db.commit()

    semesters = _current_dashboard_semesters(cursor)

    if not semesters:
        cursor.close()
        db.close()
        return jsonify({
            "total_projects": 0,
            "active_supervisors": 0,
            "acceptance_rate": 0,
            "avg_grade": 0,
            "notifications": [],
            "specializations": [],
            "coordinator": {},
            "semester": None,
            "semesters": [],
        })

    current_semester_projects, semester_params = _dashboard_project_scope(cursor, semesters)
    decided_semester_projects, decided_semester_params = _dashboard_project_scope(
        cursor, semesters, include_rejected=True
    )

    cursor.execute(f"""
        SELECT COUNT(*) AS total_projects
        {current_semester_projects}
    """, semester_params)
    total_projects = (cursor.fetchone() or {}).get("total_projects", 0)

    # Count supervisors participating in this semester, not all supervisor accounts.
    cursor.execute(f"""
        SELECT COUNT(DISTINCT f.faculty_id) AS active_supervisors
        FROM projects p
        JOIN faculty f ON f.faculty_id = p.supervisor_id
        JOIN users u ON u.user_id = f.user_id
        WHERE p.project_id IN (
            SELECT scoped.project_id
            FROM (
                SELECT p.project_id
                {current_semester_projects}
            ) scoped
        )
          AND u.is_active = TRUE
          AND u.role = 'supervisor'
    """, semester_params)
    active_supervisors = (cursor.fetchone() or {}).get("active_supervisors", 0)

    # Acceptance rate
    cursor.execute(f"""
        SELECT
            SUM(p.status = 'accepted') AS accepted_count,
            SUM(p.status = 'rejected') AS rejected_count
        {decided_semester_projects}
    """, decided_semester_params)
    row = cursor.fetchone() or {}
    accepted = row.get("accepted_count") or 0
    rejected = row.get("rejected_count") or 0
    total_decided = accepted + rejected
    acceptance_rate = round((accepted / total_decided * 100), 1) if total_decided else 0

    # Average grade
    cursor.execute(f"""
        SELECT ROUND(AVG(p.final_score), 1) AS avg_grade
        {current_semester_projects}
          AND p.final_score IS NOT NULL
    """, semester_params)
    avg_grade = (cursor.fetchone() or {}).get("avg_grade") or 0

    # Last 3 notifications
    head_user_id = session.get("user_id")
    cursor.execute("""
        SELECT
            notification_id, title, message, notification_type,
            is_read, created_at, related_project_id
        FROM notifications
        WHERE recipient_id = %s
        ORDER BY created_at DESC
        LIMIT 3
    """, (head_user_id,))
    notifications = cursor.fetchall()

    for n in notifications:
        if n.get("created_at"):
            n["created_at"] = n["created_at"].strftime("%Y-%m-%dT%H:%M:%S")

    # Performance per specialization
    cursor.execute(f"""
        SELECT
            f.specialization,
            ROUND(AVG(p.final_score), 1) AS avg_score,
            COUNT(p.project_id) AS project_count
        FROM projects p
        JOIN faculty f ON f.faculty_id = p.supervisor_id
        WHERE p.project_id IN (
            SELECT scoped.project_id
            FROM (
                SELECT p.project_id
                {current_semester_projects}
            ) scoped
        )
          AND p.final_score IS NOT NULL
        GROUP BY f.specialization
        ORDER BY avg_score DESC
    """, semester_params)
    specialization_raw = cursor.fetchall()

    spec_labels = {
        "artificial_intelligence": "AI & Machine Learning",
        "web_development": "Web Development",
        "software_engineering": "Software Engineering",
        "security_networks": "Networking & Security",
        "mobile": "Mobile Development",
        "databases": "Databases",
        "other": "Other",
    }
    spec_colors = {
        "artificial_intelligence": "var(--teal)",
        "web_development": "var(--blue)",
        "software_engineering": "var(--amber)",
        "security_networks": "var(--purple)",
        "mobile": "var(--coral)",
        "databases": "var(--green)",
        "other": "var(--color-text-secondary)",
    }

    specializations = [
        {
            "label": spec_labels.get(r["specialization"], r["specialization"]),
            "avg": float(r["avg_score"] or 0),
            "count": r["project_count"],
            "color": spec_colors.get(r["specialization"], "var(--blue)"),
            "width": min(int(float(r["avg_score"] or 0)), 100),
        }
        for r in specialization_raw
    ]

    # Current coordinator for the same semester used by the statistic cards.
    cursor.execute(f"""
        SELECT u.full_name AS coordinator_name, u.email AS coordinator_email
        FROM coordinator_assignments ca
        JOIN faculty f ON f.faculty_id = ca.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE ca.semester_id IN ({",".join(["%s"] * len(semester_params))})
        ORDER BY ca.semester_id DESC
        LIMIT 1
    """, semester_params)
    coordinator = cursor.fetchone() or {}

    cursor.close()
    db.close()

    return jsonify({
        "total_projects": total_projects,
        "active_supervisors": active_supervisors,
        "acceptance_rate": acceptance_rate,
        "avg_grade": avg_grade,
        "notifications": notifications,
        "specializations": specializations,
        "coordinator": coordinator,
        "semester": semesters[0],
        "semesters": semesters,
    })


@dashboard_bp.route('/api/switch-role', methods=['POST'])
@login_required(role="head_of_department")
def api_switch_role():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    user_id = session.get("user_id")

    cursor.execute("""
        SELECT f.faculty_id 
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE f.user_id = %s
    """, (user_id,))

    faculty = cursor.fetchone()
    cursor.close()
    db.close()

    if not faculty:
        return jsonify({"success": False, "message": "No supervisor profile found"})

    session["role"] = "supervisor"
    session["original_role"] = "head_of_department"

    return jsonify({"success": True})
