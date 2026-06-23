from flask import Blueprint, request, jsonify, current_app
from db import get_db
from datetime import datetime, timedelta
from auth import login_required
announcements_bp = Blueprint('announcements', __name__)

#create announcements
@announcements_bp.route('/api/announcements/create', methods=['POST'])
@login_required(role="head_of_department")
def api_create_announcement():
    from flask import session
    data = request.get_json(silent=True) or {}

    message = (data.get('message') or '').strip()
    days = int(data.get('days') or 20)

    if not message:
        return jsonify({'error': 'Message is required.'}), 400
    
    if days < 1 or days > 90:
        return jsonify({'error': 'Duration must be between 1 and 90 days.'}), 400
    
    expires_at = (datetime.today() + timedelta(days=days)).strftime('%Y-%m-%d')

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        #decative any previous active announcements
        cursor.execute("""
                UPDATE announcements SET is_active = FALSE
                WHERE is_active = TRUE
                       """)
        
        cursor.execute("""
                INSERT INTO announcements (message, activation_url, created_by, expires_at, is_active)
                VALUES (%s, '/activate', %s, %s, TRUE)   
                       """,(message, session['user_id'], expires_at))
        
        db.commit()
        cursor.close()
        db.close()

        return jsonify({
            'message': 'Announcement created successfully.',
            'expires_at': expires_at,
            'days': days
        }), 200
    
    except Exception as e:
        current_app.logger.error('Error in api_create_announcement: %s', e)
        return jsonify({'error': f'Database error: {e}'}), 500
    



#login page fetch this:
@announcements_bp.route('/api/announcements/active', methods=['GET'])
def api_get_active_announcement():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute("""
                SELECT announcement_id, message, activation_url, expires_at
                FROM announcements
                WHERE is_Active = TRUE
                       AND expires_at >= CURDATE()
                ORDER BY created_at DESC
                LIMIT 1
             """)
        ann = cursor.fetchone()
        cursor.close()
        db.close()

        if not ann:
            return jsonify({'announcement': None}), 200
        
        #calculate days left 
        today = datetime.today().date()
        expires = ann['expires_at']
        days_left = (expires - today).days

        return jsonify({
            'announcement': {
                'message': ann['message'],
                'activation_url': ann['activation_url'],
                'expires_at': str(expires),
                'days_left': days_left
            }
        }), 200
    except Exception as e:
        return jsonify({'error': f'Database error: {e}'}), 500
