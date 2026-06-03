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


def _student_id_for_user(cursor, user_id):
    cursor.execute(
        "SELECT student_id FROM students WHERE user_id = %s LIMIT 1",
        (user_id,),
    )
    row = cursor.fetchone()
    return row["student_id"] if row else None


def _student_challenge_scope(cursor, user_id):
    """Return every project/team that should share challenges with this student.

    The challenge page must not prefer COMP4200 over COMP4300 or COMP4300 over
    COMP4200. It collects:
      1) all projects where the logged-in student is a member,
      2) linked source/promoted projects from project_course_promotions, if present,
      3) all projects that contain any member from those projects, so a COMP4200
         team and its COMP4300 continuation share the same challenges.

    It also returns team_student_ids so old challenge rows remain visible even if
    they were saved against another project in the same team.
    """
    student_id = _student_id_for_user(cursor, user_id)
    if not student_id:
        return None, [], []

    project_ids = []

    # 1) direct memberships for this student across all courses/semesters
    cursor.execute(
        """
        SELECT DISTINCT pm.project_id
        FROM project_members pm
        JOIN projects p ON p.project_id = pm.project_id
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE pm.student_id = %s
        ORDER BY s.course_code, s.semester_id DESC, pm.project_id DESC
        """,
        (student_id,),
    )
    for row in cursor.fetchall():
        pid = row.get("project_id")
        if pid and pid not in project_ids:
            project_ids.append(pid)

    # 2) explicit COMP4200 <-> COMP4300 promotion links, when the table exists
    if project_ids and _table_exists_student(cursor, "project_course_promotions"):
        placeholders = ",".join(["%s"] * len(project_ids))
        cursor.execute(
            f"""
            SELECT DISTINCT source_project_id AS project_id
            FROM project_course_promotions
            WHERE promoted_project_id IN ({placeholders})
            UNION
            SELECT DISTINCT promoted_project_id AS project_id
            FROM project_course_promotions
            WHERE source_project_id IN ({placeholders})
            """,
            [*project_ids, *project_ids],
        )
        for row in cursor.fetchall():
            pid = row.get("project_id")
            if pid and pid not in project_ids:
                project_ids.append(pid)

    # 3) all team members from those projects
    team_student_ids = [student_id]
    if project_ids:
        placeholders = ",".join(["%s"] * len(project_ids))
        cursor.execute(
            f"""
            SELECT DISTINCT student_id
            FROM project_members
            WHERE project_id IN ({placeholders})
            """,
            project_ids,
        )
        for row in cursor.fetchall():
            sid = row.get("student_id")
            if sid and sid not in team_student_ids:
                team_student_ids.append(sid)

    # 4) any other project for those team members, regardless of COMP4200/COMP4300
    # This catches continuations even when project_course_promotions was not filled.
    if team_student_ids:
        placeholders = ",".join(["%s"] * len(team_student_ids))
        cursor.execute(
            f"""
            SELECT DISTINCT pm.project_id
            FROM project_members pm
            JOIN projects p ON p.project_id = pm.project_id
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE pm.student_id IN ({placeholders})
            ORDER BY s.course_code, s.semester_id DESC, pm.project_id DESC
            """,
            team_student_ids,
        )
        for row in cursor.fetchall():
            pid = row.get("project_id")
            if pid and pid not in project_ids:
                project_ids.append(pid)

    # refresh members after adding related projects
    if project_ids:
        placeholders = ",".join(["%s"] * len(project_ids))
        cursor.execute(
            f"""
            SELECT DISTINCT student_id
            FROM project_members
            WHERE project_id IN ({placeholders})
            """,
            project_ids,
        )
        for row in cursor.fetchall():
            sid = row.get("student_id")
            if sid and sid not in team_student_ids:
                team_student_ids.append(sid)

    return student_id, project_ids, team_student_ids


