import hashlib
import secrets
from datetime import datetime
from flask import (
    Blueprint,
    jsonify,
    render_template,
    request,
    session,
    Response,
    redirect,
    url_for,
)
import bcrypt
from werkzeug.utils import secure_filename
from db import get_db
from auth import login_required
from routes.supervisor_evaluation import supervisor_evaluation_bp
from routes.appCoordinator import (
    _get_or_create_intro_timeline,
    _insert_notification,
    _json_safe_value,
    _semester_for_course_scope,
    _table_exists,
)


general_supervisors_bp = Blueprint(
    "general_supervisors",
    __name__,
    url_prefix="/supervisor"
)


# Routes that must stay without the /supervisor prefix.
supervisor_api_bp = Blueprint("supervisor_api", __name__)
supervisor_api_bp.register_blueprint(supervisor_evaluation_bp)


def _clean_supervisor_timeline_items(items):
    clean = []
    for index, item in enumerate(items or [], start=1):
        title = (item.get("title") or "").strip()
        if not title:
            raise ValueError(f"Item #{index} must have a title.")
        start_date = (item.get("start_date") or "").strip() or None
        due_date = (item.get("due_date") or "").strip() or None
        start_time = due_time = None
        if start_date and "T" in start_date:
            start_date, start_time = start_date.split("T", 1)
            start_time = start_time[:5]
        if due_date and "T" in due_date:
            due_date, due_time = due_date.split("T", 1)
            due_time = due_time[:5]
        try:
            if start_date:
                datetime.strptime(start_date, "%Y-%m-%d")
            if due_date:
                datetime.strptime(due_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Item #{index} has an invalid date.") from exc
        clean.append(
            {
                "order": int(item.get("item_order") or index),
                "title": title,
                "description": (item.get("description") or "").strip() or None,
                "start_date": start_date,
                "start_time": start_time,
                "due_date": due_date,
                "due_time": due_time,
                "milestone_label": (item.get("milestone_label") or "").strip() or None,
                "submitted_to": "supervisor",
                "is_deadline": bool(item.get("is_deadline", True)),
            }
        )
    return clean


def _save_supervisor_timeline_items(cursor, timeline_id, items):
    cursor.execute(
        """SELECT item_id, item_order FROM comp4200_timeline_items
           WHERE timeline_id = %s AND COALESCE(is_archived, FALSE) = FALSE""",
        (timeline_id,),
    )
    existing = {row["item_order"]: row["item_id"] for row in cursor.fetchall()}
    new_orders = {item["order"] for item in items}
    for old_order, old_id in existing.items():
        if old_order in new_orders:
            continue
        has_submissions = False
        if _table_exists(cursor, "milestone_submissions"):
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM milestone_submissions WHERE item_id = %s",
                (old_id,),
            )
            has_submissions = int((cursor.fetchone() or {}).get("cnt") or 0) > 0
        if has_submissions:
            cursor.execute(
                "UPDATE comp4200_timeline_items SET is_archived = TRUE WHERE item_id = %s",
                (old_id,),
            )
        else:
            cursor.execute(
                "DELETE FROM comp4200_timeline_items WHERE item_id = %s", (old_id,)
            )

    for item in items:
        values = (
            item["order"], item["title"], item["description"], item["start_date"],
            item["start_time"], item["due_date"], item["due_time"],
            item["milestone_label"], item["is_deadline"],
        )
        if item["order"] in existing:
            cursor.execute(
                """UPDATE comp4200_timeline_items
                   SET item_order=%s, title=%s, description=%s, start_date=%s,
                       start_time=%s, due_date=%s, due_time=%s, milestone_label=%s,
                       submitted_to='supervisor', is_deadline=%s, is_archived=FALSE
                   WHERE item_id=%s""",
                values + (existing[item["order"]],),
            )
        else:
            cursor.execute(
                """INSERT INTO comp4200_timeline_items
                   (timeline_id,item_order,title,description,start_date,start_time,
                    due_date,due_time,milestone_label,submitted_to,is_deadline,is_archived)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'supervisor',%s,FALSE)""",
                (timeline_id,) + values,
            )


@supervisor_api_bp.route("/api/supervisor/intro-timeline", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_intro_timeline_get():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "introduction")
        if not semester:
            cursor.close(); db.close()
            return jsonify({"error": "No active COMP4200 semester found."}), 400
        payload = _intro_timeline_payload_for_supervisor(
            cursor, semester["semester_id"], session.get("user_id")
        )
        db.commit()
        cursor.close(); db.close()
        return jsonify(_json_safe_value(payload))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _intro_timeline_payload_for_supervisor(cursor, semester_id, user_id):
    timeline = _get_or_create_intro_timeline(
        cursor, semester_id, user_id, owner_role="supervisor"
    )
    cursor.execute(
        """SELECT item_id,item_order,title,description,start_date,start_time,due_date,
                  due_time,milestone_label,submitted_to,is_deadline
           FROM comp4200_timeline_items WHERE timeline_id=%s
           ORDER BY item_order,due_date,item_id""",
        (timeline["timeline_id"],),
    )
    items = cursor.fetchall()
    for item in items:
        item["is_deadline"] = bool(item.get("is_deadline"))
        for field, time_field in (("start_date", "start_time"), ("due_date", "due_time")):
            date_value = str(item.get(field) or "")
            time_value = (item.get(time_field) or "").strip()
            item[field] = f"{date_value}T{time_value}" if date_value and time_value else date_value
    timeline["is_published"] = bool(timeline.get("is_published"))
    return {"timeline": timeline, "items": items}


