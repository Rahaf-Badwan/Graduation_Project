from flask import Blueprint, jsonify, session

from auth import login_required
from db import get_db


promote_bp = Blueprint("promote", __name__)


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
    return int((cursor.fetchone() or {}).get("cnt") or 0) > 0


def _clear_comp4200_student_state(cursor, student_ids, user_ids):
    """Reset student-facing COMP4200 submissions/notifications after promotion."""
    if not student_ids:
        return

    student_placeholders = ",".join(["%s"] * len(student_ids))

    if _table_exists(cursor, "milestone_submissions"):
        cursor.execute(
            f"""
            DELETE ms
            FROM milestone_submissions ms
            JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
            JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
            JOIN semesters sem ON sem.semester_id = tl.semester_id
            WHERE sem.course_code = 'COMP4200'
              AND (
                ms.student_id IN ({student_placeholders})
                OR ms.project_id IN (
                    SELECT DISTINCT pm.project_id
                    FROM project_members pm
                    JOIN projects p ON p.project_id = pm.project_id
                    JOIN semesters ps ON ps.semester_id = p.semester_id
                    WHERE pm.student_id IN ({student_placeholders})
                      AND ps.course_code = 'COMP4200'
                )
              )
            """,
            [*student_ids, *student_ids],
        )

    if user_ids:
        user_placeholders = ",".join(["%s"] * len(user_ids))
        cursor.execute(
            f"DELETE FROM notifications WHERE recipient_id IN ({user_placeholders})",
            user_ids,
        )


@promote_bp.route("/api/students/passes", methods=["GET"])
@login_required(role="head_of_department")
def api_get_passes_students():
    """Students who passed COMP4200 but have not been promoted to COMP4300 yet."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT u.user_id, u.full_name, u.university_id, u.email,
                   u.avatar_initials, scr.result_id, scr.student_id,
                   sem.academic_year
            FROM student_course_results scr
            JOIN students st ON st.student_id = scr.student_id
            JOIN users u ON u.user_id = st.user_id
            JOIN semesters sem ON sem.semester_id = scr.semester_id
            WHERE u.role = 'student'
              AND u.is_active = TRUE
              AND sem.course_code = 'COMP4200'
              AND scr.status = 'passed'
              AND scr.promoted_at IS NULL
              AND scr.promoted_to_semester_id IS NULL
            ORDER BY u.full_name
            """
        )
        students = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"students": students}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/promote-all", methods=["POST"])
@login_required(role="head_of_department")
def api_promote_all():
    """Mark all passed COMP4200 students as officially promoted to COMP4300."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT semester_id
            FROM semesters
            WHERE course_code = 'COMP4300' AND is_active = TRUE
            ORDER BY semester_id DESC
            LIMIT 1
            """
        )
        comp4300 = cursor.fetchone()
        if not comp4300:
            cursor.close()
            db.close()
            return jsonify({"error": "No active COMP4300 semester found."}), 400

        cursor.execute(
            """
            SELECT scr.result_id, scr.student_id, st.user_id
            FROM student_course_results scr
            JOIN semesters sem ON sem.semester_id = scr.semester_id
            JOIN students st ON st.student_id = scr.student_id
            WHERE sem.course_code = 'COMP4200'
              AND scr.status = 'passed'
              AND scr.promoted_at IS NULL
              AND scr.promoted_to_semester_id IS NULL
            """
        )
        rows = cursor.fetchall()
        result_ids = [row["result_id"] for row in rows]
        student_ids = [row["student_id"] for row in rows]
        user_ids = [row["user_id"] for row in rows]

        if result_ids:
            placeholders = ",".join(["%s"] * len(result_ids))
            cursor.execute(
                f"""
                UPDATE student_course_results
                SET promoted_to_semester_id = %s,
                    promoted_by = %s,
                    promoted_at = NOW()
                WHERE result_id IN ({placeholders})
                """,
                [comp4300["semester_id"], session["user_id"], *result_ids],
            )

            _clear_comp4200_student_state(cursor, student_ids, user_ids)

            for row in rows:
                cursor.execute(
                    """
                    INSERT INTO notifications
                        (recipient_id, sender_id, notification_type, title, message,
                         is_read)
                    VALUES (%s, %s, 'status_changed',
                            'You have officially been moved to COMP4300',
                            'Congratulations! You have been successfully promoted to COMP4300 for the upcoming semester.',
                            FALSE)
                    """,
                    (row["user_id"], session["user_id"]),
                )

        db.commit()
        count = len(result_ids)
        cursor.close()
        db.close()
        return jsonify({"message": f"{count} student(s) promoted to COMP4300 successfully."}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/comp4300", methods=["GET"])
@login_required(role="head_of_department")
def api_get_comp4300_students():
    """Students with active, non-archived COMP4300 projects."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT DISTINCT u.user_id, u.full_name, u.university_id,
                   u.email, u.avatar_initials, p.project_id, p.title
            FROM users u
            JOIN students st ON st.user_id = u.user_id
            JOIN project_members pm ON pm.student_id = st.student_id
            JOIN projects p ON p.project_id = pm.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            WHERE u.role = 'student'
              AND u.is_active = TRUE
              AND sem.course_code = 'COMP4300'
              AND p.status != 'archived'
            ORDER BY u.full_name
            """
        )
        students = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"students": students}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/archive-all", methods=["POST"])
@login_required(role="head_of_department")
def api_archive_all():
    """Archive all active COMP4300 projects."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            UPDATE projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            SET p.status = 'archived'
            WHERE sem.course_code = 'COMP4300'
              AND p.status != 'archived'
            """
        )
        count = cursor.rowcount
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": f"{count} project(s) archived successfully."}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500
