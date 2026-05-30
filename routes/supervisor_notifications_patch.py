# ============================================================
# Supervisor Notifications Reply Control Patch
# Paste this block in app.py after supervisor routes, or keep it
# in a registered supervisor notifications route file.
# ============================================================

from flask import jsonify


def _sup_db_column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        """,
        (table_name, column_name),
    )
    return int((cursor.fetchone() or {}).get("cnt") or 0) > 0


def _sup_table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        """,
        (table_name,),
    )
    return int((cursor.fetchone() or {}).get("cnt") or 0) > 0


def _ensure_supervisor_notification_schema(cursor):
    if _sup_table_exists(cursor, "notifications"):
        if not _sup_db_column_exists(cursor, "notifications", "course_scope"):
            cursor.execute(
                """
                ALTER TABLE notifications
                ADD COLUMN course_scope ENUM('introduction','graduation_project','both')
                NOT NULL DEFAULT 'both' AFTER message
                """
            )
        if not _sup_db_column_exists(cursor, "notifications", "can_reply"):
            cursor.execute(
                "ALTER TABLE notifications ADD COLUMN can_reply TINYINT(1) NOT NULL DEFAULT 1 AFTER is_read"
            )
        if not _sup_db_column_exists(cursor, "notifications", "attachment_name"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255) NULL")
        if not _sup_db_column_exists(cursor, "notifications", "attachment_mime"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120) NULL")
        if not _sup_db_column_exists(cursor, "notifications", "attachment_data"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_data LONGBLOB NULL")


def _sup_notification_select_fields(cursor):
    attachment_fields = (
        "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"
        if _sup_db_column_exists(cursor, "notifications", "attachment_name")
        else "NULL AS attachment_name, NULL AS attachment_mime, 0 AS has_attachment"
    )
    can_reply_field = (
        "COALESCE(n.can_reply, 1) AS can_reply"
        if _sup_db_column_exists(cursor, "notifications", "can_reply")
        else "1 AS can_reply"
    )
    return attachment_fields, can_reply_field


def _sup_notification_row_to_json(row):
    clean = dict(row or {})
    if clean.get("created_at") is not None:
        clean["created_at"] = str(clean["created_at"])
    clean["is_read"] = bool(clean.get("is_read"))
    clean["course_scope"] = clean.get("course_scope") or "both"
    clean["has_attachment"] = bool(clean.get("has_attachment"))
    clean["can_reply"] = bool(clean.get("can_reply", True))
    clean.pop("attachment_data", None)
    if not clean["has_attachment"]:
        clean["attachment_name"] = None
        clean["attachment_mime"] = None
    return clean


def _supervisor_reply_allowed(cursor, original_notification_id, current_user_id, target_user_id):
    if not original_notification_id:
        return False
    can_reply_expr = "COALESCE(can_reply, 1)" if _sup_db_column_exists(cursor, "notifications", "can_reply") else "1"
    cursor.execute(
        f"""
        SELECT notification_id
        FROM notifications
        WHERE notification_id = %s
          AND recipient_id = %s
          AND sender_id = %s
          AND {can_reply_expr} = 1
        LIMIT 1
        """,
        (original_notification_id, current_user_id, target_user_id),
    )
    return cursor.fetchone() is not None


def _supervisor_notification_recipients(cursor, scope, value=None, course_scope="both"):
    scope = (scope or "").strip()
    if scope == "coordinators":
        cursor.execute("SELECT user_id FROM users WHERE role = 'coordinator' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "coordinator":
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND role = 'coordinator' AND is_active = TRUE", (value,))
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "doctors":
        cursor.execute("SELECT user_id FROM users WHERE role = 'supervisor' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "doctor":
        cursor.execute(
            """
            SELECT u.user_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s AND u.role = 'supervisor' AND u.is_active = TRUE
            """,
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "students":
        cursor.execute("SELECT user_id FROM users WHERE role = 'student' AND is_active = TRUE")
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "student":
        cursor.execute(
            """
            SELECT u.user_id
            FROM students st
            JOIN users u ON u.user_id = st.user_id
            WHERE st.student_id = %s AND u.role = 'student' AND u.is_active = TRUE
            """,
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]
    if scope == "reply":
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND is_active = TRUE", (value,))
        return [r["user_id"] for r in cursor.fetchall()]
    return []


@app.route("/supervisor/api/notifications/inbox", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_notifications_inbox():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_supervisor_notification_schema(cursor)
        db.commit()
        attachment_fields, can_reply_field = _sup_notification_select_fields(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.notification_type, n.title, n.message,
                   n.course_scope, n.related_project_id, n.is_read, n.created_at,
                   n.sender_id AS sender_user_id,
                   sender.full_name AS sender_name, sender.role AS sender_role,
                   {can_reply_field}, {attachment_fields}
            FROM notifications n
            LEFT JOIN users sender ON sender.user_id = n.sender_id
            WHERE n.recipient_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_sup_notification_row_to_json(r) for r in cursor.fetchall()]
        cursor.close(); db.close()
        return jsonify({"notifications": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/sent", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_notifications_sent():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_supervisor_notification_schema(cursor)
        db.commit()
        attachment_fields, can_reply_field = _sup_notification_select_fields(cursor)
        cursor.execute(
            f"""
            SELECT n.notification_id, n.title, n.message, n.notification_type,
                   n.course_scope, n.is_read, n.created_at,
                   n.recipient_id AS recipient_user_id,
                   recipient.full_name AS recipient_name, recipient.role AS recipient_role,
                   {can_reply_field}, {attachment_fields}
            FROM notifications n
            JOIN users recipient ON recipient.user_id = n.recipient_id
            WHERE n.sender_id = %s
            ORDER BY n.created_at DESC, n.notification_id DESC
            LIMIT 100
            """,
            (session.get("user_id"),),
        )
        rows = [_sup_notification_row_to_json(r) for r in cursor.fetchall()]
        cursor.close(); db.close()
        return jsonify({"sent": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/supervisor/api/notifications/send", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_notifications_send():
    is_multipart = bool(request.content_type and request.content_type.startswith("multipart/form-data"))
    data = request.form if is_multipart else (request.get_json(silent=True) or {})
    uploaded_file = request.files.get("file") if is_multipart else None

    scope = (data.get("scope") or "").strip()
    value = data.get("value")
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    urgent = str(data.get("urgent") or "").lower() in ("1", "true", "on", "yes")
    course_scope = (data.get("course_scope") or "both").strip()
    can_reply = str(data.get("can_reply", "1")).lower() in ("1", "true", "on", "yes")
    reply_to_notification_id = data.get("reply_to_notification_id") or data.get("notification_id")

    if course_scope not in {"introduction", "graduation_project", "both"}:
        return jsonify({"error": "Please choose the course scope."}), 400
    if not scope:
        return jsonify({"error": "Please choose who should receive the message."}), 400
    if not title:
        return jsonify({"error": "Please write a title."}), 400
    if not message:
        return jsonify({"error": "Please write a message."}), 400
    if scope in {"coordinator", "doctor", "student", "section", "reply"} and not value:
        return jsonify({"error": "Please choose the exact receiver."}), 400

    attachment_name = attachment_mime = attachment_data = None
    if uploaded_file and uploaded_file.filename:
        attachment_name = secure_filename(uploaded_file.filename) or "attachment"
        attachment_mime = uploaded_file.mimetype or "application/octet-stream"
        attachment_data = uploaded_file.read()
        if len(attachment_data) > 10 * 1024 * 1024:
            return jsonify({"error": "Attachment must be 10 MB or smaller."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_supervisor_notification_schema(cursor)
        sender_id = session.get("user_id")
        recipients = _supervisor_notification_recipients(cursor, scope, value, course_scope)
        recipients = sorted({int(r) for r in recipients if int(r) != int(sender_id)})
        if not recipients:
            cursor.close(); db.close()
            return jsonify({"error": "No recipients found for this choice."}), 404

        if scope == "reply":
            for recipient_id in recipients:
                if not _supervisor_reply_allowed(cursor, reply_to_notification_id, sender_id, recipient_id):
                    cursor.close(); db.close()
                    return jsonify({"error": "Replies are disabled for this message."}), 403
            can_reply = True

        notification_type = "urgent_alert" if urgent else "system"
        for recipient_id in recipients:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read, can_reply,
                     attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE, %s, %s, %s, %s)
                """,
                (
                    recipient_id, sender_id, notification_type, title, message,
                    course_scope, 1 if can_reply else 0,
                    attachment_name, attachment_mime, attachment_data,
                ),
            )
        db.commit()
        cursor.close(); db.close()
        return jsonify({"message": f"Message sent successfully to {len(recipients)} recipient(s).", "sent_count": len(recipients)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
