"""
head_supervisors.py
Blueprint for Head-of-Department → Supervisors management.

Endpoints
─────────
GET  /api/head/supervisors          – list all supervisors + stats
POST /api/head/supervisors/add      – add a new (inactive) supervisor

Activation is handled by the EXISTING endpoint in activate.py:
  POST /api/activate/supervisor/set-password
"""

import re
from flask import Blueprint, request, jsonify, current_app
from db import get_db
from auth import login_required

head_supervisors_bp = Blueprint('head_supervisors', __name__)


def _current_supervisor_semester(cursor):
    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
          AND start_date IS NOT NULL
          AND end_date IS NOT NULL
          AND CURDATE() BETWEEN start_date AND end_date
        ORDER BY start_date DESC, semester_id DESC
        LIMIT 1
    """)
    semester = cursor.fetchone()
    if semester:
        return semester

    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
    """)
    return cursor.fetchone()


def _supervisor_semester_ids(cursor, semester):
    if not semester:
        return []

    cursor.execute("""
        SELECT semester_id
        FROM semesters
        WHERE academic_year = %s
          AND course_code IN ('COMP4200', 'COMP4300')
        ORDER BY semester_id
    """, (semester["academic_year"],))
    rows = cursor.fetchall()
    semester_ids = [row["semester_id"] for row in rows]
    return semester_ids or [semester["semester_id"]]


def _supervisor_account_stats(cursor):
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN u.is_active = FALSE THEN 1 ELSE 0 END) AS pending
        FROM users u
        JOIN faculty f ON f.user_id = u.user_id
        WHERE u.role = 'supervisor'
    """)
    row = cursor.fetchone() or {}
    return {
        "total": int(row.get("total") or 0),
        "pending": int(row.get("pending") or 0),
    }


# ─────────────────────────────────────────────────────────────
#  GET /api/head/supervisors
# ─────────────────────────────────────────────────────────────
@head_supervisors_bp.route('/supervisors-api', methods=['GET'])
@login_required(role='head_of_department')
def api_list_supervisors():
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _current_supervisor_semester(cursor)
        semester_ids = _supervisor_semester_ids(cursor, semester)
        account_stats = _supervisor_account_stats(cursor)

        if not semester_ids:
            cursor.close()
            db.close()
            return jsonify({
                'supervisors': [],
                'stats': {
                    'total': account_stats['total'],
                    'active': 0,
                    'pending': account_stats['pending'],
                    'projects': 0,
                },
                'semester': None,
            }), 200

        semester_placeholders = ",".join(["%s"] * len(semester_ids))
        cursor.execute(f"""
           SELECT
                u.user_id,
                u.full_name,
                u.university_id,
                u.email,
                u.is_active,
                f.specialization,
                COUNT(DISTINCT gp.project_id) AS project_count
            FROM  users u
            JOIN  faculty f ON f.user_id = u.user_id
            LEFT  JOIN projects gp
                ON gp.supervisor_id = f.faculty_id
               AND gp.semester_id IN ({semester_placeholders})
               AND gp.status <> 'archived'
               AND EXISTS (
                    SELECT 1
                    FROM project_members pm
                    JOIN students st ON st.student_id = pm.student_id
                    JOIN users us ON us.user_id = st.user_id
                    WHERE pm.project_id = gp.project_id
                      AND us.is_active = TRUE
               )
            WHERE u.role = 'supervisor'
              AND u.is_active = TRUE
            
            GROUP BY 
                u.user_id, u.full_name, u.university_id,
                u.email,   u.is_active,
                f.specialization
            HAVING COUNT(DISTINCT gp.project_id) > 0
            ORDER BY u.full_name
        """, tuple(semester_ids))
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        supervisors = [{
            'user_id':                  r['user_id'],
            'full_name':                r['full_name'],
            'university_id':            r['university_id'],
            'email':                    r['email'],
            'is_active':                bool(r['is_active']),
            'specialization':           r['specialization'],
            'project_count':            int(r['project_count']),
        } for r in rows]

        total    = account_stats['total']
        active   = len(supervisors)
        pending  = account_stats['pending']
        projects = sum(s['project_count'] for s in supervisors)

        return jsonify({
            'supervisors': supervisors,
            'stats': {
                'total':    total,
                'active':   active,
                'pending':  pending,
                'projects': projects,
            },
            'semester': semester,
        }), 200

    except Exception as e:
        current_app.logger.error('api_list_supervisors: %s', e)
        return jsonify({'error': f'Database error: {e}'}), 500


# ─────────────────────────────────────────────────────────────
#  POST /api/head/supervisors/add
#  university_id = 4 digits  (supervisors)
# ─────────────────────────────────────────────────────────────
@head_supervisors_bp.route('/supervisors-api/add', methods=['POST'])
@login_required(role='head_of_department')
def api_add_supervisor():
    data = request.get_json(silent=True) or {}

    full_name_raw  = (data.get('full_name')      or '').strip()
    # Prepend "Dr." prefix if not already present
    if full_name_raw and not full_name_raw.lower().startswith('dr'):
        full_name = 'Dr. ' + full_name_raw
    else:
        full_name = full_name_raw
    university_id  = (data.get('university_id')  or '').strip()
    specialization = (data.get('specialization') or '').strip()
    spec_custom    = (data.get('spec_custom')    or '').strip()   # free-text when "other" selected

    if not full_name or not university_id:
        return jsonify({'error': 'Full name and university ID are required.'}), 400

    if not re.match(r'^\d{4}$', university_id):
        return jsonify({'error': 'University ID must be exactly 4 digits.'}), 400

    # All ENUM values accepted by the DB
    DB_ENUM_SPECS = {
        'software_engineering', 'artificial_intelligence', 'web_development',
        'mobile', 'security_networks', 'databases', 'other'
    }
    # Extended dropdown values that map to 'other' in the DB
    MAP_TO_OTHER = {
        'data_science', 'computer_vision', 'cloud_computing',
        'human_computer_interaction', 'embedded_systems'
    }

    if specialization in MAP_TO_OTHER:
        if not spec_custom:
            spec_custom = specialization.replace('_', ' ').title()
        specialization = 'other'

    if specialization and specialization not in DB_ENUM_SPECS:
        return jsonify({'error': 'Invalid specialization value.'}), 400

    if specialization == 'other' and spec_custom and len(spec_custom) > 120:
        return jsonify({'error': 'Custom specialization must be under 120 characters.'}), 400

    email = f'{university_id}@birzeit.edu'

    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT user_id FROM users
            WHERE  university_id = %s OR email = %s
        """, (university_id, email))
        if cursor.fetchone():
            cursor.close(); db.close()
            return jsonify({'error': 'A user with this ID or email already exists.'}), 409

        cursor.execute("""
            INSERT INTO users
                (full_name, university_id, email, role, is_active, password_hash)
            VALUES (%s, %s, %s, 'supervisor', FALSE, '')
        """, (full_name, university_id, email))
        new_user_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO faculty (user_id, specialization)
            VALUES (%s, %s)
        """, (new_user_id, specialization or None))

        db.commit()
        cursor.close()
        db.close()

        return jsonify({
            'message':        f'Supervisor "{full_name}" added successfully.',
            'user_id':        new_user_id,
            'email':          email,
            'activation_url': '/activate',
            'spec_custom':    spec_custom or None,
        }), 201

    except Exception as e:
        current_app.logger.error('api_add_supervisor: %s', e)
        return jsonify({'error': f'Database error: {e}'}), 500
