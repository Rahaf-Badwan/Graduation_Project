def auto_rollover_semesters(cursor):
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
          AND (start_date IS NULL OR start_date <= CURDATE())
          AND (end_date IS NULL OR end_date >= CURDATE())
        """
    )
    active_count = int((cursor.fetchone() or {}).get("active_count") or 0)
    if active_count > 0:
        return

    cursor.execute(
        """
        SELECT academic_year
        FROM semesters
        WHERE start_date IS NOT NULL
          AND end_date IS NOT NULL
          AND start_date <= CURDATE()
          AND end_date >= CURDATE()
        ORDER BY start_date DESC, semester_id DESC
        LIMIT 1
        """
    )
    next_year = cursor.fetchone()
    if not next_year:
        return

    cursor.execute("UPDATE semesters SET is_active = FALSE")
    cursor.execute(
        """
        UPDATE semesters
        SET is_active = TRUE
        WHERE academic_year = %s
          AND course_code IN ('COMP4200', 'COMP4300')
        """,
        (next_year["academic_year"],),
    )
