from flask import Blueprint, render_template, session, redirect, url_for
from functools import wraps
from db import get_db

supervisor_mystudents_bp = Blueprint("supervisor_mystudents", __name__)

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


@supervisor_mystudents_bp.route('/supervisor/mystudents')
@login_required(role='supervisor')
def supervisor_mystudents():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT faculty_id FROM faculty WHERE user_id = %s", (user_id,))
    faculty_row = cursor.fetchone()
    if not faculty_row:
        return "Supervisor not found", 404
    faculty_id = faculty_row['faculty_id']

    cursor.execute("""
        SELECT
            p.project_id,
            p.title,
            p.status,
            p.final_score,
            p.group_name,
            s.academic_year,
            s.course_code,
            COALESCE(pp_overall.percentage, 0) AS overall_progress,
            COALESCE(pp_report.percentage,  0) AS report_progress,
            COALESCE(pp_code.percentage,    0) AS code_progress,
            COALESCE(pp_slides.percentage,  0) AS slides_progress,
            GROUP_CONCAT(u.full_name ORDER BY u.full_name SEPARATOR ', ') AS students,
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
               ON pp_report.project_id  = p.project_id AND pp_report.component  = 'final_report'
        LEFT JOIN project_progress pp_code
               ON pp_code.project_id    = p.project_id AND pp_code.component    = 'source_code'
        LEFT JOIN project_progress pp_slides
               ON pp_slides.project_id  = p.project_id AND pp_slides.component  = 'presentation'
        WHERE p.supervisor_id = %s
          AND s.is_active = TRUE
        GROUP BY
            p.project_id, p.title, p.status, p.final_score,
            p.group_name, s.academic_year, s.course_code,
            pp_overall.percentage, pp_report.percentage,
            pp_code.percentage, pp_slides.percentage
        ORDER BY FIELD(p.status,
            'under_review','submitted','committee_evaluation',
            'needs_revision','accepted','rejected','archived','draft')
    """, (faculty_id, faculty_id, faculty_id))

    projects = cursor.fetchall()
    cursor.close()

    total = len(projects)

    return render_template(
        'supervisor/mystudents.html',
        projects = projects,
        total    = total,
    )