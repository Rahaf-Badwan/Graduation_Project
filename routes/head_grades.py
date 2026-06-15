from flask import Blueprint, render_template, jsonify, session
from auth import login_required
from db import get_db

head_grades_bp = Blueprint("head_grades_bp", __name__)


@head_grades_bp.route('/head/grades')
@login_required(role='head_of_department')
def head_grades_page():
    return render_template('head/grades.html')


@head_grades_bp.route('/head/api/grades-from-supervisors')
@login_required(role='head_of_department')
def api_grades_from_supervisors():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            efr.result_id,
            efr.final_score,
            efr.workflow_status,
            efr.course_scope,
            p.title AS project_title,
            p.project_id,
            u_sup.full_name AS supervisor_name,
            GROUP_CONCAT(
                DISTINCT u_st.full_name
                ORDER BY u_st.full_name
                SEPARATOR ', '
            ) AS students
        FROM evaluation_final_results efr
        JOIN projects p ON p.project_id = efr.reference_id
        LEFT JOIN faculty f_sup ON f_sup.faculty_id = efr.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u_st ON u_st.user_id = st.user_id
        WHERE efr.workflow_status = 'sent_to_head'
        GROUP BY efr.result_id, efr.final_score, efr.workflow_status,
                 efr.course_scope, p.title, p.project_id, u_sup.full_name
        ORDER BY u_sup.full_name, p.title
    """)

    grades = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify({"grades": grades})


@head_grades_bp.route('/head/api/publish-grades', methods=['POST'])
@login_required(role='head_of_department')
def api_publish_grades():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            efr.final_score,
            efr.reference_id AS project_id,
            st.user_id AS student_user_id,
            p.title AS project_title
        FROM evaluation_final_results efr
        JOIN projects p ON p.project_id = efr.reference_id
        JOIN project_members pm ON pm.project_id = p.project_id
        JOIN students st ON st.student_id = pm.student_id
        WHERE efr.workflow_status = 'sent_to_head'
    """)
    to_notify = cursor.fetchall()

    if not to_notify:
        cursor.close()
        return jsonify({"success": False, "message": "No grades to publish."})

    cursor.execute("""
        UPDATE evaluation_final_results
        SET
            workflow_status   = 'published_to_students',
            head_published_by = %s,
            head_published_at = NOW()
        WHERE workflow_status = 'sent_to_head'
    """, (user_id,))

    notified = 0
    for s in to_notify:
        cursor.execute("""
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type,
                 title, message, related_project_id)
            VALUES (%s, %s, 'status_changed',
                    'Your Final Grade Has Been Published',
                    %s, %s)
        """, (
            s['student_user_id'],
            user_id,
            f"Your final grade for project \"{s['project_title']}\" "
            f"has been published. Final Score: {s['final_score']}",
            s['project_id']
        ))
        notified += 1

    db.commit()
    cursor.close()
    db.close()
    return jsonify({"success": True, "notified": notified})