from datetime import datetime

from flask import Blueprint, jsonify, session

from auth import login_required
from db import get_db


promote_bp = Blueprint("promote", __name__)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
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


def _db_column_exists(cursor, table_name, column_name):
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


def _ensure_project_course_promotions_schema(cursor):
    """Track the COMP4200 project that produced each COMP4300 project."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS project_course_promotions (
            promotion_id INT PRIMARY KEY AUTO_INCREMENT,
            source_project_id INT NOT NULL,
            promoted_project_id INT NOT NULL,
            promoted_to_semester_id INT NOT NULL,
            promoted_by INT NULL,
            promoted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_project_course_promotion_source (source_project_id),
            UNIQUE KEY uq_project_course_promotion_target (promoted_project_id),
            FOREIGN KEY (source_project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (promoted_project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
            FOREIGN KEY (promoted_to_semester_id) REFERENCES semesters(semester_id) ON DELETE RESTRICT,
            FOREIGN KEY (promoted_by) REFERENCES users(user_id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _notification_enum_values(cursor):
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
    column_type = str(row.get("column_type") or "")
    if not column_type.lower().startswith("enum("):
        return []

    raw = column_type[5:-1]
    values = []
    current = ""
    in_quote = False
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


def _safe_notification_type(cursor, requested_type="system"):
    allowed = _notification_enum_values(cursor)
    if not allowed:
        return requested_type or "system"
    if requested_type in allowed:
        return requested_type
    for fallback in ("system", "status_changed", "info", "message", "alert"):
        if fallback in allowed:
            return fallback
    return allowed[0]


def _insert_notification(
    cursor,
    recipient_id,
    sender_id,
    notification_type,
    title,
    message,
    related_project_id=None,
    course_scope="both",
):
    """Insert notifications safely across old/new APMS schemas."""
    notification_type = _safe_notification_type(cursor, notification_type)
    has_course_scope = _db_column_exists(cursor, "notifications", "course_scope")
    has_can_reply = _db_column_exists(cursor, "notifications", "can_reply")

    columns = [
        "recipient_id",
        "sender_id",
        "notification_type",
        "title",
        "message",
    ]
    values = [recipient_id, sender_id, notification_type, title, message]

    if has_course_scope:
        columns.append("course_scope")
        values.append(course_scope)

    if related_project_id is not None:
        # Some older schemas use related_project_id. If it is missing, ignore it.
        if _db_column_exists(cursor, "notifications", "related_project_id"):
            columns.append("related_project_id")
            values.append(related_project_id)
        elif _db_column_exists(cursor, "notifications", "project_id"):
            columns.append("project_id")
            values.append(related_project_id)

    columns.append("is_read")
    values.append(False)

    if has_can_reply:
        columns.append("can_reply")
        values.append(False)

    placeholders = ", ".join(["%s"] * len(values))
    cursor.execute(
        f"INSERT INTO notifications ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values),
    )


def _active_comp4300_semester(cursor):
    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE course_code = 'COMP4300'
          AND is_active = TRUE
        ORDER BY semester_id DESC
        LIMIT 1
        """
    )
    semester = cursor.fetchone()
    if semester:
        return semester

    cursor.execute(
        """
        SELECT semester_id, academic_year, semester_number, course_code
        FROM semesters
        WHERE course_code = 'COMP4300'
        ORDER BY semester_id DESC
        LIMIT 1
        """
    )
    return cursor.fetchone()


def _project_member_ids(cursor, project_id):
    cursor.execute(
        """
        SELECT student_id
        FROM project_members
        WHERE project_id = %s
        ORDER BY student_id
        """,
        (project_id,),
    )
    return tuple(int(row["student_id"]) for row in cursor.fetchall())


def _project_student_user_ids(cursor, project_id):
    cursor.execute(
        """
        SELECT DISTINCT st.student_id, u.user_id, u.full_name
        FROM project_members pm
        JOIN students st ON st.student_id = pm.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE pm.project_id = %s
          AND u.role = 'student'
          AND u.is_active = TRUE
        ORDER BY u.full_name
        """,
        (project_id,),
    )
    return cursor.fetchall()


def _find_matching_comp4300_project(cursor, semester_id, member_ids):
    """Reuse an unlinked COMP4300 project if it already has exactly the same students."""
    if not member_ids:
        return None

    cursor.execute(
        """
        SELECT p.project_id,
               GROUP_CONCAT(DISTINCT pm.student_id ORDER BY pm.student_id SEPARATOR ',') AS member_ids
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN project_course_promotions pcp
          ON pcp.promoted_project_id = p.project_id
        WHERE p.semester_id = %s
          AND sem.course_code = 'COMP4300'
          AND pcp.promotion_id IS NULL
          AND COALESCE(p.status, '') <> 'archived'
        GROUP BY p.project_id
        """,
        (semester_id,),
    )
    for row in cursor.fetchall():
        candidate_ids = tuple(
            int(student_id)
            for student_id in (row.get("member_ids") or "").split(",")
            if student_id
        )
        if candidate_ids == member_ids:
            return row["project_id"]
    return None


