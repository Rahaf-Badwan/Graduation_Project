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


def _find_matching_comp4300_project(cursor, semester_id, member_ids):
    """Reuse an existing COMP4300 copy if a promoted team already has one."""
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


def _ensure_comp4300_projects_for_promoted_groups(cursor, semester_id, promoted_by):
    """Move fully promoted succeeded COMP4200 teams into the COMP4300 section list."""
    _ensure_project_course_promotions_schema(cursor)
    cursor.execute(
        """
        SELECT p.project_id,
               COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id)) AS group_name
        FROM section_completion_status scs
        JOIN projects p
          ON scs.course_scope = 'introduction'
         AND scs.reference_id = p.project_id
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE scs.status = 'succeeded'
          AND sem.course_code = 'COMP4200'
          AND EXISTS (
              SELECT 1
              FROM project_members pm
              WHERE pm.project_id = p.project_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM project_course_promotions pcp
              WHERE pcp.source_project_id = p.project_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM project_members pm
              LEFT JOIN student_course_results scr
                ON scr.student_id = pm.student_id
               AND scr.semester_id = p.semester_id
              WHERE pm.project_id = p.project_id
                AND (
                    scr.result_id IS NULL
                    OR scr.status != 'passed'
                    OR scr.promoted_at IS NULL
                    OR scr.promoted_to_semester_id IS NULL
                    OR scr.promoted_to_semester_id != %s
                )
          )
        ORDER BY p.project_id
        """,
        (semester_id,),
    )
    sources = cursor.fetchall()
    moved_groups = []

    for source in sources:
        source_project_id = source["project_id"]
        member_ids = _project_member_ids(cursor, source_project_id)
        if not member_ids:
            continue

        promoted_project_id = _find_matching_comp4300_project(
            cursor, semester_id, member_ids
        )
        if not promoted_project_id:
            cursor.execute(
                """
                INSERT INTO projects
                    (group_name, title, title_en, abstract, keywords, project_type,
                     semester_id, supervisor_id, status, submission_date)
                SELECT COALESCE(NULLIF(group_name, ''), CONCAT('Group ', project_id)),
                       title, title_en, abstract, keywords, project_type,
                       %s, supervisor_id, 'submitted', submission_date
                FROM projects
                WHERE project_id = %s
                """,
                (semester_id, source_project_id),
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
        cursor.execute(
            """
            INSERT INTO project_course_promotions
                (source_project_id, promoted_project_id, promoted_to_semester_id,
                 promoted_by)
            VALUES (%s, %s, %s, %s)
            """,
            (source_project_id, promoted_project_id, semester_id, promoted_by),
        )
        moved_groups.append(
            {
                "source_project_id": source_project_id,
                "promoted_project_id": promoted_project_id,
                "group_name": source["group_name"],
            }
        )

    return moved_groups


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
    """Succeeded COMP4200 groups that are still waiting for promotion."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT p.project_id,
                   COALESCE(NULLIF(p.group_name, ''),
                            CONCAT('Group ', p.project_id)) AS group_name,
                   p.title,
                   sem.academic_year,
                   COALESCE(
                       GROUP_CONCAT(
                           DISTINCT u.full_name
                           ORDER BY pm.is_primary_contact DESC, u.full_name
                           SEPARATOR ', '
                       ),
                       ''
                   ) AS students,
                   COUNT(DISTINCT pm.student_id) AS student_count
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'introduction'
             AND scs.reference_id = p.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE scs.status = 'succeeded'
              AND sem.course_code = 'COMP4200'
              AND u.role = 'student'
              AND u.is_active = TRUE
              AND NOT EXISTS (
                  SELECT 1
                  FROM student_course_results scr
                  WHERE scr.student_id = pm.student_id
                    AND scr.semester_id = p.semester_id
                    AND (
                        scr.promoted_at IS NOT NULL
                        OR scr.promoted_to_semester_id IS NOT NULL
                    )
              )
            GROUP BY p.project_id, p.group_name, p.title, sem.academic_year,
                     scs.marked_at
            HAVING student_count > 0
            ORDER BY scs.marked_at DESC, p.project_id DESC
            """
        )
        groups = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"groups": groups}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/promote-all", methods=["POST"])
