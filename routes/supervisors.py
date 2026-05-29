from flask import Blueprint, request, jsonify, render_template
from db import get_db
import bcrypt

supervisor_bp = Blueprint('supervisor', __name__)


# ─────────────────────────────────────────────
#  PAGE
# ─────────────────────────────────────────────

@supervisor_bp.route('/supervisors')
def supervisors_page():
    return render_template('supervisors.html')


# ─────────────────────────────────────────────
#  API: List of active supervisors with stats
# ─────────────────────────────────────────────

@supervisor_bp.route('/supervisors/api/list', methods=['GET'])
def api_get_supervisors():
    """
    Returns all active supervisors with per-semester project count,
    average final score, and total project count.
    """
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.avatar_initials,
                u.email,
                u.university_id,
                f.faculty_id,
                f.specialization,
                f.years_experience,
                f.title,

                /* projects in the most-recent active semester */
                COALESCE(sem_stats.this_semester, 0)  AS this_semester,
                /* average final score across all graded projects */
                COALESCE(all_stats.avg_score, 0)      AS average_score,
                /* total supervised projects */
                COALESCE(all_stats.total, 0)           AS total_projects

            FROM users u
            JOIN faculty f ON f.user_id = u.user_id
            LEFT JOIN (
                /* per-active-semester count */
                SELECT
                    p.supervisor_id,
                    COUNT(p.project_id) AS this_semester
                FROM projects p
                JOIN semesters s ON s.semester_id = p.semester_id
                WHERE s.is_active = TRUE
                GROUP BY p.supervisor_id
            ) sem_stats ON sem_stats.supervisor_id = f.faculty_id
            LEFT JOIN (
                SELECT
                    p.supervisor_id,
                    COUNT(p.project_id)             AS total,
                    ROUND(AVG(p.final_score), 1)    AS avg_score
                FROM projects p
                GROUP BY p.supervisor_id
            ) all_stats ON all_stats.supervisor_id = f.faculty_id

            WHERE u.role = 'supervisor'
              AND u.is_active = TRUE
            ORDER BY u.full_name
        """)
        supervisors = cursor.fetchall()
        cursor.close()
        db.close()

        return jsonify({'supervisors': supervisors}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  API: Supervisor Statistics Summary (right panel)
# ─────────────────────────────────────────────

@supervisor_bp.route('/api/supervisors/stats', methods=['GET'])
def api_supervisor_stats():
    """
    Aggregated stats shown in the right-side summary card.
    """
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                COUNT(DISTINCT u.user_id)                          AS active_supervisors,
                ROUND(
                    (SELECT COUNT(*) FROM projects p
                     JOIN semesters s ON s.semester_id = p.semester_id
                     WHERE s.is_active = TRUE AND p.supervisor_id IS NOT NULL)
                    / NULLIF(COUNT(DISTINCT u.user_id), 0)
                , 1)                                               AS avg_projects_per_supervisor,
                (SELECT ROUND(MAX(sub.avg_s), 1)
                 FROM (
                     SELECT AVG(p.final_score) AS avg_s
                     FROM projects p
                     WHERE p.supervisor_id IS NOT NULL AND p.final_score IS NOT NULL
                     GROUP BY p.supervisor_id
                 ) sub)                                            AS highest_average,
                (SELECT ROUND(MIN(sub.avg_s), 1)
                 FROM (
                     SELECT AVG(p.final_score) AS avg_s
                     FROM projects p
                     WHERE p.supervisor_id IS NOT NULL AND p.final_score IS NOT NULL
                     GROUP BY p.supervisor_id
                 ) sub)                                            AS lowest_average,
                (SELECT MAX(sem_load.cnt)
                 FROM (
                     SELECT COUNT(*) AS cnt
                     FROM projects p
                     JOIN semesters s ON s.semester_id = p.semester_id
                     WHERE s.is_active = TRUE
                     GROUP BY p.supervisor_id
                 ) sem_load)                                       AS max_load

            FROM users u
            JOIN faculty f ON f.user_id = u.user_id
            WHERE u.role = 'supervisor'
              AND u.is_active = TRUE
        """)
        stats = cursor.fetchone()
        cursor.close()
        db.close()

        return jsonify({'stats': stats}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  API: Inactive supervisors (for the Add panel)
# ─────────────────────────────────────────────

@supervisor_bp.route('/api/supervisors/inactive', methods=['GET'])
def api_inactive_supervisors():
    """
    Returns supervisors that exist in the users table but are NOT yet active.
    Used to populate the "Add New Supervisor" table in the UI.
    """
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.university_id,
                u.email,
                u.avatar_initials,
                f.specialization,
                f.years_experience,
                f.title,
                f.faculty_id
            FROM users u
            LEFT JOIN faculty f ON f.user_id = u.user_id
            WHERE u.role = 'supervisor'
              AND u.is_active = FALSE
            ORDER BY u.full_name
        """)
        inactive = cursor.fetchall()
        cursor.close()
        db.close()

        return jsonify({'supervisors': inactive}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  API: Activate a supervisor (set hours + password)
# ─────────────────────────────────────────────

@supervisor_bp.route('/api/supervisors/activate', methods=['POST'])
def api_activate_supervisor():
    """
    Activates an inactive supervisor account.
    Expects: user_id, graduation_project_hours, password, confirm_password
    """
    data = request.get_json(silent=True) or {}

    user_id   = data.get('user_id')
    hours     = data.get('graduation_project_hours')
    password  = (data.get('password') or '').strip()
    confirm   = (data.get('confirm_password') or '').strip()

    if not user_id or hours is None or not password:
        return jsonify({'error': 'Missing required fields.'}), 400

    if password != confirm:
        return jsonify({'error': 'Passwords do not match.'}), 400

    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters.'}), 400

    try:
        hours = float(hours)
        if hours < 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid hours value.'}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Verify the account exists and is still inactive
        cursor.execute("""
            SELECT u.user_id, f.faculty_id
            FROM users u
            JOIN faculty f ON f.user_id = u.user_id
            WHERE u.user_id = %s
              AND u.role = 'supervisor'
              AND u.is_active = FALSE
        """, (user_id,))
        row = cursor.fetchone()

        if not row:
            cursor.close()
            db.close()
            return jsonify({'error': 'Supervisor not found or already active.'}), 404

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Activate user
        cursor.execute("""
            UPDATE users
            SET password_hash = %s,
                is_active     = TRUE
            WHERE user_id = %s
        """, (hashed, user_id))

        # Save hours in faculty_load_settings
        active_semester_id = _get_active_semester_id(cursor)
        if active_semester_id:
            cursor.execute("""
                INSERT INTO faculty_load_settings
                    (faculty_id, semester_id, graduation_project_hours)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    graduation_project_hours = VALUES(graduation_project_hours)
            """, (row['faculty_id'], active_semester_id, hours))

        db.commit()
        cursor.close()
        db.close()

        return jsonify({'message': 'Supervisor activated successfully.'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  API: Hours summary (sidebar Hours tab)
# ─────────────────────────────────────────────

@supervisor_bp.route('/api/supervisors/hours', methods=['GET'])
def api_supervisor_hours():
    """
    Returns each active supervisor with their graduation project hours.
    Used in the Hours sidebar panel.
    """
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        active_semester_id = _get_active_semester_id(cursor)

        cursor.execute("""
            SELECT
                u.full_name,
                u.avatar_initials,
                f.faculty_id,
                f.specialization,
                COALESCE(fls.graduation_project_hours, 0) AS hours
            FROM users u
            JOIN faculty f ON f.user_id = u.user_id
            LEFT JOIN faculty_load_settings fls
                   ON fls.faculty_id = f.faculty_id
                  AND fls.semester_id = %s
            WHERE u.role = 'supervisor'
              AND u.is_active = TRUE
            ORDER BY u.full_name
        """, (active_semester_id,))
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        total_hours = sum(float(r['hours'] or 0) for r in rows)
        return jsonify({'supervisors': rows, 'total_hours': total_hours}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  API: Send hours to coordinator
# ─────────────────────────────────────────────

@supervisor_bp.route('/api/supervisors/hours/send', methods=['POST'])
def api_send_hours_to_coordinator():
    """
    Sends a notification to the coordinator with the hours summary.
    Expects: sender_user_id (head of department user_id)
    """
    data = request.get_json(silent=True) or {}
    sender_id = data.get('sender_user_id')

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # Get coordinator user_id
        cursor.execute("""
            SELECT user_id FROM users
            WHERE role = 'coordinator' AND is_active = TRUE
            LIMIT 1
        """)
        coord = cursor.fetchone()
        if not coord:
            cursor.close()
            db.close()
            return jsonify({'error': 'No active coordinator found.'}), 404

        active_semester_id = _get_active_semester_id(cursor)

        # Build hours summary message
        cursor.execute("""
            SELECT
                u.full_name,
                COALESCE(fls.graduation_project_hours, 0) AS hours
            FROM users u
            JOIN faculty f ON f.user_id = u.user_id
            LEFT JOIN faculty_load_settings fls
                   ON fls.faculty_id = f.faculty_id
                  AND fls.semester_id = %s
            WHERE u.role = 'supervisor'
              AND u.is_active = TRUE
            ORDER BY u.full_name
        """, (active_semester_id,))
        rows = cursor.fetchall()

        lines = [f"• {r['full_name']}: {r['hours']} hrs" for r in rows]
        body  = "Supervisor hours summary for the current semester:\n\n" + "\n".join(lines)

        cursor.execute("""
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type, title, message, course_scope)
            VALUES (%s, %s, 'system', %s, %s, 'both')
        """, (
            coord['user_id'],
            sender_id,
            'Supervisor Hours Summary',
            body
        ))

        db.commit()
        cursor.close()
        db.close()

        return jsonify({'message': 'Hours summary sent to coordinator.'}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────
#  Helper
# ─────────────────────────────────────────────

def _get_active_semester_id(cursor):
    cursor.execute("""
        SELECT semester_id FROM semesters
        WHERE is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()
    return row['semester_id'] if row else None