def _copy_optional_project_rows(cursor, source_project_id, promoted_project_id):
    # COMP4300 must start with a clean submission workspace. Keep notes only;
    # do not carry COMP4200 files/progress/lifecycle into the graduation project.

    if _table_exists(cursor, "supervisor_notes"):
        cursor.execute(
            """
            INSERT INTO supervisor_notes
                (project_id, supervisor_id, note_text, urgency)
            SELECT %s, supervisor_id, note_text, urgency
            FROM supervisor_notes
            WHERE project_id = %s
            """,
            (promoted_project_id, source_project_id),
        )


def _clear_comp4200_student_state(cursor, source_project_id):
    """Remove coordinator-facing COMP4200 timeline submissions for promoted groups only."""
    if _table_exists(cursor, "milestone_submissions"):
        cursor.execute(
            """
            DELETE ms
            FROM milestone_submissions ms
            LEFT JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
            LEFT JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
            LEFT JOIN semesters sem ON sem.semester_id = tl.semester_id
            WHERE ms.project_id = %s
              AND (sem.course_code = 'COMP4200' OR sem.course_code IS NULL)
            """,
            (source_project_id,),
        )


def _copy_project_to_comp4300(cursor, source_project_id, comp4300_semester_id, promoted_by):
    _ensure_project_course_promotions_schema(cursor)

    cursor.execute(
        """
        SELECT p.*, sem.academic_year, sem.semester_id AS source_semester_id
        FROM projects p
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE p.project_id = %s
          AND sem.course_code = 'COMP4200'
          AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.project_id)
        LIMIT 1
        """,
        (source_project_id,),
    )
    source = cursor.fetchone()
    if not source:
        raise ValueError("COMP4200 group was not found or has no students.")

    cursor.execute(
        """
        SELECT promoted_project_id
        FROM project_course_promotions
        WHERE source_project_id = %s
        LIMIT 1
        """,
        (source_project_id,),
    )
    existing = cursor.fetchone()
    if existing:
        return {
            "source_project_id": source_project_id,
            "promoted_project_id": existing["promoted_project_id"],
            "created": False,
        }

    member_ids = _project_member_ids(cursor, source_project_id)
    promoted_project_id = _find_matching_comp4300_project(
        cursor, comp4300_semester_id, member_ids
    )

    if not promoted_project_id:
        copy_columns = []
        copy_values = []
        for column in [
            "group_name",
            "title",
            "title_en",
            "abstract",
            "keywords",
            "project_type",
            "supervisor_id",
            "preferred_supervisor_1",
            "preferred_supervisor_2",
            "preferred_supervisor_3",
            "coordinator_notes",
        ]:
            if _db_column_exists(cursor, "projects", column):
                value = source.get(column)
                if isinstance(value, set):
                    value = ",".join(sorted(str(v) for v in value))
                copy_columns.append(column)
                copy_values.append(value)

        copy_columns.extend(["semester_id", "status"])
        copy_values.extend([comp4300_semester_id, "submitted"])
        if _db_column_exists(cursor, "projects", "submission_date"):
            copy_columns.append("submission_date")
            copy_values.append(datetime.now().date())

        placeholders = ", ".join(["%s"] * len(copy_values))
        cursor.execute(
            f"INSERT INTO projects ({', '.join(copy_columns)}) VALUES ({placeholders})",
            tuple(copy_values),
        )
        promoted_project_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT IGNORE INTO project_members
            (project_id, student_id, is_primary_contact)
        SELECT %s, student_id, is_primary_contact
        FROM project_members
        WHERE project_id = %s
        """,
        (promoted_project_id, source_project_id),
    )

    cursor.execute(
        """
        UPDATE projects target
        JOIN projects source ON source.project_id = %s
        SET target.group_name = COALESCE(
                NULLIF(target.group_name, ''),
                NULLIF(source.group_name, ''),
                CONCAT('Group ', source.project_id)
            ),
            target.supervisor_id = COALESCE(target.supervisor_id, source.supervisor_id)
        WHERE target.project_id = %s
        """,
        (source_project_id, promoted_project_id),
    )

    _copy_optional_project_rows(cursor, source_project_id, promoted_project_id)

    cursor.execute(
        """
        INSERT INTO project_course_promotions
            (source_project_id, promoted_project_id, promoted_to_semester_id,
             promoted_by, promoted_at)
        VALUES (%s, %s, %s, %s, NOW())
        """,
        (source_project_id, promoted_project_id, comp4300_semester_id, promoted_by),
    )

    if _table_exists(cursor, "student_course_results"):
        cursor.execute(
            """
            INSERT INTO student_course_results
                (student_id, semester_id, status, updated_by, notes,
                 promoted_to_semester_id, promoted_by, promoted_at)
            SELECT DISTINCT pm.student_id, %s, 'passed', %s,
                   'Approved by Head of Department and promoted to COMP4300.',
                   %s, %s, NOW()
            FROM project_members pm
            WHERE pm.project_id = %s
            ON DUPLICATE KEY UPDATE
                status = 'passed',
                updated_by = VALUES(updated_by),
                notes = VALUES(notes),
                promoted_to_semester_id = VALUES(promoted_to_semester_id),
                promoted_by = VALUES(promoted_by),
                promoted_at = COALESCE(student_course_results.promoted_at, NOW()),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                source.get("source_semester_id"),
                promoted_by,
                comp4300_semester_id,
                promoted_by,
                source_project_id,
            ),
        )

    _clear_comp4200_student_state(cursor, source_project_id)

    group_name = source.get("group_name") or source.get("title") or f"Group {source_project_id}"
    for student in _project_student_user_ids(cursor, source_project_id):
        _insert_notification(
            cursor,
            student["user_id"],
            promoted_by,
            "status_changed",
            "You have officially been moved to COMP4300",
            f"Congratulations! {group_name} was approved by the Head of Department and moved to COMP4300.",
            promoted_project_id,
            "graduation_project",
        )

    if source.get("supervisor_id"):
        cursor.execute(
            """
            SELECT u.user_id
            FROM faculty f
            JOIN users u ON u.user_id = f.user_id
            WHERE f.faculty_id = %s
              AND u.is_active = TRUE
            LIMIT 1
            """,
            (source.get("supervisor_id"),),
        )
        supervisor = cursor.fetchone()
        if supervisor:
            _insert_notification(
                cursor,
                supervisor["user_id"],
                promoted_by,
                "status_changed",
                "COMP4200 Group Promoted to COMP4300",
                f"{group_name} was moved to COMP4300 with the same students under your supervision.",
                promoted_project_id,
                "graduation_project",
            )

    return {
        "source_project_id": source_project_id,
        "promoted_project_id": promoted_project_id,
        "created": True,
    }


