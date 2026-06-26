from flask import Blueprint, request, jsonify, render_template
from db import get_db
import bcrypt, re


activate_bp = Blueprint('activate', __name__)


@activate_bp.route('/activate')
def activate_page():
    return render_template('activate_student.html')


# ─────────────────────────────────────────────────────────────
#  STUDENT  –  Step 1: Verify
# ─────────────────────────────────────────────────────────────
@activate_bp.route('/api/activate/verify', methods=['POST'])
def api_verify_student():
    data = request.get_json(silent=True) or {}

    university_id = (data.get('university_id') or '').strip()

    if not university_id:
        return jsonify({'error': 'Please enter your university ID.'}), 400

    if not re.match(r'^\d{7}$', university_id):
        return jsonify({'error': 'The university ID number must be 7 digits.'}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id, full_name, is_active
            FROM   users
            WHERE  university_id = %s
              AND  role = 'student'
        """, (university_id,))
        student = cursor.fetchone()
        cursor.close()
        db.close()

        if not student:
            return jsonify({'error': 'The information is incorrect or the account is not registered. Please contact the department head.'}), 404

        if student['is_active']:
            return jsonify({'error': 'The account is already activated. You can log in directly.'}), 409

        return jsonify({
            'message': 'Your information has been verified. Please create a password.',
            'user_id': student['user_id'],
            'full_name': student['full_name'],
        }), 200

    except Exception as e:
        return jsonify({'error': f'An error occurred: {e}'}), 500


# ─────────────────────────────────────────────────────────────
#  STUDENT  –  Step 2: Set Password
# ─────────────────────────────────────────────────────────────
@activate_bp.route('/api/activate/set-password', methods=['POST'])
def api_set_password():
    data = request.get_json(silent=True) or {}

    user_id  = data.get('user_id')
    password = data.get('password', '')
    confirm  = data.get('confirm_password', '')

    if not user_id or not password:
        return jsonify({'error': 'Incomplete data.'}), 400

    if password != confirm:
        return jsonify({'error': 'The two passwords do not match.'}), 400

    if len(password) < 8:
        return jsonify({'error': 'The password must be at least 8 characters long.'}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id FROM users
            WHERE  user_id   = %s
              AND  is_active = FALSE
              AND  role      = 'student'
        """, (user_id,))
        if not cursor.fetchone():
            cursor.close(); db.close()
            return jsonify({'error': 'The request is invalid or the account is already activated.'}), 400

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        cursor.execute("""
            UPDATE users
            SET    password_hash = %s,
                   is_active     = TRUE
            WHERE  user_id = %s
        """, (hashed, user_id))

        db.commit()
        cursor.close()
        db.close()

        return jsonify({'message': 'Your account has been activated successfully.'}), 200

    except Exception as e:
        return jsonify({'error': f'An error occurred: {e}'}), 500


# ─────────────────────────────────────────────────────────────
#  SUPERVISOR  –  Step 1: Verify
#  university_id = 4 digits  (supervisors use 4-digit IDs)
# ─────────────────────────────────────────────────────────────
@activate_bp.route('/api/activate/supervisor/verify', methods=['POST'])
def api_verify_supervisor():
    data = request.get_json(silent=True) or {}

    university_id = (data.get('university_id') or '').strip()

    if not university_id:
        return jsonify({'error': 'Please enter your university ID.'}), 400

    # ── 4-digit ID for supervisors ──
    if not re.match(r'^\d{4}$', university_id):
        return jsonify({'error': 'Supervisor university ID must be 4 digits.'}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT u.user_id, u.full_name, u.is_active
            FROM   users u
            WHERE  u.university_id = %s
              AND  u.role          = 'supervisor'
        """, (university_id,))
        sup = cursor.fetchone()
        cursor.close()
        db.close()

        if not sup:
            return jsonify({
                'error': 'No supervisor account found with that ID. '
                         'Please contact the head of department.'
            }), 404

        if sup['is_active']:
            return jsonify({
                'error': 'This supervisor account is already active. You can log in directly.'
            }), 409

        return jsonify({
            'message':   f'Welcome, {sup["full_name"]}. Please set your hours and password.',
            'user_id':   sup['user_id'],
            'full_name': sup['full_name'],
        }), 200

    except Exception as e:
        return jsonify({'error': f'An error occurred: {e}'}), 500


# ─────────────────────────────────────────────────────────────
#  SUPERVISOR  –  Step 2: Set Hours + Password  →  Activate
# ─────────────────────────────────────────────────────────────
@activate_bp.route('/api/activate/supervisor/set-password', methods=['POST'])
def api_supervisor_set_password():
    data = request.get_json(silent=True) or {}

    user_id  = data.get('user_id')
    hours    = data.get('graduation_project_hours')
    password = (data.get('password')         or '').strip()
    confirm  = (data.get('confirm_password') or '').strip()

    if not user_id or not password or hours is None:
        return jsonify({'error': 'Please fill in all fields.'}), 400

    if password != confirm:
        return jsonify({'error': 'The two passwords do not match.'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters long.'}), 400

    try:
        hours_val = float(hours)
        if hours_val < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid hours value.'}), 400

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        # Make sure account is still inactive
        cursor.execute("""
            SELECT u.user_id, f.faculty_id
            FROM   users   u
            JOIN   faculty f ON f.user_id = u.user_id
            WHERE  u.user_id   = %s
              AND  u.role      = 'supervisor'
              AND  u.is_active = FALSE
        """, (user_id,))
        row = cursor.fetchone()

        if not row:
            cursor.close(); db.close()
            return jsonify({'error': 'Supervisor not found or already active.'}), 404

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Activate the user
        cursor.execute("""
            UPDATE users
            SET    password_hash = %s,
                   is_active     = TRUE
            WHERE  user_id = %s
        """, (hashed, user_id))

       

        # Store in faculty_load_settings for the active semester
        cursor.execute("""
            SELECT semester_id FROM semesters
            WHERE  is_active = TRUE
            ORDER  BY semester_id DESC
            LIMIT  1
        """)
        sem = cursor.fetchone()
        if sem:
            cursor.execute("""
                INSERT INTO faculty_load_settings
                    (faculty_id, semester_id, graduation_project_hours)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    graduation_project_hours = VALUES(graduation_project_hours)
            """, (row['faculty_id'], sem['semester_id'], hours_val))

        db.commit()
        cursor.close()
        db.close()

        return jsonify({
            'message': 'Your supervisor account has been activated successfully. You may now log in.'
        }), 200

    except Exception as e:
        return jsonify({'error': f'An error occurred: {e}'}), 500
