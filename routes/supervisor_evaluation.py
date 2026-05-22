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