# ─────────────────────────────────────────────────────────────
# API endpoints used by Head → Add Student → Promote & Archive
# ─────────────────────────────────────────────────────────────
@promote_bp.route("/api/students/passes", methods=["GET"])
@login_required(role="head_of_department")
def api_get_passes_students():
    """Succeeded COMP4200 groups that are still waiting for Head promotion."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_project_course_promotions_schema(cursor)

        cursor.execute(
            """
            SELECT p.project_id,
                   COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id)) AS group_name,
                   COALESCE(NULLIF(p.title, ''), 'Project Introduction Group') AS title,
                   sem.academic_year,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(
                       GROUP_CONCAT(
                           DISTINCT u.full_name
                           ORDER BY pm.is_primary_contact DESC, u.full_name
                           SEPARATOR ', '
                       ),
                       ''
                   ) AS students,
                   COUNT(DISTINCT pm.student_id) AS student_count,
                   scs.marked_at
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'introduction'
             AND scs.reference_id = p.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
            LEFT JOIN project_course_promotions pcp
              ON pcp.source_project_id = p.project_id
            WHERE scs.status = 'succeeded'
              AND sem.course_code = 'COMP4200'
              AND pcp.promotion_id IS NULL
              AND u.role = 'student'
              AND u.is_active = TRUE
            GROUP BY p.project_id, p.group_name, p.title, sem.academic_year,
                     u_sup.full_name, scs.marked_at
            HAVING student_count > 0
            ORDER BY scs.marked_at DESC, p.project_id DESC
            """
        )
        groups = cursor.fetchall()

        # Backward-compatible flat list for old JS versions.
        students = []
        for group in groups:
            cursor.execute(
                """
                SELECT u.full_name, u.university_id,
                       UPPER(LEFT(REPLACE(u.full_name, ' ', ''), 2)) AS avatar_initials
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users u ON u.user_id = st.user_id
                WHERE pm.project_id = %s
                ORDER BY pm.is_primary_contact DESC, u.full_name
                """,
                (group["project_id"],),
            )
            for student in cursor.fetchall():
                student["group_name"] = group.get("group_name")
                students.append(student)

        cursor.close()
        db.close()
        return jsonify({"groups": groups, "students": students}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/promote-all", methods=["POST"])
@login_required(role="head_of_department")
def api_promote_all():
    """Head approval: move every succeeded COMP4200 group to COMP4300."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)
        _ensure_project_course_promotions_schema(cursor)

        comp4300 = _active_comp4300_semester(cursor)
        if not comp4300:
            cursor.close()
            db.close()
            return jsonify({"error": "No COMP4300 semester found."}), 400

        cursor.execute(
            """
            SELECT DISTINCT p.project_id
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'introduction'
             AND scs.reference_id = p.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            LEFT JOIN project_course_promotions pcp
              ON pcp.source_project_id = p.project_id
            WHERE scs.status = 'succeeded'
              AND sem.course_code = 'COMP4200'
              AND pcp.promotion_id IS NULL
              AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.project_id)
            ORDER BY p.project_id
            """
        )
        source_ids = [row["project_id"] for row in cursor.fetchall()]

        moved_groups = []
        for source_project_id in source_ids:
            moved_groups.append(
                _copy_project_to_comp4300(
                    cursor,
                    source_project_id,
                    comp4300["semester_id"],
                    session.get("user_id"),
                )
            )

        db.commit()
        cursor.close()
        db.close()
        return jsonify(
            {
                "message": f"{len(moved_groups)} COMP4200 group(s) promoted to COMP4300 successfully.",
                "moved_groups": len(moved_groups),
                "groups": moved_groups,
            }
        ), 200
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/comp4300", methods=["GET"])
@login_required(role="head_of_department")
def api_get_comp4300_students():
    """Succeeded, non-archived COMP4300 project groups waiting for Head archive."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT p.project_id,
                   COALESCE(NULLIF(p.group_name, ''), NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS group_name,
                   COALESCE(NULLIF(p.title, ''), 'Graduation Project') AS title,
                   COALESCE(u_sup.full_name, 'Not assigned') AS supervisor_name,
                   COALESCE(
                       GROUP_CONCAT(
                           DISTINCT u.full_name
                           ORDER BY pm.is_primary_contact DESC, u.full_name
                           SEPARATOR ', '
                       ),
                       ''
                   ) AS students,
                   COUNT(DISTINCT pm.student_id) AS student_count,
                   scs.marked_at
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'graduation_project'
             AND scs.reference_id = p.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
            LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
            WHERE scs.status = 'succeeded'
              AND sem.course_code = 'COMP4300'
              AND COALESCE(p.status, '') <> 'archived'
              AND u.role = 'student'
              AND u.is_active = TRUE
            GROUP BY p.project_id, p.group_name, p.title, u_sup.full_name, scs.marked_at
            HAVING student_count > 0
            ORDER BY scs.marked_at DESC, p.project_id DESC
            """
        )
        projects = cursor.fetchall()

        # Backward-compatible flat list for old JS versions.
        students = []
        for project in projects:
            cursor.execute(
                """
                SELECT u.full_name, u.university_id,
                       UPPER(LEFT(REPLACE(u.full_name, ' ', ''), 2)) AS avatar_initials
                FROM project_members pm
                JOIN students st ON st.student_id = pm.student_id
                JOIN users u ON u.user_id = st.user_id
                WHERE pm.project_id = %s
                ORDER BY pm.is_primary_contact DESC, u.full_name
                """,
                (project["project_id"],),
            )
            for student in cursor.fetchall():
                student["group_name"] = project.get("group_name")
                students.append(student)

        cursor.close()
        db.close()
        return jsonify({"projects": projects, "students": students}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/archive-all", methods=["POST"])
@login_required(role="head_of_department")
def api_archive_all():
    """Head approval: archive COMP4300 projects marked as succeeded by coordinator."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT DISTINCT p.project_id
            FROM projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN section_completion_status scs
              ON scs.course_scope = 'graduation_project'
             AND scs.reference_id = p.project_id
             AND scs.status = 'succeeded'
            WHERE sem.course_code = 'COMP4300'
              AND COALESCE(p.status, '') <> 'archived'
              AND EXISTS (SELECT 1 FROM project_members pm WHERE pm.project_id = p.project_id)
            """
        )
        project_ids = [row["project_id"] for row in cursor.fetchall()]

        if project_ids:
            placeholders = ",".join(["%s"] * len(project_ids))
            cursor.execute(
                f"UPDATE projects SET status = 'archived' WHERE project_id IN ({placeholders})",
                tuple(project_ids),
            )

            for project_id in project_ids:
                for student in _project_student_user_ids(cursor, project_id):
                    _insert_notification(
                        cursor,
                        student["user_id"],
                        session.get("user_id"),
                        "status_changed",
                        "Graduation project archived",
                        "Your COMP4300 graduation project was approved by the Head of Department and archived.",
                        project_id,
                        "graduation_project",
                    )

        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": f"{len(project_ids)} project(s) archived successfully."}), 200
    except Exception as e:
        try:
            db.rollback()
        except Exception:
            pass
        return jsonify({"error": f"Database error: {e}"}), 500
