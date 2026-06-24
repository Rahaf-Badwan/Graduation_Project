from flask import Blueprint, jsonify, request, session

from auth import login_required
from db import get_db
from routes.appCoordinator import (
    _db_column_exists,
    _ensure_evaluation_schema,
    _evaluation_fetch_grade_rows,
    _evaluation_scores_from_grades,
    _json_safe_value,
    _safe_notification_type,
    _table_exists,
)

supervisor_evaluation_bp = Blueprint("supervisor_evaluation", __name__)


def _current_faculty(cursor):
    cursor.execute(
        """
        SELECT f.faculty_id, u.user_id, u.full_name
        FROM faculty f
        JOIN users u ON u.user_id = f.user_id
        WHERE u.user_id = %s
        LIMIT 1
        """,
        (session.get("user_id"),),
    )
    return cursor.fetchone()


def _notify_user(cursor, recipient_id, sender_id, title, message, course_scope="both", related_project_id=None):
    if not recipient_id:
        return False

    notification_type = _safe_notification_type(cursor, "system")

    if _db_column_exists(cursor, "notifications", "course_scope"):
        cursor.execute(
            """
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type, title, message,
                 course_scope, related_project_id, is_read)
            VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE)
            """,
            (recipient_id, sender_id, notification_type, title, message, course_scope, related_project_id),
        )
    else:
        cursor.execute(
            """
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type, title, message,
                 related_project_id, is_read)
            VALUES (%s, %s, %s, %s, %s, %s, FALSE)
            """,
            (recipient_id, sender_id, notification_type, title, message, related_project_id),
        )
    return True


def _evaluation_item_title(cursor, course_scope, reference_id):
    if course_scope == "graduation_project":
        cursor.execute(
            """
            SELECT p.title,
                   COALESCE(GROUP_CONCAT(DISTINCT u.full_name ORDER BY u.full_name SEPARATOR ', '), '') AS students
            FROM projects p
            LEFT JOIN project_members pm ON pm.project_id = p.project_id
            LEFT JOIN students st ON st.student_id = pm.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            WHERE p.project_id = %s
            GROUP BY p.project_id, p.title
            """,
            (reference_id,),
        )
    else:
        cursor.execute(
            """
            SELECT sec.section_name AS title,
                   COALESCE(GROUP_CONCAT(DISTINCT u.full_name ORDER BY u.full_name SEPARATOR ', '), '') AS students
            FROM student_distribution_sections sec
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            LEFT JOIN students st ON st.student_id = ss.student_id
            LEFT JOIN users u ON u.user_id = st.user_id
            WHERE sec.section_id = %s
            GROUP BY sec.section_id, sec.section_name
            """,
            (reference_id,),
        )
    return cursor.fetchone() or {"title": "Evaluation item", "students": ""}


def _component_label(component):
    return {
        "intro_report_reader": "Report reader / 40",
        "intro_coordinator": "Coordinator mark / 10",
        "intro_supervisor": "Supervisor mark / 10",
        "intro_discussion_member": "Discussion member / 10",
        "grad_report_reader": "Report reader / 30",
        "grad_supervisor": "Supervisor mark / 20",
        "grad_committee_member": "Committee member / 25",
    }.get(component, component.replace("_", " ").title())


