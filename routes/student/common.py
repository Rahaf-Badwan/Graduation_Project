"""Shared helpers for student-facing routes."""

from db import get_db
from semester_lifecycle import auto_rollover_semesters


ALLOWED_EXTENSIONS = {
    "final_report": {"pdf"},
    "source_code": {"zip", "rar", "tar", "gz", "7z"},
    "presentation": {"pdf", "pptx", "ppt"},
}


MAX_FILE_MB = 50


PROJECT_TYPE_VALUES = {
    "web",
    "mobile",
    "ai",
    "software_engineering",
    "security",
    "databases",
    "other",
}


def _fmt_date(dt):
    if not dt:
        return ""
    return f"{dt.strftime('%b')} {dt.day}, {dt.year}"


def _fmt_short(dt):
    if not dt:
        return ""
    return f"{dt.strftime('%b')} {dt.day}"


def _as_date(val):
    if val is None:
        return None
    try:
        return val.date()
    except AttributeError:
        return val


def _project_type_text(value):
    if not value:
        return ""
    if isinstance(value, (set, list, tuple)):
        return ",".join(str(v) for v in value if v)
    return str(value)


def _normalize_project_type_value(value, default=None):
    if isinstance(value, (set, list, tuple)):
        raw_items = value
    else:
        raw_items = str(value or "").split(",")

    parts = []
    for item in raw_items:
        normalized = str(item or "").strip().lower()
        if normalized in PROJECT_TYPE_VALUES and normalized not in parts:
            parts.append(normalized)

    return ",".join(parts) if parts else default


def _split_project_types(value):
    """Return a clean list of project type values from MySQL SET/string values."""
    if not value:
        return []
    if isinstance(value, (set, list, tuple)):
        raw_items = value
    else:
        raw_items = str(value).split(",")
    return [str(item).strip().lower() for item in raw_items if str(item).strip()]


def _pretty_project_type(value):
    labels = {
        "web": "Web",
        "mobile": "Mobile",
        "ai": "AI",
        "desktop": "Desktop",
        "database": "Database",
        "network": "Network",
        "security": "Security",
        "iot": "IoT",
        "other": "Other",
        "software_engineering": "Software Engineering",
        "software engineering": "Software Engineering",
    }
    return labels.get(str(value).strip().lower(), str(value).strip().title())


def _json_safe(value):
    """Convert MySQL/Python values that Flask cannot serialize to JSON-safe values."""
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(value, set):
        return ", ".join(str(v) for v in value if v)
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _db_column_exists_student(cursor, table_name, column_name):
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
    row = cursor.fetchone() or {}
    return int(row.get("cnt") or 0) > 0


def _table_exists_student(cursor, table_name):
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


def _student_course_context_for_id(cursor, student_id):
    target_course = "COMP4200"
    if student_id and _table_exists_student(cursor, "student_course_results"):
        cursor.execute(
            """
            SELECT scr.status AS course_status,
                   scr.promoted_to_semester_id,
                   scr.promoted_at
            FROM student_course_results scr
            JOIN semesters s ON s.semester_id = scr.semester_id
            WHERE scr.student_id = %s AND s.course_code = 'COMP4200'
            ORDER BY scr.semester_id DESC
            LIMIT 1
            """,
            (student_id,),
        )
        result_row = cursor.fetchone() or {}
        is_promoted = bool(
            result_row.get("promoted_to_semester_id")
            or result_row.get("promoted_at")
        )
        if result_row.get("course_status") == "passed" and is_promoted:
            target_course = "COMP4300"

    return {
        "student_id": student_id,
        "target_course": target_course,
        "can_use_comp4200_registration": bool(student_id)
        and target_course == "COMP4200",
    }


def _student_course_context(cursor, user_id):
    cursor.execute(
        "SELECT student_id FROM students WHERE user_id = %s LIMIT 1",
        (user_id,),
    )
    student_row = cursor.fetchone()
    return _student_course_context_for_id(
        cursor, student_row["student_id"] if student_row else None
    )


def _student_visible_project_ids(cursor, user_id):
    """Projects whose feedback/challenges should remain visible to the student.

    Includes current project memberships plus COMP4200 source projects linked to
    a promoted COMP4300 continuation.
    """
    cursor.execute(
        "SELECT student_id FROM students WHERE user_id = %s LIMIT 1",
        (user_id,),
    )
    student = cursor.fetchone()
    if not student:
        return []

    student_id = student["student_id"]
    project_ids = []

    cursor.execute(
        """
        SELECT pm.project_id
        FROM project_members pm
        JOIN projects p ON p.project_id = pm.project_id
        JOIN semesters sem ON sem.semester_id = p.semester_id
        WHERE pm.student_id = %s
        ORDER BY sem.semester_id DESC, pm.project_id DESC
        """,
        (student_id,),
    )
    for row in cursor.fetchall():
        project_id = row.get("project_id")
        if project_id and project_id not in project_ids:
            project_ids.append(project_id)

    if _table_exists_student(cursor, "project_course_promotions"):
        cursor.execute(
            """
            SELECT pcp.source_project_id
            FROM project_course_promotions pcp
            JOIN project_members pm ON pm.project_id = pcp.promoted_project_id
            WHERE pm.student_id = %s
            ORDER BY pcp.promoted_at DESC, pcp.source_project_id DESC
            """,
            (student_id,),
        )
        for row in cursor.fetchall():
            project_id = row.get("source_project_id")
            if project_id and project_id not in project_ids:
                project_ids.append(project_id)

    return project_ids


