from flask import Blueprint, request, jsonify, session
from db import get_db
from auth import login_required

promote_bp = Blueprint('promote', __name__)

#get the student that pass the COMP4200
@promote_bp.route('/api/students/passes', methods=['GET'])
@login_required(role="head_of_department")
def api_get_passes_students():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        
        cursor.execute("""
                SELEST u.user_id, u.full_name, u.univesity_id, u.email
                          u.avatar_intials, scr.result_id
                FROM users u
                JOIN students st ON st.user_id = u.user_id
                JOIN student_course_result scr ON scr.student_id = st.student_id
                JOIN semesters sem ON sem.semester_id = scr.semester_id
                WHERE u.role = 'student'
                       AND u.is_active = TRUE
                       AND sem.course_code = 'COMP4200'
                       AND scr.status = 'passed'
                       AND scr.promoted_at IS NULL
                ORDER BY u.full_name
        """)
        students = cursor.fetchall()
        cursor.close()
        db.close()

        return jsonify({'students': students}), 200
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500
    
#sending the successfull students to the COMP4300 course
@promote_bp.route('/api/students/promote-all', methods=['POST'])
@login_required(role="head_of_department")
def api_promote_all():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
                    SELECT semester_id FROM semesters
                    WHERE course_code = 'COMP4300' AND is_active = TRUE
                    LIMIT 1; 
                       """)
        comp4300 = cursor.fetchone()

        if not comp4300:
            return jsonify({'error': 'No active COMP4300 semester found.'}), 400
        
        cursor.execute("""
            UPDATE student_course_results sct
            JOIN students st ON st.student_id = scr.student_id
            JOIN semesters sem ON sem.semester_id = scr.semester_id
            SET sct.promoted_to_semester_id = %s,
                       scr.promoted_by = %s
                       scr.promoted_at = NOW()
            WHERE sem.course_code = 'COMP4200'
                    AND scr.status = 'passes'
                    AND scr.promoted_at IS NULL
                       """, (comp4300['semester_id'], session['user_id']))
        count = cursor.rowcount
        db.commit()
        cursor.close()
        db.close()

        return jsonify({'message': f'{count} student(s) promoted to COMP4300 successfully.'}), 200
    
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500
    


#get the students on COMP4300 to archive their projects
@promote_bp.route('/api/students/comp4300', methods=['GET'])
@login_required(role="head_of_department")
def api_get_comp4300_students():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT DISTINCT u.user_id, u.full_name, u.university_id, 
                         u.email, u.avatar_initials
            FROM users u
            JOIN students st ON st.user_id = u.user_id
            JOIN project_members pm ON pm.student_id = st.student_id
            JOIN projects p ON p.project_id = pm.project_id
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE u.role = 'student'
                AND u.is_active = TRUE
                AND  sem.course_code = 'COMP4300'
                AND p.status != 'archived'
            ORDER BY u.full_name 
            """)
        
        students = cursor.fetchall()
        cursor.close()
        db.close()

        return jsonify({'students': students}), 200
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500
    
#archiving the projects
@promote_bp.route('/api/students/archive-all', methods=['POST'])
@login_required(role="head_of_department")
def api_archive_all():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
        UPDATE projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        SET p.status = 'archived'
        WHERE sem.course_code = 'COMP4300'
                AND p.status != 'archived'               
        """)

        count = cursor.rowcount
        db.commit()
        cursor.close()
        db.close()

        return jsonify({'message': f'{count} project(s) archived successfully.'}), 200
    
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500