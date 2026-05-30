from flask import (
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
import bcrypt
from werkzeug.utils import secure_filename

from auth import login_required
from db import get_db
from .blueprint import student_bp
from .common import *

@student_bp.route("/notifs")
@login_required(role="student")
def notifs():
    return render_template("student/notifs.html")


def _ensure_notif_attachment_columns(cursor):
    """Add notification attachment/reply-control columns if they don't exist yet."""
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'notifications'
          AND COLUMN_NAME  = 'attachment_name'
        """)
    if not (cursor.fetchone() or {}).get("cnt"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255)  DEFAULT NULL"
        )
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120)  DEFAULT NULL"
        )
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN attachment_data MEDIUMBLOB    DEFAULT NULL"
        )

    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME   = 'notifications'
          AND COLUMN_NAME  = 'can_reply'
        """)
    if not (cursor.fetchone() or {}).get("cnt"):
        cursor.execute(
            "ALTER TABLE notifications ADD COLUMN can_reply TINYINT(1) NOT NULL DEFAULT 1 AFTER is_read"
        )


def _student_notif_row_to_json(row):
    """Convert a notification row dict to safe JSON-serialisable values."""
    if not row:
        return row
    clean = dict(row)
    if clean.get("created_at") is not None:
        clean["created_at"] = str(clean["created_at"])
    clean["is_read"] = bool(clean.get("is_read"))
    clean["can_reply"] = bool(clean.get("can_reply", 1))
    clean["course_scope"] = clean.get("course_scope") or "both"
    clean["has_attachment"] = bool(clean.get("attachment_name"))
    clean.pop("attachment_data", None)  # never send binary over JSON
    return clean


def _get_student_project_info(cursor, user_id):
    """Return (student_id, project_id, supervisor_user_id) or (None, None, None)."""
    cursor.execute("SELECT student_id FROM students WHERE user_id = %s", (user_id,))
    st_row = cursor.fetchone()
    if not st_row:
        return None, None, None
    student_id = st_row["student_id"]
    cursor.execute(
        """
        SELECT p.project_id, f.user_id AS supervisor_user_id
        FROM   project_members pm
        JOIN   projects  p  ON p.project_id = pm.project_id
        LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
        WHERE  pm.student_id = %s
        ORDER  BY p.project_id DESC LIMIT 1
        """,
        (student_id,),
    )
    proj = cursor.fetchone()
    if not proj:
        return student_id, None, None
    return student_id, proj["project_id"], proj["supervisor_user_id"]


@student_bp.route("/api/notifications/options", methods=["GET"])
@login_required(role="student")
def api_student_notification_options():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        student_id, project_id, _ = _get_student_project_info(cursor, user_id)
        team_members = []
        supervisor = None
        if project_id:
            cursor.execute(
                """
                SELECT u.user_id, u.full_name, u.university_id
                FROM   project_members pm
                JOIN   students st ON st.student_id = pm.student_id
                JOIN   users    u  ON u.user_id     = st.user_id
                WHERE  pm.project_id = %s AND st.user_id != %s AND u.is_active = TRUE
                """,
                (project_id, user_id),
            )
            team_members = [dict(r) for r in cursor.fetchall()]
            cursor.execute(
                """
                SELECT u.user_id, u.full_name, f.faculty_id
                FROM   projects p
                JOIN   faculty  f ON f.faculty_id = p.supervisor_id
                JOIN   users    u ON u.user_id    = f.user_id
                WHERE  p.project_id = %s AND u.is_active = TRUE
                """,
                (project_id,),
            )
            sup = cursor.fetchone()
            if sup:
                supervisor = dict(sup)
        cursor.close()
        db.close()
        return jsonify({"team_members": team_members, "supervisor": supervisor})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/notifications/inbox", methods=["GET"])
