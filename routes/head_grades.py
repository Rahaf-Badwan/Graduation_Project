from flask import Blueprint, render_template, jsonify, session
from auth import login_required
from db import get_db

head_grades_bp = Blueprint("head_grades_bp", __name__)


def _head_db_column_exists(cursor, table_name, column_name):
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


def _ensure_student_course_results_score_schema(cursor):
    if not _head_db_column_exists(cursor, "student_course_results", "final_score"):
        cursor.execute(
            """
            ALTER TABLE student_course_results
            ADD COLUMN final_score DECIMAL(6,2) NULL AFTER status
            """
        )


@head_grades_bp.route('/head/grades')
@login_required(role='head_of_department')
def head_grades_page():
    return render_template('head/grades.html')


@head_grades_bp.route('/head/api/grades-from-supervisors')
@login_required(role='head_of_department')
def api_grades_from_supervisors():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            efr.result_id,
            efr.final_score,
            efr.workflow_status,
            efr.course_scope,
            sec.section_name AS project_title,
            sec.section_id AS project_id,
            u_sup.full_name AS supervisor_name,
            GROUP_CONCAT(
                DISTINCT u_st.full_name
                ORDER BY u_st.full_name
                SEPARATOR ', '
            ) AS students
        FROM evaluation_final_results efr
        JOIN student_distribution_sections sec
          ON sec.section_id = efr.reference_id
         AND efr.course_scope = 'introduction'
        LEFT JOIN faculty f_sup ON f_sup.faculty_id = efr.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
        LEFT JOIN section_students ss ON ss.section_id = sec.section_id
        LEFT JOIN students st ON st.student_id = ss.student_id
        LEFT JOIN users u_st ON u_st.user_id = st.user_id
        WHERE efr.workflow_status = 'sent_to_head'
        GROUP BY efr.result_id, efr.final_score, efr.workflow_status,
                 efr.course_scope, sec.section_name, sec.section_id, u_sup.full_name
    """)
    grades = cursor.fetchall()

    cursor.execute("""
        SELECT
            efr.result_id,
            efr.final_score,
            efr.workflow_status,
            efr.course_scope,
            p.title AS project_title,
            p.project_id,
            u_sup.full_name AS supervisor_name,
            GROUP_CONCAT(
                DISTINCT u_st.full_name
                ORDER BY u_st.full_name
                SEPARATOR ', '
            ) AS students
        FROM evaluation_final_results efr
        JOIN projects p
          ON p.project_id = efr.reference_id
         AND efr.course_scope = 'graduation_project'
        LEFT JOIN faculty f_sup ON f_sup.faculty_id = efr.supervisor_id
        LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
        LEFT JOIN project_members pm ON pm.project_id = p.project_id
        LEFT JOIN students st ON st.student_id = pm.student_id
        LEFT JOIN users u_st ON u_st.user_id = st.user_id
        WHERE efr.workflow_status = 'sent_to_head'
        GROUP BY efr.result_id, efr.final_score, efr.workflow_status,
                 efr.course_scope, p.title, p.project_id, u_sup.full_name
    """)
    grades.extend(cursor.fetchall())
    grades.sort(key=lambda row: ((row.get("supervisor_name") or ""), (row.get("project_title") or "")))
    cursor.close()
    db.close()
    return jsonify({"grades": grades})


@head_grades_bp.route('/head/api/publish-grades', methods=['POST'])
@login_required(role='head_of_department')
def api_publish_grades():
    user_id = session['user_id']
    db = get_db()
    cursor = db.cursor(dictionary=True)
    _ensure_student_course_results_score_schema(cursor)

    cursor.execute("""
        SELECT
            efr.final_score,
            NULL AS related_project_id,
            st.user_id AS student_user_id,
            sec.section_name AS project_title
        FROM evaluation_final_results efr
        JOIN student_distribution_sections sec
          ON sec.section_id = efr.reference_id
         AND efr.course_scope = 'introduction'
        JOIN section_students ss ON ss.section_id = sec.section_id
        JOIN students st ON st.student_id = ss.student_id
        WHERE efr.workflow_status = 'sent_to_head'
    """)
    to_notify = cursor.fetchall()

    cursor.execute("""
        SELECT
            efr.final_score,
            p.project_id AS related_project_id,
            st.user_id AS student_user_id,
            p.title AS project_title
        FROM evaluation_final_results efr
        JOIN projects p
          ON p.project_id = efr.reference_id
         AND efr.course_scope = 'graduation_project'
        JOIN project_members pm ON pm.project_id = p.project_id
        JOIN students st ON st.student_id = pm.student_id
        WHERE efr.workflow_status = 'sent_to_head'
    """)
    to_notify.extend(cursor.fetchall())

    if not to_notify:
        cursor.close()
        db.close()
        return jsonify({"success": False, "message": "No grades to publish."})

    cursor.execute("""
        SELECT DISTINCT
            efr.result_id,
            efr.final_score,
            efr.reference_id AS section_id,
            cps.project_id,
            p.semester_id,
            CASE WHEN efr.final_score >= 60 THEN 'passed' ELSE 'failed' END AS course_status
        FROM evaluation_final_results efr
        JOIN student_distribution_sections sec
          ON sec.section_id = efr.reference_id
         AND efr.course_scope = 'introduction'
        LEFT JOIN comp4200_project_sections cps ON cps.section_id = sec.section_id
        LEFT JOIN projects p ON p.project_id = cps.project_id
        WHERE efr.workflow_status = 'sent_to_head'
    """)
    intro_results = cursor.fetchall()

    for item in intro_results:
        project_id = item.get("project_id")
        semester_id = item.get("semester_id")
        final_score = item.get("final_score")
        course_status = item.get("course_status")

        if project_id:
            cursor.execute(
                """
                UPDATE projects
                SET final_score = %s,
                    status = CASE
                        WHEN %s = 'passed' AND status NOT IN ('archived') THEN 'accepted'
                        WHEN %s = 'failed' AND status NOT IN ('archived') THEN 'rejected'
                        ELSE status
                    END
                WHERE project_id = %s
                """,
                (final_score, course_status, course_status, project_id),
            )

        if semester_id:
            cursor.execute(
                """
                INSERT INTO student_course_results
                    (student_id, semester_id, status, final_score, updated_by, notes)
                SELECT DISTINCT ss.student_id, %s, %s, %s, %s,
                       'Final grade published by Head of Department.'
                FROM section_students ss
                WHERE ss.section_id = %s
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    final_score = VALUES(final_score),
                    updated_by = VALUES(updated_by),
                    notes = VALUES(notes),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (semester_id, course_status, final_score, user_id, item.get("section_id")),
            )

    cursor.execute("""
        SELECT DISTINCT
            efr.result_id,
            efr.final_score,
            p.project_id,
            p.semester_id,
            CASE WHEN efr.final_score >= 60 THEN 'passed' ELSE 'failed' END AS course_status
        FROM evaluation_final_results efr
        JOIN projects p
          ON p.project_id = efr.reference_id
         AND efr.course_scope = 'graduation_project'
        WHERE efr.workflow_status = 'sent_to_head'
    """)
    grad_results = cursor.fetchall()

    for item in grad_results:
        cursor.execute(
            """
            UPDATE projects
            SET final_score = %s,
                status = CASE
                    WHEN %s = 'passed' AND status NOT IN ('archived') THEN 'accepted'
                    WHEN %s = 'failed' AND status NOT IN ('archived') THEN 'rejected'
                    ELSE status
                END
            WHERE project_id = %s
            """,
            (
                item.get("final_score"),
                item.get("course_status"),
                item.get("course_status"),
                item.get("project_id"),
            ),
        )
        cursor.execute(
            """
            INSERT INTO student_course_results
                (student_id, semester_id, status, final_score, updated_by, notes)
            SELECT DISTINCT pm.student_id, %s, %s, %s, %s,
                   'Final grade published by Head of Department.'
            FROM project_members pm
            WHERE pm.project_id = %s
            ON DUPLICATE KEY UPDATE
                status = VALUES(status),
                final_score = VALUES(final_score),
                updated_by = VALUES(updated_by),
                notes = VALUES(notes),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                item.get("semester_id"),
                item.get("course_status"),
                item.get("final_score"),
                user_id,
                item.get("project_id"),
            ),
        )

    cursor.execute("""
        UPDATE evaluation_final_results
        SET
            workflow_status   = 'published_to_students',
            head_published_by = %s,
            head_published_at = NOW()
        WHERE workflow_status = 'sent_to_head'
    """, (user_id,))

    notified = 0
    for s in to_notify:
        cursor.execute("""
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type,
                 title, message, related_project_id)
            VALUES (%s, %s, 'status_changed',
                    'Your Final Grade Has Been Published',
                    %s, %s)
        """, (
            s['student_user_id'],
            user_id,
            f"Your final grade for project \"{s['project_title']}\" "
            f"has been published. Final Score: {s['final_score']}",
            s['related_project_id']
        ))
        notified += 1

    db.commit()
    cursor.close()
    db.close()
    return jsonify({"success": True, "notified": notified})