def _cleanup_comp4200_state_for_promoted_student(cursor, student_id, promoted_at=None):
    """Clear old COMP4200 student-facing state once a student is promoted."""
    if not student_id:
        return

    cursor.execute(
        """
        SELECT DISTINCT p.project_id
        FROM project_members pm
        JOIN projects p ON p.project_id = pm.project_id
        JOIN semesters s ON s.semester_id = p.semester_id
        WHERE pm.student_id = %s
          AND s.course_code = 'COMP4200'
        """,
        (student_id,),
    )
    project_ids = [row["project_id"] for row in cursor.fetchall()]
    if not project_ids:
        return

    project_placeholders = ",".join(["%s"] * len(project_ids))
    cursor.execute(
        f"""
        SELECT DISTINCT pm.student_id, u.user_id
        FROM project_members pm
        JOIN students st ON st.student_id = pm.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE pm.project_id IN ({project_placeholders})
        """,
        project_ids,
    )
    team_rows = cursor.fetchall()
    team_student_ids = [row["student_id"] for row in team_rows if row.get("student_id")]
    team_user_ids = [row["user_id"] for row in team_rows if row.get("user_id")]
    if not team_student_ids:
        team_student_ids = [student_id]

    if _table_exists_student(cursor, "milestone_submissions"):
        student_placeholders = ",".join(["%s"] * len(team_student_ids))
        cursor.execute(
            f"""
            DELETE ms
            FROM milestone_submissions ms
            JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
            JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
            JOIN semesters sem ON sem.semester_id = tl.semester_id
            WHERE sem.course_code = 'COMP4200'
              AND (
                    ms.project_id IN ({project_placeholders})
                 OR ms.student_id IN ({student_placeholders})
              )
            """,
            [*project_ids, *team_student_ids],
        )

    if team_user_ids:
        user_placeholders = ",".join(["%s"] * len(team_user_ids))
        params = [*team_user_ids, *project_ids]
        created_filter = ""
        if promoted_at:
            created_filter = " OR n.created_at < %s"
            params.append(promoted_at)
        cursor.execute(
            f"""
            DELETE n
            FROM notifications n
            WHERE n.recipient_id IN ({user_placeholders})
              AND (
                    n.related_project_id IN ({project_placeholders})
                    {created_filter}
              )
            """,
            params,
        )


