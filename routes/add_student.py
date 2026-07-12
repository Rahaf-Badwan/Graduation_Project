# routes add_student.py
from flask import Blueprint, request, jsonify, current_app
from db import get_db
from auth import login_required
from semester_lifecycle import auto_rollover_semesters
import bcrypt, re

add_student_bp = Blueprint("add_student", __name__)


# head of depatment add student with active = 'pending' (is_active = 0)
@add_student_bp.route("/api/students/add", methods=["POST"])
@login_required(role="head_of_department")
def api_add_student():
    data = request.get_json(silent=True) or {}

    full_name = (data.get("full_name") or "").strip()
    university_id = (data.get("university_id") or "").strip()

    # check validation
    if not full_name or not university_id:
        return jsonify({"error": "Name and University ID are required."}), 400

    if not re.match(r"^\d{7}$", university_id):
        return jsonify({"error": "University ID must be exactly 7 digits."}), 400

    email = f"{university_id}@student.birzeit.edu"

    # Avater initials
    parts = full_name.split()
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()

    # temporary password, the student cannot log in until activate
    temp_hash = bcrypt.hashpw(b"__pending__", bcrypt.gensalt()).decode()

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        # check for duplicate
        cursor.execute(
            "SELECT user_id FROM users WHERE university_id = %s OR email = %s",
            (university_id, email),
        )
        if cursor.fetchone():
            cursor.close()
            db.close()
            return jsonify({"error": "University ID or email already exists."}), 400
        # add student is_active = 0 that mean account status = pending
        cursor.execute(
            """
                INSERT INTO users
                       (university_id, full_name, email, password_hash, role, avatar_initials, is_active)
                       VALUES (%s, %s, %s, %s, 'student', %s, FALSE)
                       """,
            (university_id, full_name, email, temp_hash, initials),
        )

        user_id = cursor.lastrowid

        # add field in student table
        cursor.execute(
            "INSERT INTO students (user_id, enrollment_year) VALUES (%s, YEAR(CURDATE()))",
            (user_id,),
        )

        student_id = cursor.lastrowid

        try:
            auto_rollover_semesters(cursor)
        except Exception:
            pass

        cursor.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'semesters'
              AND COLUMN_NAME = 'start_date'
            """
        )
        has_start_date = int((cursor.fetchone() or {}).get("cnt") or 0) > 0
        semester_order = (
            "start_date DESC, semester_id DESC" if has_start_date else "semester_id DESC"
        )
        cursor.execute(
            f"""
            INSERT INTO student_course_results (student_id, semester_id, status)
            SELECT %s, semester_id, 'pending'
            FROM semesters
            WHERE course_code = 'COMP4200'
            ORDER BY
              CASE WHEN is_active = TRUE THEN 0 ELSE 1 END,
              {semester_order}
            LIMIT 1
            """,
            (student_id,),
        )
        db.commit()
        cursor.close()
        db.close()

        return (
            jsonify(
                {
                    "message": "تم إضافة الطالب بنجاح. حالة الحساب: بانتظار التفعيل.",
                    "user_id": user_id,
                    "status": "pending",
                }
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error("Error in api_add_student: %s", e)
        return jsonify({"error": f"Database error: {e}"}), 500


# Return active students based on Head-approved lifecycle transitions.
# Coordinator success only makes a group/project ready for Head approval; it
# must not move students between tabs or remove them from the active list.
@add_student_bp.route("/api/students/active", methods=["GET"])
@login_required(role="head_of_department")
def api_active_students():
    course = request.args.get("course", "COMP4200").upper()

    if course not in ("COMP4200", "COMP4300"):
        return jsonify({"error": "Unkown course code."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        if course == "COMP4200":
            cursor.execute(
                """
                SELECT DISTINCT
                       u.user_id,
                       u.university_id,
                       u.full_name,
                       u.email,
                       u.avatar_initials
                FROM users u
                JOIN students st ON st.user_id = u.user_id
                JOIN student_course_results scr ON scr.student_id = st.student_id
                JOIN semesters s ON s.semester_id = scr.semester_id
                WHERE u.role = 'student'
                  AND u.is_active = TRUE
                  AND s.course_code = 'COMP4200'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM student_course_results promoted_result
                      JOIN users promoter
                        ON promoter.user_id = promoted_result.promoted_by
                       AND promoter.role = 'head_of_department'
                      JOIN semesters promoted_target
                        ON promoted_target.semester_id = promoted_result.promoted_to_semester_id
                       AND promoted_target.course_code = 'COMP4300'
                      WHERE promoted_result.student_id = st.student_id
                        AND promoted_result.promoted_at IS NOT NULL
                  )
                ORDER BY u.full_name
                """
            )
        else:
            cursor.execute(
                """
                SELECT DISTINCT
                       u.user_id,
                       u.university_id,
                       u.full_name,
                       u.email,
                       u.avatar_initials
                FROM users u
                JOIN students st ON st.user_id = u.user_id
                WHERE u.role = 'student'
                  AND u.is_active = TRUE
                  AND (
                      EXISTS (
                          SELECT 1
                          FROM student_course_results promoted_result
                          JOIN users promoter
                            ON promoter.user_id = promoted_result.promoted_by
                           AND promoter.role = 'head_of_department'
                          JOIN semesters promoted_target
                            ON promoted_target.semester_id = promoted_result.promoted_to_semester_id
                           AND promoted_target.course_code = 'COMP4300'
                          WHERE promoted_result.student_id = st.student_id
                            AND promoted_result.promoted_at IS NOT NULL
                      )
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM project_members archived_pm
                      JOIN projects archived_project
                        ON archived_project.project_id = archived_pm.project_id
                      JOIN semesters archived_semester
                        ON archived_semester.semester_id = archived_project.semester_id
                      WHERE archived_pm.student_id = st.student_id
                        AND archived_semester.course_code = 'COMP4300'
                        AND LOWER(COALESCE(archived_project.status, '')) IN ('archived', 'archive')
                  )
                ORDER BY u.full_name
                """
            )
        students = cursor.fetchall()
        cursor.close()
        db.close()

        return jsonify({"students": students, "course": course}), 200

    except Exception as e:
        current_app.logger.error("Error in api_active_students: %s", e)
        return jsonify({"error": f"Database error: {e}"}), 500
