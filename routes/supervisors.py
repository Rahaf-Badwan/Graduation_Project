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


# ─────────────────────────────────────────────────────────────
#  GET /api/head/supervisors
# ─────────────────────────────────────────────────────────────
@head_supervisors_bp.route('/supervisors-api', methods=['GET'])
@login_required(role='head_of_department')
def api_list_supervisors():
    try:
        db     = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
           SELECT
                u.user_id,
                u.full_name,
                u.university_id,
                u.email,
                u.is_active,
                f.specialization,
                COUNT(gp.project_id) AS project_count
            FROM  users u
            JOIN  faculty f ON f.user_id = u.user_id
            LEFT  JOIN projects gp
                ON gp.supervisor_id = f.faculty_id
                     AND gp.status  IN ('cancelled', 'rejected', 'archived', 'draft', 'accepted')
            
            GROUP BY 
                u.user_id, u.full_name, u.university_id,
                u.email,   u.is_active,
                f.specialization
			HAVING COUNT(gp.project_id) > 0
            ORDER BY u.full_name
        """)
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

        total    = len(supervisors)
        active   = sum(1 for s in supervisors if s['is_active'])
        pending  = total - active
        projects = sum(s['project_count'] for s in supervisors)

        return jsonify({
            'supervisors': supervisors,
            'stats': {
                'total':    total,
                'active':   active,
                'pending':  pending,
                'projects': projects,
            }
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

    full_name      = (data.get('full_name')      or '').strip()
    university_id  = (data.get('university_id')  or '').strip()
    email          = (data.get('email')          or '').strip()
    specialization = (data.get('specialization') or '').strip()

    if not full_name or not university_id or not email:
        return jsonify({'error': 'Full name, university ID, and email are required.'}), 400

    if not re.match(r'^\d{4}$', university_id):
        return jsonify({'error': 'University ID must be exactly 4 digits.'}), 400

    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        return jsonify({'error': 'Invalid email address.'}), 400

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
            'activation_url': '/activate'
        }), 201

    except Exception as e:
        current_app.logger.error('api_add_supervisor: %s', e)
        return jsonify({'error': f'Database error: {e}'}), 500