def _notify_project_team(
    cursor,
    project_id,
    sender_id,
    title,
    message,
    notification_type="system",
    exclude_user_id=None,
    course_scope=None,
):
    """Create a notification for every active student in a project team."""
    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM   project_members pm
        JOIN   students st ON st.student_id = pm.student_id
        JOIN   users    u  ON u.user_id     = st.user_id
        WHERE  pm.project_id = %s
          AND  u.is_active = TRUE
        """,
        (project_id,),
    )
    recipients = []
    for row in cursor.fetchall():
        recipient_id = row.get("user_id")
        if not recipient_id:
            continue
        if exclude_user_id is not None and int(recipient_id) == int(exclude_user_id):
            continue
        recipients.append(int(recipient_id))

    include_course_scope = course_scope and _db_column_exists_student(
        cursor, "notifications", "course_scope"
    )
    for recipient_id in sorted(set(recipients)):
        if include_course_scope:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read)
                VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE)
                """,
                (
                    recipient_id,
                    sender_id,
                    notification_type,
                    title,
                    message,
                    course_scope,
                    project_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     related_project_id, is_read)
                VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                """,
                (
                    recipient_id,
                    sender_id,
                    notification_type,
                    title,
                    message,
                    project_id,
                ),
            )


def _notify_comp4300_submission_staff(
    cursor,
    project_id,
    sender_id,
    title,
    message,
):
    """Notify the assigned supervisor and all active course coordinators."""
    cursor.execute(
        """
        SELECT DISTINCT recipient_id
        FROM (
            SELECT u_sup.user_id AS recipient_id
            FROM projects p
            JOIN faculty f ON f.faculty_id = p.supervisor_id
            JOIN users u_sup ON u_sup.user_id = f.user_id
            WHERE p.project_id = %s AND u_sup.is_active = TRUE

            UNION

            SELECT u_coord.user_id AS recipient_id
            FROM users u_coord
            WHERE u_coord.role = 'coordinator' AND u_coord.is_active = TRUE
        ) recipients
        WHERE recipient_id IS NOT NULL AND recipient_id <> %s
        """,
        (project_id, sender_id),
    )
    recipient_ids = sorted(
        {int(row["recipient_id"]) for row in cursor.fetchall() if row.get("recipient_id")}
    )
    include_course_scope = _db_column_exists_student(
        cursor, "notifications", "course_scope"
    )
    for recipient_id in recipient_ids:
        if include_course_scope:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     course_scope, related_project_id, is_read)
                VALUES (%s, %s, 'file_uploaded', %s, %s,
                        'graduation_project', %s, FALSE)
                """,
                (recipient_id, sender_id, title, message, project_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO notifications
                    (recipient_id, sender_id, notification_type, title, message,
                     related_project_id, is_read)
                VALUES (%s, %s, 'file_uploaded', %s, %s, %s, FALSE)
                """,
                (recipient_id, sender_id, title, message, project_id),
            )
    return len(recipient_ids)


def _student_intro_section(cursor, student_id):
    """Return the current COMP4200 section for a student, if assigned."""
    if (
        not student_id
        or not _table_exists_student(cursor, "student_distribution_sections")
        or not _table_exists_student(cursor, "section_students")
    ):
        return None

    cursor.execute(
        """
        SELECT sec.section_id, sec.section_name, ss.created_at AS joined_at
        FROM section_students ss
        JOIN student_distribution_sections sec ON sec.section_id = ss.section_id
        WHERE ss.student_id = %s
        ORDER BY sec.section_id DESC
        LIMIT 1
        """,
        (student_id,),
    )
    return cursor.fetchone()


def _notify_intro_section_team(
    cursor,
    section_id,
    sender_id,
    title,
    message,
    notification_type="system",
    exclude_user_id=None,
):
    """Create a notification for every active student in a COMP4200 section."""
    cursor.execute(
        """
        SELECT DISTINCT u.user_id
        FROM section_students ss
        JOIN students st ON st.student_id = ss.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE ss.section_id = %s
          AND u.is_active = TRUE
        """,
        (section_id,),
    )
    recipients = []
    for row in cursor.fetchall():
        recipient_id = row.get("user_id")
        if not recipient_id:
            continue
        if exclude_user_id is not None and int(recipient_id) == int(exclude_user_id):
            continue
        recipients.append(int(recipient_id))

    for recipient_id in sorted(set(recipients)):
        cursor.execute(
            """
            INSERT INTO notifications
                (recipient_id, sender_id, notification_type, title, message, is_read)
            VALUES (%s, %s, %s, %s, %s, FALSE)
            """,
            (recipient_id, sender_id, notification_type, title, message),
        )


def _student_intro_timeline_tables_ready(cursor):
    cursor.execute("""
        SELECT COUNT(*) AS cnt
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME IN ('comp4200_timelines', 'comp4200_timeline_items')
        """)
    return int((cursor.fetchone() or {}).get("cnt") or 0) == 2


def _student_semester_for_course(cursor, course_code, include_distribution=False):
    try:
        auto_rollover_semesters(cursor)
    except Exception:
        pass

    has_start_date = _db_column_exists_student(cursor, "semesters", "start_date")
    has_end_date = _db_column_exists_student(cursor, "semesters", "end_date")
    fields = ["semester_id", "academic_year", "semester_number", "course_code"]
    if has_start_date:
        fields.append("start_date")
    if has_end_date:
        fields.append("end_date")
    if include_distribution:
        fields.append(
            "COALESCE(distribution_open, 0) AS distribution_open"
            if _db_column_exists_student(cursor, "semesters", "distribution_open")
            else "0 AS distribution_open"
        )
        fields.append(
            "distribution_opened_at"
            if _db_column_exists_student(cursor, "semesters", "distribution_opened_at")
            else "NULL AS distribution_opened_at"
        )
        fields.append(
            "distribution_closed_at"
            if _db_column_exists_student(cursor, "semesters", "distribution_closed_at")
            else "NULL AS distribution_closed_at"
        )
        fields.append(
            "distribution_close_at"
            if _db_column_exists_student(cursor, "semesters", "distribution_close_at")
            else "NULL AS distribution_close_at"
        )
    semester_order = (
        "start_date DESC, semester_id DESC" if has_start_date else "semester_id DESC"
    )

    cursor.execute(f"""
        SELECT {', '.join(fields)}
        FROM semesters
        WHERE is_active = TRUE
          AND course_code = %s
        ORDER BY {semester_order}
        LIMIT 1
        """, (course_code,))
    row = cursor.fetchone()
    if row:
        return row

    if has_start_date and has_end_date:
        cursor.execute(f"""
            SELECT {', '.join(fields)}
            FROM semesters
            WHERE course_code = %s
              AND (start_date IS NULL OR start_date <= CURDATE())
              AND (end_date IS NULL OR end_date >= CURDATE())
            ORDER BY {semester_order}
            LIMIT 1
            """, (course_code,))
        row = cursor.fetchone()
        if row:
            return row

    cursor.execute(f"""
        SELECT {', '.join(fields)}
        FROM semesters
        WHERE course_code = %s
        ORDER BY {semester_order}
        LIMIT 1
        """, (course_code,))
    return cursor.fetchone()


def _student_active_semester(cursor):
    return _student_semester_for_course(cursor, "COMP4200")


def _target_semester_for_submission(cursor, student_id, timeline_item_id=None):
    cursor.execute(
        """
        SELECT scr.status AS course_status,
               scr.promoted_to_semester_id,
               scr.promoted_at
        FROM   student_course_results scr
        JOIN   semesters s ON s.semester_id = scr.semester_id
        WHERE  scr.student_id = %s AND s.course_code = 'COMP4200'
        ORDER  BY scr.semester_id DESC LIMIT 1
        """,
        (student_id,),
    )
    result_row = cursor.fetchone()
    course_status = (result_row or {}).get("course_status", "pending")
    promoted_to = (result_row or {}).get("promoted_to_semester_id")
    promoted_at = (result_row or {}).get("promoted_at")
    is_promoted = bool(promoted_to or promoted_at)
    target_course = "COMP4300" if course_status == "passed" and is_promoted else "COMP4200"
    if target_course == "COMP4300":
        _cleanup_comp4200_state_for_promoted_student(
            cursor, student_id, promoted_at=promoted_at
        )

    if target_course == "COMP4300" and promoted_to:
        cursor.execute(
            """
            SELECT semester_id, academic_year, course_code
            FROM semesters
            WHERE semester_id = %s AND course_code = 'COMP4300'
            LIMIT 1
            """,
            (promoted_to,),
        )
        promoted_semester = cursor.fetchone()
        if promoted_semester:
            return promoted_semester, target_course, course_status

    return _student_semester_for_course(cursor, target_course), target_course, course_status


def _student_published_intro_timeline(cursor):
    if not _student_intro_timeline_tables_ready(cursor):
        return None

    semester = _student_active_semester(cursor)
    if not semester:
        return None

    cursor.execute(
        """
        SELECT timeline_id, semester_id, title, note, is_published, published_at, updated_at
        FROM comp4200_timelines
        WHERE semester_id = %s AND is_published = TRUE
        LIMIT 1
        """,
        (semester["semester_id"],),
    )
    return cursor.fetchone()


def _student_dashboard_milestone_progress(
    cursor, student_id, project_id=None, section_id=None, final_report_uploaded=False
):
    milestone_total = 0
    milestone_submitted = 0
    last_milestone_submission = ""
    last_milestone_title = ""

    try:
        timeline = _student_published_intro_timeline(cursor)
        if timeline:
            cursor.execute(
                """
                SELECT COUNT(DISTINCT ti.item_id) AS total
                FROM comp4200_timeline_items ti
                JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
                WHERE tl.timeline_id = %s
                  AND tl.is_published = TRUE
                  AND ti.is_deadline = TRUE
                  AND COALESCE(ti.is_archived, FALSE) = FALSE
                """,
                (timeline["timeline_id"],),
            )
            milestone_total = int((cursor.fetchone() or {}).get("total") or 0)

            cursor.execute("""
                SELECT COUNT(*) AS tbl_exists
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'milestone_submissions'
            """)
            if (cursor.fetchone() or {}).get("tbl_exists"):
                if section_id:
                    submit_where = """
                          AND EXISTS (
                              SELECT 1
                              FROM section_students ss_scope
                              WHERE ss_scope.section_id = %s
                                AND ss_scope.student_id = ms.student_id
                                AND ms.submitted_at >= ss_scope.created_at
                          )
                    """
                    submit_params = (section_id,)
                elif project_id:
                    submit_where = """
                          AND (
                                ms.project_id = %s
                             OR ms.student_id = %s
                             OR EXISTS (
                                  SELECT 1
                                  FROM project_members pm_team
                                  WHERE pm_team.project_id = %s
                                    AND pm_team.student_id = ms.student_id
                                )
                          )
                    """
                    submit_params = (project_id, student_id, project_id)
                else:
                    submit_where = " AND ms.student_id = %s"
                    submit_params = (student_id,)

                cursor.execute(
                    f"""
                    SELECT COUNT(DISTINCT ms.item_id) AS submitted
                    FROM milestone_submissions ms
                    JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
                    JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
                    WHERE tl.timeline_id = %s
                      AND tl.is_published = TRUE
                      AND ti.is_deadline = TRUE
                      AND COALESCE(ti.is_archived, FALSE) = FALSE
                    {submit_where}
                    """,
                    (timeline["timeline_id"], *submit_params),
                )
                milestone_submitted = int(
                    (cursor.fetchone() or {}).get("submitted") or 0
                )

                cursor.execute(
                    f"""
                    SELECT ms.submitted_at, ti.title
                    FROM milestone_submissions ms
                    JOIN comp4200_timeline_items ti ON ti.item_id = ms.item_id
                    JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
                    WHERE tl.timeline_id = %s
                      AND tl.is_published = TRUE
                      AND ti.is_deadline = TRUE
                      AND COALESCE(ti.is_archived, FALSE) = FALSE
                    {submit_where}
                    ORDER BY ms.submitted_at DESC
                    LIMIT 1
                    """,
                    (timeline["timeline_id"], *submit_params),
                )
                last_row = cursor.fetchone() or {}
                last_milestone_submission = _fmt_date(last_row.get("submitted_at"))
                last_milestone_title = last_row.get("title") or ""
    except Exception:
        milestone_total = 0
        milestone_submitted = 0
        last_milestone_submission = ""
        last_milestone_title = ""

    total_steps = milestone_total + 1
    completed_steps = min(milestone_submitted, milestone_total) + (
        1 if final_report_uploaded else 0
    )
    overall = (
        100
        if final_report_uploaded
        else round((completed_steps / total_steps) * 100) if total_steps else 0
    )

    return {
        "submitted": min(milestone_submitted, milestone_total),
        "total": milestone_total,
        "final_report_uploaded": final_report_uploaded,
        "last_submission": last_milestone_submission,
        "last_submission_title": last_milestone_title,
        "overall": overall,
    }


def _student_intro_timeline_deadlines(cursor, limit=5):
    timeline = _student_published_intro_timeline(cursor)
    timeline_id = (timeline or {}).get("timeline_id")
    if not timeline_id:
        return []

    cursor.execute(
        """
        SELECT title, due_date
        FROM comp4200_timeline_items
        WHERE timeline_id = %s
          AND is_deadline = TRUE
          AND COALESCE(is_archived, FALSE) = FALSE
          AND due_date >= CURDATE()
        ORDER BY due_date ASC, item_order ASC, item_id ASC
        LIMIT %s
        """,
        (timeline_id, limit),
    )
    return [
        {
            "label": row.get("title") or "Timeline milestone",
            "date_str": _fmt_short(row.get("due_date")),
            "deadline_type": "timeline",
            "_sort": _as_date(row.get("due_date")),
        }
        for row in cursor.fetchall()
    ]


def _comp4300_final_submission_window(cursor, semester_id):
    """Return the latest published COMP4300 final-submission window."""
    if not semester_id or not _table_exists_student(cursor, "coordinator_deliverables"):
        return None

    cursor.execute(
        """
        SELECT deliverable_id, semester_id, title, description, start_at, due_at,
               CASE
                   WHEN due_at IS NOT NULL AND TIME(due_at) = '00:00:00'
                       THEN TIMESTAMP(DATE(due_at), '23:59:59')
                   ELSE due_at
               END AS effective_due_at,
               status, is_published, published_at,
               (
                   (start_at IS NULL OR start_at <= NOW())
                   AND (
                       due_at IS NULL
                       OR CASE
                           WHEN TIME(due_at) = '00:00:00'
                               THEN TIMESTAMP(DATE(due_at), '23:59:59')
                           ELSE due_at
                       END >= NOW()
                   )
               ) AS is_active
        FROM coordinator_deliverables
        WHERE semester_id = %s
          AND course_scope = 'graduation_project'
          AND title = 'Graduation Project Final Submission'
          AND is_published = TRUE
        ORDER BY deliverable_id DESC
        LIMIT 1
        """,
        (semester_id,),
    )
    return cursor.fetchone()


def _student_final_submission_window(cursor, student_id):
    """Return the currently active final-submission menu link for a student."""
    if not student_id:
        return {"is_active": False, "item_id": None, "submit_url": "/student/submit"}

    course_context = _student_course_context_for_id(cursor, student_id)
    target_course = course_context["target_course"]
    semester = _student_semester_for_course(cursor, target_course) or {}

    if target_course == "COMP4300":
        window = _comp4300_final_submission_window(cursor, semester.get("semester_id"))
        return {
            "is_active": bool(window and window.get("is_active")),
            "item_id": None,
            "submit_url": "/student/submit",
        }

    if not _student_intro_timeline_tables_ready(cursor):
        return {"is_active": False, "item_id": None, "submit_url": "/student/submit"}

    cursor.execute(
        """
        SELECT ti.item_id
        FROM comp4200_timeline_items ti
        JOIN comp4200_timelines tl ON tl.timeline_id = ti.timeline_id
        WHERE tl.is_published = TRUE
          AND ti.is_deadline = TRUE
          AND COALESCE(ti.is_archived, FALSE) = FALSE
          AND (
                LOWER(ti.title) LIKE '%final report%'
             OR LOWER(ti.title) LIKE '%final submission%'
          )
          AND (
                ti.start_date IS NULL
             OR TIMESTAMP(
                    ti.start_date,
                    COALESCE(NULLIF(TRIM(ti.start_time), ''), '00:00:00')
                ) <= NOW()
          )
          AND (
                ti.due_date IS NULL
             OR TIMESTAMP(
                    ti.due_date,
                    COALESCE(NULLIF(TRIM(ti.due_time), ''), '23:59:59')
                ) >= NOW()
          )
        ORDER BY ti.item_id DESC
        LIMIT 1
        """
    )
    item = cursor.fetchone() or {}
    item_id = item.get("item_id")
    return {
        "is_active": bool(item_id),
        "item_id": item_id,
        "submit_url": (
            f"/student/submit?milestone_id={item_id}" if item_id else "/student/submit"
        ),
    }


def _student_workspace_context(cursor, user_id):
    """Return whether a COMP4200 student may enter the project workspace."""
    course_context = _student_course_context(cursor, user_id)
    student_id = course_context.get("student_id")
    target_course = course_context.get("target_course") or "COMP4200"

    if target_course != "COMP4200":
        return {
            **course_context,
            "is_registered": True,
            "workspace_ready": True,
            "registration_only": False,
        }

    project = None
    semester = _get_active_semester_st(cursor)
    if student_id and semester:
        cursor.execute(
            """
            SELECT p.project_id, p.status, p.supervisor_id
            FROM project_members pm
            JOIN projects p ON p.project_id = pm.project_id
            WHERE pm.student_id = %s
              AND p.semester_id = %s
            ORDER BY
                CASE WHEN p.status = 'solo_pending' THEN 1 ELSE 0 END,
                p.project_id DESC
            LIMIT 1
            """,
            (student_id, semester["semester_id"]),
        )
        project = cursor.fetchone()

    registered = bool(project)
    workspace_ready = bool(
        project
        and project.get("status") != "solo_pending"
        and project.get("supervisor_id")
    )
    return {
        **course_context,
        "is_registered": registered,
        "workspace_ready": workspace_ready,
        "registration_only": not workspace_ready,
        "project_id": project.get("project_id") if project else None,
    }


def _student_sidebar_context(cursor, user_id):
    """Build sidebar visibility before the student page is rendered."""
    workspace = _student_workspace_context(cursor, user_id)
    student_id = workspace.get("student_id")

    submit_window = _student_final_submission_window(cursor, student_id)
    return {
        **workspace,
        "show_registration": bool(workspace.get("registration_only")),
        "show_submit": bool(
            workspace.get("workspace_ready") and submit_window.get("is_active")
        ),
        "submit_url": submit_window.get("submit_url") or "/student/submit",
    }


def _is_submission_open(cursor, semester_id, project_id):
    """Returns True if the file_submission deadline hasn't passed yet.
    Also returns True if there is an active 'final report/submission'
    timeline milestone (timeline controls the window in that case).
    If no deadline configured at all, submission is considered open."""
    from datetime import date, datetime as _dt

    cursor.execute(
        "SELECT course_code FROM semesters WHERE semester_id = %s LIMIT 1",
        (semester_id,),
    )
    semester = cursor.fetchone() or {}
    if semester.get("course_code") == "COMP4300":
        window = _comp4300_final_submission_window(cursor, semester_id)
        return bool(window and window.get("is_active"))

    # ── Check if an active final-report timeline milestone exists ──
    try:
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME IN ('comp4200_timelines','comp4200_timeline_items')
        """)
        if int((cursor.fetchone() or {}).get("cnt") or 0) >= 2:
            now = _dt.now()
            cursor.execute("""
                SELECT ti.due_date, ti.due_time, ti.start_date, ti.start_time
                FROM comp4200_timeline_items ti
                JOIN comp4200_timelines t ON t.timeline_id = ti.timeline_id
                WHERE t.is_published = TRUE
                  AND ti.is_deadline = TRUE
                  AND COALESCE(ti.is_archived, FALSE) = FALSE
                  AND (LOWER(ti.title) LIKE '%final report%'
                    OR LOWER(ti.title) LIKE '%final submission%')
            """)
            final_milestones = cursor.fetchall()
            for item in final_milestones:
                # Build start datetime
                s_d = item.get("start_date")
                s_t = (item.get("start_time") or "").strip()
                if s_d and s_t:
                    try:
                        start_dt = _dt.strptime(f"{s_d} {s_t}", "%Y-%m-%d %H:%M")
                    except:
                        start_dt = _dt(s_d.year, s_d.month, s_d.day, 0, 0)
                elif s_d:
                    start_dt = _dt(s_d.year, s_d.month, s_d.day, 0, 0)
                else:
                    start_dt = None
                # Build due datetime
                d_d = item.get("due_date")
                d_t = (item.get("due_time") or "").strip()
                if d_d and d_t:
                    try:
                        due_dt = _dt.strptime(f"{d_d} {d_t}", "%Y-%m-%d %H:%M")
                    except:
                        due_dt = _dt(d_d.year, d_d.month, d_d.day, 23, 59)
                elif d_d:
                    due_dt = _dt(d_d.year, d_d.month, d_d.day, 23, 59)
                else:
                    due_dt = None
                # Window open?
                if start_dt and now < start_dt:
                    continue
                if due_dt and now > due_dt:
                    continue
                return True  # active final milestone → allow upload
            if final_milestones:
                return False
    except Exception:
        pass

    # ── Fall back to deadlines table ───────────────────────────────
    cursor.execute(
        """
        SELECT MIN(deadline_date) AS deadline
        FROM   deadlines
        WHERE  semester_id = %s
          AND  (project_id IS NULL OR project_id = %s)
          AND  deadline_type = 'file_submission'
        """,
        (semester_id, project_id),
    )
    row = cursor.fetchone()
    if not row or not row.get("deadline"):
        return True  # no deadline configured → open
    return _as_date(row["deadline"]) >= date.today()


