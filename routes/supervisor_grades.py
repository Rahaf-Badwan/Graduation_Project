from flask import Blueprint, render_template, jsonify, session
from auth import login_required
from db import get_db
from routes.appCoordinator import (
    _ensure_evaluation_schema,
    _evaluation_fetch_grade_rows,
    _evaluation_grade_completion,
    _evaluation_ready_for_calculation,
    _evaluation_window_for_item,
)

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
        db.close()
        return jsonify({"grades": []})
    faculty_id = faculty['faculty_id']

    cursor.execute("""
        SELECT
            efr.result_id,
            efr.final_score,
            efr.workflow_status,
            efr.course_scope,
            COALESCE(NULLIF(p_intro.title, ''), sec.section_name) AS project_title,
            GROUP_CONCAT(
                DISTINCT u.full_name
                ORDER BY u.full_name
                SEPARATOR ', '
            ) AS students
        FROM evaluation_final_results efr
        JOIN student_distribution_sections sec
          ON sec.section_id = efr.reference_id
         AND efr.course_scope = 'introduction'
        LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
        LEFT JOIN projects p_intro ON p_intro.project_id = cps.project_id
        LEFT JOIN section_students ss ON ss.section_id = sec.section_id
        LEFT JOIN students st ON st.student_id = ss.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE sec.supervisor_id = %s
          AND efr.workflow_status IN ('sent_to_supervisor', 'sent_to_head', 'published_to_students')
        GROUP BY efr.result_id, efr.final_score, efr.workflow_status,
                 efr.course_scope, sec.section_name, p_intro.title
    """, (faculty_id,))
    grades = cursor.fetchall()

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
        JOIN projects p
          ON p.project_id = efr.reference_id
         AND efr.course_scope = 'graduation_project'
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u ON u.user_id = st.user_id
        WHERE p.supervisor_id = %s
          AND efr.workflow_status IN ('sent_to_supervisor', 'sent_to_head', 'published_to_students')
        GROUP BY efr.result_id, efr.final_score, efr.workflow_status,
                 efr.course_scope, p.title
    """, (faculty_id,))
    grades.extend(cursor.fetchall())
    grades.sort(key=lambda row: row.get("project_title") or "")
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
        db.close()
        return jsonify({"success": False, "message": "Supervisor not found"})
    faculty_id = faculty['faculty_id']

    cursor.execute("""
        SELECT efr.result_id, efr.course_scope, efr.reference_id, efr.final_score
        FROM evaluation_final_results efr
        WHERE efr.workflow_status = 'sent_to_supervisor'
          AND (
              EXISTS (
                  SELECT 1
                  FROM student_distribution_sections sec
                  WHERE efr.course_scope = 'introduction'
                    AND sec.section_id = efr.reference_id
                    AND sec.supervisor_id = %s
              )
              OR EXISTS (
                  SELECT 1
                  FROM projects p
                  WHERE efr.course_scope = 'graduation_project'
                    AND p.project_id = efr.reference_id
                    AND p.supervisor_id = %s
              )
          )
    """, (faculty_id, faculty_id))
    ready_rows = cursor.fetchall()

    if not ready_rows:
        cursor.close()
        db.close()
        return jsonify({"success": False, "message": "No grades ready to send."})

    _ensure_evaluation_schema(cursor)
    for row in ready_rows:
        course_scope = row.get("course_scope")
        reference_id = row.get("reference_id")
        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        completion = _evaluation_grade_completion(course_scope, grades)
        window = _evaluation_window_for_item(cursor, course_scope, reference_id)
        if (
            row.get("final_score") is None
            or not completion["grades_complete"]
            or not _evaluation_ready_for_calculation(window, completion)
        ):
            cursor.close()
            db.close()
            return jsonify({
                "success": False,
                "message": "All marks must be submitted and closed/calculated before sending to Head."
            })

    cursor.execute("""
        UPDATE evaluation_final_results efr
        SET
            efr.workflow_status            = 'sent_to_head',
            efr.supervisor_id              = %s,
            efr.supervisor_sent_by         = %s,
            efr.supervisor_sent_to_head_at = NOW()
        WHERE efr.workflow_status = 'sent_to_supervisor'
          AND (
              EXISTS (
                  SELECT 1
                  FROM student_distribution_sections sec
                  WHERE efr.course_scope = 'introduction'
                    AND sec.section_id = efr.reference_id
                    AND sec.supervisor_id = %s
              )
              OR EXISTS (
                  SELECT 1
                  FROM projects p
                  WHERE efr.course_scope = 'graduation_project'
                    AND p.project_id = efr.reference_id
                    AND p.supervisor_id = %s
              )
          )
    """, (faculty_id, user_id, faculty_id, faculty_id))

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
