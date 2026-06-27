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
from semester_lifecycle import auto_rollover_semesters

head_supervisors_bp = Blueprint('head_supervisors', __name__)


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    row = cursor.fetchone() or {}
    return int(row.get("cnt") or 0) > 0


def _current_supervisor_semesters(cursor):
    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
          AND start_date IS NOT NULL
          AND end_date IS NOT NULL
          AND CURDATE() BETWEEN start_date AND end_date
        ORDER BY start_date DESC, semester_id DESC
    """)
    semesters = cursor.fetchall()
    if semesters:
        return _project_year_semesters(cursor, semesters)

    cursor.execute("""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
    """)
    semesters = cursor.fetchall()
    return _project_year_semesters(cursor, semesters) if semesters else []


def _project_year_semesters(cursor, anchor_semesters):
    academic_years = sorted({
        row["academic_year"]
        for row in anchor_semesters
        if row.get("academic_year")
    })
    if not academic_years:
        return anchor_semesters

    placeholders = ",".join(["%s"] * len(academic_years))
    cursor.execute(f"""
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE academic_year IN ({placeholders})
          AND course_code IN ('COMP4200', 'COMP4300')
        ORDER BY academic_year DESC, semester_number DESC, semester_id DESC
    """, tuple(academic_years))
    scoped = cursor.fetchall()
    if not scoped:
        return anchor_semesters

    anchor_ids = {row["semester_id"] for row in anchor_semesters if row.get("semester_id")}
    scoped.sort(
        key=lambda row: (
            0 if row.get("semester_id") in anchor_ids else 1,
            -int(row.get("semester_id") or 0),
        )
    )
    return scoped


def _supervisor_semester_ids(semesters):
    return [row["semester_id"] for row in semesters if row.get("semester_id")]


def _supervisor_project_filters(cursor, alias="gp"):
    promotion_filter = ""
    if _table_exists(cursor, "project_course_promotions"):
        promotion_filter = f"""
               AND NOT EXISTS (
                    SELECT 1
                    FROM project_course_promotions pcp
                    WHERE pcp.source_project_id = {alias}.project_id
               )
        """

    return f"""
               AND LOWER(COALESCE({alias}.status, '')) NOT IN (
                    'archived', 'archive', 'draft', 'cancelled', 'rejected',
                    'promoted', 'search', 'search_only', 'imported_archive',
                    'solo_pending'
               )
               AND COALESCE({alias}.title, '') NOT LIKE 'Committee Demo%%'
               AND COALESCE({alias}.title, '') NOT LIKE 'COMP4300 Graduation Project%%'
               {promotion_filter}
    """


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

        auto_rollover_semesters(cursor)
        db.commit()

        semesters = _current_supervisor_semesters(cursor)
        semester_ids = _supervisor_semester_ids(semesters)
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
                'semesters': [],
            }), 200

        semester_placeholders = ",".join(["%s"] * len(semester_ids))
        project_filters = _supervisor_project_filters(cursor, "gp")
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
               {project_filters}
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
            'semester': semesters[0],
            'semesters': semesters,
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
