from flask import Blueprint, jsonify, render_template, request, session, redirect, url_for
from db import get_db
from auth import login_required

dashboard_bp = Blueprint("dashboard_bp", __name__)


@dashboard_bp.route('/api/dashboard-data')
@login_required(role="head_of_department")
def api_dashboard_data():
    course_code = request.args.get("course", "COMP4200").upper().strip()

    if course_code not in ("COMP4200", "COMP4300"):
        course_code = "COMP4200"

    db = get_db()
    cursor = db.cursor(dictionary=True)
#numeber of projects
    cursor.execute("""
            SELECT COUNT(*) AS total_projects
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE s.is_active = TRUE
                   AND s.course_code = %s 
                   """, (course_code,))
    total_projetcs = (cursor.fetchone() or {}).get("total_projects", 0)
#number of supervisors
    cursor.execute("""
            SELECT COUNT(DISTINCT p.supervisor_id) AS active_supervisors
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE s.is_active = TRUE
                   AND s.course_code = %s
                   AND p.supervisor_id IS NOT NULL
                   """,(course_code,))
    active_supervisors = (cursor.fetchone() or {}).get("active_supervisors", 0)

    #acceptence rate
    cursor.execute("""
        SELECT
            SUM(status = 'accepted') AS accepted_count,
            SUM(status = 'rejected') AS rejected_count
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE s.is_active = TRUE
            AND s.course_code = %s    
                   """, (course_code,))
    row = cursor.fetchone() or {}
    accepted = row.get("accepted_count") or 0
    rejected = row.get("rejected_count") or 0
    total_decided = accepted + rejected
    acceptance_rate = round((accepted / total_decided * 100), 1) if total_decided else 0

    #avg of degress
    cursor.execute("""
        SELECT ROUND(AVG(p.final_score), 1) AS avg_grade
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE s.is_active = TRUE
                AND s.course_code = %s
                AND p.final_score IS NOT NULL
                   """, (course_code,))
    avg_grade = (cursor.fetchone() or {}).get("avg_grade") or 0

    #get the last three notification
    head_user_id = session.get("user_id")
    cursor.execute("""
        SELECT
            n.notification_id,
            n.title,
            n.message,
            n.notification_type,
            n.is_read,
            n.created_at,
            n.related_project_id
        FROM notifications n
        WHERE n.recipient_id = %s
        ORDER BY n.created_at DESC
        LIMIT 3
    """, (head_user_id, ))
    notifications = cursor.fetchall()
    
    for n in notifications:
        if n.get("created_at"):
            n["created_at"] = n["created_at"].strftime("%Y-%m-%dT%H:%M:%S")

    #performance of specialization
    cursor.execute("""
            SELECT
                f.specialization,
                ROUND(AVG(p.final_score), 1) AS avg_score,
                COUNT(p.project_id) AS project_count
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            WHERE s.is_active = TRUE
                AND s.course_code = %s
                AND p.final_score IS NOT NULL
            GROUP BY f.specialization
            ORDER BY avg_score DESC
                   """, (course_code,))
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

    #get the coordinator
    cursor.execute("""
        SELECT u.full_name AS coordinator_name, u.email AS coordinator_email
        FROM coordinator_assignments ca
        JOIN semesters s ON s.semester_id = ca.semester_id
        JOIN faculty f ON f.faculty_id = ca.faculty_id
        JOIN users u ON u.user_id = f.user_id
        WHERE s.is_active = TRUE
                AND s.course_code = %s
        LIMIT 1
                   """, (course_code,))
    coordinator = cursor.fetchone() or {}

    cursor.close()
    db.close()

    return jsonify({
       "course_code": course_code,
        "total_projects": total_projetcs,
        "active_supervisors": active_supervisors,
        "acceptance_rate": acceptance_rate,
        "avg_grade": avg_grade,
        "notifications": notifications,
        "specializations": specializations,
        "coordinator": coordinator,

    })