from flask import Blueprint, jsonify, session
from db import get_db
from auth import login_required

dashboard_bp = Blueprint("dashboard_bp", __name__)


def _current_dashboard_semester(cursor):
    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
          AND start_date IS NOT NULL
          AND end_date IS NOT NULL
          AND CURDATE() BETWEEN start_date AND end_date
        ORDER BY start_date DESC, semester_id DESC
        LIMIT 1
    """)
    semester = cursor.fetchone()
    if semester:
        return semester

    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
    """)
    return cursor.fetchone()


@dashboard_bp.route('/api/dashboard-data')
@login_required(role="head_of_department")
def api_dashboard_data():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    semester = _current_dashboard_semester(cursor)
    semester_id = semester["semester_id"] if semester else None

    if not semester_id:
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
        })

    current_semester_projects = """
        FROM projects p
        WHERE p.semester_id = %s
          AND p.status <> 'archived'
          AND EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users us ON us.user_id = st.user_id
                WHERE pm.project_id = p.project_id
                  AND us.is_active = TRUE
          )
    """

    cursor.execute(f"""
        SELECT COUNT(*) AS total_projects
        {current_semester_projects}
    """, (semester_id,))
    total_projects = (cursor.fetchone() or {}).get("total_projects", 0)

    # Count supervisors participating in this semester, not all supervisor accounts.
    cursor.execute("""
        SELECT COUNT(DISTINCT f.faculty_id) AS active_supervisors
        FROM projects p
        JOIN faculty f ON f.faculty_id = p.supervisor_id
        JOIN users u ON u.user_id = f.user_id
        WHERE p.semester_id = %s
          AND p.status <> 'archived'
          AND u.is_active = TRUE
          AND u.role = 'supervisor'
          AND EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users us ON us.user_id = st.user_id
                WHERE pm.project_id = p.project_id
                  AND us.is_active = TRUE
          )
    """, (semester_id,))
    active_supervisors = (cursor.fetchone() or {}).get("active_supervisors", 0)

    # Acceptance rate
    cursor.execute(f"""
        SELECT
            SUM(p.status = 'accepted') AS accepted_count,
            SUM(p.status = 'rejected') AS rejected_count
        {current_semester_projects}
    """, (semester_id,))
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
    """, (semester_id,))
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
    cursor.execute("""
        SELECT
            f.specialization,
            ROUND(AVG(p.final_score), 1) AS avg_score,
            COUNT(p.project_id) AS project_count
        FROM projects p
        JOIN faculty f ON f.faculty_id = p.supervisor_id
        WHERE p.semester_id = %s
          AND p.status <> 'archived'
          AND p.final_score IS NOT NULL
          AND EXISTS (
                SELECT 1
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users us ON us.user_id = st.user_id
                WHERE pm.project_id = p.project_id
                  AND us.is_active = TRUE
          )
        GROUP BY f.specialization
        ORDER BY avg_score DESC
    """, (semester_id,))
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
    cursor.execute("""
        SELECT u.full_name AS coordinator_name, u.email AS coordinator_email
        FROM coordinator_assignments ca
        JOIN faculty f ON f.faculty_id = ca.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE ca.semester_id = %s
        LIMIT 1
    """, (semester_id,))
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
        "semester": semester,
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
