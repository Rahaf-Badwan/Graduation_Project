def auto_rollover_semesters(cursor):
    """Keep the active term current without deleting semester data.

    A term can contain both COMP4200 and COMP4300 rows, so activation must use
    academic_year + semester_number rather than the academic year alone.
    """
    cursor.execute(
        """
        UPDATE semesters
        SET is_active = FALSE
        WHERE is_active = TRUE
          AND end_date IS NOT NULL
          AND end_date < CURDATE()
        """
    )

    cursor.execute(
        """
        SELECT COUNT(*) AS active_count
        FROM semesters
        WHERE is_active = TRUE
          AND course_code IN ('COMP4200', 'COMP4300')
          AND (start_date IS NULL OR start_date <= CURDATE())
          AND (end_date IS NULL OR end_date >= CURDATE())
        """
    )
    active_count = int((cursor.fetchone() or {}).get("active_count") or 0)
    if active_count > 0:
        return

    cursor.execute(
        """
        SELECT academic_year, semester_number
        FROM semesters
        WHERE start_date IS NOT NULL
          AND end_date IS NOT NULL
          AND start_date <= CURDATE()
          AND end_date >= CURDATE()
          AND course_code IN ('COMP4200', 'COMP4300')
        ORDER BY start_date DESC, semester_id DESC
        LIMIT 1
        """
    )
    next_term = cursor.fetchone()
    if not next_term:
        return

    cursor.execute("UPDATE semesters SET is_active = FALSE")
    cursor.execute(
        """
        UPDATE semesters
        SET is_active = TRUE
        WHERE academic_year = %s
          AND semester_number = %s
          AND course_code IN ('COMP4200', 'COMP4300')
        """,
        (next_term["academic_year"], next_term["semester_number"]),
    )
