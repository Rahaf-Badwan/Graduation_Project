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

@student_bp.route("/challenges")
@login_required(role="student")
def challenges():
    return render_template("student/challenges.html")


def _get_student_project(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT st.student_id, pm.project_id
        FROM   students st
        JOIN   project_members pm ON pm.student_id = st.student_id
        WHERE  st.user_id = %s
        ORDER  BY pm.project_id DESC
        LIMIT  1
    """,
        (user_id,),
    )
    row = cursor.fetchone()
    cursor.close()
    db.close()
    return row  # None if student has no project yet


@student_bp.route("/api/challenges", methods=["GET"])
@login_required(role="student")
def api_challenges_list():
    user_id = session["user_id"]
    try:
        info = _get_student_project(user_id)
        if not info:
            return jsonify({"challenges": [], "project_id": None})

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT cr.challenge_id,
                   cr.project_id,
                   cr.student_id,
                   cr.type,
                   cr.title,
                   cr.description,
                   cr.solution_lesson,
                   cr.created_at,
                   u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.project_id = %s
            ORDER  BY cr.created_at DESC
        """,
            (info["project_id"],),
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        # mark which ones belong to the current user + format date
        for r in rows:
            r["is_mine"] = r["student_id"] == user_id
            r["created_date"] = _fmt_date(r.pop("created_at", None))

        return jsonify({"challenges": rows, "project_id": info["project_id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/challenges", methods=["POST"])
@login_required(role="student")
def api_challenges_add():
    user_id = session["user_id"]
    data = request.get_json(force=True) or {}

    ch_type = data.get("type", "").strip().lower()
    title = data.get("title", "").strip()
    details = data.get("description", "").strip()
    solution = data.get("solution_lesson", "").strip() or None

    if ch_type not in ("technical", "administrative", "reflection"):
        return jsonify({"error": "Invalid type."}), 400
    if not title:
        return jsonify({"error": "Title is required."}), 400
    if not details:
        return jsonify({"error": "Details are required."}), 400

    try:
        info = _get_student_project(user_id)
        if not info:
            return jsonify({"error": "You are not assigned to any project."}), 400

        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO challenges_reflections
                (project_id, student_id, type, title, description, solution_lesson)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
            (info["project_id"], user_id, ch_type, title, details, solution),
        )
        db.commit()
        new_id = cursor.lastrowid

        # notify the rest of the team
        type_label = {
            "technical": "Technical Challenge",
            "administrative": "Administrative Challenge",
            "reflection": "Reflection",
        }.get(ch_type, "Challenge")
        _notify_project_team(
            cursor,
            project_id=info["project_id"],
            sender_id=user_id,
            title=f"New {type_label} Added",
            message=f'A team member added a new {type_label.lower()}: "{title}"',
            notification_type="system",
            exclude_user_id=user_id,
        )
        db.commit()

        # return the inserted row with full_name
        cursor.execute(
            """
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.challenge_id = %s
        """,
            (new_id,),
        )
        row = cursor.fetchone()
        row["is_mine"] = True
        row["created_date"] = _fmt_date(row.pop("created_at", None))
        cursor.close()
        db.close()
        return jsonify({"challenge": row}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/challenges/<int:challenge_id>", methods=["PUT"])
@login_required(role="student")
def api_challenges_update(challenge_id):
    user_id = session["user_id"]
    data = request.get_json(force=True) or {}

    ch_type = data.get("type", "").strip().lower()
    title = data.get("title", "").strip()
    details = data.get("description", "").strip()
    solution = data.get("solution_lesson", "").strip() or None

    if ch_type not in ("technical", "administrative", "reflection"):
        return jsonify({"error": "Invalid type."}), 400
    if not title:
        return jsonify({"error": "Title is required."}), 400
    if not details:
        return jsonify({"error": "Details are required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        # verify ownership
        cursor.execute(
            "SELECT student_id FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "Not found."}), 404
        if row["student_id"] != user_id:
            cursor.close()
            db.close()
            return jsonify({"error": "You can only edit your own entries."}), 403

        cursor.execute(
            """
            UPDATE challenges_reflections
            SET    type = %s, title = %s, description = %s, solution_lesson = %s
            WHERE  challenge_id = %s
        """,
            (ch_type, title, details, solution, challenge_id),
        )
        db.commit()

        # notify the rest of the team about the update
        type_label = {
            "technical": "Technical Challenge",
            "administrative": "Administrative Challenge",
            "reflection": "Reflection",
        }.get(ch_type, "Challenge")
        cursor.execute(
            "SELECT project_id FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,),
        )
        proj = cursor.fetchone()
        if proj:
            _notify_project_team(
                cursor,
                project_id=proj["project_id"],
                sender_id=user_id,
                title=f"{type_label} Updated",
                message=f'A team member updated a {type_label.lower()}: "{title}"',
                notification_type="system",
                exclude_user_id=user_id,
            )
            db.commit()

        # return updated row
        cursor.execute(
            """
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, u.full_name
            FROM   challenges_reflections cr
            JOIN   users u ON u.user_id = cr.student_id
            WHERE  cr.challenge_id = %s
        """,
            (challenge_id,),
        )
        updated = cursor.fetchone()
        updated["is_mine"] = True
        updated["created_date"] = _fmt_date(updated.pop("created_at", None))
        cursor.close()
        db.close()
        return jsonify({"challenge": updated})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/challenges/<int:challenge_id>", methods=["DELETE"])
@login_required(role="student")
def api_challenges_delete(challenge_id):
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT student_id FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "Not found."}), 404
        if row["student_id"] != user_id:
            cursor.close()
            db.close()
            return jsonify({"error": "You can only delete your own entries."}), 403

        cursor.execute(
            "DELETE FROM challenges_reflections WHERE challenge_id = %s",
            (challenge_id,),
        )
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"deleted": challenge_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
