from flask import Blueprint, jsonify, session
from db import get_db
from auth import login_required

dashboard_bp = Blueprint("dashboard_bp", __name__)


@dashboard_bp.route('/api/dashboard-data')
@login_required(role="head_of_department")
def api_dashboard_data():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Dashboard statistics describe the current cycle only. Historical and
    # archived projects must not leak into the "this semester" cards.
    active_semester_join = """
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE s.is_active = TRUE
          AND p.status <> 'archived'
    """

    cursor.execute(f"""
        SELECT COUNT(*) AS total_projects
        {active_semester_join}
    """)
    total_projects = (cursor.fetchone() or {}).get("total_projects", 0)

    # Active supervisor accounts are independent of whether projects have
    # already been created in the current cycle.
    cursor.execute("""
        SELECT COUNT(DISTINCT f.faculty_id) AS active_supervisors
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.is_active = TRUE
          AND u.role = 'supervisor'
    """)
    active_supervisors = (cursor.fetchone() or {}).get("active_supervisors", 0)

    # Acceptance rate
    cursor.execute(f"""
        SELECT
            SUM(p.status = 'accepted') AS accepted_count,
            SUM(p.status = 'rejected') AS rejected_count
        {active_semester_join}
    """)
    row = cursor.fetchone() or {}
    accepted = row.get("accepted_count") or 0
    rejected = row.get("rejected_count") or 0
    total_decided = accepted + rejected
    acceptance_rate = round((accepted / total_decided * 100), 1) if total_decided else 0

    # Average grade
    cursor.execute(f"""
        SELECT ROUND(AVG(p.final_score), 1) AS avg_grade
        {active_semester_join}
          AND p.final_score IS NOT NULL
    """)
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
        JOIN semesters s ON s.semester_id = p.semester_id
        JOIN faculty f ON f.faculty_id = p.supervisor_id
        WHERE s.is_active = TRUE
          AND p.status <> 'archived'
          AND p.final_score IS NOT NULL
        GROUP BY f.specialization
        ORDER BY avg_score DESC
    """)
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

    # Current coordinator (active semester, any course)
    cursor.execute("""
        SELECT u.full_name AS coordinator_name, u.email AS coordinator_email
        FROM coordinator_assignments ca
        JOIN semesters s ON s.semester_id = ca.semester_id
        JOIN faculty f ON f.faculty_id = ca.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE s.is_active = TRUE
        LIMIT 1
    """)
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
