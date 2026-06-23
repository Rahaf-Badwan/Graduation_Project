"""Lifecycle cleanup for projects that leave an active supervisor workspace."""


def _table_exists(cursor, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        LIMIT 1
        """,
        (table_name,),
    )
    return bool(cursor.fetchone())


def _column_exists(cursor, table_name, column_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (table_name, column_name),
    )
    return bool(cursor.fetchone())


def _delete_project_rows(cursor, table_name, project_id, column_name="project_id"):
    if _table_exists(cursor, table_name) and _column_exists(cursor, table_name, column_name):
        cursor.execute(
            f"DELETE FROM `{table_name}` WHERE `{column_name}` = %s",
            (project_id,),
        )


def clear_supervisor_project_workspace(
    cursor,
    project_id,
    *,
    promoted_from_comp4200=False,
):
    """Delete live-workspace data while retaining the small permanent project record.

    Archive identity, members, final report/files and final results are deliberately
    retained so the archive remains searchable. A promoted COMP4200 source is
    stripped more aggressively because COMP4300 receives a fresh workspace.
    """
    if not project_id:
        return

    cursor.execute(
        """
        SELECT CASE WHEN s.course_code = 'COMP4200'
                    THEN 'introduction' ELSE 'graduation_project' END AS course_scope
        FROM projects p
        LEFT JOIN semesters s ON s.semester_id = p.semester_id
        WHERE p.project_id = %s
        LIMIT 1
        """,
        (project_id,),
    )
    project_row = cursor.fetchone() or {}
    course_scope = project_row.get("course_scope")

    # Feedback points are removed by the feedback FK cascade.
    for table_name in (
        "feedback",
        "supervisor_notes",
        "supervisor_progress_notes",
        "project_progress",
        "supervisor_assignments",
        "challenges_reflections",
        "milestone_submissions",
        "project_evaluation_windows",
        "committees",
        "committee_plan_projects",
        "project_report_readers",
    ):
        _delete_project_rows(cursor, table_name, project_id)

    for table_name in ("evaluation_grade_tasks", "evaluation_windows"):
        if not (_table_exists(cursor, table_name) and _column_exists(cursor, table_name, "reference_id")):
            continue
        if course_scope and _column_exists(cursor, table_name, "course_scope"):
            cursor.execute(
                f"DELETE FROM `{table_name}` WHERE reference_id = %s AND course_scope = %s",
                (project_id, course_scope),
            )
        else:
            cursor.execute(
                f"DELETE FROM `{table_name}` WHERE reference_id = %s",
                (project_id,),
            )

    if _table_exists(cursor, "notifications"):
        if _column_exists(cursor, "notifications", "related_project_id"):
            cursor.execute(
                "DELETE FROM notifications WHERE related_project_id = %s",
                (project_id,),
            )
        elif _column_exists(cursor, "notifications", "project_id"):
            cursor.execute(
                "DELETE FROM notifications WHERE project_id = %s",
                (project_id,),
            )

    if _table_exists(cursor, "supervisor_lectures"):
        cursor.execute(
            """
            DELETE FROM supervisor_lectures
            WHERE target_kind = 'project' AND target_id = %s
            """,
            (project_id,),
        )

    if not promoted_from_comp4200:
        return

    # COMP4300 starts clean; old COMP4200 uploads and scheduling links are not
    # part of the new workspace.
    for table_name in (
        "project_files",
        "deadlines",
        "grade_entries",
        "grade_entry_sessions",
        "project_grade_entries",
        "project_final_evaluation_results",
    ):
        _delete_project_rows(cursor, table_name, project_id)

    if not _table_exists(cursor, "comp4200_project_sections"):
        return

    cursor.execute(
        "SELECT section_id FROM comp4200_project_sections WHERE project_id = %s",
        (project_id,),
    )
    section_ids = [row["section_id"] for row in cursor.fetchall()]
    for section_id in section_ids:
        if _table_exists(cursor, "supervisor_lectures"):
            cursor.execute(
                """
                DELETE FROM supervisor_lectures
                WHERE target_kind = 'section' AND target_id = %s
                """,
                (section_id,),
            )
        if _table_exists(cursor, "student_distribution_sections"):
            cursor.execute(
                "DELETE FROM student_distribution_sections WHERE section_id = %s",
                (section_id,),
            )