@login_required(role="head_of_department")
def api_promote_all():
    """Promote every member of succeeded COMP4200 groups to COMP4300."""
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
        _ensure_project_course_promotions_schema(cursor)

        # Backfill old section results too. This makes existing succeeded groups
        # promotable even if they were marked before group-result syncing existed.
        cursor.execute(
            """
            INSERT INTO student_course_results
                (student_id, semester_id, status, updated_by, notes)
            SELECT DISTINCT pm.student_id, p.semester_id, 'passed',
                            scs.marked_by, scs.notes
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'introduction'
             AND scs.reference_id = p.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            WHERE scs.status = 'succeeded'
              AND sem.course_code = 'COMP4200'
            ON DUPLICATE KEY UPDATE
                status = IF(student_course_results.promoted_at IS NULL, 'passed', student_course_results.status),
                updated_by = IF(student_course_results.promoted_at IS NULL, VALUES(updated_by), student_course_results.updated_by),
                notes = IF(student_course_results.promoted_at IS NULL, VALUES(notes), student_course_results.notes),
                updated_at = CURRENT_TIMESTAMP
            """
        )

        cursor.execute(
            """
            SELECT DISTINCT scr.result_id, scr.student_id, st.user_id
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'introduction'
             AND scs.reference_id = p.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN student_course_results scr
              ON scr.student_id = pm.student_id
             AND scr.semester_id = p.semester_id
            JOIN students st ON st.student_id = scr.student_id
            WHERE scs.status = 'succeeded'
              AND sem.course_code = 'COMP4200'
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

        moved_groups = _ensure_comp4300_projects_for_promoted_groups(
            cursor, comp4300["semester_id"], session["user_id"]
        )
        db.commit()
        count = len(result_ids)
        group_count = len(moved_groups)
        cursor.close()
        db.close()
        return (
            jsonify(
                {
                    "message": (
                        f"{count} student(s) promoted to COMP4300 successfully. "
                        f"{group_count} group(s) moved to Graduation Project Sections."
                    ),
                    "promoted_students": count,
                    "moved_groups": group_count,
                }
            ),
            200,
        )
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/comp4300", methods=["GET"])
@login_required(role="head_of_department")
def api_get_comp4300_students():
    """Succeeded, non-archived COMP4300 project groups."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT p.project_id,
                   COALESCE(NULLIF(p.group_name, ''), NULLIF(p.title, ''),
                            CONCAT('Project ', p.project_id)) AS group_name,
                   p.title,
                   COALESCE(
                       GROUP_CONCAT(
                           DISTINCT u.full_name
                           ORDER BY pm.is_primary_contact DESC, u.full_name
                           SEPARATOR ', '
                       ),
                       ''
                   ) AS students,
                   COUNT(DISTINCT pm.student_id) AS student_count
            FROM section_completion_status scs
            JOIN projects p
              ON scs.course_scope = 'graduation_project'
             AND scs.reference_id = p.project_id
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN project_members pm ON pm.project_id = p.project_id
            JOIN students st ON st.student_id = pm.student_id
            JOIN users u ON u.user_id = st.user_id
            WHERE scs.status = 'succeeded'
              AND sem.course_code = 'COMP4300'
              AND p.status != 'archived'
              AND u.role = 'student'
              AND u.is_active = TRUE
            GROUP BY p.project_id, p.group_name, p.title, scs.marked_at
            HAVING student_count > 0
            ORDER BY scs.marked_at DESC, p.project_id DESC
            """
        )
        projects = cursor.fetchall()
        cursor.close()
        db.close()
        return jsonify({"projects": projects}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500


@promote_bp.route("/api/students/archive-all", methods=["POST"])
@login_required(role="head_of_department")
def api_archive_all():
    """Archive only the COMP4300 projects marked as succeeded by the coordinator."""
    try:
        db = get_db()
        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            UPDATE projects p
            JOIN semesters sem ON sem.semester_id = p.semester_id
            JOIN section_completion_status scs
              ON scs.course_scope = 'graduation_project'
             AND scs.reference_id = p.project_id
             AND scs.status = 'succeeded'
            SET p.status = 'archived'
            WHERE sem.course_code = 'COMP4300'
              AND p.status != 'archived'
              AND EXISTS (
                  SELECT 1
                  FROM project_members pm
                  WHERE pm.project_id = p.project_id
              )
            """
        )
        count = cursor.rowcount
        db.commit()
        cursor.close()
        db.close()
        return jsonify({"message": f"{count} project(s) archived successfully."}), 200
    except Exception as e:
        return jsonify({"error": f"Database error: {e}"}), 500
