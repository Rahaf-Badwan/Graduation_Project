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
            COALESCE(NULLIF(p.title, ''), NULLIF(p.group_name, ''), CONCAT('Project ', p.project_id)) AS title,
            p.status,
            p.final_score,
            p.group_name,
            CASE
                WHEN COALESCE(p.group_name, '') REGEXP '^Group [0-9]+$'
                    THEN CONCAT('Group ', p.project_id)
                ELSE COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id))
            END AS display_group_name,
            s.academic_year,
            s.course_code,
            CASE
                WHEN pf.has_final_report = 1 AND s.course_code = 'COMP4300' THEN 100
                ELSE GREATEST(
                    COALESCE(pp_overall.percentage, 0),
                    ROUND((
                        CASE WHEN pf.has_final_report = 1 THEN 100 ELSE 0 END +
                        CASE WHEN pf.has_source_code = 1 THEN 100 ELSE 0 END +
                        CASE WHEN pf.has_presentation = 1 THEN 100 ELSE 0 END
                    ) / 3)
                )
            END AS overall_progress,
            GREATEST(COALESCE(pp_report.percentage, 0), CASE WHEN pf.has_final_report = 1 THEN 100 ELSE 0 END) AS report_progress,
            GREATEST(COALESCE(pp_code.percentage, 0), CASE WHEN pf.has_source_code = 1 THEN 100 ELSE 0 END) AS code_progress,
            GREATEST(COALESCE(pp_slides.percentage, 0), CASE WHEN pf.has_presentation = 1 THEN 100 ELSE 0 END) AS slides_progress,
            COALESCE(pf.has_final_report, 0) AS has_final_report,
            COALESCE(pf.has_source_code, 0) AS has_source_code,
            COALESCE(pf.has_presentation, 0) AS has_presentation,
            pf.latest_uploaded_at,
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
          AND LOWER(COALESCE(p.status, '')) NOT IN ('archived', 'archive', 'draft', 'cancelled')
        GROUP BY
            p.project_id, p.title, p.status, p.final_score,
            p.group_name, s.academic_year, s.course_code,
            pp_overall.percentage, pp_report.percentage,
            pp_code.percentage, pp_slides.percentage,
            pf.has_final_report, pf.has_source_code, pf.has_presentation, pf.latest_uploaded_at
        HAVING team_size > 0
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