def _get_student_project(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    student_id, project_ids, _team_student_ids = _student_challenge_scope(cursor, user_id)
    row = None
    if project_ids:
        # Add new challenges to the latest related project, not only COMP4200 or COMP4300.
        placeholders = ",".join(["%s"] * len(project_ids))
        cursor.execute(
            f"""
            SELECT %s AS student_id, p.project_id
            FROM projects p
            JOIN semesters s ON s.semester_id = p.semester_id
            WHERE p.project_id IN ({placeholders})
            ORDER BY s.semester_id DESC, p.project_id DESC
            LIMIT 1
            """,
            [student_id, *project_ids],
        )
        row = cursor.fetchone()
    cursor.close()
    db.close()
    return row


@student_bp.route("/api/challenges", methods=["GET"])
@login_required(role="student")
def api_challenges_list():
    user_id = session["user_id"]
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        student_id, project_ids, team_student_ids = _student_challenge_scope(cursor, user_id)
        if not student_id or (not project_ids and not team_student_ids):
            cursor.close()
            db.close()
            return jsonify({"challenges": [], "project_id": None})

        where_parts = []
        params = []

        if project_ids:
            placeholders = ",".join(["%s"] * len(project_ids))
            where_parts.append(f"cr.project_id IN ({placeholders})")
            params.extend(project_ids)

        if team_student_ids:
            placeholders = ",".join(["%s"] * len(team_student_ids))
            # cr.student_id is supposed to store students.student_id.
            # The second condition keeps old/legacy rows visible if user_id was
            # accidentally stored in cr.student_id before the fix.
            where_parts.append(
                f"(cr.student_id IN ({placeholders}) OR legacy_st.student_id IN ({placeholders}))"
            )
            params.extend(team_student_ids)
            params.extend(team_student_ids)

        cursor.execute(
            f"""
            SELECT DISTINCT
                   cr.challenge_id,
                   cr.project_id,
                   cr.student_id,
                   cr.type,
                   cr.title,
                   cr.description,
                   cr.solution_lesson,
                   cr.created_at,
                   COALESCE(author.full_name, legacy_author.full_name, 'Team member') AS full_name,
                   author_st.student_id AS real_student_id,
                   legacy_st.student_id AS legacy_student_id,
                   sem.course_code
            FROM   challenges_reflections cr
            LEFT JOIN students author_st ON author_st.student_id = cr.student_id
            LEFT JOIN users author ON author.user_id = author_st.user_id
            LEFT JOIN students legacy_st ON legacy_st.user_id = cr.student_id
            LEFT JOIN users legacy_author ON legacy_author.user_id = legacy_st.user_id
            LEFT JOIN projects p ON p.project_id = cr.project_id
            LEFT JOIN semesters sem ON sem.semester_id = p.semester_id
            WHERE  {' OR '.join(where_parts)}
            ORDER  BY cr.created_at DESC, cr.challenge_id DESC
            """,
            tuple(params),
        )
        rows = cursor.fetchall()
        cursor.close()
        db.close()

        for r in rows:
            actual_author_student_id = r.get("real_student_id") or r.get("legacy_student_id") or r.get("student_id")
            r["is_mine"] = actual_author_student_id == student_id
            r["created_date"] = _fmt_date(r.pop("created_at", None))
            r.pop("real_student_id", None)
            r.pop("legacy_student_id", None)

        return jsonify({"challenges": rows, "project_id": project_ids[0] if project_ids else None})
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
            (info["project_id"], info["student_id"], ch_type, title, details, solution),
        )
        db.commit()
        new_id = cursor.lastrowid

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

        cursor.execute(
            """
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, u.full_name
            FROM   challenges_reflections cr
            JOIN   students st ON st.student_id = cr.student_id
            JOIN   users u ON u.user_id = st.user_id
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
        cursor.execute(
            """
            SELECT cr.student_id,
                   COALESCE(author_st.user_id, legacy_st.user_id) AS author_user_id
            FROM challenges_reflections cr
            LEFT JOIN students author_st ON author_st.student_id = cr.student_id
            LEFT JOIN students legacy_st ON legacy_st.user_id = cr.student_id
            WHERE cr.challenge_id = %s
            """,
            (challenge_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "Not found."}), 404
        if row["author_user_id"] != user_id:
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

        cursor.execute(
            """
            SELECT cr.challenge_id, cr.project_id, cr.student_id,
                   cr.type, cr.title, cr.description, cr.solution_lesson,
                   cr.created_at, COALESCE(u.full_name, legacy_u.full_name, 'Team member') AS full_name
            FROM   challenges_reflections cr
            LEFT JOIN students st ON st.student_id = cr.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            LEFT JOIN students legacy_st ON legacy_st.user_id = cr.student_id
            LEFT JOIN users legacy_u ON legacy_u.user_id = legacy_st.user_id
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
            """
            SELECT cr.student_id,
                   COALESCE(author_st.user_id, legacy_st.user_id) AS author_user_id
            FROM challenges_reflections cr
            LEFT JOIN students author_st ON author_st.student_id = cr.student_id
            LEFT JOIN students legacy_st ON legacy_st.user_id = cr.student_id
            WHERE cr.challenge_id = %s
            """,
            (challenge_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            db.close()
            return jsonify({"error": "Not found."}), 404
        if row["author_user_id"] != user_id:
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