def _coerce_positive_int(value):
    value = str(value or "").strip()
    if not value.isdigit():
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _ensure_milestone_submissions_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS milestone_submissions (
            submission_id  INT          PRIMARY KEY AUTO_INCREMENT,
            item_id        INT          NOT NULL,
            student_id     INT          NOT NULL,
            project_id     INT          NULL,
            file_name      VARCHAR(255) NOT NULL,
            file_data      LONGBLOB     NOT NULL,
            file_mime      VARCHAR(120) NOT NULL,
            file_size_mb   DECIMAL(6,2) NULL,
            submitted_to   ENUM('supervisor','coordinator','both')
                           NOT NULL DEFAULT 'supervisor',
            submitted_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            item_title     VARCHAR(255) NULL,
            item_label     VARCHAR(180) NULL,
            INDEX idx_ms_item    (item_id),
            INDEX idx_ms_student (student_id),
            FOREIGN KEY (item_id)
                REFERENCES comp4200_timeline_items(item_id)
                ON DELETE CASCADE,
            FOREIGN KEY (student_id)
                REFERENCES students(student_id)
                ON DELETE CASCADE,
            FOREIGN KEY (project_id)
                REFERENCES projects(project_id)
                ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

    try:
        cursor.execute(
            """
            ALTER TABLE milestone_submissions
            MODIFY COLUMN submitted_to ENUM('supervisor','coordinator','both')
            NOT NULL DEFAULT 'supervisor'
            """
        )
    except Exception:
        pass

    for col_name, col_def in [
        ("project_id", "INT NULL"),
        ("item_title", "VARCHAR(255) NULL"),
        ("item_label", "VARCHAR(180) NULL"),
    ]:
        try:
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'milestone_submissions'
                  AND COLUMN_NAME = %s
                """,
                (col_name,),
            )
            if not int((cursor.fetchone() or {}).get("cnt") or 0):
                cursor.execute(
                    f"ALTER TABLE milestone_submissions ADD COLUMN {col_name} {col_def}"
                )
        except Exception:
            pass


def _sync_final_report_timeline_submission(
    cursor,
    *,
    timeline_item_id,
    student_id,
    project_id,
    file_name,
    file_bytes,
    mime_type,
    size_mb,
):
    item_id = _coerce_positive_int(timeline_item_id)
    if not item_id or not project_id or not file_bytes:
        return None

    _ensure_milestone_submissions_table(cursor)
    cursor.execute(
        """
        SELECT item_id, title, milestone_label, submitted_to, start_date,
               start_time, due_date, due_time
        FROM comp4200_timeline_items
        WHERE item_id = %s
        """,
        (item_id,),
    )
    item = cursor.fetchone()
    if not item:
        return None

    title_lower = (item.get("title") or "").lower()
    if "final report" not in title_lower and "final submission" not in title_lower:
        return None

    from datetime import datetime as _datetime

    now = _datetime.now()
    start_date_val = _as_date(item.get("start_date"))
    start_time_str = (item.get("start_time") or "").strip()
    due_date_val = _as_date(item.get("due_date"))
    due_time_str = (item.get("due_time") or "").strip()

    if start_date_val and start_time_str:
        try:
            start_dt = _datetime.strptime(
                f"{start_date_val} {start_time_str}", "%Y-%m-%d %H:%M"
            )
        except ValueError:
            start_dt = _datetime(
                start_date_val.year, start_date_val.month, start_date_val.day, 0, 0
            )
    elif start_date_val:
        start_dt = _datetime(
            start_date_val.year, start_date_val.month, start_date_val.day, 0, 0
        )
    else:
        start_dt = None

    if due_date_val and due_time_str:
        try:
            due_dt = _datetime.strptime(
                f"{due_date_val} {due_time_str}", "%Y-%m-%d %H:%M"
            )
        except ValueError:
            due_dt = _datetime(
                due_date_val.year, due_date_val.month, due_date_val.day, 23, 59
            )
    elif due_date_val:
        due_dt = _datetime(
            due_date_val.year, due_date_val.month, due_date_val.day, 23, 59
        )
    else:
        due_dt = None

    if start_dt and now < start_dt:
        raise PermissionError("The submission window has not opened yet.")
    if due_dt and now > due_dt:
        raise PermissionError("The submission window has closed. No more uploads are allowed.")

    cursor.execute(
        """
        SELECT ms.submission_id, ms.student_id, u.full_name AS submitted_by
        FROM milestone_submissions ms
        JOIN students st ON st.student_id = ms.student_id
        JOIN users u ON u.user_id = st.user_id
        WHERE ms.item_id = %s AND ms.project_id = %s
        ORDER BY ms.submitted_at DESC
        LIMIT 1
        """,
        (item_id, project_id),
    )
    existing = cursor.fetchone()
    if existing and existing.get("student_id") != student_id:
        submitted_by = existing.get("submitted_by") or "a teammate"
        raise PermissionError(
            f"This timeline milestone has already been submitted by {submitted_by}."
        )

    cursor.execute(
        "DELETE FROM milestone_submissions WHERE item_id = %s AND project_id = %s",
        (item_id, project_id),
    )
    submitted_to = (item.get("submitted_to") or "coordinator").strip().lower()
    if submitted_to not in ("supervisor", "coordinator", "both"):
        submitted_to = "coordinator"

    cursor.execute(
        """
        INSERT INTO milestone_submissions
            (item_id, student_id, project_id, file_name, file_data,
             file_mime, file_size_mb, submitted_to, item_title, item_label)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            item_id,
            student_id,
            project_id,
            file_name,
            file_bytes,
            mime_type or "application/octet-stream",
            size_mb,
            submitted_to,
            item.get("title") or "",
            item.get("milestone_label") or "",
        ),
    )
    return cursor.lastrowid