@supervisor_evaluation_bp.route("/api/supervisor/evaluation/tasks", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_evaluation_tasks():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        faculty = _current_faculty(cursor)
        if not faculty:
            cursor.close()
            db.close()
            return jsonify({"tasks": [], "completed": [], "summary": {"pending": 0, "completed": 0}})

        cursor.execute(
            """
            SELECT egt.task_id, egt.course_scope, egt.reference_id, egt.component,
                   egt.max_mark, egt.mark, egt.notes, egt.is_submitted, egt.submitted_at,
                   ew.is_open, ew.opened_at, ew.closed_at
            FROM evaluation_grade_tasks egt
            JOIN evaluation_windows ew
              ON ew.course_scope = egt.course_scope
             AND ew.reference_id = egt.reference_id
            WHERE egt.evaluator_faculty_id = %s
            ORDER BY egt.is_submitted ASC, ew.opened_at DESC, egt.task_id DESC
            """,
            (faculty["faculty_id"],),
        )
        rows = cursor.fetchall()

        tasks = []
        completed = []
        for row in rows:
            item = _evaluation_item_title(cursor, row["course_scope"], row["reference_id"])
            payload = {
                "task_id": row["task_id"],
                "course_scope": row["course_scope"],
                "course_label": "COMP4200" if row["course_scope"] == "introduction" else "COMP4300",
                "reference_id": row["reference_id"],
                "title": item.get("title") or "Evaluation item",
                "students": item.get("students") or "",
                "component": row["component"],
                "component_label": _component_label(row["component"]),
                "max_mark": float(row.get("max_mark") or 0),
                "mark": None if row.get("mark") is None else float(row.get("mark") or 0),
                "notes": row.get("notes") or "",
                "is_submitted": bool(row.get("is_submitted")),
                "is_open": bool(row.get("is_open")),
                "opened_at": str(row.get("opened_at") or ""),
                "submitted_at": str(row.get("submitted_at") or ""),
            }
            if payload["is_submitted"]:
                completed.append(payload)
            elif payload["is_open"]:
                tasks.append(payload)

        cursor.close()
        db.close()
        return jsonify({
            "tasks": _json_safe_value(tasks),
            "completed": _json_safe_value(completed),
            "summary": {"pending": len(tasks), "completed": len(completed)},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@supervisor_evaluation_bp.route("/api/supervisor/evaluation/tasks/<int:task_id>/submit", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_submit_evaluation_task(task_id):
    data = request.get_json(silent=True) or {}
    mark = data.get("mark")
    notes = (data.get("notes") or "").strip() or None

    if mark is None or str(mark).strip() == "":
        return jsonify({"error": "Mark is required."}), 400

    try:
        mark = float(mark)
    except Exception:
        return jsonify({"error": "Mark must be a number."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)

        faculty = _current_faculty(cursor)
        if not faculty:
            cursor.close()
            db.close()
            return jsonify({"error": "Faculty record not found for this user."}), 404

        cursor.execute(
            """
            SELECT egt.task_id, egt.course_scope, egt.reference_id, egt.component,
                   egt.max_mark, egt.evaluator_faculty_id, ew.is_open, ew.opened_by
            FROM evaluation_grade_tasks egt
            JOIN evaluation_windows ew
              ON ew.course_scope = egt.course_scope
             AND ew.reference_id = egt.reference_id
            WHERE egt.task_id = %s
              AND egt.evaluator_faculty_id = %s
            LIMIT 1
            """,
            (task_id, faculty["faculty_id"]),
        )
        task = cursor.fetchone()

        if not task:
            cursor.close()
            db.close()
            return jsonify({"error": "Evaluation task not found."}), 404

        if not bool(task.get("is_open")):
            cursor.close()
            db.close()
            return jsonify({"error": "Grade entry is closed for this item."}), 400

        max_mark = float(task.get("max_mark") or 0)
        if mark < 0 or mark > max_mark:
            cursor.close()
            db.close()
            return jsonify({"error": f"Mark must be between 0 and {max_mark:g}."}), 400

        cursor.execute(
            """
            UPDATE evaluation_grade_tasks
            SET mark = %s,
                notes = %s,
                is_submitted = TRUE,
                submitted_at = NOW()
            WHERE task_id = %s
              AND evaluator_faculty_id = %s
            """,
            (mark, notes, task_id, faculty["faculty_id"]),
        )

        grades = _evaluation_fetch_grade_rows(cursor, task["course_scope"], task["reference_id"])
        scores = _evaluation_scores_from_grades(task["course_scope"], grades)
        item = _evaluation_item_title(cursor, task["course_scope"], task["reference_id"])

        label = "COMP4200" if task["course_scope"] == "introduction" else "COMP4300"
        title = f"✓ {label} Grade Submitted"
        message = (
            f"{faculty.get('full_name') or 'A doctor'} submitted {_component_label(task['component'])} "
            f"for {item.get('title') or 'the evaluation item'}. Mark: {mark:g}/{max_mark:g}."
        )

        notified = set()
        opened_by = task.get("opened_by")
        if opened_by and opened_by != session.get("user_id"):
            _notify_user(cursor, opened_by, session.get("user_id"), title, message, task["course_scope"], task["reference_id"] if task["course_scope"] == "graduation_project" else None)
            notified.add(opened_by)

        cursor.execute("SELECT user_id FROM users WHERE role = 'coordinator' AND is_active = TRUE")
        for row in cursor.fetchall():
            uid = row.get("user_id")
            if uid and uid not in notified and uid != session.get("user_id"):
                _notify_user(cursor, uid, session.get("user_id"), title, message, task["course_scope"], task["reference_id"] if task["course_scope"] == "graduation_project" else None)
                notified.add(uid)

        db.commit()
        cursor.close()
        db.close()
        return jsonify({
            "message": "Evaluation submitted successfully. The coordinator can now see the ✓ sign.",
            "scores": _json_safe_value(scores),
        })
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────
# Per-student supervisor/committee evaluation APIs
# These APIs are used by templates/supervisor/evaluation.html
# ─────────────────────────────────────────────────────────────

def _ensure_student_task_score_schema(cursor):
    """Create/repair the per-student marks table used by supervisor evaluation."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_student_task_scores (
            id INT PRIMARY KEY AUTO_INCREMENT,
            task_id INT NOT NULL,
            student_id INT NOT NULL,
            mark DECIMAL(6,2) NULL,
            notes TEXT NULL,
            is_submitted BOOLEAN NOT NULL DEFAULT FALSE,
            submitted_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_eval_task_student (task_id, student_id),
            INDEX idx_eval_task_student_task (task_id),
            INDEX idx_eval_task_student_student (student_id),
            FOREIGN KEY (task_id) REFERENCES evaluation_grade_tasks(task_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    # Safe repair for databases where the table was created by an older version.
    repair_columns = {
        "mark": "ALTER TABLE evaluation_student_task_scores ADD COLUMN mark DECIMAL(6,2) NULL AFTER student_id",
        "notes": "ALTER TABLE evaluation_student_task_scores ADD COLUMN notes TEXT NULL AFTER mark",
        "is_submitted": "ALTER TABLE evaluation_student_task_scores ADD COLUMN is_submitted BOOLEAN NOT NULL DEFAULT FALSE AFTER notes",
        "submitted_at": "ALTER TABLE evaluation_student_task_scores ADD COLUMN submitted_at DATETIME NULL AFTER is_submitted",
    }
    for column_name, sql in repair_columns.items():
        if not _db_column_exists(cursor, "evaluation_student_task_scores", column_name):
            cursor.execute(sql)


def _supervisor_eval_item_students(cursor, course_scope, reference_id):
    """Return students for one COMP4200 section or COMP4300 project."""
    reference_id = int(reference_id or 0)

    if course_scope == "graduation_project":
        if not _table_exists(cursor, "project_members"):
            return []
        cursor.execute(
            """
            SELECT DISTINCT
                st.student_id,
                u.user_id,
                u.full_name AS student_name,
                u.university_id,
                u.email
            FROM project_members pm
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE pm.project_id = %s
              AND u.role = 'student'
              AND u.is_active = TRUE
            ORDER BY pm.is_primary_contact DESC, u.full_name
            """,
            (reference_id,),
        )
    else:
        if not _table_exists(cursor, "section_students"):
            return []
        cursor.execute(
            """
            SELECT DISTINCT
                st.student_id,
                u.user_id,
                u.full_name AS student_name,
                u.university_id,
                u.email
            FROM section_students ss
            JOIN students st ON st.student_id = ss.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE ss.section_id = %s
              AND u.role = 'student'
              AND u.is_active = TRUE
            ORDER BY u.full_name
            """,
            (reference_id,),
        )

    return cursor.fetchall()


def _supervisor_student_absence_counts(cursor, course_scope, student_ids):
    """Return {student_id: absence_count} for the selected course scope.

    Attendance is course-level in APMS lectures. For evaluation, doctors see how
    many times each student was marked Absent in the course lectures.
    """
    student_ids = sorted({int(sid) for sid in student_ids if sid is not None})
    if not student_ids:
        return {}
    if not (_table_exists(cursor, "coordinator_lectures") and _table_exists(cursor, "coordinator_lecture_attendance")):
        return {sid: 0 for sid in student_ids}

    placeholders = ",".join(["%s"] * len(student_ids))
    cursor.execute(
        f"""
        SELECT cla.student_id, COUNT(*) AS absence_count
        FROM coordinator_lecture_attendance cla
        JOIN coordinator_lectures cl ON cl.lecture_id = cla.lecture_id
        WHERE cl.course_scope = %s
          AND cla.attendance_status = 'absent'
          AND cla.student_id IN ({placeholders})
        GROUP BY cla.student_id
        """,
        (course_scope, *student_ids),
    )
    counts = {sid: 0 for sid in student_ids}
    for row in cursor.fetchall():
        counts[int(row["student_id"])] = int(row.get("absence_count") or 0)
    return counts


@supervisor_evaluation_bp.route("/api/supervisor/evaluation/my-tasks", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_evaluation_my_tasks():
    """
    Return the logged-in doctor's evaluation tasks grouped by project/section.
    Each task contains the students, so the doctor can enter a separate mark
    for every student.
    """
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        _ensure_student_task_score_schema(cursor)
        db.commit()

        faculty = _current_faculty(cursor)
        if not faculty:
            cursor.close()
            db.close()
            return jsonify({"items": []})

        cursor.execute(
            """
            SELECT
                egt.task_id,
                egt.course_scope,
                egt.reference_id,
                egt.component,
                egt.max_mark,
                egt.mark,
                egt.notes,
                egt.is_submitted,
                egt.submitted_at,
                egt.created_at,
                COALESCE(ew.is_open, FALSE) AS is_open,
                ew.opened_at,
                ew.closed_at
            FROM evaluation_grade_tasks egt
            LEFT JOIN evaluation_windows ew
              ON ew.course_scope = egt.course_scope
             AND ew.reference_id = egt.reference_id
            WHERE egt.evaluator_faculty_id = %s
              AND (COALESCE(ew.is_open, FALSE) = TRUE OR egt.is_submitted = TRUE)
            ORDER BY COALESCE(ew.is_open, FALSE) DESC,
                     egt.is_submitted ASC,
                     egt.created_at DESC,
                     egt.task_id DESC
            """,
            (faculty["faculty_id"],),
        )
        rows = cursor.fetchall()

        grouped = {}
        for task in rows:
            course_scope = task.get("course_scope") or "introduction"
            reference_id = int(task.get("reference_id") or 0)
            group_key = (course_scope, reference_id)

            if group_key not in grouped:
                item = _evaluation_item_title(cursor, course_scope, reference_id)
                grouped[group_key] = {
                    "course_scope": course_scope,
                    "course_code": "COMP4200" if course_scope == "introduction" else "COMP4300",
                    "reference_id": reference_id,
                    "item_title": item.get("title") or "Evaluation item",
                    "students_text": item.get("students") or "",
                    "is_open": bool(task.get("is_open")),
                    "opened_at": str(task.get("opened_at") or ""),
                    "closed_at": str(task.get("closed_at") or ""),
                    "tasks": [],
                }

            task_id = int(task.get("task_id"))
            students = _supervisor_eval_item_students(cursor, course_scope, reference_id)
            absence_counts = _supervisor_student_absence_counts(
                cursor,
                course_scope,
                [student.get("student_id") for student in students],
            )

            cursor.execute(
                """
                SELECT student_id, mark, notes, is_submitted, submitted_at
                FROM evaluation_student_task_scores
                WHERE task_id = %s
                """,
                (task_id,),
            )
            saved_by_student = {
                int(row["student_id"]): row
                for row in cursor.fetchall()
            }

            student_marks = []
            for student in students:
                student_id = int(student["student_id"])
                saved = saved_by_student.get(student_id) or {}
                mark = saved.get("mark")
                submitted = bool(saved.get("is_submitted"))

                # Backward compatibility: if this task was submitted before
                # per-student marks existed, show the old shared mark for all students.
                if mark is None and bool(task.get("is_submitted")) and task.get("mark") is not None:
                    mark = task.get("mark")
                    submitted = True

                student_marks.append({
                    "student_id": student_id,
                    "user_id": student.get("user_id"),
                    "student_name": student.get("student_name"),
                    "university_id": student.get("university_id"),
                    "email": student.get("email"),
                    "absence_count": int(absence_counts.get(student_id, 0)),
                    "mark": None if mark is None else float(mark),
                    "notes": saved.get("notes") or "",
                    "is_submitted": submitted,
                    "submitted_at": str(saved.get("submitted_at") or ""),
                })

            grouped[group_key]["tasks"].append({
                "task_id": task_id,
                "component": task.get("component"),
                "component_label": _component_label(task.get("component")),
                "max_mark": float(task.get("max_mark") or 0),
                "mark": None if task.get("mark") is None else float(task.get("mark")),
                "notes": task.get("notes") or "",
                "is_submitted": bool(task.get("is_submitted")),
                "submitted_at": str(task.get("submitted_at") or ""),
                "student_marks": student_marks,
            })

        cursor.close()
        db.close()
        return jsonify(_json_safe_value({"items": list(grouped.values())}))

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@supervisor_evaluation_bp.route("/api/supervisor/evaluation/student-marks", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_evaluation_student_marks():
    """
    Save one doctor's marks for every student in one task.
    The task average is stored back in evaluation_grade_tasks.mark so older
    coordinator calculations still work, while the detailed per-student marks
    stay in evaluation_student_task_scores.
    """
    data = request.get_json(silent=True) or {}
    task_id = data.get("task_id")
    marks = data.get("marks") or []

    if not task_id:
        return jsonify({"error": "task_id is required."}), 400
    if not isinstance(marks, list) or not marks:
        return jsonify({"error": "Student marks are required."}), 400

    try:
        task_id = int(task_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid task_id."}), 400

    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_evaluation_schema(cursor)
        _ensure_student_task_score_schema(cursor)
        db.commit()

        faculty = _current_faculty(cursor)
        if not faculty:
            cursor.close()
            db.close()
            return jsonify({"error": "Faculty record not found for this user."}), 404

        cursor.execute(
            """
            SELECT
                egt.task_id,
                egt.course_scope,
                egt.reference_id,
                egt.component,
                egt.evaluator_faculty_id,
                egt.max_mark,
                COALESCE(ew.is_open, FALSE) AS is_open,
                ew.opened_by
            FROM evaluation_grade_tasks egt
            LEFT JOIN evaluation_windows ew
              ON ew.course_scope = egt.course_scope
             AND ew.reference_id = egt.reference_id
            WHERE egt.task_id = %s
              AND egt.evaluator_faculty_id = %s
            LIMIT 1
            """,
            (task_id, faculty["faculty_id"]),
        )
        task = cursor.fetchone()

        if not task:
            cursor.close()
            db.close()
            return jsonify({"error": "Evaluation task not found for your account."}), 404

        if not bool(task.get("is_open")):
            cursor.close()
            db.close()
            return jsonify({"error": "Grade entry is closed for this task."}), 400

        course_scope = task.get("course_scope") or "introduction"
        reference_id = int(task.get("reference_id") or 0)
        max_mark = float(task.get("max_mark") or 0)

        students = _supervisor_eval_item_students(cursor, course_scope, reference_id)
        valid_student_ids = {int(row["student_id"]) for row in students}
        if not valid_student_ids:
            cursor.close()
            db.close()
            return jsonify({"error": "No students found for this evaluation item."}), 400

        received = {}
        for row in marks:
            try:
                student_id = int(row.get("student_id"))
            except (TypeError, ValueError):
                cursor.close()
                db.close()
                return jsonify({"error": "Invalid student in submitted marks."}), 400

            if student_id not in valid_student_ids:
                cursor.close()
                db.close()
                return jsonify({"error": "A submitted student does not belong to this project/section."}), 400

            mark_raw = row.get("mark")
            if mark_raw is None or str(mark_raw).strip() == "":
                cursor.close()
                db.close()
                return jsonify({"error": "Please enter a mark for every student."}), 400

            try:
                mark = float(mark_raw)
            except (TypeError, ValueError):
                cursor.close()
                db.close()
                return jsonify({"error": "Every mark must be a valid number."}), 400

            if mark < 0 or mark > max_mark:
                cursor.close()
                db.close()
                return jsonify({"error": f"Marks must be between 0 and {max_mark:g}."}), 400

            received[student_id] = {
                "mark": mark,
                "notes": (row.get("notes") or "").strip() or None,
            }

        missing = sorted(valid_student_ids - set(received.keys()))
        if missing:
            cursor.close()
            db.close()
            return jsonify({"error": "Please enter a mark for every student before submitting."}), 400

        for student_id, row in received.items():
            cursor.execute(
                """
                INSERT INTO evaluation_student_task_scores
                    (task_id, student_id, mark, notes, is_submitted, submitted_at)
                VALUES (%s, %s, %s, %s, TRUE, NOW())
                ON DUPLICATE KEY UPDATE
                    mark = VALUES(mark),
                    notes = VALUES(notes),
                    is_submitted = TRUE,
                    submitted_at = NOW()
                """,
                (task_id, student_id, row["mark"], row["notes"]),
            )

        average_mark = round(sum(row["mark"] for row in received.values()) / len(received), 2)
        cursor.execute(
            """
            UPDATE evaluation_grade_tasks
            SET mark = %s,
                notes = %s,
                is_submitted = TRUE,
                submitted_at = NOW()
            WHERE task_id = %s
              AND evaluator_faculty_id = %s
            """,
            (
                average_mark,
                f"Per-student evaluation submitted for {len(received)} student(s).",
                task_id,
                faculty["faculty_id"],
            ),
        )

        grades = _evaluation_fetch_grade_rows(cursor, course_scope, reference_id)
        scores = _evaluation_scores_from_grades(course_scope, grades)

        item = _evaluation_item_title(cursor, course_scope, reference_id)
        label = "COMP4200" if course_scope == "introduction" else "COMP4300"
        title = f"✓ {label} Student Marks Submitted"
        message = (
            f"{faculty.get('full_name') or 'A doctor'} submitted per-student "
            f"{_component_label(task.get('component'))} marks for "
            f"{item.get('title') or 'the evaluation item'}. "
            f"Average: {average_mark:g}/{max_mark:g}."
        )

        notified = set()
        opened_by = task.get("opened_by")
        if opened_by and opened_by != session.get("user_id"):
            _notify_user(
                cursor,
                opened_by,
                session.get("user_id"),
                title,
                message,
                course_scope,
                reference_id if course_scope == "graduation_project" else None,
            )
            notified.add(opened_by)

        cursor.execute("SELECT user_id FROM users WHERE role = 'coordinator' AND is_active = TRUE")
        for row in cursor.fetchall():
            uid = row.get("user_id")
            if uid and uid not in notified and uid != session.get("user_id"):
                _notify_user(
                    cursor,
                    uid,
                    session.get("user_id"),
                    title,
                    message,
                    course_scope,
                    reference_id if course_scope == "graduation_project" else None,
                )
                notified.add(uid)

        db.commit()
        cursor.close()
        db.close()
        return jsonify(_json_safe_value({
            "message": "Student marks saved successfully. The coordinator can now see the submitted status.",
            "average_mark": average_mark,
            "scores": scores,
        }))

    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500

