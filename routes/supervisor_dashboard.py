from flask import Blueprint, render_template, session, redirect, url_for
from functools import wraps
from db import get_db

supervisor_dashboard_bp = Blueprint("supervisor_dashboard", __name__)

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

    cursor.execute("SELECT faculty_id FROM faculty WHERE user_id = %s", (user_id,))
    faculty_row = cursor.fetchone()

    print("=== SUPERVISOR DASHBOARD DEBUG ===")
    print("session user_id:", user_id)
    print("faculty_row:", faculty_row)

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
        print("fallback lookup:", fallback)
        cursor.close()
        return "Supervisor not found (check console debug output)", 404

    faculty_id = faculty_row['faculty_id']
    print("resolved faculty_id:", faculty_id)

    cursor.execute("""
        SELECT
            COUNT(DISTINCT p.project_id)                        AS total_projects,
            SUM(p.status NOT IN ('draft','rejected'))           AS active_projects,
            ROUND(AVG(p.final_score), 1)                        AS avg_score,
            SUM(
                EXISTS (
                    SELECT 1 FROM supervisor_notes sn
                    WHERE sn.project_id   = p.project_id
                      AND sn.supervisor_id = %s
                      AND sn.urgency       = 'urgent'
                )
            ) AS urgent_count
        FROM projects p
        WHERE p.supervisor_id = %s
    """, (faculty_id, faculty_id))
    stats = cursor.fetchone() or {}

    total_projects = stats.get('total_projects') or 0
    urgent_count   = stats.get('urgent_count')   or 0
    avg_score      = stats.get('avg_score')       or 0
    on_track_count = (stats.get('active_projects') or 0) - urgent_count

    cursor.execute("""
        SELECT
            p.project_id,
            p.title,
            p.status,
            p.group_name,
            s.course_code,
            COALESCE(pp.percentage, 0) AS overall_progress,
            GROUP_CONCAT(u.full_name ORDER BY u.full_name SEPARATOR ', ') AS students,
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
        LEFT JOIN project_progress pp
               ON pp.project_id = p.project_id AND pp.component = 'overall'
        WHERE p.supervisor_id = %s
          AND p.status NOT IN ('archived', 'draft')
        GROUP BY p.project_id, p.title, p.status, p.group_name,
                 s.course_code, pp.percentage
        ORDER BY FIELD(p.status,
            'under_review','submitted','needs_revision',
            'committee_evaluation','accepted','rejected')
        LIMIT 3
    """, (faculty_id, faculty_id, faculty_id))
    overview_projects = cursor.fetchall()

    cursor.execute("""
        SELECT deadline_type, deadline_date, description,
               DATEDIFF(deadline_date, CURDATE()) AS days_left
        FROM deadlines
        WHERE semester_id = (
            SELECT semester_id FROM semesters WHERE is_active = TRUE LIMIT 1
        )
          AND (project_id IS NULL
               OR project_id IN (
                   SELECT project_id FROM projects WHERE supervisor_id = %s
               ))
          AND deadline_date >= CURDATE()
        ORDER BY deadline_date ASC
        LIMIT 4
    """, (faculty_id,))
    deadlines = cursor.fetchall()

    cursor.execute("""
        SELECT
            COUNT(DISTINCT p.project_id) AS total,
            SUM(p.status NOT IN ('draft','rejected')) AS active,
            COUNT(DISTINCT f.feedback_id) AS feedback_count
        FROM projects p
        LEFT JOIN feedback f ON f.project_id = p.project_id
                             AND f.reviewer_id = %s
        WHERE p.supervisor_id = %s
    """, (user_id, faculty_id))
    perf = cursor.fetchone() or {}

    perf_total    = perf.get('total')          or 0
    perf_active   = perf.get('active')         or 0
    perf_feedback = perf.get('feedback_count') or 0
    progress_pct  = round((perf_active / perf_total * 100) if perf_total else 0)
    feedback_pct  = round((perf_feedback / (perf_total * 3) * 100) if perf_total else 0)
    feedback_pct  = min(feedback_pct, 100)

    cursor.execute("""
        SELECT p.project_id, p.title,
               GROUP_CONCAT(u.full_name ORDER BY u.full_name SEPARATOR ', ') AS students
        FROM projects p
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE p.supervisor_id = %s
          AND p.status NOT IN ('archived','draft','rejected')
          AND NOT EXISTS (
              SELECT 1 FROM feedback f
              WHERE f.project_id  = p.project_id
                AND f.reviewer_id = %s
                AND f.created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
          )
        GROUP BY p.project_id, p.title
        LIMIT 3
    """, (faculty_id, user_id))
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