from flask import Blueprint, render_template, jsonify, session
from auth import login_required
from db import get_db

supervisor_grades_bp = Blueprint("supervisor_grades_bp", __name__)


@supervisor_grades_bp.route('/supervisor/grades')
@login_required(role='supervisor')
def supervisor_grades_page():
    return render_template('supervisor/grades.html')


@supervisor_grades_bp.route('/supervisor/api/my-grades')
@login_required(role='supervisor')
def api_supervisor_my_grades():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT faculty_id FROM faculty WHERE user_id = %s", (user_id,))
    faculty = cursor.fetchone()
    if not faculty:
        cursor.close()
        return jsonify({"grades": []})
    faculty_id = faculty['faculty_id']

    cursor.execute("""
        SELECT
            efr.result_id,
            efr.final_score,
            efr.workflow_status,
            efr.course_scope,
            p.title AS project_title,
            GROUP_CONCAT(
                DISTINCT u.full_name
                ORDER BY u.full_name
                SEPARATOR ', '
            ) AS students
        FROM evaluation_final_results efr
        JOIN projects p ON p.project_id = efr.reference_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE p.supervisor_id = %s
          AND efr.workflow_status IN ('sent_to_supervisor', 'sent_to_head', 'published_to_students')
        GROUP BY efr.result_id, efr.final_score, efr.workflow_status,
                 efr.course_scope, p.title
        ORDER BY p.title
    """, (faculty_id,))

    grades = cursor.fetchall()
    cursor.close()
    db.close()
    return jsonify({"grades": grades})


@supervisor_grades_bp.route('/supervisor/api/send-grades-to-head', methods=['POST'])
@login_required(role='supervisor')
def api_send_grades_to_head():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT faculty_id FROM faculty WHERE user_id = %s", (user_id,))
    faculty = cursor.fetchone()
    if not faculty:
        cursor.close()
        return jsonify({"success": False, "message": "Supervisor not found"})
    faculty_id = faculty['faculty_id']

    cursor.execute("""
        SELECT COUNT(*) AS cnt
        FROM evaluation_final_results efr
        JOIN projects p ON p.project_id = efr.reference_id
        WHERE p.supervisor_id = %s
          AND efr.workflow_status = 'sent_to_supervisor'
    """, (faculty_id,))
    count = (cursor.fetchone() or {}).get('cnt', 0)

    if not count:
        cursor.close()
        return jsonify({"success": False, "message": "No grades ready to send."})

    cursor.execute("""
        UPDATE evaluation_final_results efr
        JOIN projects p ON p.project_id = efr.reference_id
        SET
            efr.workflow_status            = 'sent_to_head',
            efr.supervisor_id              = %s,
            efr.supervisor_sent_by         = %s,
            efr.supervisor_sent_to_head_at = NOW()
        WHERE p.supervisor_id = %s
          AND efr.workflow_status = 'sent_to_supervisor'
    """, (faculty_id, user_id, faculty_id))

    cursor.execute("SELECT full_name FROM users WHERE user_id = %s", (user_id,))
    sup = cursor.fetchone()
    sup_name = sup['full_name'] if sup else 'A Supervisor'

    cursor.execute(
        "SELECT user_id FROM users WHERE role = 'head_of_department' LIMIT 1"
    )
    head = cursor.fetchone()
    if head:
        cursor.execute("""
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type, title, message)
            VALUES (%s, %s, 'status_changed',
                    'Grades Received from Supervisor', %s)
        """, (
            head['user_id'],
            user_id,
            f"{sup_name} has sent final grades for their supervised projects. "
            f"Please review and publish them to students."
        ))

    db.commit()
    cursor.close()
    db.close()
    return jsonify({"success": True})