@supervisor_api_bp.route("/api/supervisor/intro-timeline", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_intro_timeline_save():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "My Students Timeline").strip()
    try:
        items = _clean_supervisor_timeline_items(data.get("items") or [])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not title or not items:
        return jsonify({"error": "Add a title and at least one timeline item."}), 400
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "introduction")
        if not semester:
            cursor.close(); db.close()
            return jsonify({"error": "No active COMP4200 semester found."}), 400
        timeline = _get_or_create_intro_timeline(
            cursor, semester["semester_id"], session.get("user_id"), "supervisor"
        )
        cursor.execute(
            "UPDATE comp4200_timelines SET title=%s,note=%s WHERE timeline_id=%s",
            (title, (data.get("note") or "").strip() or None, timeline["timeline_id"]),
        )
        _save_supervisor_timeline_items(cursor, timeline["timeline_id"], items)
        db.commit()
        payload = _intro_timeline_payload_for_supervisor(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.close(); db.close()
        return jsonify(_json_safe_value({"message": "Timeline saved successfully.", **payload}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@supervisor_api_bp.route("/api/supervisor/intro-timeline/publish", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_intro_timeline_publish():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "introduction")
        if not semester:
            cursor.close(); db.close()
            return jsonify({"error": "No active COMP4200 semester found."}), 400
        timeline = _get_or_create_intro_timeline(
            cursor, semester["semester_id"], session.get("user_id"), "supervisor"
        )
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM comp4200_timeline_items WHERE timeline_id=%s AND is_deadline=TRUE",
            (timeline["timeline_id"],),
        )
        if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
            cursor.close(); db.close()
            return jsonify({"error": "Save at least one deadline before publishing."}), 400
        cursor.execute(
            "UPDATE comp4200_timelines SET is_published=TRUE,published_at=NOW() WHERE timeline_id=%s",
            (timeline["timeline_id"],),
        )
        faculty_id = session.get("faculty_id")
        if not faculty_id:
            cursor.execute("SELECT faculty_id FROM faculty WHERE user_id=%s LIMIT 1", (session.get("user_id"),))
            faculty_id = (cursor.fetchone() or {}).get("faculty_id")
        recipients = []
        if faculty_id:
            cursor.execute(
                """SELECT DISTINCT u.user_id FROM projects p
                   JOIN project_members pm ON pm.project_id=p.project_id
                   JOIN students s ON s.student_id=pm.student_id
                   JOIN users u ON u.user_id=s.user_id
                   WHERE p.semester_id=%s AND p.supervisor_id=%s AND u.is_active=TRUE""",
                (semester["semester_id"], faculty_id),
            )
            recipients = [row["user_id"] for row in cursor.fetchall()]
        for user_id in recipients:
            _insert_notification(
                cursor, user_id, session.get("user_id"), "deadline_reminder",
                "Supervisor Timeline Published",
                "Your supervisor published an updated COMP4200 timeline. Open Student Timeline to view it.",
                None, "introduction",
            )
        db.commit()
        payload = _intro_timeline_payload_for_supervisor(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.close(); db.close()
        return jsonify(_json_safe_value({
            "message": f"Timeline published to your students. Notifications sent: {len(recipients)}.",
            **payload,
        }))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@supervisor_api_bp.route("/api/supervisor/grad-timeline", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_grad_timeline_get():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "graduation_project")
        if not semester:
            cursor.close(); db.close()
            return jsonify({"error": "No active COMP4300 semester found."}), 400
        payload = _intro_timeline_payload_for_supervisor(
            cursor, semester["semester_id"], session.get("user_id")
        )
        db.commit(); cursor.close(); db.close()
        return jsonify(_json_safe_value(payload))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@supervisor_api_bp.route("/api/supervisor/grad-timeline", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_grad_timeline_save():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Graduation Project Timeline").strip()
    try:
        items = _clean_supervisor_timeline_items(data.get("items") or [])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if not title or not items:
        return jsonify({"error": "Add a title and at least one timeline item."}), 400
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "graduation_project")
        if not semester:
            cursor.close(); db.close()
            return jsonify({"error": "No active COMP4300 semester found."}), 400
        timeline = _get_or_create_intro_timeline(
            cursor, semester["semester_id"], session.get("user_id"), "supervisor"
        )
        cursor.execute(
            "UPDATE comp4200_timelines SET title=%s,note=%s WHERE timeline_id=%s",
            (title, (data.get("note") or "").strip() or None, timeline["timeline_id"]),
        )
        _save_supervisor_timeline_items(cursor, timeline["timeline_id"], items)
        db.commit()
        payload = _intro_timeline_payload_for_supervisor(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.close(); db.close()
        return jsonify(_json_safe_value({"message": "COMP4300 timeline saved successfully.", **payload}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@supervisor_api_bp.route("/api/supervisor/grad-timeline/publish", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_grad_timeline_publish():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        semester = _semester_for_course_scope(cursor, "graduation_project")
        if not semester:
            cursor.close(); db.close()
            return jsonify({"error": "No active COMP4300 semester found."}), 400
        timeline = _get_or_create_intro_timeline(
            cursor, semester["semester_id"], session.get("user_id"), "supervisor"
        )
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM comp4200_timeline_items WHERE timeline_id=%s AND is_deadline=TRUE",
            (timeline["timeline_id"],),
        )
        if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
            cursor.close(); db.close()
            return jsonify({"error": "Save at least one deadline before publishing."}), 400
        cursor.execute(
            "UPDATE comp4200_timelines SET is_published=TRUE,published_at=NOW() WHERE timeline_id=%s",
            (timeline["timeline_id"],),
        )
        faculty_id = _current_supervisor_faculty_id(cursor)
        recipients = []
        if faculty_id:
            cursor.execute(
                """SELECT DISTINCT u.user_id FROM projects p
                   JOIN project_members pm ON pm.project_id=p.project_id
                   JOIN students st ON st.student_id=pm.student_id
                   JOIN users u ON u.user_id=st.user_id
                   WHERE p.semester_id=%s AND p.supervisor_id=%s AND u.is_active=TRUE""",
                (semester["semester_id"], faculty_id),
            )
            recipients = [row["user_id"] for row in cursor.fetchall()]
        for user_id in recipients:
            _insert_notification(
                cursor, user_id, session.get("user_id"), "deadline_reminder",
                "Supervisor COMP4300 Timeline Published",
                "Your supervisor published an updated COMP4300 timeline. Open Student Timeline to view it.",
                None, "graduation_project",
            )
        db.commit()
        payload = _intro_timeline_payload_for_supervisor(
            cursor, semester["semester_id"], session.get("user_id")
        )
        cursor.close(); db.close()
        return jsonify(_json_safe_value({
            "message": f"COMP4300 timeline published. Notifications sent: {len(recipients)}.",
            **payload,
        }))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ============================================================
# Supervisor lectures (scoped to the supervisor's own groups)
# ============================================================

def _ensure_supervisor_lecture_tables(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS supervisor_lectures (
            lecture_id INT PRIMARY KEY AUTO_INCREMENT,
            semester_id INT NULL,
            supervisor_id INT NOT NULL,
            course_scope ENUM('introduction','graduation_project') NOT NULL DEFAULT 'introduction',
            target_kind ENUM('all','section','project') NOT NULL DEFAULT 'all',
            target_id INT NULL,
            title VARCHAR(200) NOT NULL,
            description TEXT NULL,
            lecture_date DATE NULL,
            lecture_time TIME NULL,
            week_label VARCHAR(80) NULL,
            status ENUM('scheduled','completed','cancelled') NOT NULL DEFAULT 'scheduled',
            created_by INT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_supervisor_lectures_owner (supervisor_id, semester_id, course_scope),
            FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE SET NULL,
            FOREIGN KEY (supervisor_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    if not _supervisor_db_column_exists(cursor, "supervisor_lectures", "lecture_time"):
        cursor.execute(
            "ALTER TABLE supervisor_lectures ADD COLUMN lecture_time TIME NULL AFTER lecture_date"
        )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS supervisor_lecture_recipients (
            lecture_id INT NOT NULL,
            student_id INT NOT NULL,
            notified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lecture_id, student_id),
            FOREIGN KEY (lecture_id) REFERENCES supervisor_lectures(lecture_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS supervisor_lecture_attendance (
            lecture_id INT NOT NULL,
            student_id INT NOT NULL,
            attendance_status ENUM('present','absent') NOT NULL,
            marked_by INT NULL,
            marked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (lecture_id, student_id),
            FOREIGN KEY (lecture_id) REFERENCES supervisor_lectures(lecture_id) ON DELETE CASCADE,
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            FOREIGN KEY (marked_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _supervisor_lecture_targets(cursor, faculty_id):
    targets = {"introduction": [], "graduation_project": []}
    if _supervisor_table_exists(cursor, "student_distribution_sections"):
        cursor.execute(
            """
            SELECT CONCAT('s:', sec.section_id) AS target_key,
                   sec.section_id AS target_id,
                   sec.section_name AS target_name,
                   COUNT(DISTINCT ss.student_id) AS students_count
            FROM student_distribution_sections sec
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            WHERE sec.supervisor_id = %s
            GROUP BY sec.section_id, sec.section_name
            ORDER BY sec.section_name, sec.section_id
            """,
            (faculty_id,),
        )
        targets["introduction"] = cursor.fetchall()
    cursor.execute(
        """
        SELECT CONCAT('p:', p.project_id) AS target_key,
               p.project_id AS target_id,
               COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS target_name,
               COUNT(DISTINCT pm.student_id) AS students_count
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        WHERE p.supervisor_id = %s AND sem.course_code = 'COMP4300'
        GROUP BY p.project_id, p.title
        ORDER BY p.title, p.project_id
        """,
        (faculty_id,),
    )
    targets["graduation_project"] = cursor.fetchall()
    return targets


def _supervisor_lecture_recipients(cursor, faculty_id, course_scope, target_kind, target_id, semester_id):
    if course_scope == "graduation_project":
        params = [faculty_id, semester_id]
        target_sql = ""
        if target_kind == "project":
            target_sql = "AND p.project_id = %s"
            params.append(target_id)
        cursor.execute(
            f"""
            SELECT DISTINCT u.user_id
            FROM projects p
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE p.supervisor_id = %s AND p.semester_id = %s
              AND u.is_active = TRUE {target_sql}
            """,
            tuple(params),
        )
    else:
        params = [faculty_id]
        target_sql = ""
        if target_kind == "section":
            target_sql = "AND sec.section_id = %s"
            params.append(target_id)
        cursor.execute(
            f"""
            SELECT DISTINCT u.user_id
            FROM student_distribution_sections sec
            JOIN section_students ss ON ss.section_id = sec.section_id
            JOIN students st ON st.student_id = ss.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE sec.supervisor_id = %s AND u.is_active = TRUE {target_sql}
            """,
            tuple(params),
        )
    return [row["user_id"] for row in cursor.fetchall()]


def _parse_supervisor_lecture_payload(data, course_scope):
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("Lecture title is required.")
    status = data.get("status") if data.get("status") in {"scheduled", "completed", "cancelled"} else "scheduled"
    lecture_date = (data.get("lecture_date") or "").strip() or None
    if not lecture_date:
        raise ValueError("Lecture date is required before sending the lecture.")
    try:
        datetime.strptime(lecture_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Lecture date is invalid.") from exc
    lecture_time = (data.get("lecture_time") or "").strip()
    if not lecture_time:
        raise ValueError("Lecture time is required before sending the lecture.")
    try:
        datetime.strptime(lecture_time, "%H:%M")
    except ValueError as exc:
        raise ValueError("Lecture time is invalid.") from exc
    target_key = (data.get("target_key") or "all").strip().lower()
    target_kind, target_id = "all", None
    if target_key != "all":
        expected_prefix = "p:" if course_scope == "graduation_project" else "s:"
        if not target_key.startswith(expected_prefix):
            raise ValueError("Choose a valid section or All Sections.")
        try:
            target_id = int(target_key.split(":", 1)[1])
        except (TypeError, ValueError) as exc:
            raise ValueError("Choose a valid section.") from exc
        target_kind = "project" if course_scope == "graduation_project" else "section"
    return {
        "title": title,
        "description": (data.get("description") or "").strip() or None,
        "lecture_date": lecture_date,
        "lecture_time": lecture_time,
        "week_label": (data.get("week_label") or "").strip() or None,
        "status": status,
        "target_kind": target_kind,
        "target_id": target_id,
    }


def _validate_supervisor_lecture_target(cursor, faculty_id, course_scope, target_kind, target_id):
    if target_kind == "all":
        return True
    if course_scope == "graduation_project":
        cursor.execute("SELECT 1 FROM projects WHERE project_id=%s AND supervisor_id=%s", (target_id, faculty_id))
    else:
        cursor.execute("SELECT 1 FROM student_distribution_sections WHERE section_id=%s AND supervisor_id=%s", (target_id, faculty_id))
    return bool(cursor.fetchone())


def _ensure_supervisor_lecture_attendance_defaults(cursor, lecture_id, marked_by=None):
    """Create Present rows for every notified student that has no attendance row yet."""
    cursor.execute(
        """
        INSERT IGNORE INTO supervisor_lecture_attendance
            (lecture_id, student_id, attendance_status, marked_by, marked_at)
        SELECT slr.lecture_id, slr.student_id, 'present', %s, NOW()
        FROM supervisor_lecture_recipients slr
        WHERE slr.lecture_id = %s
        """,
        (marked_by, lecture_id),
    )


def _snapshot_supervisor_lecture_recipients(cursor, lecture_id, user_ids):
    """Keep the exact student audience that received this lecture."""
    cursor.execute(
        "DELETE FROM supervisor_lecture_recipients WHERE lecture_id = %s",
        (lecture_id,),
    )
    if not user_ids:
        return
    placeholders = ",".join(["%s"] * len(user_ids))
    cursor.execute(
        f"""
        INSERT IGNORE INTO supervisor_lecture_recipients (lecture_id, student_id)
        SELECT %s, st.student_id
        FROM students st
        WHERE st.user_id IN ({placeholders})
        """,
        (lecture_id, *user_ids),
    )
    cursor.execute(
        """
        DELETE sla
        FROM supervisor_lecture_attendance sla
        LEFT JOIN supervisor_lecture_recipients slr
          ON slr.lecture_id = sla.lecture_id AND slr.student_id = sla.student_id
        WHERE sla.lecture_id = %s AND slr.student_id IS NULL
        """,
        (lecture_id,),
    )
    _ensure_supervisor_lecture_attendance_defaults(cursor, lecture_id, session.get("user_id"))


def _notify_supervisor_lecture(cursor, faculty_id, semester_id, scope, lecture, action, lecture_id):
    recipients = _supervisor_lecture_recipients(
        cursor, faculty_id, scope, lecture["target_kind"], lecture.get("target_id"), semester_id
    )
    course_label = "COMP4300" if scope == "graduation_project" else "COMP4200"
    course_name = "Graduation Project" if scope == "graduation_project" else "Project Introduction"
    _snapshot_supervisor_lecture_recipients(cursor, lecture_id, recipients)
    status_label = str(lecture.get("status") or "scheduled").replace("_", " ").title()
    message = "\n".join(
        (
            f"Lecture: {lecture['title']}",
            f"Course: {course_label} — {course_name}",
            f"Date: {lecture.get('lecture_date') or 'To be announced'}",
            f"Time: {lecture.get('lecture_time') or 'To be announced'}",
            f"Week: {lecture.get('week_label') or 'Not specified'}",
            f"Status: {status_label}",
            f"Details: {lecture.get('description') or 'No additional details.'}",
        )
    )
    for user_id in recipients:
        _insert_notification(
            cursor, user_id, session.get("user_id"), "system",
            f"Supervisor Lecture {action.title()}: {lecture['title']}",
            message, None, scope,
        )
    return len(recipients)


@supervisor_api_bp.route("/api/supervisor/lectures-data", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_lectures_data():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_lecture_tables(cursor)
        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            cursor.close(); db.close()
            return jsonify({"error": "Supervisor faculty profile was not found."}), 404
        targets = _supervisor_lecture_targets(cursor, faculty_id)
        cursor.execute(
            """
            SELECT sl.*,
                   CASE
                     WHEN sl.target_kind='all' THEN 'All Sections'
                     WHEN sl.target_kind='section' THEN COALESCE(sec.section_name, 'Section')
                     ELSE COALESCE(p.title, 'Project')
                   END AS target_name
            FROM supervisor_lectures sl
            LEFT JOIN student_distribution_sections sec
              ON sl.target_kind='section' AND sec.section_id=sl.target_id
            LEFT JOIN projects p
              ON sl.target_kind='project' AND p.project_id=sl.target_id
            WHERE sl.supervisor_id=%s
            ORDER BY sl.course_scope, COALESCE(sl.lecture_date, '9999-12-31'), sl.lecture_id
            """,
            (faculty_id,),
        )
        lectures = {"introduction": [], "graduation_project": []}
        for row in cursor.fetchall():
            for key, value in list(row.items()):
                if key == "lecture_time" and value is not None:
                    row[key] = str(value)[:5]
                elif hasattr(value, "isoformat"):
                    row[key] = value.isoformat()
            row["target_key"] = "all" if row["target_kind"] == "all" else f"{'p' if row['target_kind']=='project' else 's'}:{row['target_id']}"
            lectures[row["course_scope"]].append(row)
        db.commit(); cursor.close(); db.close()
        return jsonify({"lectures": lectures, "targets": targets})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@supervisor_api_bp.route("/api/supervisor/lectures", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_create_lecture():
    data = request.get_json(silent=True) or {}
    scope = data.get("course_scope") if data.get("course_scope") in {"introduction", "graduation_project"} else "introduction"
    try:
        lecture = _parse_supervisor_lecture_payload(data, scope)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_lecture_tables(cursor)
        faculty_id = _current_supervisor_faculty_id(cursor)
        semester = _supervisor_active_semester_by_course(cursor, "COMP4300" if scope == "graduation_project" else "COMP4200")
        if not faculty_id or not semester:
            cursor.close(); db.close()
            return jsonify({"error": "Supervisor profile or active semester was not found."}), 400
        if not _validate_supervisor_lecture_target(cursor, faculty_id, scope, lecture["target_kind"], lecture["target_id"]):
            cursor.close(); db.close()
            return jsonify({"error": "You can only select sections assigned to you."}), 403
        cursor.execute(
            """INSERT INTO supervisor_lectures
               (semester_id,supervisor_id,course_scope,target_kind,target_id,title,description,
                lecture_date,lecture_time,week_label,status,created_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (semester["semester_id"], faculty_id, scope, lecture["target_kind"], lecture["target_id"],
             lecture["title"], lecture["description"], lecture["lecture_date"], lecture["lecture_time"], lecture["week_label"],
             lecture["status"], session.get("user_id")),
        )
        lecture_id = cursor.lastrowid
        sent = _notify_supervisor_lecture(cursor, faculty_id, semester["semester_id"], scope, lecture, "posted", lecture_id)
        db.commit(); cursor.close(); db.close()
        return jsonify({"message": f"Lecture saved. {sent} student notification(s) sent."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@supervisor_api_bp.route("/api/supervisor/lectures/<int:lecture_id>", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_update_lecture(lecture_id):
    data = request.get_json(silent=True) or {}
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_lecture_tables(cursor)
        faculty_id = _current_supervisor_faculty_id(cursor)
        cursor.execute("SELECT * FROM supervisor_lectures WHERE lecture_id=%s AND supervisor_id=%s", (lecture_id, faculty_id))
        current = cursor.fetchone()
        if not current:
            cursor.close(); db.close()
            return jsonify({"error": "Lecture not found."}), 404
        scope = current["course_scope"]
        try:
            lecture = _parse_supervisor_lecture_payload(data, scope)
        except ValueError as exc:
            cursor.close(); db.close()
            return jsonify({"error": str(exc)}), 400
        if not _validate_supervisor_lecture_target(cursor, faculty_id, scope, lecture["target_kind"], lecture["target_id"]):
            cursor.close(); db.close()
            return jsonify({"error": "You can only select sections assigned to you."}), 403
        cursor.execute(
            """UPDATE supervisor_lectures SET target_kind=%s,target_id=%s,title=%s,description=%s,
                      lecture_date=%s,lecture_time=%s,week_label=%s,status=%s WHERE lecture_id=%s AND supervisor_id=%s""",
            (lecture["target_kind"], lecture["target_id"], lecture["title"], lecture["description"],
             lecture["lecture_date"], lecture["lecture_time"], lecture["week_label"], lecture["status"], lecture_id, faculty_id),
        )
        sent = _notify_supervisor_lecture(cursor, faculty_id, current["semester_id"], scope, lecture, "updated", lecture_id)
        db.commit(); cursor.close(); db.close()
        return jsonify({"message": f"Lecture updated. {sent} student notification(s) sent."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _attendance_lecture(cursor, lecture_id, faculty_id):
    cursor.execute(
        """
        SELECT lecture_id, semester_id, supervisor_id, course_scope,
               target_kind, target_id, title, lecture_date, lecture_time,
               CASE
                   WHEN lecture_time IS NULL THEN lecture_date < CURDATE()
                   ELSE TIMESTAMP(lecture_date, lecture_time) <= NOW()
               END AS has_started
        FROM supervisor_lectures
        WHERE lecture_id = %s AND supervisor_id = %s
        LIMIT 1
        """,
        (lecture_id, faculty_id),
    )
    return cursor.fetchone()


def _ensure_lecture_recipient_snapshot(cursor, lecture):
    cursor.execute(
        "SELECT COUNT(*) AS total FROM supervisor_lecture_recipients WHERE lecture_id = %s",
        (lecture["lecture_id"],),
    )
    if int((cursor.fetchone() or {}).get("total") or 0) > 0:
        return
    recipients = _supervisor_lecture_recipients(
        cursor,
        lecture["supervisor_id"],
        lecture["course_scope"],
        lecture["target_kind"],
        lecture.get("target_id"),
        lecture["semester_id"],
    )
    _snapshot_supervisor_lecture_recipients(
        cursor, lecture["lecture_id"], recipients
    )


@supervisor_api_bp.route("/api/supervisor/lectures/<int:lecture_id>/attendance", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_lecture_attendance(lecture_id):
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        _ensure_supervisor_lecture_tables(cursor)
        faculty_id = _current_supervisor_faculty_id(cursor)
        lecture = _attendance_lecture(cursor, lecture_id, faculty_id)
        if not lecture:
            return jsonify({"error": "Lecture not found."}), 404
        if not lecture.get("has_started"):
            return jsonify({"error": "Attendance opens after the lecture date and time."}), 400
        _ensure_lecture_recipient_snapshot(cursor, lecture)
        _ensure_supervisor_lecture_attendance_defaults(cursor, lecture_id, session.get("user_id"))
        cursor.execute(
            """
            SELECT st.student_id, u.full_name, u.university_id,
                   COALESCE(sla.attendance_status, 'present') AS attendance_status
            FROM supervisor_lecture_recipients slr
            JOIN students st ON st.student_id = slr.student_id
            JOIN users u ON u.user_id = st.user_id
            LEFT JOIN supervisor_lecture_attendance sla
              ON sla.lecture_id = slr.lecture_id
             AND sla.student_id = slr.student_id
            WHERE slr.lecture_id = %s
            ORDER BY u.full_name
            """,
            (lecture_id,),
        )
        students = cursor.fetchall()
        db.commit()
        return jsonify({"lecture_id": lecture_id, "title": lecture["title"], "students": students})
    except Exception as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        cursor.close(); db.close()


@supervisor_api_bp.route("/api/supervisor/lectures/<int:lecture_id>/attendance", methods=["POST"])
@login_required(role="supervisor")
def api_save_supervisor_lecture_attendance(lecture_id):
    data = request.get_json(silent=True) or {}
    attendance = data.get("attendance") or []
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        _ensure_supervisor_lecture_tables(cursor)
        faculty_id = _current_supervisor_faculty_id(cursor)
        lecture = _attendance_lecture(cursor, lecture_id, faculty_id)
        if not lecture:
            return jsonify({"error": "Lecture not found."}), 404
        if not lecture.get("has_started"):
            return jsonify({"error": "Attendance opens after the lecture date and time."}), 400
        _ensure_lecture_recipient_snapshot(cursor, lecture)
        _ensure_supervisor_lecture_attendance_defaults(cursor, lecture_id, session.get("user_id"))
        cursor.execute(
            "SELECT student_id FROM supervisor_lecture_recipients WHERE lecture_id = %s",
            (lecture_id,),
        )
        allowed_ids = {int(row["student_id"]) for row in cursor.fetchall()}
        cleaned = []
        for row in attendance:
            try:
                student_id = int(row.get("student_id"))
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid student in attendance list."}), 400
            status = (row.get("status") or "").strip().lower()
            if student_id not in allowed_ids or status not in {"present", "absent"}:
                return jsonify({"error": "Attendance can only be recorded for notified students."}), 400
            cleaned.append((student_id, status))
        if allowed_ids and {student_id for student_id, _ in cleaned} != allowed_ids:
            return jsonify({"error": "Mark every notified student as present or absent."}), 400
        for student_id, status in cleaned:
            cursor.execute(
                """
                INSERT INTO supervisor_lecture_attendance
                    (lecture_id, student_id, attendance_status, marked_by, marked_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    attendance_status = VALUES(attendance_status),
                    marked_by = VALUES(marked_by),
                    marked_at = NOW()
                """,
                (lecture_id, student_id, status, session.get("user_id")),
            )
        db.commit()
        return jsonify({"message": f"Attendance saved for {len(cleaned)} student(s)."})
    except Exception as exc:
        db.rollback()
        return jsonify({"error": str(exc)}), 500
    finally:
        cursor.close(); db.close()


@supervisor_api_bp.route("/api/supervisor/lectures/reset-scheduled", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_reset_scheduled_lectures():
    data = request.get_json(silent=True) or {}
    scope = data.get("course_scope") if data.get("course_scope") in {"introduction", "graduation_project"} else "introduction"
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        _ensure_supervisor_lecture_tables(cursor)
        faculty_id = _current_supervisor_faculty_id(cursor)
        cursor.execute(
            "DELETE FROM supervisor_lectures WHERE supervisor_id=%s AND course_scope=%s AND status='scheduled'",
            (faculty_id, scope),
        )
        deleted = cursor.rowcount
        db.commit(); cursor.close(); db.close()
        return jsonify({"message": f"{deleted} scheduled lecture(s) removed."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500



# ─── Dashboard ──────────────────────────────────────────────
@general_supervisors_bp.route("/")
@general_supervisors_bp.route("/dashboard")
@login_required(role="supervisor")
def dashboard():
    return render_template("supervisor/index.html")


SUPERVISOR_PAGES = {
    "dashboard": "supervisor/index.html",
    "mystudents": "supervisor/mystudents.html",
    "progress": "supervisor/progress.html",
    "timeline": "supervisor/progress.html",
    "lectures": "supervisor/lectures.html",
    "feedback": "supervisor/feedback.html",
    "evaluation": "supervisor/evaluation.html",
    "hours": "supervisor/hours.html",
    "search": "shared/archive_search.html",
    "notifs": "supervisor/notifs.html",
    "ai": "shared/ai.html",
    "profile": "supervisor/profile.html",
}


@general_supervisors_bp.route("/<page>")
@login_required(role="supervisor")
def supervisor_subpage(page):
    template = SUPERVISOR_PAGES.get(page)
    if not template:
        return redirect(url_for("general_supervisors.dashboard"))
    if page in {"search", "ai"}:
        return render_template(template, base_template="supervisor/base.html")
    return render_template(template)


# ─── Search ─────────────────────────────────────────────────
@general_supervisors_bp.route("/search")
@login_required(role="supervisor")
def search():
    return render_template("shared/archive_search.html", base_template="supervisor/base.html")


# ─── Notifications Page ─────────────────────────────────────
@general_supervisors_bp.route("/notifs")
@login_required(role="supervisor")
def notifs():
    return render_template("supervisor/notifs.html")


# ─── AI Assistant ───────────────────────────────────────────
@general_supervisors_bp.route("/ai")
@login_required(role="supervisor")
def ai():
    return render_template("shared/ai.html", base_template="supervisor/base.html")


# ─── Profile ────────────────────────────────────────────────
def _load_supervisor_profile_user(include_password=False):
    """Load one complete supervisor profile for direct or switched sessions."""
    db = None
    cursor = None
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        password_field = ", u.password_hash" if include_password else ""
        faculty_id = session.get("faculty_id")
        if faculty_id:
            cursor.execute(
                f"""
                SELECT u.user_id, u.university_id, u.full_name, u.email,
                       u.avatar_initials, f.faculty_id, f.specialization,
                       f.years_experience, f.title, f.office_number
                       {password_field}
                FROM users u
                JOIN faculty f ON f.user_id = u.user_id
                WHERE f.faculty_id = %s
                LIMIT 1
                """,
                (faculty_id,),
            )
        else:
            cursor.execute(
                f"""
                SELECT u.user_id, u.university_id, u.full_name, u.email,
                       u.avatar_initials, f.faculty_id, f.specialization,
                       f.years_experience, f.title, f.office_number
                       {password_field}
                FROM users u
                LEFT JOIN faculty f ON f.user_id = u.user_id
                WHERE u.user_id = %s
                LIMIT 1
                """,
                (session.get("user_id"),),
            )
        user = cursor.fetchone()
        if not user:
            return None

        title = (user.get("title") or "Dr.").strip()
        full_name = (user.get("full_name") or "").strip()
        if full_name.lower().startswith(f"{title.lower()} "):
            user["display_name"] = full_name
        else:
            user["display_name"] = f"{title} {full_name}".strip()
        if not user.get("avatar_initials"):
            parts = [part for part in full_name.replace("Dr.", "").split() if part]
            user["avatar_initials"] = "".join(part[0].upper() for part in parts[:2])
        return user
    finally:
        if cursor:
            cursor.close()
        if db:
            db.close()


@general_supervisors_bp.route("/profile")
@login_required(role="supervisor")
def profile():
    try:
        user = _load_supervisor_profile_user()
    except Exception:
        user = None

    return render_template(
        "supervisor/profile.html",
        user=user,
        pwd_error=None,
        pwd_success=None
    )


# ─── Change Password ────────────────────────────────────────
@general_supervisors_bp.route("/profile/change-password", methods=["POST"])
@login_required(role="supervisor")
def change_password():
    current_pwd = request.form.get("current_password", "").strip()
    new_pwd = request.form.get("new_password", "").strip()
    confirm_pwd = request.form.get("confirm_password", "").strip()

    try:
        user = _load_supervisor_profile_user(include_password=True)
    except Exception:
        user = None

    if not current_pwd or not new_pwd or not confirm_pwd:
        return render_template("supervisor/profile.html", user=user, pwd_error="Fill all fields", pwd_success=None)

    if len(new_pwd) < 8:
        return render_template("supervisor/profile.html", user=user, pwd_error="Password too short", pwd_success=None)

    if new_pwd != confirm_pwd:
        return render_template("supervisor/profile.html", user=user, pwd_error="Passwords do not match", pwd_success=None)

    if not user or not bcrypt.checkpw(current_pwd.encode(), user["password_hash"].encode()):
        return render_template("supervisor/profile.html", user=user, pwd_error="Wrong current password", pwd_success=None)

    try:
        hashed = bcrypt.hashpw(new_pwd.encode(), bcrypt.gensalt()).decode()
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE user_id = %s",
            (hashed, user["user_id"]),
        )
        db.commit()
        cursor.close()
        db.close()

        return render_template(
            "supervisor/profile.html",
            user=user,
            pwd_error=None,
            pwd_success="Password updated successfully!"
        )
    except Exception as e:
        return render_template("supervisor/profile.html", user=user, pwd_error=str(e), pwd_success=None)


# ============================================================
# Helpers (Supervisor-safe version)
# ============================================================

def _supervisor_table_exists(cursor, table):
    cursor.execute(
        "SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME=%s",
        (table,),
    )
    return int(cursor.fetchone()["cnt"]) > 0


def _supervisor_db_column_exists(cursor, table, column):
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME=%s
          AND COLUMN_NAME=%s
        """,
        (table, column),
    )
    return int(cursor.fetchone()["cnt"]) > 0


# ============================================================
# Notifications / Messaging
# ============================================================

def _ensure_supervisor_notification_schema(cursor):
    if _supervisor_table_exists(cursor, "notifications"):
        if not _supervisor_db_column_exists(cursor, "notifications", "course_scope"):
            cursor.execute("""
                ALTER TABLE notifications
                ADD COLUMN course_scope ENUM('introduction','graduation_project','both')
                NOT NULL DEFAULT 'both'
            """)

        if not _supervisor_db_column_exists(cursor, "notifications", "can_reply"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN can_reply TINYINT(1) NOT NULL DEFAULT 0 AFTER is_read")

        if not _supervisor_db_column_exists(cursor, "notifications", "message_origin"):
            cursor.execute(
                "ALTER TABLE notifications ADD COLUMN message_origin ENUM('dynamic','manual','reply') NOT NULL DEFAULT 'dynamic' AFTER can_reply"
            )

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_name"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_name VARCHAR(255) NULL")

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_mime"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_mime VARCHAR(120) NULL")

        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_data"):
            cursor.execute("ALTER TABLE notifications ADD COLUMN attachment_data LONGBLOB NULL")


def _notification_attachment_fields(cursor):
    if _supervisor_db_column_exists(cursor, "notifications", "attachment_name"):
        return "n.attachment_name, n.attachment_mime, n.attachment_data IS NOT NULL AS has_attachment"
    return "NULL AS attachment_name, NULL AS attachment_mime, 0 AS has_attachment"


def _row_to_json(row):
    if not row:
        return row
    r = dict(row)
    r["is_read"] = bool(r.get("is_read"))
    r["course_scope"] = r.get("course_scope") or "both"
    r["created_at"] = str(r.get("created_at")) if r.get("created_at") else None
    r["has_attachment"] = bool(r.get("has_attachment"))
    r["can_reply"] = (
        r.get("message_origin") in {"manual", "reply"}
        and bool(r.get("can_reply", False))
    )
    if not r["has_attachment"]:
        r["attachment_name"] = None
        r["attachment_mime"] = None
    r.pop("attachment_data", None)
    return r


def _supervisor_notification_enum_values(cursor):
    cursor.execute(
        """
        SELECT COLUMN_TYPE AS column_type
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'notifications'
          AND COLUMN_NAME = 'notification_type'
        LIMIT 1
        """
    )
    row = cursor.fetchone() or {}
    column_type = str(row.get("column_type") or row.get("COLUMN_TYPE") or "")
    if not column_type.lower().startswith("enum("):
        return []

    raw = column_type[5:-1]
    values, current, in_quote = [], "", False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == "'":
            if in_quote and i + 1 < len(raw) and raw[i + 1] == "'":
                current += "'"
                i += 1
            else:
                in_quote = not in_quote
        elif ch == "," and not in_quote:
            values.append(current)
            current = ""
        else:
            current += ch
        i += 1
    if current or raw:
        values.append(current)
    return [v for v in values if v]


def _supervisor_safe_notification_type(cursor, requested_type="system"):
    allowed = _supervisor_notification_enum_values(cursor)
    if not allowed:
        return requested_type or "system"
    if requested_type in allowed:
        return requested_type
    for fallback in ("system", "info", "message", "deadline_reminder", "urgent_alert", "alert"):
        if fallback in allowed:
            return fallback
    return allowed[0]


def _supervisor_active_semester_by_course(cursor, course_code):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE is_active = TRUE AND course_code = %s
        ORDER BY semester_id DESC
        LIMIT 1
        """,
        (course_code,),
    )
    return cursor.fetchone()


def _supervisor_course_from_scope(course_scope):
    if course_scope == "introduction":
        return "COMP4200"
    if course_scope == "graduation_project":
        return "COMP4300"
    return None


def _supervisor_coordinator_user_ids_for_scope(cursor, course_scope):
    course_code = _supervisor_course_from_scope(course_scope)
    if course_code and _supervisor_table_exists(cursor, "coordinator_assignments"):
        semester = _supervisor_active_semester_by_course(cursor, course_code)
        if semester:
            cursor.execute(
                """
                SELECT DISTINCT u.user_id
                FROM coordinator_assignments ca
                JOIN faculty f ON f.faculty_id = ca.faculty_id
                JOIN users u ON u.user_id = f.user_id
                WHERE ca.semester_id = %s
                  AND u.role = 'coordinator'
                  AND u.is_active = TRUE
                LIMIT 1
                """,
                (semester["semester_id"],),
            )
            rows = cursor.fetchall()
            if rows:
                return [r["user_id"] for r in rows]

    limit = 1 if course_scope in {"introduction", "graduation_project"} else 1000
    cursor.execute(
        "SELECT user_id FROM users WHERE role = 'coordinator' AND is_active = TRUE ORDER BY user_id LIMIT %s",
        (limit,),
    )
    return [r["user_id"] for r in cursor.fetchall()]


def _supervisor_current_faculty_id_for_notifications(cursor):
    """Return the faculty_id for the logged-in supervisor."""
    faculty_id = session.get("faculty_id")
    if faculty_id:
        try:
            return int(faculty_id)
        except Exception:
            pass
    cursor.execute(
        """
        SELECT faculty_id
        FROM faculty
        WHERE user_id = %s
        LIMIT 1
        """,
        (session.get("user_id"),),
    )
    row = cursor.fetchone() or {}
    return row.get("faculty_id")


def _supervisor_head_user_ids(cursor, value=None):
    params = []
    extra = ""
    if value:
        extra = "AND user_id = %s"
        params.append(value)
    cursor.execute(
        f"""
        SELECT user_id
        FROM users
        WHERE role = 'head_of_department'
          AND is_active = TRUE
          {extra}
        ORDER BY full_name
        """,
        tuple(params),
    )
    return [r["user_id"] for r in cursor.fetchall()]


def _supervisor_owned_comp4200_student_rows(cursor, faculty_id, course_scope="introduction", section_id=None, student_id=None):
    if course_scope not in {"introduction", "both"}:
        return []
    if not (_supervisor_table_exists(cursor, "student_distribution_sections") and _supervisor_table_exists(cursor, "section_students")):
        return []

    params = [faculty_id]
    filters = ["sec.supervisor_id = %s", "u.is_active = TRUE"]
    if section_id:
        filters.append("sec.section_id = %s")
        params.append(str(section_id).replace("s:", "", 1))
    if student_id:
        filters.append("st.student_id = %s")
        params.append(student_id)

    cursor.execute(
        f"""
        SELECT DISTINCT
               st.student_id,
               u.user_id,
               u.full_name,
               u.university_id,
               'introduction' AS course_scope,
               'COMP4200' AS course_code,
               sec.section_id,
               sec.section_name
        FROM student_distribution_sections sec
        JOIN section_students ss ON ss.section_id = sec.section_id
        JOIN students st ON st.student_id = ss.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE {' AND '.join(filters)}
        ORDER BY sec.section_name, u.full_name
        """,
        tuple(params),
    )
    return cursor.fetchall()


def _supervisor_owned_comp4300_student_rows(cursor, faculty_id, course_scope="graduation_project", project_id=None, student_id=None):
    if course_scope not in {"graduation_project", "both"}:
        return []
    params = [faculty_id]
    filters = ["p.supervisor_id = %s", "s.course_code = 'COMP4300'", "u.is_active = TRUE"]
    if project_id:
        filters.append("p.project_id = %s")
        params.append(str(project_id).replace("p:", "", 1))
    if student_id:
        filters.append("st.student_id = %s")
        params.append(student_id)

    cursor.execute(
        f"""
        SELECT DISTINCT
               st.student_id,
               u.user_id,
               u.full_name,
               u.university_id,
               'graduation_project' AS course_scope,
               'COMP4300' AS course_code,
               p.project_id AS section_id,
               COALESCE(NULLIF(p.title, ''), CONCAT('COMP4300 Project ', p.project_id)) AS section_name
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        JOIN project_members pm ON pm.project_id = p.project_id
        JOIN students st ON st.student_id = pm.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE {' AND '.join(filters)}
        ORDER BY p.project_id DESC, u.full_name
        """,
        tuple(params),
    )
    return cursor.fetchall()


def _supervisor_owned_student_rows(cursor, faculty_id, course_scope="both", student_id=None):
    rows = []
    if course_scope in {"introduction", "both"}:
        rows.extend(_supervisor_owned_comp4200_student_rows(cursor, faculty_id, "introduction", student_id=student_id))
    if course_scope in {"graduation_project", "both"}:
        rows.extend(_supervisor_owned_comp4300_student_rows(cursor, faculty_id, "graduation_project", student_id=student_id))

    # Deduplicate the same student if old data accidentally links them more than once.
    seen = set()
    result = []
    for row in rows:
        key = row.get("student_id")
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _supervisor_owned_sections(cursor, faculty_id):
    sections = []
    if _supervisor_table_exists(cursor, "student_distribution_sections") and _supervisor_table_exists(cursor, "section_students"):
        cursor.execute(
            """
            SELECT CONCAT('s:', sec.section_id) AS section_key,
                   sec.section_id,
                   sec.section_name,
                   'introduction' AS course_scope,
                   'COMP4200' AS course_code,
                   u_sup.full_name AS supervisor_name,
                   COUNT(DISTINCT ss.student_id) AS students_count
            FROM student_distribution_sections sec
            JOIN faculty f ON f.faculty_id = sec.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            WHERE sec.supervisor_id = %s
            GROUP BY sec.section_id, sec.section_name, u_sup.full_name
            HAVING students_count > 0
            ORDER BY sec.section_id DESC
            """,
            (faculty_id,),
        )
        sections.extend(cursor.fetchall())

    cursor.execute(
        """
        SELECT CONCAT('p:', p.project_id) AS section_key,
               p.project_id AS section_id,
               COALESCE(NULLIF(p.title, ''), CONCAT('COMP4300 Project ', p.project_id)) AS section_name,
               'graduation_project' AS course_scope,
               'COMP4300' AS course_code,
               COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
               COUNT(DISTINCT pm.student_id) AS students_count
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        LEFT JOIN faculty f ON f.faculty_id = p.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = f.user_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        WHERE s.course_code = 'COMP4300'
          AND p.supervisor_id = %s
        GROUP BY p.project_id, p.title, u_sup.full_name
        HAVING students_count > 0
        ORDER BY p.project_id DESC
        """,
        (faculty_id,),
    )
    sections.extend(cursor.fetchall())
    return sections


def _supervisor_comp4200_section_recipients(cursor, section_id=None):
    faculty_id = _supervisor_current_faculty_id_for_notifications(cursor)
    if not faculty_id:
        return []
    rows = _supervisor_owned_comp4200_student_rows(cursor, faculty_id, "introduction", section_id=section_id)
    return [r["user_id"] for r in rows]


def _supervisor_comp4300_project_recipients(cursor, project_id=None):
    faculty_id = _supervisor_current_faculty_id_for_notifications(cursor)
    if not faculty_id:
        return []
    rows = _supervisor_owned_comp4300_student_rows(cursor, faculty_id, "graduation_project", project_id=project_id)
    return [r["user_id"] for r in rows]


def _supervisor_notification_recipients(cursor, scope, value=None, course_scope="both"):
    scope = (scope or "").strip()
    course_scope = (course_scope or "both").strip()
    faculty_id = _supervisor_current_faculty_id_for_notifications(cursor)

    if scope == "coordinators":
        return _supervisor_coordinator_user_ids_for_scope(cursor, course_scope)

    if scope == "coordinator":
        cursor.execute(
            "SELECT user_id FROM users WHERE user_id = %s AND role = 'coordinator' AND is_active = TRUE",
            (value,),
        )
        return [r["user_id"] for r in cursor.fetchall()]

    if scope == "heads":
        return _supervisor_head_user_ids(cursor)

    if scope == "head":
        return _supervisor_head_user_ids(cursor, value)

    if scope == "students":
        if not faculty_id:
            return []
        return [r["user_id"] for r in _supervisor_owned_student_rows(cursor, faculty_id, course_scope)]

    if scope == "student":
        if not faculty_id:
            return []
        return [r["user_id"] for r in _supervisor_owned_student_rows(cursor, faculty_id, course_scope, student_id=value)]

    if scope == "section":
        if not faculty_id:
            return []
        if course_scope == "graduation_project" or str(value).startswith("p:"):
            project_id = str(value).replace("p:", "", 1)
            return [r["user_id"] for r in _supervisor_owned_comp4300_student_rows(cursor, faculty_id, "graduation_project", project_id=project_id)]
        section_id = str(value).replace("s:", "", 1)
        return [r["user_id"] for r in _supervisor_owned_comp4200_student_rows(cursor, faculty_id, "introduction", section_id=section_id)]

    # Kept for compatibility with old forms: now means all of MY sections/projects only.
    if scope == "all_sections":
        if not faculty_id:
            return []
        return [r["user_id"] for r in _supervisor_owned_student_rows(cursor, faculty_id, course_scope)]

    if scope == "reply":
        cursor.execute("SELECT user_id FROM users WHERE user_id = %s AND is_active = TRUE", (value,))
        return [r["user_id"] for r in cursor.fetchall()]

    # Supervisors are not allowed to broadcast to all doctors or unrelated students from this page.
    return []


def _supervisor_scope_is_student_target(scope):
    return scope in {"students", "student", "section", "all_sections"}


# ============================================================
# API: Options
# ============================================================

@general_supervisors_bp.route("/api/notifications/options", methods=["GET"])
@login_required(role="supervisor")
def options():
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        coordinator_rows = []
        for course_scope, course_code in (("introduction", "COMP4200"), ("graduation_project", "COMP4300")):
            semester = _supervisor_active_semester_by_course(cursor, course_code)
            if semester and _supervisor_table_exists(cursor, "coordinator_assignments"):
                cursor.execute(
                    """
                    SELECT DISTINCT u.user_id, u.full_name, u.university_id,
                           %s AS course_scope, %s AS course_code
                    FROM coordinator_assignments ca
                    JOIN faculty f ON f.faculty_id = ca.faculty_id
                    JOIN users u ON u.user_id = f.user_id
                    WHERE ca.semester_id = %s
                      AND u.role = 'coordinator'
                      AND u.is_active = TRUE
                    LIMIT 1
                    """,
                    (course_scope, course_code, semester["semester_id"]),
                )
                coordinator_rows.extend(cursor.fetchall())
        if not coordinator_rows:
            cursor.execute(
                """
                SELECT user_id, full_name, university_id, 'both' AS course_scope, 'Both' AS course_code
                FROM users
                WHERE role = 'coordinator' AND is_active = TRUE
                ORDER BY full_name
                """
            )
            coordinator_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT user_id, full_name, university_id
            FROM users
            WHERE role = 'head_of_department'
              AND is_active = TRUE
            ORDER BY full_name
            """
        )
        heads = cursor.fetchall()

        faculty_id = _supervisor_current_faculty_id_for_notifications(cursor)
        students = _supervisor_owned_student_rows(cursor, faculty_id, "both") if faculty_id else []
        sections = _supervisor_owned_sections(cursor, faculty_id) if faculty_id else []

        cursor.close()
        db.close()
        return jsonify(
            {
                "heads": heads,
                "coordinators": coordinator_rows,
                "doctors": [],
                "students": students,
                "sections": sections,
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# API: Inbox
# ============================================================

@general_supervisors_bp.route("/api/notifications/inbox")
@login_required(role="supervisor")
def inbox():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    _ensure_supervisor_notification_schema(cursor)
    db.commit()

    fields = _notification_attachment_fields(cursor)

    cursor.execute(f"""
        SELECT n.*, n.sender_id AS sender_user_id,
               sender.full_name AS sender_name, sender.role AS sender_role,
               {fields}
        FROM notifications n
        LEFT JOIN users sender ON sender.user_id = n.sender_id
        WHERE n.recipient_id = %s
        ORDER BY n.created_at DESC
        LIMIT 100
    """, (session["user_id"],))

    rows = [_row_to_json(r) for r in cursor.fetchall()]

    cursor.close()
    db.close()
    return jsonify({"notifications": rows})


# ============================================================
# API: Sent
# ============================================================

@general_supervisors_bp.route("/api/notifications/sent")
@login_required(role="supervisor")
def sent():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    _ensure_supervisor_notification_schema(cursor)
    db.commit()

    fields = _notification_attachment_fields(cursor)

    cursor.execute(f"""
        SELECT n.*, n.recipient_id AS recipient_user_id,
               recipient.full_name AS recipient_name, recipient.role AS recipient_role,
               {fields}
        FROM notifications n
        JOIN users recipient ON recipient.user_id = n.recipient_id
        WHERE n.sender_id = %s
        ORDER BY n.created_at DESC
        LIMIT 100
    """, (session["user_id"],))

    rows = [_row_to_json(r) for r in cursor.fetchall()]

    cursor.close()
    db.close()
    return jsonify({"sent": rows})



def _supervisor_reply_allowed(cursor, notification_id, current_user_id, target_user_id):
    """Allow reply only when the original received notification has can_reply = 1."""
    if not notification_id:
        return False
    can_reply_expr = "COALESCE(can_reply, 0)" if _supervisor_db_column_exists(cursor, "notifications", "can_reply") else "0"
    cursor.execute(
        f"""
        SELECT notification_id
        FROM notifications
        WHERE notification_id = %s
          AND recipient_id = %s
          AND sender_id = %s
          AND message_origin IN ('manual', 'reply')
          AND {can_reply_expr} = 1
        LIMIT 1
        """,
        (notification_id, current_user_id, target_user_id),
    )
    return cursor.fetchone() is not None

# ============================================================
# API: Send Notification
# ============================================================

@general_supervisors_bp.route("/api/notifications/send", methods=["POST"])
@login_required(role="supervisor")
def send():
    is_multipart = bool(request.content_type and request.content_type.startswith("multipart/form-data"))
    if is_multipart:
        data = request.form
        uploaded_file = request.files.get("file")
    else:
        data = request.get_json(silent=True) or {}
        uploaded_file = None

    scope = (data.get("scope") or "").strip()
    value = data.get("value")
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    urgent = str(data.get("urgent") or "").lower() in ("1", "true", "on", "yes")
    course_scope = (data.get("course_scope") or "both").strip()
    can_reply = str(data.get("can_reply", data.get("allow_reply", "0"))).lower() in ("1", "true", "on", "yes")
    reply_to_notification_id = data.get("reply_to_notification_id") or data.get("notification_id")

    if course_scope not in {"introduction", "graduation_project", "both"}:
        return jsonify({"error": "Please choose the course scope."}), 400
    allowed_scopes = {"coordinators", "heads", "students", "student", "section", "reply", "coordinator", "head", "all_sections"}
    if not scope:
        return jsonify({"error": "Please choose who should receive the message."}), 400
    if scope not in allowed_scopes:
        return jsonify({"error": "Supervisors can send only to their own students/sections, the Head, or the Coordinator."}), 403
    if not title:
        return jsonify({"error": "Please write a title."}), 400
    if not message:
        return jsonify({"error": "Please write a message."}), 400
    if scope in {"student", "section", "reply"} and not value:
        return jsonify({"error": "Please choose the exact receiver."}), 400

    attachment_name = None
    attachment_mime = None
    attachment_data = None
    if uploaded_file and uploaded_file.filename:
        attachment_name = secure_filename(uploaded_file.filename) or "attachment"
        attachment_mime = uploaded_file.mimetype or "application/octet-stream"
        attachment_data = uploaded_file.read()
        if len(attachment_data) > 10 * 1024 * 1024:
            return jsonify({"error": "Attachment must be 10 MB or smaller."}), 400

    db = get_db()
    cursor = db.cursor(dictionary=True)

    _ensure_supervisor_notification_schema(cursor)
    recipients = _supervisor_notification_recipients(cursor, scope, value, course_scope)
    sender_id = session.get("user_id")

    # Any supervisor message sent to students is also copied to the course coordinator.
    if _supervisor_scope_is_student_target(scope):
        recipients = list(recipients or []) + _supervisor_coordinator_user_ids_for_scope(cursor, course_scope)

    if scope == "reply":
        raw_recipients = [int(r) for r in recipients if r]
        if not raw_recipients:
            cursor.close()
            db.close()
            return jsonify({"error": "No recipients found for this choice."}), 404
        target_user_id = raw_recipients[0]
        if not _supervisor_reply_allowed(cursor, reply_to_notification_id, sender_id, target_user_id):
            cursor.close()
            db.close()
            return jsonify({"error": "Replies are disabled for this message."}), 403
        can_reply = True
    recipients = sorted({int(r) for r in recipients if int(r) != int(sender_id)})
    if not recipients:
        cursor.close()
        db.close()
        return jsonify({"error": "No recipients found for this choice."}), 404

    notification_type = _supervisor_safe_notification_type(cursor, "urgent_alert" if urgent else "system")
    attachment_cols = _supervisor_db_column_exists(cursor, "notifications", "attachment_name")
    for r in recipients:
        if attachment_cols:
            cursor.execute("""
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read, can_reply,
                     message_origin, attachment_name, attachment_mime, attachment_data)
                VALUES (%s, %s, %s, %s, %s, %s, NULL, FALSE, %s, %s, %s, %s, %s)
            """, (r, sender_id, notification_type, title, message, course_scope, 1 if can_reply else 0, "reply" if scope == "reply" else "manual", attachment_name, attachment_mime, attachment_data))
        else:
            cursor.execute("""
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     is_read, can_reply, message_origin)
                VALUES (%s, %s, %s, %s, %s, FALSE, %s, %s)
            """, (r, sender_id, notification_type, title, message, 1 if can_reply else 0, "reply" if scope == "reply" else "manual"))

    db.commit()
    cursor.close()
    db.close()

    return jsonify({"message": f"Message sent successfully to {len(recipients)} recipient(s).", "sent_count": len(recipients)})


# ============================================================
# Mark Read
# ============================================================

@general_supervisors_bp.route("/api/notifications/<int:nid>/read", methods=["POST"])
@login_required(role="supervisor")
def mark_read(nid):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE notifications SET is_read=TRUE WHERE notification_id=%s AND recipient_id=%s",
        (nid, session["user_id"]),
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "updated"})


# ============================================================
# Read All
# ============================================================

@general_supervisors_bp.route("/api/notifications/read-all", methods=["POST"])
@login_required(role="supervisor")
def read_all():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE notifications SET is_read=TRUE WHERE recipient_id=%s",
        (session["user_id"],),
    )
    db.commit()
    cursor.close()
    db.close()
    return jsonify({"message": "all updated"})


@general_supervisors_bp.route("/api/notifications/<int:nid>/attachment", methods=["GET"])
@login_required(role="supervisor")
def attachment(nid):
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        if not _supervisor_db_column_exists(cursor, "notifications", "attachment_data"):
            cursor.close()
            db.close()
            return jsonify({"error": "Attachment not found."}), 404
        cursor.execute(
            """
            SELECT attachment_name, attachment_mime, attachment_data
            FROM notifications
            WHERE notification_id = %s
              AND (recipient_id = %s OR sender_id = %s)
            LIMIT 1
            """,
            (nid, session.get("user_id"), session.get("user_id")),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        if not row or not row.get("attachment_data"):
            return jsonify({"error": "Attachment not found."}), 404
        filename = secure_filename(row.get("attachment_name") or "attachment") or "attachment"
        mimetype = row.get("attachment_mime") or "application/octet-stream"
        return Response(
            row["attachment_data"],
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@general_supervisors_bp.route("/api/notifications/unread-count", methods=["GET"])
def unread_count():
    if "user_id" not in session or session.get("role") != "supervisor":
        return jsonify({"unread": 0})
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM notifications WHERE recipient_id = %s AND is_read = FALSE",
            (session.get("user_id"),),
        )
        row = cursor.fetchone()
        cursor.close()
        db.close()
        return jsonify({"unread": int((row or {}).get("cnt") or 0)})
    except Exception:
        return jsonify({"unread": 0})




# ============================================================
# Supervisor feedback helpers (independent from progress files)
# ============================================================

def _current_supervisor_faculty_id(cursor):
    """Return the faculty_id for the currently logged-in supervisor."""
    faculty_id = session.get("faculty_id")
    if faculty_id:
        return faculty_id

    cursor.execute(
        """
        SELECT f.faculty_id
        FROM faculty f
        WHERE f.user_id = %s
        LIMIT 1
        """,
        (session.get("user_id"),),
    )
    row = cursor.fetchone()
    return row["faculty_id"] if row else None



# ============================================================
# Supervisor Project Hours (COMP4200 + COMP4300)
# ============================================================

MAX_PROJECT_HOURS_PER_COURSE = 4.5

PROJECT_HOUR_COURSES = {
    "introduction": {
        "course_code": "COMP4200",
        "column": "introduction_project_hours",
        "label": "Project Introduction",
        "notice_scope": "introduction",
    },
    "graduation_project": {
        "course_code": "COMP4300",
        "column": "graduation_project_hours",
        "label": "Graduation Project",
        "notice_scope": "graduation_project",
    },
}


def _ensure_supervisor_hours_schema(cursor):
    """Create/repair the table used by supervisors to request COMP4200 and COMP4300 hours."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS faculty_load_settings (
            load_id INT PRIMARY KEY AUTO_INCREMENT,
            faculty_id INT NOT NULL,
            semester_id INT NOT NULL,
            introduction_project_hours DECIMAL(5,2) NOT NULL DEFAULT 0,
            graduation_project_hours DECIMAL(5,2) NOT NULL DEFAULT 0,
            min_hours DECIMAL(5,2) NOT NULL DEFAULT 12,
            max_hours DECIMAL(5,2) NOT NULL DEFAULT 4.5,
            employment_type ENUM('full_time','part_time') NOT NULL DEFAULT 'full_time',
            intro_students INT NOT NULL DEFAULT 0,
            extra_bonus DECIMAL(5,2) NOT NULL DEFAULT 0,
            assigned_courses TEXT NULL,
            notes TEXT NULL,
            updated_by INT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_faculty_semester_load (faculty_id, semester_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    required_columns = {
        "introduction_project_hours": "ALTER TABLE faculty_load_settings ADD COLUMN introduction_project_hours DECIMAL(5,2) NOT NULL DEFAULT 0 AFTER semester_id",
        "graduation_project_hours": "ALTER TABLE faculty_load_settings ADD COLUMN graduation_project_hours DECIMAL(5,2) NOT NULL DEFAULT 0",
        "min_hours": "ALTER TABLE faculty_load_settings ADD COLUMN min_hours DECIMAL(5,2) NOT NULL DEFAULT 12",
        "max_hours": "ALTER TABLE faculty_load_settings ADD COLUMN max_hours DECIMAL(5,2) NOT NULL DEFAULT 4.5",
        "employment_type": "ALTER TABLE faculty_load_settings ADD COLUMN employment_type ENUM('full_time','part_time') NOT NULL DEFAULT 'full_time'",
        "intro_students": "ALTER TABLE faculty_load_settings ADD COLUMN intro_students INT NOT NULL DEFAULT 0",
        "extra_bonus": "ALTER TABLE faculty_load_settings ADD COLUMN extra_bonus DECIMAL(5,2) NOT NULL DEFAULT 0",
        "assigned_courses": "ALTER TABLE faculty_load_settings ADD COLUMN assigned_courses TEXT NULL",
        "notes": "ALTER TABLE faculty_load_settings ADD COLUMN notes TEXT NULL",
        "updated_by": "ALTER TABLE faculty_load_settings ADD COLUMN updated_by INT NULL",
        "updated_at": "ALTER TABLE faculty_load_settings ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    }

    for column, ddl in required_columns.items():
        if not _supervisor_db_column_exists(cursor, "faculty_load_settings", column):
            cursor.execute(ddl)

    # Keep existing databases aligned with the rule: max project hours per course = 4.5.
    cursor.execute("UPDATE faculty_load_settings SET max_hours = %s WHERE max_hours IS NULL OR max_hours > %s", (MAX_PROJECT_HOURS_PER_COURSE, MAX_PROJECT_HOURS_PER_COURSE))

    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'faculty_load_settings'
          AND INDEX_NAME = 'uq_faculty_semester_load'
        """
    )
    if int((cursor.fetchone() or {}).get("cnt") or 0) == 0:
        try:
            cursor.execute("ALTER TABLE faculty_load_settings ADD UNIQUE KEY uq_faculty_semester_load (faculty_id, semester_id)")
        except Exception:
            pass


def _supervisor_semester_for_course(cursor, course_code):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE course_code = %s AND is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
        """,
        (course_code,),
    )
    row = cursor.fetchone()
    if row:
        return row

    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE course_code = %s
        ORDER BY semester_id DESC
        LIMIT 1
        """,
        (course_code,),
    )
    return cursor.fetchone()


def _assigned_units_for_course(cursor, faculty_id, semester_id, course_code):
    if not faculty_id or not semester_id:
        return {"assigned_students": 0, "assigned_groups": 0, "used_hours": 0.0}

    if course_code == "COMP4200" and _supervisor_table_exists(cursor, "student_distribution_sections") and _supervisor_table_exists(cursor, "section_students"):
        cursor.execute(
            """
            SELECT
                COUNT(DISTINCT sec.section_id) AS assigned_groups,
                COUNT(DISTINCT ss.student_id) AS assigned_students
            FROM student_distribution_sections sec
            LEFT JOIN section_students ss ON ss.section_id = sec.section_id
            WHERE sec.supervisor_id = %s
            """,
            (faculty_id,),
        )
        row = cursor.fetchone() or {}
        students = int(row.get("assigned_students") or 0)
        groups = int(row.get("assigned_groups") or 0)
        return {"assigned_students": students, "assigned_groups": groups, "used_hours": round(students * 0.5, 2)}

    cursor.execute(
        """
        SELECT
            COUNT(DISTINCT p.project_id) AS assigned_groups,
            COUNT(DISTINCT pm.student_id) AS assigned_students
        FROM projects p
        JOIN semesters s ON s.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        WHERE p.supervisor_id = %s
          AND p.semester_id = %s
          AND s.course_code = %s
          AND LOWER(COALESCE(p.status, '')) NOT IN (
              'draft','archived','archive','rejected','cancelled','search','search_only','imported_archive'
          )
        """,
        (faculty_id, semester_id, course_code),
    )
    row = cursor.fetchone() or {}
    students = int(row.get("assigned_students") or 0)
    groups = int(row.get("assigned_groups") or 0)
    used_hours = students * 0.5 if students > 0 else groups * 1.0
    return {"assigned_students": students, "assigned_groups": groups, "used_hours": round(used_hours, 2)}


def _supervisor_hours_payload(cursor, faculty_id, semester, scope):
    cfg = PROJECT_HOUR_COURSES[scope]
    semester_id = semester.get("semester_id") if semester else None
    requested_column = cfg["column"]

    row = None
    if semester_id:
        cursor.execute(
            """
            SELECT
                faculty_id,
                semester_id,
                introduction_project_hours,
                graduation_project_hours,
                min_hours,
                max_hours,
                employment_type,
                intro_students,
                extra_bonus,
                assigned_courses,
                notes,
                updated_at
            FROM faculty_load_settings
            WHERE faculty_id = %s
              AND semester_id = %s
            LIMIT 1
            """,
            (faculty_id, semester_id),
        )
        row = cursor.fetchone()

    if not row:
        row = {
            "faculty_id": faculty_id,
            "semester_id": semester_id,
            "introduction_project_hours": 0,
            "graduation_project_hours": 0,
            "min_hours": 12,
            "max_hours": MAX_PROJECT_HOURS_PER_COURSE,
            "employment_type": "full_time",
            "intro_students": 0,
            "extra_bonus": 0,
            "assigned_courses": "",
            "notes": "",
            "updated_at": None,
        }

    assigned = _assigned_units_for_course(cursor, faculty_id, semester_id, cfg["course_code"])
    requested = float(row.get(requested_column) or 0)
    row["course_scope"] = scope
    row["course_code"] = cfg["course_code"]
    row["requested_hours"] = requested
    row["used_hours"] = assigned["used_hours"]
    row["remaining_hours"] = max(round(requested - assigned["used_hours"], 2), 0)
    row["assigned_students"] = assigned["assigned_students"]
    row["assigned_groups"] = assigned["assigned_groups"]
    return _json_safe(row)


def _supervisor_all_project_hours(cursor, faculty_id):
    _ensure_supervisor_hours_schema(cursor)
    result = {}
    semesters = {}
    for scope, cfg in PROJECT_HOUR_COURSES.items():
        semester = _supervisor_semester_for_course(cursor, cfg["course_code"])
        semesters[scope] = _json_safe(semester) if semester else None
        result[scope] = _supervisor_hours_payload(cursor, faculty_id, semester or {}, scope)
    return result, semesters


def _save_project_hours_from_payload(data):
    scope = (data.get("course_scope") or data.get("scope") or "").strip()
    if scope not in PROJECT_HOUR_COURSES:
        return jsonify({"error": "Please choose COMP4200 or COMP4300."}), 400

    raw_hours = data.get("requested_hours", data.get("hours"))
    try:
        requested_hours = float(raw_hours)
    except (TypeError, ValueError):
        return jsonify({"error": "Please enter a valid number of hours."}), 400

    if requested_hours < 0:
        return jsonify({"error": "Hours cannot be negative."}), 400
    if requested_hours > MAX_PROJECT_HOURS_PER_COURSE:
        return jsonify({"error": f"Project hours cannot be more than {MAX_PROJECT_HOURS_PER_COURSE}."}), 400

    # This column stores the maximum allowed PROJECT hours only, not the total teaching load.
    max_hours = MAX_PROJECT_HOURS_PER_COURSE
    notes = (data.get("notes") or "").strip()

    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            return jsonify({"error": "Supervisor faculty record was not found."}), 404

        cfg = PROJECT_HOUR_COURSES[scope]
        semester = _supervisor_semester_for_course(cursor, cfg["course_code"])
        if not semester:
            return jsonify({"error": f"No {cfg['course_code']} semester was found."}), 404

        _ensure_supervisor_hours_schema(cursor)
        _ensure_supervisor_notification_schema(cursor)

        requested_column = cfg["column"]
        cursor.execute(
            f"""
            INSERT INTO faculty_load_settings
                (faculty_id, semester_id, {requested_column}, max_hours, notes, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                {requested_column} = VALUES({requested_column}),
                max_hours = VALUES(max_hours),
                notes = VALUES(notes),
                updated_by = VALUES(updated_by),
                updated_at = CURRENT_TIMESTAMP
            """,
            (faculty_id, semester["semester_id"], requested_hours, max_hours, notes, session.get("user_id")),
        )

        cursor.execute(
            """
            SELECT u.full_name
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s
            LIMIT 1
            """,
            (faculty_id,),
        )
        supervisor_name = (cursor.fetchone() or {}).get("full_name") or "A supervisor"

        notification_type = _supervisor_safe_notification_type(cursor, "system")
        coordinator_ids = _supervisor_coordinator_user_ids_for_scope(cursor, cfg["notice_scope"])
        for coordinator_id in coordinator_ids:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     related_project_id, is_read, course_scope, can_reply, message_origin)
                VALUES (%s, %s, %s, %s, %s, NULL, FALSE, %s, 1, 'manual')
                """,
                (
                    coordinator_id,
                    session.get("user_id"),
                    notification_type,
                    f"{cfg['course_code']} project hours updated",
                    f"{supervisor_name} requested {requested_hours:g} project hour(s) for {cfg['course_code']} ({cfg['label']}). Maximum allowed is 4.5.",
                    cfg["notice_scope"],
                ),
            )

        db.commit()
        hours, semesters = _supervisor_all_project_hours(cursor, faculty_id)
        return jsonify({
            "success": True,
            "message": f"{cfg['course_code']} project hours saved successfully.",
            "hours": hours,
            "semesters": semesters,
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


@general_supervisors_bp.route("/api/project-hours", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_get_project_hours():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            return jsonify({"error": "Supervisor faculty record was not found."}), 404
        hours, semesters = _supervisor_all_project_hours(cursor, faculty_id)
        db.commit()
        return jsonify({"hours": hours, "semesters": semesters})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


@general_supervisors_bp.route("/api/project-hours", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_save_project_hours():
    return _save_project_hours_from_payload(request.get_json(silent=True) or {})


# Backward-compatible endpoints used by older HTML files.
@general_supervisors_bp.route("/api/graduation-hours", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_get_graduation_hours():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            return jsonify({"error": "Supervisor faculty record was not found."}), 404
        _ensure_supervisor_hours_schema(cursor)
        semester = _supervisor_semester_for_course(cursor, "COMP4300")
        if not semester:
            return jsonify({"error": "No COMP4300 semester was found."}), 404
        db.commit()
        return jsonify({
            "semester": _json_safe(semester),
            "hours": _supervisor_hours_payload(cursor, faculty_id, semester, "graduation_project"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


@general_supervisors_bp.route("/api/graduation-hours", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_save_graduation_hours():
    data = request.get_json(silent=True) or {}
    data["course_scope"] = "graduation_project"
    data["requested_hours"] = data.get("graduation_project_hours", data.get("requested_hours", data.get("hours")))
    return _save_project_hours_from_payload(data)

def _json_safe(value):
    """Convert MySQL/date/set values to JSON-safe values."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return ", ".join(str(v) for v in sorted(value))
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def _fetch_supervisor_projects(cursor, faculty_id):
    """Load active projects assigned to this supervisor for the feedback page.

    This version is independent from progress files and avoids columns/values
    that can break JSON serialization.
    """
    if not faculty_id:
        return []

    project_type_expr = "p.project_type" if _supervisor_db_column_exists(cursor, "projects", "project_type") else "NULL"
    updated_order = "COALESCE(p.updated_at, p.submission_date) DESC," if _supervisor_db_column_exists(cursor, "projects", "updated_at") else ""
    submission_select = "p.submission_date," if _supervisor_db_column_exists(cursor, "projects", "submission_date") else "NULL AS submission_date,"

    cursor.execute(
        f"""
        SELECT
            p.project_id,
            COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS title,
            {project_type_expr} AS project_type,
            p.status,
            {submission_select}
            sem.academic_year,
            sem.course_code,
            COALESCE(
                GROUP_CONCAT(
                    DISTINCT u_st.full_name
                    ORDER BY pm.is_primary_contact DESC, u_st.full_name
                    SEPARATOR ', '
                ),
                ''
            ) AS team_members
        FROM projects p
        LEFT JOIN semesters sem ON sem.semester_id = p.semester_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u_st ON u_st.user_id = st.user_id
        WHERE p.supervisor_id = %s
          AND p.semester_id IS NOT NULL
          AND LOWER(COALESCE(p.status, '')) NOT IN (
              'draft',
              'archived',
              'archive',
              'search',
              'search_only',
              'imported_archive',
              'rejected',
              'cancelled'
          )
          AND NOT EXISTS (
              SELECT 1 FROM project_course_promotions pcp
              WHERE pcp.source_project_id = p.project_id
          )
        GROUP BY
            p.project_id,
            p.title,
            project_type,
            p.status,
            submission_date,
            sem.academic_year,
            sem.course_code
        HAVING COUNT(DISTINCT st.student_id) > 0
        ORDER BY {updated_order} p.project_id DESC
        """,
        (faculty_id,),
    )

    projects = []
    for row in cursor.fetchall():
        item = dict(row)
        # The feedback page uses title/team_members; keep both common keys.
        item["members"] = item.get("team_members") or ""
        projects.append(_json_safe(item))
    return projects


def _get_project_for_supervisor(cursor, project_id, faculty_id):
    """Check that a project belongs to the logged-in supervisor."""
    if not project_id or not faculty_id:
        return None

    cursor.execute(
        """
        SELECT p.project_id
        FROM projects p
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u_st ON u_st.user_id = st.user_id
        WHERE p.project_id = %s
          AND p.supervisor_id = %s
          AND p.semester_id IS NOT NULL
          AND LOWER(COALESCE(p.status, '')) NOT IN (
              'draft',
              'archived',
              'archive',
              'search',
              'search_only',
              'imported_archive',
              'rejected',
              'cancelled'
          )
          AND NOT EXISTS (
              SELECT 1 FROM project_course_promotions pcp
              WHERE pcp.source_project_id = p.project_id
          )
        GROUP BY p.project_id
        HAVING COUNT(DISTINCT st.student_id) > 0
        LIMIT 1
        """,
        (project_id, faculty_id),
    )
    return cursor.fetchone()


# ============================================================
# Supervisor feedback APIs moved from app.py
# ============================================================

def _ensure_feedback_target_schema(cursor):
    additions = {
        "target_scope": "ALTER TABLE feedback ADD COLUMN target_scope VARCHAR(20) NOT NULL DEFAULT 'group' AFTER is_draft",
        "target_student_id": "ALTER TABLE feedback ADD COLUMN target_student_id INT NULL AFTER target_scope",
        "target_label": "ALTER TABLE feedback ADD COLUMN target_label VARCHAR(220) NULL AFTER target_student_id",
    }
    for column, ddl in additions.items():
        if not _supervisor_db_column_exists(cursor, "feedback", column):
            cursor.execute(ddl)


def _supervisor_feedback_groups(cursor, faculty_id):
    groups = {}
    if _supervisor_table_exists(cursor, "comp4200_project_sections"):
        cursor.execute(
            """
            SELECT CONCAT('s:', sec.section_id) AS target_key,
                   sec.section_name AS group_name, cps.project_id,
                   COALESCE(NULLIF(p.title,''),sec.section_name) AS project_title,
                   'COMP4200' AS course_code,
                   st.student_id, u.user_id, u.full_name, u.university_id
            FROM student_distribution_sections sec
            JOIN comp4200_project_sections cps ON cps.section_id=sec.section_id
            JOIN projects p ON p.project_id=cps.project_id
            LEFT JOIN section_students ss ON ss.section_id=sec.section_id
            LEFT JOIN students st ON st.student_id=ss.student_id
            LEFT JOIN users u ON u.user_id=st.user_id
            WHERE sec.supervisor_id=%s
              AND LOWER(COALESCE(p.status,'')) NOT IN ('archived','promoted','cancelled','rejected')
              AND NOT EXISTS (
                  SELECT 1 FROM project_course_promotions pcp
                  WHERE pcp.source_project_id=p.project_id
              )
            ORDER BY sec.section_name,u.full_name
            """,
            (faculty_id,),
        )
        intro_rows = cursor.fetchall()
    else:
        intro_rows = []
    cursor.execute(
        """
        SELECT CONCAT('p:',p.project_id) AS target_key,
               COALESCE(NULLIF(p.title,''),CONCAT('Project ',p.project_id)) AS group_name,
               p.project_id, p.title AS project_title, 'COMP4300' AS course_code,
               st.student_id, u.user_id, u.full_name, u.university_id
        FROM projects p
        JOIN semesters sem ON sem.semester_id=p.semester_id AND sem.course_code='COMP4300'
        LEFT JOIN project_members pm ON pm.project_id=p.project_id
        LEFT JOIN students st ON st.student_id=pm.student_id
        LEFT JOIN users u ON u.user_id=st.user_id
        WHERE p.supervisor_id=%s
          AND LOWER(COALESCE(p.status,'')) NOT IN ('archived','promoted','cancelled','rejected')
        ORDER BY p.title,u.full_name
        """,
        (faculty_id,),
    )
    for row in intro_rows + cursor.fetchall():
        key = row["target_key"]
        group = groups.setdefault(key, {
            "target_key": key,
            "group_name": row.get("group_name") or row.get("project_title") or "Group",
            "project_id": row["project_id"],
            "course_code": row["course_code"],
            "students": [],
        })
        if row.get("student_id"):
            group["students"].append({
                "student_id": row["student_id"],
                "user_id": row.get("user_id"),
                "full_name": row.get("full_name") or "Student",
                "university_id": row.get("university_id") or "",
            })
    return list(groups.values())


@supervisor_api_bp.route("/api/supervisor/feedback-targets", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_feedback_targets():
    db = get_db(); cursor = db.cursor(dictionary=True)
    try:
        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            return jsonify({"error": "Supervisor faculty profile was not found."}), 404
        return jsonify({"groups": _json_safe(_supervisor_feedback_groups(cursor, faculty_id))})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    finally:
        cursor.close(); db.close()

@supervisor_api_bp.route("/api/supervisor/my-projects", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_my_projects():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        faculty_id = _current_supervisor_faculty_id(cursor)
        projects = _fetch_supervisor_projects(cursor, faculty_id)
        return jsonify({"projects": _json_safe(projects)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


@supervisor_api_bp.route("/api/supervisor/submit-feedback", methods=["POST"])
@login_required(role="supervisor")
def api_supervisor_submit_feedback():
    user_id = session["user_id"]
    data = request.get_json(force=True)
    project_id = data.get("project_id")
    target_scope = (data.get("target_scope") or "group").strip().lower()
    target_key = (data.get("target_key") or "").strip()
    target_student_id = data.get("target_student_id")
    feedback_type = data.get("feedback_type", "general_performance")
    feedback_text = (data.get("feedback_text") or "").strip()
    priority = data.get("priority", "normal")
    is_draft = bool(data.get("is_draft", False))
    points = data.get("improvement_points", [])
    if target_scope not in {"all", "group", "student"}:
        return jsonify({"error": "Invalid feedback audience."}), 400
    if not feedback_text:
        return jsonify({"error": "Feedback text is required"}), 400
    if priority not in {"normal", "important", "urgent"}:
        return jsonify({"error": "Invalid feedback priority"}), 400
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        faculty_id = _current_supervisor_faculty_id(cursor)
        if not faculty_id:
            return jsonify({"error": "Supervisor faculty profile was not found."}), 403
        _ensure_feedback_target_schema(cursor)
        groups = _supervisor_feedback_groups(cursor, faculty_id)
        by_key = {group["target_key"]: group for group in groups}
        targets = []
        if target_scope == "all":
            targets = [(group, None) for group in groups]
        else:
            group = by_key.get(target_key)
            if not group:
                return jsonify({"error": "Choose one of your assigned sections."}), 403
            if target_scope == "student":
                try:
                    target_student_id = int(target_student_id)
                except (TypeError, ValueError):
                    return jsonify({"error": "Choose a student from the selected section."}), 400
                student = next((row for row in group["students"] if int(row["student_id"]) == target_student_id), None)
                if not student:
                    return jsonify({"error": "The selected student is not in this section."}), 403
                targets = [(group, student)]
            else:
                targets = [(group, None)]
        if not targets:
            return jsonify({"error": "No assigned students were found."}), 404

        feedback_ids = []
        notified_users = set()
        for group, student in targets:
            label = student["full_name"] if student else group["group_name"]
            cursor.execute(
                """
                INSERT INTO feedback
                    (project_id,reviewer_id,feedback_type,feedback_text,priority,is_draft,
                     target_scope,target_student_id,target_label)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (group["project_id"], user_id, feedback_type, feedback_text, priority,
                 is_draft, target_scope, student["student_id"] if student else None, label),
            )
            feedback_id = cursor.lastrowid
            feedback_ids.append(feedback_id)
            for pt in points:
                pt = str(pt).strip()
                if pt:
                    cursor.execute(
                        "INSERT INTO feedback_improvement_points (feedback_id, point_text) VALUES (%s, %s)",
                        (feedback_id, pt),
                    )
            recipients = [student] if student else group["students"]
            if not is_draft:
                for recipient in recipients:
                    recipient_user_id = recipient.get("user_id")
                    if not recipient_user_id or recipient_user_id in notified_users:
                        continue
                    _insert_notification(
                        cursor, recipient_user_id, user_id, "feedback_received",
                        "New Supervisor Feedback",
                        f'Your supervisor posted feedback for {label}. Open the Feedback page to review it.',
                        group["project_id"],
                        "graduation_project" if group["course_code"] == "COMP4300" else "introduction",
                    )
                    notified_users.add(recipient_user_id)
        db.commit()
        return jsonify({"success": True, "feedback_ids": feedback_ids, "sent_count": len(notified_users)})
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


@supervisor_api_bp.route("/api/supervisor/my-feedback", methods=["GET"])
@login_required(role="supervisor")
def api_supervisor_my_feedback():
    user_id = session["user_id"]
    project_id = request.args.get("project_id")
    db = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        _ensure_feedback_target_schema(cursor)
        sql = """
            SELECT f.feedback_id, f.project_id, p.title AS project_title,
                   f.feedback_type, f.feedback_text, f.priority,
                   f.is_draft, f.created_at, f.target_scope, f.target_label
            FROM   feedback f
            JOIN   projects p ON p.project_id = f.project_id
            WHERE  f.reviewer_id = %s
        """
        params = [user_id]
        if project_id:
            sql += " AND f.project_id = %s"
            params.append(project_id)
        sql += " ORDER BY f.created_at DESC LIMIT 20"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        for r in rows:
            r["created_at"] = r["created_at"].strftime("%b %d, %Y") if r["created_at"] else ""
            r["is_draft"] = bool(r["is_draft"])
        return jsonify({"feedback": _json_safe(rows)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


@supervisor_api_bp.route("/switch-back-to-coordinator", methods=["POST", "GET"])
@login_required(role="supervisor")
def switch_back_to_coordinator():
    if not session.get("is_switched_to_supervisor"):
        return redirect(url_for("general_supervisors.dashboard"))
    session["role"] = session.get("original_role", "coordinator")
    session["user_id"] = session.get("original_user_id", session.get("user_id"))
    session["full_name"] = session.get("original_full_name", session.get("full_name"))
    session.pop("original_role", None)
    session.pop("original_user_id", None)
    session.pop("original_full_name", None)
    session.pop("is_switched_to_supervisor", None)
    return redirect(url_for("coordinator_bp.coordinator_dashboard"))
