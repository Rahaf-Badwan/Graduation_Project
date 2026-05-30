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

@student_bp.route("/registration")
@login_required(role="student")
def registration():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        context = _student_course_context(cursor, session.get("user_id"))
        cursor.close()
        db.close()
        if context.get("target_course") == "COMP4300":
            return redirect(url_for("student.dashboard"))
    except Exception:
        pass
    return render_template("student/registration.html")


@student_bp.route("/api/supervisors", methods=["GET"])
@login_required(role="student")
def api_student_supervisors():
    """Return list of supervisors for the registration form."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT f.faculty_id, u.full_name,
                   COUNT(DISTINCT p.project_id) AS assigned_projects
            FROM   faculty f
            JOIN   users u ON u.user_id = f.user_id
            LEFT JOIN projects p ON p.supervisor_id = f.faculty_id
            WHERE  u.role = 'supervisor'
            GROUP  BY f.faculty_id, u.full_name
            ORDER  BY u.full_name
        """)
        rows = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"supervisors": rows})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/registration-check", methods=["GET"])
@login_required(role="student")
def api_student_registration_check():
    user_id = session.get("user_id")
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester_st(cursor)
        if not semester:
            cursor.close()
            db.close()
            return jsonify(
                {"registered": False, "project": None, "distribution_open": False}
            )

        course_context = _student_course_context(cursor, user_id)
        target_course = course_context["target_course"]
        distribution_open = bool(semester.get("distribution_open"))
        close_at = semester.get("distribution_close_at")
        if close_at:
            from datetime import datetime as _dt

            distribution_open = distribution_open and _dt.now() < close_at
        if target_course != "COMP4200":
            distribution_open = False

        cursor.execute(
            """
            SELECT
                p.project_id,
                p.title, p.status, p.submission_date,
                pref1.full_name AS preferred_1,
                pref2.full_name AS preferred_2,
                pref3.full_name AS preferred_3,
                GROUP_CONCAT(u2.full_name ORDER BY pm2.is_primary_contact DESC SEPARATOR ', ') AS team_members
            FROM project_members pm
            JOIN students st ON st.student_id = pm.student_id
            JOIN projects p  ON p.project_id  = pm.project_id
            JOIN semesters s ON s.semester_id  = p.semester_id AND s.is_active = TRUE
            LEFT JOIN faculty f1  ON f1.faculty_id = p.preferred_supervisor_1
            LEFT JOIN users pref1 ON pref1.user_id = f1.user_id
            LEFT JOIN faculty f2  ON f2.faculty_id = p.preferred_supervisor_2
            LEFT JOIN users pref2 ON pref2.user_id = f2.user_id
            LEFT JOIN faculty f3  ON f3.faculty_id = p.preferred_supervisor_3
            LEFT JOIN users pref3 ON pref3.user_id = f3.user_id
            LEFT JOIN project_members pm2 ON pm2.project_id = p.project_id
            LEFT JOIN students st2        ON st2.student_id  = pm2.student_id
            LEFT JOIN users u2            ON u2.user_id      = st2.user_id
            WHERE st.user_id = %s
              AND p.semester_id = %s
            GROUP BY p.project_id, p.title, p.status, p.submission_date,
                     preferred_1, preferred_2, preferred_3
            ORDER BY p.project_id DESC
            LIMIT 1
        """,
            (user_id, semester["semester_id"]),
        )
        project = cursor.fetchone()
        cursor.close()
        db.close()

        if project:
            if isinstance(project.get("submission_date"), object) and hasattr(
                project["submission_date"], "isoformat"
            ):
                project["submission_date"] = str(project["submission_date"])
            return jsonify(
                {
                    "registered": True,
                    "project": project,
                    "distribution_open": distribution_open,
                    "target_course": target_course,
                    "timeline_available": target_course != "COMP4300",
                }
            )
        return jsonify(
            {
                "registered": False,
                "project": None,
                "distribution_open": distribution_open,
                "target_course": target_course,
                "timeline_available": target_course != "COMP4300",
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/distribution-window-status", methods=["GET"])
@login_required(role="student")
def api_student_distribution_window_status():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester_st(cursor)
        course_context = _student_course_context(cursor, session.get("user_id"))
        target_course = course_context["target_course"]
        cursor.close()
        db.close()
        if not semester:
            return jsonify({"error": "No active semester found."}), 400
        is_open = bool(semester.get("distribution_open"))
        close_at = semester.get("distribution_close_at")
        if close_at:
            from datetime import datetime as _dt

            is_open = is_open and _dt.now() < close_at
        if target_course != "COMP4200":
            is_open = False
        return jsonify(
            {
                "is_open": is_open,
                "opened_at": str(semester.get("distribution_opened_at") or ""),
                "closed_at": str(semester.get("distribution_closed_at") or ""),
                "course_code": "COMP4200",
                "target_course": target_course,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@student_bp.route("/api/distribution-submit", methods=["POST"])
@login_required(role="student")
def api_student_distribution_submit():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    group_name = (data.get("group_name") or "").strip()
    abstract = (data.get("abstract") or "").strip()
    keywords = (data.get("keywords") or "").strip()
    preferred = data.get("preferred_supervisors") or []
    member_ids = [
        str(x).strip() for x in (data.get("member_ids") or []) if str(x).strip()
    ]
    user_id = session.get("user_id")
    user_uid = session.get("university_id")

    if user_uid and user_uid not in member_ids:
        member_ids.insert(0, user_uid)

    if not title:
        return jsonify({"error": "Project title is required."}), 400
    if not member_ids:
        return jsonify({"error": "At least one team member is required."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _get_active_semester_st(cursor)

        if not semester:
            cursor.close()
            db.close()
            return jsonify({"error": "No active semester is configured."}), 400

        course_context = _student_course_context(cursor, user_id)
        if course_context.get("target_course") != "COMP4200":
            cursor.close()
            db.close()
            return (
                jsonify(
                    {
                        "error": "COMP4300 students are already registered through their COMP4200 team and cannot use this registration window."
                    }
                ),
                403,
            )

        is_open = int(semester.get("distribution_open") or 0) == 1
        close_at = semester.get("distribution_close_at")
        if close_at:
            from datetime import datetime as _dt

            is_open = is_open and _dt.now() < close_at
        if not is_open:
            cursor.close()
            db.close()
            return jsonify({"error": "Student distribution is currently closed."}), 403

        for uid in member_ids:
            cursor.execute(
                """
                SELECT st.student_id, u.user_id, u.is_active
                FROM students st
                JOIN users u ON u.user_id = st.user_id
                WHERE u.university_id = %s
                  AND u.role = 'student'
                LIMIT 1
                """,
                (uid,),
            )
            member_row = cursor.fetchone()
            if not member_row:
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "error": f"Student {uid} was not found."
                        }
                    ),
                    400,
                )
            if not member_row.get("is_active"):
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "error": f"Student {uid} cannot be added because their account is inactive."
                        }
                    ),
                    400,
                )
            member_context = _student_course_context(cursor, member_row["user_id"])
            if member_context.get("target_course") != "COMP4200":
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "error": f"Student {uid} is not eligible for COMP4200 registration."
                        }
                    ),
                    400,
                )

        # Duplicate check
        for uid in member_ids:
            cursor.execute(
                """
                SELECT p.project_id, p.title
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users u     ON u.user_id      = st.user_id
                JOIN projects p  ON p.project_id   = pm.project_id
                JOIN semesters s ON s.semester_id   = p.semester_id AND s.is_active = TRUE
                WHERE u.university_id = %s
                  AND p.semester_id = %s
                LIMIT 1
            """,
                (uid, semester["semester_id"]),
            )
            dup = cursor.fetchone()
            if dup:
                cursor.close()
                db.close()
                return (
                    jsonify(
                        {
                            "already_registered": True,
                            "error": f"Student {uid} is already registered (Project: \"{dup['title']}\").",
                        }
                    ),
                    409,
                )

        pref_ids = [int(x) for x in preferred[:3] if str(x).strip().isdigit()]
        while len(pref_ids) < 3:
            pref_ids.append(None)

        has_group_name = _db_column_exists_student(cursor, "projects", "group_name")

        if has_group_name:
            cursor.execute(
                """
                INSERT INTO projects
                    (group_name, title, abstract, keywords, project_type, semester_id, status, submission_date,
                     preferred_supervisor_1, preferred_supervisor_2, preferred_supervisor_3)
                VALUES (%s, %s, %s, %s, '', %s, 'submitted', CURDATE(), %s, %s, %s)
                """,
                (
                    group_name or None,
                    title,
                    abstract or None,
                    keywords or None,
                    semester["semester_id"],
                    pref_ids[0],
                    pref_ids[1],
                    pref_ids[2],
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO projects
                    (title, abstract, keywords, project_type, semester_id, status, submission_date,
                     preferred_supervisor_1, preferred_supervisor_2, preferred_supervisor_3)
                VALUES (%s, %s, %s, '', %s, 'submitted', CURDATE(), %s, %s, %s)
                """,
                (
                    title,
                    abstract or None,
                    keywords or None,
                    semester["semester_id"],
                    pref_ids[0],
                    pref_ids[1],
                    pref_ids[2],
                ),
            )
        project_id = cursor.lastrowid

        for i, uid in enumerate(member_ids):
            cursor.execute(
                """
                SELECT st.student_id FROM students st
                JOIN users u ON u.user_id = st.user_id
                WHERE u.university_id = %s
                  AND u.role = 'student'
                  AND u.is_active = TRUE
            """,
                (uid,),
            )
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES (%s, %s, %s)",
                    (project_id, row["student_id"], i == 0),
                )

        actor_name = session.get("full_name") or "A teammate"
        _notify_project_team(
            cursor,
            project_id,
            session.get("user_id"),
            "Project registration submitted",
            f'{actor_name} registered your team project "{title}".',
            notification_type="system",
            exclude_user_id=session.get("user_id"),
        )

        # Sync lifecycle
        _sync_lifecycle(cursor, project_id)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": "Project proposal submitted successfully.",
                "project_id": project_id,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