@login_required(role="student")
def api_student_notifications_inbox():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notif_attachment_columns(cursor)
        cursor.execute(
            """
            SELECT n.notification_id, n.notification_type, n.title, n.message,
                   n.course_scope, n.is_read, COALESCE(n.can_reply, 1) AS can_reply, n.created_at,
                   n.attachment_name, n.attachment_mime,
                   sender.user_id  AS sender_user_id,
                   sender.full_name AS sender_name,
                   sender.role      AS sender_role
            FROM   notifications n
            LEFT JOIN users sender ON sender.user_id = n.sender_id
            WHERE  n.recipient_id = %s
            ORDER  BY n.created_at DESC, n.notification_id DESC
            """,
            (user_id,),
        )
        rows = [_student_notif_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"notifications": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/notifications/sent", methods=["GET"])
@login_required(role="student")
def api_student_notifications_sent():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notif_attachment_columns(cursor)
        cursor.execute(
            """
            SELECT n.notification_id, n.title, n.message, n.notification_type,
                   n.course_scope, COALESCE(n.can_reply, 1) AS can_reply, n.created_at,
                   n.attachment_name, n.attachment_mime,
                   recip.full_name AS recipient_name,
                   recip.role      AS recipient_role
            FROM   notifications n
            JOIN   users recip ON recip.user_id = n.recipient_id
            WHERE  n.sender_id = %s
            ORDER  BY n.created_at DESC, n.notification_id DESC
            """,
            (user_id,),
        )
        rows = [_student_notif_row_to_json(r) for r in cursor.fetchall()]
        cursor.close()
        db.close()
        return jsonify({"sent": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/notifications/send", methods=["POST"])
@login_required(role="student")
def api_student_notifications_send():
    """
    Accepts multipart/form-data:
      scope   : 'team' | 'supervisor' | 'member' | 'reply'
      value   : user_id  (for 'member' and 'reply')
      title   : string
      message : string
      file    : (optional) attached file
    """
    scope = (request.form.get("scope") or "").strip()
    title = (request.form.get("title") or "").strip()
    message = (request.form.get("message") or "").strip()
    value = request.form.get("value")
    reply_to_notification_id = request.form.get("reply_to_notification_id")

    if not title:
        return jsonify({"error": "Please enter a title for your memo."}), 400
    if not message:
        return jsonify({"error": "Please write a message."}), 400
    if scope not in ("team", "supervisor", "member", "reply"):
        return jsonify({"error": "Please choose who to send the message to."}), 400

    # ── optional attachment ────────────────────────────────────
    att_name = att_mime = att_data = None
    uploaded = request.files.get("file")
    if uploaded and uploaded.filename:
        att_data = uploaded.read()
        att_name = secure_filename(uploaded.filename)
        att_mime = uploaded.mimetype or "application/octet-stream"
        MAX_ATT_MB = 10
        if len(att_data) > MAX_ATT_MB * 1024 * 1024:
            return jsonify({"error": f"Attachment exceeds {MAX_ATT_MB} MB limit."}), 400

    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_notif_attachment_columns(cursor)

        student_id, project_id, supervisor_user_id = _get_student_project_info(
            cursor, user_id
        )

        recipients = []

        if scope in ("team", "supervisor", "member"):
            if not project_id:
                return (
                    jsonify({"error": "You are not registered in any project yet."}),
                    400,
                )

            if scope == "team":
                cursor.execute(
                    """
                    SELECT u.user_id FROM project_members pm
                    JOIN students st ON st.student_id = pm.student_id
                    JOIN users    u  ON u.user_id     = st.user_id
                    WHERE pm.project_id = %s AND st.user_id != %s AND u.is_active = TRUE
                    """,
                    (project_id, user_id),
                )
                recipients = [r["user_id"] for r in cursor.fetchall()]

            elif scope == "supervisor":
                if not supervisor_user_id:
                    return (
                        jsonify(
                            {"error": "No supervisor assigned to your project yet."}
                        ),
                        400,
                    )
                recipients = [supervisor_user_id]

            elif scope == "member":
                if not value:
                    return (
                        jsonify({"error": "Please choose a specific team member."}),
                        400,
                    )
                cursor.execute(
                    """
                    SELECT u.user_id FROM project_members pm
                    JOIN students st ON st.student_id = pm.student_id
                    JOIN users    u  ON u.user_id     = st.user_id
                    WHERE pm.project_id = %s AND st.user_id = %s AND u.is_active = TRUE
                    """,
                    (project_id, int(value)),
                )
                row = cursor.fetchone()
                if not row:
                    return jsonify({"error": "This member is not on your team."}), 400
                recipients = [row["user_id"]]

        elif scope == "reply":
            # Reply only if the original received notification allows replies.
            if not value:
                return jsonify({"error": "Missing reply recipient."}), 400
            if not reply_to_notification_id:
                return jsonify({"error": "This reply cannot be sent because the original message was not identified."}), 400

            cursor.execute(
                """
                SELECT n.notification_id, n.sender_id, COALESCE(n.can_reply, 1) AS can_reply
                FROM notifications n
                WHERE n.notification_id = %s
                  AND n.recipient_id = %s
                  AND n.sender_id = %s
                LIMIT 1
                """,
                (int(reply_to_notification_id), user_id, int(value)),
            )
            row = cursor.fetchone()
            if not row:
                return jsonify({"error": "Original message was not found for this reply."}), 404
            if not bool(row.get("can_reply", 1)):
                return jsonify({"error": "Replies are disabled for this message."}), 403
            recipients = [int(value)]

        recipients = sorted({int(r) for r in recipients if int(r) != int(user_id)})
        if not recipients:
            return jsonify({"error": "No valid recipients found."}), 400

        for recipient_id in recipients:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, is_read, can_reply, attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, 'system', %s, %s, 'both', FALSE, TRUE, %s, %s, %s)
                """,
                (recipient_id, user_id, title, message, att_name, att_mime, att_data),
            )
        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": f"Memo sent successfully to {len(recipients)} recipient(s).",
                "sent_count": len(recipients),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route(
    "/api/notifications/<int:notification_id>/attachment", methods=["GET"]
)
@login_required(role="student")
def api_student_notification_attachment(notification_id):
    """Download the file attached to a notification (inbox or sent)."""
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT attachment_name, attachment_mime, attachment_data
            FROM   notifications
            WHERE  notification_id = %s
              AND  (recipient_id = %s OR sender_id = %s)
            """,
            (notification_id, user_id, user_id),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if not row or not row.get("attachment_data"):
            return jsonify({"error": "Attachment not found."}), 404
        return Response(
            row["attachment_data"],
            mimetype=row["attachment_mime"] or "application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{row["attachment_name"]}"'
            },
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/notifications/unread-count", methods=["GET"])
@login_required(role="student")
def api_student_notifications_unread_count():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE recipient_id = %s AND is_read = FALSE",
            (user_id,),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return jsonify({"unread": int((row or {}).get("cnt") or 0)})
    except Exception as e:
        return jsonify({"unread": 0})


@student_bp.route("/api/notifications/<int:notification_id>/read", methods=["POST"])
@login_required(role="student")
def api_student_notification_mark_read(notification_id):
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "UPDATE notifications SET is_read = TRUE WHERE notification_id = %s AND recipient_id = %s",
            (notification_id, user_id),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "Marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required(role="student")
def api_student_notifications_mark_all_read():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "UPDATE notifications SET is_read = TRUE WHERE recipient_id = %s",
            (user_id,),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": "All notifications marked as read."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