def _get_active_semester_st(cursor):
    """Local copy of _get_active_semester for student blueprint."""
    try:
        auto_rollover_semesters(cursor)
    except Exception:
        pass

    has_course_code = _db_column_exists_student(cursor, "semesters", "course_code")
    has_start_date = _db_column_exists_student(cursor, "semesters", "start_date")
    has_end_date = _db_column_exists_student(cursor, "semesters", "end_date")
    fields = ["semester_id", "academic_year", "semester_number"]
    fields.append("course_code" if has_course_code else "'COMP4200' AS course_code")
    fields.append(
        "COALESCE(distribution_open, 0) AS distribution_open"
        if _db_column_exists_student(cursor, "semesters", "distribution_open")
        else "0 AS distribution_open"
    )
    fields.append(
        "distribution_opened_at"
        if _db_column_exists_student(cursor, "semesters", "distribution_opened_at")
        else "NULL AS distribution_opened_at"
    )
    fields.append(
        "distribution_closed_at"
        if _db_column_exists_student(cursor, "semesters", "distribution_closed_at")
        else "NULL AS distribution_closed_at"
    )
    fields.append(
        "distribution_close_at"
        if _db_column_exists_student(cursor, "semesters", "distribution_close_at")
        else "NULL AS distribution_close_at"
    )
    semester_order = (
        "start_date DESC, semester_id DESC" if has_start_date else "semester_id DESC"
    )

    where = "is_active = TRUE"
    params = []
    if has_course_code:
        where += " AND course_code = %s"
        params.append("COMP4200")

    cursor.execute(f"""
        SELECT {', '.join(fields)}
        FROM semesters
        WHERE {where}
        ORDER BY {semester_order}
        LIMIT 1
    """, tuple(params))
    semester = cursor.fetchone()
    if semester:
        return semester

    if has_course_code and has_start_date and has_end_date:
        cursor.execute(f"""
            SELECT {', '.join(fields)}
            FROM semesters
            WHERE course_code = %s
              AND (start_date IS NULL OR start_date <= CURDATE())
              AND (end_date IS NULL OR end_date >= CURDATE())
            ORDER BY {semester_order}
            LIMIT 1
        """, ("COMP4200",))
        semester = cursor.fetchone()
        if semester:
            return semester

    if has_course_code:
        cursor.execute(f"""
            SELECT {', '.join(fields)}
            FROM semesters
            WHERE course_code = %s
            ORDER BY {semester_order}
            LIMIT 1
        """, ("COMP4200",))
        return cursor.fetchone()

    return None


