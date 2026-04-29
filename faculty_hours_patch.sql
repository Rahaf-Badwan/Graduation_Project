USE apms_db;
CREATE TABLE IF NOT EXISTS faculty_load_settings (
    load_id INT PRIMARY KEY AUTO_INCREMENT,
    faculty_id INT NOT NULL,
    semester_id INT NOT NULL,
    base_hours DECIMAL(5,2) NOT NULL DEFAULT 12,
    max_hours DECIMAL(5,2) NOT NULL DEFAULT 18,
    employment_type ENUM('full_time', 'part_time') NOT NULL DEFAULT 'full_time',
    intro_sections INT NOT NULL DEFAULT 0,
    extra_bonus INT NOT NULL DEFAULT 1,
    assigned_courses TEXT NULL,
    updated_by INT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_faculty_semester_load (faculty_id, semester_id),
    CONSTRAINT fk_load_faculty FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
    CONSTRAINT fk_load_semester FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
    CONSTRAINT fk_load_updated_by FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL
);

INSERT INTO faculty_load_settings (faculty_id, semester_id, base_hours, max_hours, employment_type, intro_sections, extra_bonus, assigned_courses, updated_by)
SELECT
    f.faculty_id,
    s.semester_id,
    12,
    18,
    'full_time',
    0,
    1,
    'COMP4200 - Project Introduction, COMP4300 - Graduation Projects',
    2
FROM faculty f
JOIN users u ON u.user_id = f.user_id
JOIN semesters s ON s.is_active = TRUE
WHERE u.role IN ('supervisor', 'coordinator', 'head_of_department')
AND NOT EXISTS (
    SELECT 1
    FROM faculty_load_settings fls
    WHERE fls.faculty_id = f.faculty_id
      AND fls.semester_id = s.semester_id
);