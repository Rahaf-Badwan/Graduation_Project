# routes add_student.py 



from flask import Blueprint, request, jsonify, current_app
from db import get_db
from auth import login_required
import bcrypt, re


add_student_bp = Blueprint('add_student', __name__)


#head of depatment add student with active = 'pending' (is_active = 0) 
@add_student_bp.route('/api/students/add', methods=['POST'])
@login_required(role="head_of_department")
def api_add_student():
    data = request.get_json(silent=True) or {}

    full_name = (data.get('full_name') or '').strip()
    university_id = (data.get('university_id') or '').strip()
    email = (data.get('email') or '').strip()

    #check validation
    if not full_name or not university_id or not email:
        return jsonify({'error': 'All fields are requires.'}), 400
    
    if not re.match(r'^\d{7}$', university_id):
        return jsonify({'error': 'University ID must be exactly 7 digits.'}), 400
    
    #Avater initials
    parts = full_name.split()
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else '')).upper()

    #temporary password, the student cannot log in until activate
    temp_hash = bcrypt.hashpw(b'__pending__', bcrypt.gensalt()).decode()

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        #check for duplicate
        cursor.execute('SELECT user_id FROM users WHERE university_id = %s OR email = %s',
                       (university_id, email)
                       )
        if cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({'error': 'University ID or email already exists.'}), 400
        #add student is_active = 0 that mean account status = pending
        cursor.execute("""
                INSERT INTO users
                       (university_id, full_name, email, password_hash, role, avatar_initials, is_active)
                       VALUES (%s, %s, %s, %s, 'student', %s, FALSE)
                       """, (university_id, full_name, email, temp_hash, initials)
                       )
        
        user_id = cursor.lastrowid

        # add field in student table
        cursor.execute('INSERT INTO students (user_id, enrollment_year) VALUES (%s, YEAR(CURDATE()))',
                       (user_id,)
        )

        db.commit()
        cursor.close()
        db.close()

        return jsonify({
            'message': 'Student added successfully.',
            'user_id': user_id,
            'statues': 'pending'
        }), 201
    
    except Exception as e:
        current_app.logger.error('Error in api_add_student: %s', e)
        return jsonify({'error': f'Database error: {e}'}), 500
    
# return the students that is_active = TRUE based ON course
@add_student_bp.route('/api/students/active', methods=['GET'])
@login_required(role="head_of_department")
def api_active_students():
        course = request.args.get('course', 'COMP4200').upper()

        if course not in ('COMP4200', 'COMP4300'):
            return jsonify({'error': 'Unkown course code.'}), 400
        
        try:
            db = get_db()
            cursor = db.cursor(dictionary=True)

            #filter the course base on semesters
            cursor.execute("""
                    SELECT DISTINCT
                           u.user_id,
                           u.university_id,
                           u.full_name,
                           u.email,
                           u.avatar_initials
                    FROM users u
                    JOIN students st ON st.user_id = u.user_id
                    JOIN project_members pm ON pm.student_id = st.student_id
                    JOIN projects p ON p.project_id = pm.project_id
                    JOIN semesters s ON s.semester_id = p.semester_id
                    WHERE u.role = 'student'
                        AND u.is_active = TRUE
                        AND s.course_code = %s
                    ORDER BY u.full_name""",
                    (course,)
            )
            students = cursor.fetchall()

            # if the student is activate but not have projects
            if not students:
                cursor.execute(
                    """SELECT u.user_id, u.university_id, u.full_name,
                              u.email, u.avatar_initials
                        FROM users u
                        JOIN students s ON s.user_id = u.user_id
                        WHERE u.role = 'student'
                            AND is_active = TRUE
                        ORDER BY u.full_name"""
                )
                students = cursor.fetchall()

                cursor.close()
                db.close()

            return jsonify({'students': students, 'course': course}), 200

        except Exception as e:
            current_app.logger.error('Error in api_active_students: %s', e)
            return jsonify({'error': f'Database error: {e}'}), 500