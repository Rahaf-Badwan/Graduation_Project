from flask import Blueprint, request, jsonify, render_template
from db import get_db
import bcrypt, re



activate_bp = Blueprint('activate', __name__)


@activate_bp.route('/activate')
def activate_page():
    return render_template('activate_student.html')

#check if the student in the database or not
@activate_bp.route('/api/activate/verify', methods=['POST'])
def api_verify_student():
    data = request.get_json(silent=True) or {}


    full_name = (data.get('full_name') or '').strip()
    university_id = (data.get('university_id') or '').strip()
    email = (data.get('email') or '').strip()

    if not full_name or not university_id or not email:
        return jsonify({'error': 'Please fill in all fields.'}), 400
    if not re.match(r'^\d{7}$', university_id):
        return jsonify({'error': 'The university ID number must be 7 digits.'}), 400
    
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
                     SELECT user_id, full_name, is_active
                       FROM users 
                       WHERE university_id = %s
                            AND role = 'student'
                       """, (university_id))
        student = cursor.fetchone()
        cursor.close()
        db.close()

        if not student:
            return jsonify({'error': 'The information is inccorect or the accfount is not registered. Please contacat the department head.'}), 404
        
        if student['is_active']:
            return jsonify({'error': 'The account is already activated. You can log in directly.'}), 409
        
        #the information is coorect and account is pending , can set password
        return jsonify({
            'message': 'Your information has been verifies. Please create a password.',
            'user_id': student['user_id']
        }), 200
    except Exception as e:
        return jsonify({'error': f'An error occurred: {e}'}), 500

#the student set the password and activate account
@activate_bp.route('/api/activate/set-password', methods=['POST'])
def api_set_password():
    data = request.get_json(silent=True) or {}

    user_id = data.get('user_id')
    password = data.get('password', '')
    confirm = data.get('confirm_password', '')

    if not user_id or not password:
        return jsonify({'error': 'Incomplete data.'}), 400
    
    if password != confirm:
        return jsonify({'error': 'The two passwords do not match.'}), 400
    
    if len(password) < 8:
        return jsonify({'error': 'The password must be at least 8 characters long.'}), 400
    
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        #check if the account is not activate 
        cursor.execute("""
               SELECT user_id FROM users
                WHERE user_id = %s AND is_active = FALSE AND role ='student'
                       """,(user_id,))
        if not cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({'error': 'The request is invalid or the account is already activated.'}), 400
       
       
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


        cursor.execute("""
               UPDATE users
               SET password_hash = %s,
                       is_active = TRUE
                WHERE user_id = %s
                       """, (hashed, user_id))
        
        db.commit()
        cursor.close()
        db.close()

        return jsonify({'message': 'Your account has been activated successfully.'}), 200
    except Exception as e:
        return jsonify({'error': f'An error occurred: {e}'}), 500
        


 