def _sync_lifecycle(cursor, project_id):
    """
    Auto-update project_lifecycle based on actual project state.
    Called after registration or file upload.

    Rules (student-controlled stages only):
      registration    → completed  : always (project exists)
      file_submission → in_progress: at least 1 required file uploaded
      file_submission → completed  : final_report + source_code both uploaded
      initial_review  → in_progress: auto when file_submission = completed
    """
    # 1. Ensure all lifecycle rows exist
    STAGES = [
        "registration",
        "file_submission",
        "initial_review",
        "supervisor_review",
        "committee_evaluation",
        "final_result",
        "archiving",
    ]
    for stage in STAGES:
        cursor.execute(
            """
            INSERT IGNORE INTO project_lifecycle (project_id, stage, status)
            VALUES (%s, %s, 'pending')
            """,
            (project_id, stage),
        )

    # 2. Registration → always completed
    cursor.execute(
        """
        UPDATE project_lifecycle
        SET    status = 'completed', completed_date = COALESCE(completed_date, CURDATE())
        WHERE  project_id = %s AND stage = 'registration' AND status != 'completed'
        """,
        (project_id,),
    )

    # 3. Check uploaded files
    cursor.execute(
        """
        SELECT file_type FROM project_files
        WHERE  project_id = %s AND upload_status = 'uploaded'
          AND  file_type IN ('final_report', 'source_code', 'presentation')
        """,
        (project_id,),
    )
    uploaded = {r["file_type"] for r in cursor.fetchall()}
    required_done = "final_report" in uploaded and "source_code" in uploaded

    if required_done:
        # file_submission → completed
        cursor.execute(
            """
            UPDATE project_lifecycle
            SET    status = 'completed', completed_date = COALESCE(completed_date, CURDATE())
            WHERE  project_id = %s AND stage = 'file_submission' AND status != 'completed'
            """,
            (project_id,),
        )
        # initial_review → in_progress (only if still pending)
        cursor.execute(
            """
            UPDATE project_lifecycle
            SET    status = 'in_progress'
            WHERE  project_id = %s AND stage = 'initial_review' AND status = 'pending'
            """,
            (project_id,),
        )
    elif uploaded:
        # at least one file → file_submission in_progress
        cursor.execute(
            """
            UPDATE project_lifecycle
            SET    status = 'in_progress'
            WHERE  project_id = %s AND stage = 'file_submission' AND status = 'pending'
            """,
            (project_id,),
        )


# ─────────────────────────────────────────────────────────────
# Graduation archive access helpers
# ─────────────────────────────────────────────────────────────

def _ensure_student_graduation_access_schema(cursor):
    """Track the 20-day grace period after a COMP4300 project is archived."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS student_graduation_access (
            access_id INT PRIMARY KEY AUTO_INCREMENT,
            student_id INT NOT NULL,
            project_id INT NOT NULL,
            archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            access_expires_at DATETIME NOT NULL,
            notice_seen_at DATETIME NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_student_graduation_project (student_id, project_id),
            INDEX idx_student_graduation_student (student_id),
            INDEX idx_student_graduation_expires (access_expires_at),
            FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _student_archived_project_row(cursor, student_id):
    """Return the latest archived/succeeded COMP4300 project for this student, if any."""
    if not student_id:
        return None

    has_final_decisions = _table_exists_student(cursor, "final_decisions")
    has_lifecycle = _table_exists_student(cursor, "project_lifecycle")
    has_archived_at = _db_column_exists_student(cursor, "projects", "archived_at")
    has_updated_at = _db_column_exists_student(cursor, "projects", "updated_at")

    score_expr = "p.final_score"
    decision_join = ""
    decision_condition = ""
    decision_date = "NULL"
    if has_final_decisions:
        decision_join = "LEFT JOIN final_decisions fd ON fd.project_id = p.project_id"
        score_expr = "COALESCE(fd.final_score, p.final_score)"
        decision_condition = "OR LOWER(COALESCE(fd.decision, '')) IN ('accepted','passed','succeeded')"
        decision_date = "fd.decided_at"

    lifecycle_join = ""
    lifecycle_condition = ""
    lifecycle_date = "NULL"
    if has_lifecycle:
        lifecycle_join = """
            LEFT JOIN project_lifecycle pl_archive
              ON pl_archive.project_id = p.project_id
             AND pl_archive.stage = 'archiving'
        """
        lifecycle_condition = "OR LOWER(COALESCE(pl_archive.status, '')) = 'completed'"
        lifecycle_date = "pl_archive.completed_date"

    archived_date_expr_parts = []
    if has_archived_at:
        archived_date_expr_parts.append("p.archived_at")
    archived_date_expr_parts.append(lifecycle_date)
    archived_date_expr_parts.append(decision_date)
    if has_updated_at:
        archived_date_expr_parts.append("p.updated_at")
    archived_date_expr_parts.append("CURRENT_TIMESTAMP")
    archived_at_expr = "COALESCE(" + ", ".join(archived_date_expr_parts) + ")"

    cursor.execute(
        f"""
        SELECT p.project_id,
               COALESCE(NULLIF(p.title, ''), CONCAT('Project ', p.project_id)) AS project_title,
               sem.academic_year,
               {score_expr} AS final_score,
               {archived_at_expr} AS archived_at
        FROM project_members pm
        JOIN projects p ON p.project_id = pm.project_id
        JOIN semesters sem ON sem.semester_id = p.semester_id
        {decision_join}
        {lifecycle_join}
        WHERE pm.student_id = %s
          AND sem.course_code = 'COMP4300'
          AND (
                LOWER(COALESCE(p.status, '')) IN ('archived','accepted','completed','succeeded','passed')
                {decision_condition}
                {lifecycle_condition}
              )
        ORDER BY {archived_at_expr} DESC, p.project_id DESC
        LIMIT 1
        """,
        (student_id,),
    )
    return cursor.fetchone()


def _student_graduation_access(cursor, user_id):
    """Return graduation notice/session-expiry state for a student user."""
    from datetime import datetime

    cursor.execute(
        """
        SELECT st.student_id, u.full_name, u.university_id
        FROM students st
        JOIN users u ON u.user_id = st.user_id
        WHERE st.user_id = %s
        LIMIT 1
        """,
        (user_id,),
    )
    student = cursor.fetchone()
    if not student:
        return None

    _ensure_student_graduation_access_schema(cursor)
    archived_project = _student_archived_project_row(cursor, student["student_id"])
    if not archived_project:
        return None

    archived_at = archived_project.get("archived_at")
    if not archived_at:
        archived_at = datetime.now()

    # Keep one stable expiry date per student/project once detected.
    cursor.execute(
        """
        INSERT INTO student_graduation_access
            (student_id, project_id, archived_at, access_expires_at)
        VALUES (%s, %s, %s, DATE_ADD(%s, INTERVAL 20 DAY))
        ON DUPLICATE KEY UPDATE
            archived_at = LEAST(archived_at, VALUES(archived_at)),
            access_expires_at = DATE_ADD(LEAST(archived_at, VALUES(archived_at)), INTERVAL 20 DAY)
        """,
        (
            student["student_id"],
            archived_project["project_id"],
            archived_at,
            archived_at,
        ),
    )

    cursor.execute(
        """
        SELECT access_id, student_id, project_id, archived_at, access_expires_at, notice_seen_at,
               GREATEST(DATEDIFF(access_expires_at, NOW()), 0) AS days_left,
               CASE WHEN NOW() >= access_expires_at THEN 1 ELSE 0 END AS is_expired
        FROM student_graduation_access
        WHERE student_id = %s AND project_id = %s
        LIMIT 1
        """,
        (student["student_id"], archived_project["project_id"]),
    )
    access = cursor.fetchone() or {}
    if not access:
        return None

    return {
        "student_id": student["student_id"],
        "student_name": student.get("full_name") or "",
        "university_id": student.get("university_id") or "",
        "project_id": archived_project.get("project_id"),
        "project_title": archived_project.get("project_title") or "Graduation Project",
        "academic_year": archived_project.get("academic_year") or "",
        "final_score": float(archived_project["final_score"]) if archived_project.get("final_score") is not None else None,
        "archived_at": access.get("archived_at"),
        "access_expires_at": access.get("access_expires_at"),
        "days_left": int(access.get("days_left") or 0),
        "is_expired": bool(access.get("is_expired")),
        "notice_seen": bool(access.get("notice_seen_at")),
        "result_url": "/student/result",
    }


def _student_mark_graduation_notice_seen(cursor, user_id):
    access = _student_graduation_access(cursor, user_id)
    if not access:
        return None
    cursor.execute(
        """
        UPDATE student_graduation_access
        SET notice_seen_at = COALESCE(notice_seen_at, NOW())
        WHERE student_id = %s AND project_id = %s
        """,
        (access["student_id"], access["project_id"]),
    )
    access["notice_seen"] = True
    return access


__all__ = [
    "ALLOWED_EXTENSIONS",
    "MAX_FILE_MB",
    "PROJECT_TYPE_VALUES",
    "_fmt_date",
    "_fmt_short",
    "_as_date",
    "_project_type_text",
    "_normalize_project_type_value",
    "_split_project_types",
    "_pretty_project_type",
    "_json_safe",
    "_db_column_exists_student",
    "_table_exists_student",
    "_student_course_context_for_id",
    "_student_course_context",
    "_student_visible_project_ids",
    "_cleanup_comp4200_state_for_promoted_student",
    "_notify_project_team",
    "_notify_comp4300_submission_staff",
    "_student_intro_section",
    "_notify_intro_section_team",
    "_student_intro_timeline_tables_ready",
    "_student_semester_for_course",
    "_student_active_semester",
    "_target_semester_for_submission",
    "_student_published_intro_timeline",
    "_student_dashboard_milestone_progress",
    "_student_intro_timeline_deadlines",
    "_comp4300_final_submission_window",
    "_student_final_submission_window",
    "_student_workspace_context",
    "_student_sidebar_context",
    "_is_submission_open",
    "_coerce_positive_int",
    "_ensure_milestone_submissions_table",
    "_sync_final_report_timeline_submission",
    "_get_active_semester_st",
    "_sync_lifecycle",
    "_ensure_student_graduation_access_schema",
    "_student_graduation_access",
    "_student_mark_graduation_notice_seen",
]
