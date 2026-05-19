-- ============================================================
--  APMS FULL SQL — CLEANED VERSION
--  Fixed by ChatGPT: safe rerun, no project deletion, views for real projects
-- ============================================================

-- ============================================================
--  APMS — Academic Project Management System
--  Birzeit University · Department of Computer Science
--  Full MySQL Database Schema + Sample Data
--  Version 2.0 · April 2026
--  Merged: APMS.sql + AI_ARCHIVE_MIGRATION.sql
-- ============================================================

CREATE DATABASE IF NOT EXISTS apms_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE apms_db;

SET SQL_SAFE_UPDATES = 0;
SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;

-- Drop all tables if they exist (safe re-run)
-- Extra drops added for tables that appear later in this full file.
-- FOREIGN_KEY_CHECKS is already OFF, so rerun will not fail on dependencies.
DROP TABLE IF EXISTS project_report_readers;
DROP TABLE IF EXISTS project_final_evaluation_results;
DROP TABLE IF EXISTS project_grade_entries;
DROP TABLE IF EXISTS project_evaluation_windows;
DROP TABLE IF EXISTS grade_entries;
DROP TABLE IF EXISTS grade_entry_sessions;
DROP TABLE IF EXISTS committee_plan_projects;
DROP TABLE IF EXISTS committee_plan_members;
DROP TABLE IF EXISTS committee_plans;
DROP TABLE IF EXISTS discussion_rooms;
DROP TABLE IF EXISTS announcements;
DROP TABLE IF EXISTS system_notices;
DROP TABLE IF EXISTS section_students;
DROP TABLE IF EXISTS student_distribution_sections;
DROP TABLE IF EXISTS faculty_load_settings;
DROP TABLE IF EXISTS student_groups;

DROP TABLE IF EXISTS milestone_submissions;
DROP TABLE IF EXISTS comp4200_timeline_items;
DROP TABLE IF EXISTS comp4200_timelines;
DROP TABLE IF EXISTS coordinator_deliverable_submissions;
DROP TABLE IF EXISTS coordinator_deliverables;
DROP TABLE IF EXISTS coordinator_lectures;
DROP TABLE IF EXISTS section_completion_status;
DROP TABLE IF EXISTS ai_conversations;
DROP TABLE IF EXISTS challenges_reflections;
DROP TABLE IF EXISTS supervisor_assignments;
DROP TABLE IF EXISTS notifications;
DROP TABLE IF EXISTS student_course_results;
DROP TABLE IF EXISTS deadlines;
DROP TABLE IF EXISTS supervisor_notes;
DROP TABLE IF EXISTS final_decisions;
DROP TABLE IF EXISTS coordinator_decisions;
DROP TABLE IF EXISTS committee_members;
DROP TABLE IF EXISTS committees;
DROP TABLE IF EXISTS feedback_improvement_points;
DROP TABLE IF EXISTS feedback;
DROP TABLE IF EXISTS project_lifecycle;
DROP TABLE IF EXISTS project_progress;
DROP TABLE IF EXISTS project_files;
DROP TABLE IF EXISTS project_members;
DROP TABLE IF EXISTS projects;
DROP TABLE IF EXISTS coordinator_assignments;
DROP TABLE IF EXISTS students;
DROP TABLE IF EXISTS faculty;
DROP TABLE IF EXISTS semesters;
DROP TABLE IF EXISTS password_reset_tokens;
DROP TABLE IF EXISTS users;

-- ============================================================
--  TABLE 1 — users
--  All system users regardless of role
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    user_id        INT            PRIMARY KEY AUTO_INCREMENT,
    university_id  VARCHAR(20)    UNIQUE NOT NULL          COMMENT 'University ID number',
    full_name      VARCHAR(120)   NOT NULL,
    email          VARCHAR(150)   UNIQUE NOT NULL,
    password_hash  VARCHAR(255)   NOT NULL,
    role           ENUM(
                     'student',
                     'supervisor',
                     'coordinator',
                     'head_of_department'
                   )              NOT NULL,
    avatar_initials VARCHAR(5)    NULL                     COMMENT 'Avatar initials for display',
    is_active      BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                           ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 2 — faculty
--  Extra data for supervisors, coordinators, head
-- ============================================================
CREATE TABLE IF NOT EXISTS faculty (
    faculty_id       INT   PRIMARY KEY AUTO_INCREMENT,
    user_id          INT   UNIQUE NOT NULL,
    specialization   ENUM(
                       'software_engineering',
                       'artificial_intelligence',
                       'web_development',
                       'mobile',
                       'security_networks',
                       'databases',
                       'other'
                     )     NOT NULL,
    years_experience TINYINT UNSIGNED DEFAULT 0,
    title            VARCHAR(30) DEFAULT 'Dr.'              COMMENT 'Academic title (e.g. Dr., Prof.)',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 3 — students
--  Extra data for student users
-- ============================================================
CREATE TABLE IF NOT EXISTS students (
    student_id      INT  PRIMARY KEY AUTO_INCREMENT,
    user_id         INT  UNIQUE NOT NULL,
    enrollment_year YEAR NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 4 — semesters
--  Academic semesters (COMP4200 course)
-- ============================================================
CREATE TABLE IF NOT EXISTS semesters (
    semester_id      INT          PRIMARY KEY AUTO_INCREMENT,
    academic_year    VARCHAR(20)  NOT NULL                COMMENT 'e.g. 2025/2026',
    semester_number  TINYINT      NOT NULL                COMMENT '1 or 2',
    course_code      VARCHAR(20)  NOT NULL DEFAULT 'COMP4200',
    start_date       DATE         NULL,
    end_date         DATE         NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE KEY uq_semester (academic_year, semester_number)
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 5 — coordinator_assignments
--  Head assigns one coordinator per semester
-- ============================================================
CREATE TABLE IF NOT EXISTS coordinator_assignments (
    assignment_id INT       PRIMARY KEY AUTO_INCREMENT,
    faculty_id    INT       NOT NULL                      COMMENT 'Assigned coordinator faculty_id',
    semester_id   INT       NOT NULL,
    assigned_by   INT       NOT NULL                      COMMENT 'Head of department user_id',
    notes         TEXT      NULL,
    assigned_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_coordinator_semester (semester_id),
    FOREIGN KEY (faculty_id)  REFERENCES faculty(faculty_id),
    FOREIGN KEY (semester_id) REFERENCES semesters(semester_id),
    FOREIGN KEY (assigned_by) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 6 — projects
--  Core project entity
-- ============================================================
CREATE TABLE IF NOT EXISTS projects (
    project_id        INT             PRIMARY KEY AUTO_INCREMENT,
    title             VARCHAR(300)    NOT NULL,
    title_en          VARCHAR(300)    NULL,
    abstract          TEXT            NULL,
    keywords          VARCHAR(600)    NULL,
    project_type      SET(
                        'web',
                        'mobile',
                        'ai',
                        'software_engineering',
                        'security',
                        'databases',
                        'other'
                      )               NOT NULL,
    semester_id       INT             NOT NULL,
    supervisor_id     INT             NULL,
    status            ENUM(
                        'draft',
                        'submitted',
                        'under_review',
                        'needs_revision',
                        'committee_evaluation',
                        'accepted',
                        'rejected',
                        'archived'
                      )               NOT NULL DEFAULT 'draft',
    submission_date   DATE            NULL,
    coordinator_notes TEXT            NULL,
    rejection_reason  TEXT            NULL,
    final_score       DECIMAL(5,2)    NULL     COMMENT 'Final score out of 100',
    created_at        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP
                                               ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (semester_id)   REFERENCES semesters(semester_id),
    FOREIGN KEY (supervisor_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 7 — project_members
--  Team members for each project (up to ~3 students)
-- ============================================================
CREATE TABLE IF NOT EXISTS project_members (
    member_id          INT      PRIMARY KEY AUTO_INCREMENT,
    project_id         INT      NOT NULL,
    student_id         INT      NOT NULL,
    is_primary_contact BOOLEAN  NOT NULL DEFAULT FALSE    COMMENT 'Primary contact for the project',
    joined_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_project_student (project_id, student_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id)  ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(student_id)  ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 8 — project_files
--  Files uploaded for each project (report, code, slides)
-- ============================================================
CREATE TABLE IF NOT EXISTS project_files (
    file_id       INT             PRIMARY KEY AUTO_INCREMENT,
    project_id    INT             NOT NULL,
    file_type     ENUM(
                    'final_report',
                    'source_code',
                    'presentation',
                    'other'
                  )               NOT NULL,
    file_name     VARCHAR(255)    NOT NULL,
    file_path     VARCHAR(600)    NULL,
    file_data     LONGBLOB        NULL                    COMMENT 'Binary file content stored in DB',
    file_mime     VARCHAR(100)    NULL                    COMMENT 'MIME type of the uploaded file',
    file_size_mb  DECIMAL(7,2)    NULL,
    upload_status ENUM(
                    'not_uploaded',
                    'uploaded',
                    'required'
                  )               NOT NULL DEFAULT 'not_uploaded',
    uploaded_by   INT             NULL                    COMMENT 'student user_id',
    uploaded_at   TIMESTAMP       NULL,
    version       TINYINT         NOT NULL DEFAULT 1,
    UNIQUE KEY uq_project_file_type (project_id, file_type),
    FOREIGN KEY (project_id)  REFERENCES projects(project_id)  ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id)        ON DELETE SET NULL
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 9 — project_progress
--  Completion percentage per component and overall
-- ============================================================
CREATE TABLE IF NOT EXISTS project_progress (
    progress_id INT     PRIMARY KEY AUTO_INCREMENT,
    project_id  INT     NOT NULL,
    component   ENUM(
                  'final_report',
                  'source_code',
                  'presentation',
                  'overall'
                )       NOT NULL,
    percentage  TINYINT NOT NULL DEFAULT 0
                        CHECK (percentage BETWEEN 0 AND 100),
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                          ON UPDATE CURRENT_TIMESTAMP,
    updated_by  INT     NULL,
    UNIQUE KEY uq_project_component (project_id, component),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 10 — project_lifecycle
--  Tracks each stage of a project's lifecycle
-- ============================================================
CREATE TABLE IF NOT EXISTS project_lifecycle (
    lifecycle_id   INT  PRIMARY KEY AUTO_INCREMENT,
    project_id     INT  NOT NULL,
    stage          ENUM(
                     'registration',
                     'file_submission',
                     'initial_review',
                     'supervisor_review',
                     'committee_evaluation',
                     'final_result',
                     'archiving'
                   )    NOT NULL,
    status         ENUM(
                     'pending',
                     'in_progress',
                     'completed',
                     'skipped'
                   )    NOT NULL DEFAULT 'pending',
    scheduled_date DATE NULL,
    completed_date DATE NULL,
    notes          TEXT NULL,
    UNIQUE KEY uq_project_stage (project_id, stage),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 11 — feedback
--  Feedback from supervisors and committee members
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id   INT             PRIMARY KEY AUTO_INCREMENT,
    project_id    INT             NOT NULL,
    reviewer_id   INT             NOT NULL                COMMENT 'Reviewer user_id',
    feedback_type ENUM(
                    'final_report_review',
                    'source_code_review',
                    'general_performance',
                    'discussion_notes',
                    'follow_up',
                    'committee_evaluation'
                  )               NOT NULL,
    feedback_text TEXT            NOT NULL,
    score         DECIMAL(5,2)    NULL                    COMMENT 'Score out of 100',
    priority      ENUM(
                    'normal',
                    'important',
                    'urgent'
                  )               NOT NULL DEFAULT 'normal',
    is_draft      BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id)  REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (reviewer_id) REFERENCES users(user_id)       ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 12 — feedback_improvement_points
--  Action items / improvement points attached to feedback
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback_improvement_points (
    point_id    INT          PRIMARY KEY AUTO_INCREMENT,
    feedback_id INT          NOT NULL,
    point_text  VARCHAR(600) NOT NULL,
    is_resolved BOOLEAN      NOT NULL DEFAULT FALSE,
    FOREIGN KEY (feedback_id) REFERENCES feedback(feedback_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 13 — committees
--  Evaluation committee for each project
-- ============================================================
CREATE TABLE IF NOT EXISTS committees (
    committee_id      INT         PRIMARY KEY AUTO_INCREMENT,
    project_id        INT         UNIQUE NOT NULL,
    committee_name    VARCHAR(255) NULL,
    discussion_date   DATE        NOT NULL,
    discussion_time   TIME        NULL,
    room              VARCHAR(100) NULL,
    status            ENUM(
                        'scheduled',
                        'in_progress',
                        'completed',
                        'cancelled'
                      )           NOT NULL DEFAULT 'scheduled',
    final_average     DECIMAL(5,2) NULL    COMMENT 'Average score from all committee members',
    created_by        INT         NOT NULL COMMENT 'coordinator user_id',
    created_at        TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id)  REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by)  REFERENCES users(user_id)
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 14 — committee_members
--  Faculty members of each evaluation committee
-- ============================================================
CREATE TABLE IF NOT EXISTS committee_members (
    cm_id                   INT          PRIMARY KEY AUTO_INCREMENT,
    committee_id            INT          NOT NULL,
    faculty_id              INT          NOT NULL,
    role                    ENUM(
                              'supervisor',
                              'member',
                              'chair'
                            )            NOT NULL DEFAULT 'member',
    evaluation_score        DECIMAL(5,2) NULL,
    evaluation_comments     TEXT         NULL,
    evaluation_submitted    BOOLEAN      NOT NULL DEFAULT FALSE,
    evaluation_submitted_at TIMESTAMP    NULL,
    UNIQUE KEY uq_committee_faculty (committee_id, faculty_id),
    FOREIGN KEY (committee_id) REFERENCES committees(committee_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id)   REFERENCES faculty(faculty_id)      ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 15 — coordinator_decisions
--  Coordinator actions on projects (accept / reject / revise)
-- ============================================================
CREATE TABLE IF NOT EXISTS coordinator_decisions (
    decision_id    INT       PRIMARY KEY AUTO_INCREMENT,
    project_id     INT       NOT NULL,
    coordinator_id INT       NOT NULL COMMENT 'user_id',
    decision       ENUM(
                     'accepted',
                     'rejected',
                     'needs_revision',
                     'send_to_committee'
                   )         NOT NULL,
    notes          TEXT      NULL,
    decided_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id)     REFERENCES projects(project_id)  ON DELETE CASCADE,
    FOREIGN KEY (coordinator_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 16 — final_decisions
--  Coordinator final decision after committee evaluation
-- ============================================================
CREATE TABLE IF NOT EXISTS final_decisions (
    decision_id    INT          PRIMARY KEY AUTO_INCREMENT,
    project_id     INT          UNIQUE NOT NULL,
    coordinator_id INT          NOT NULL COMMENT 'user_id',
    decision       ENUM(
                     'accepted',
                     'rejected'
                   )            NOT NULL,
    final_score    DECIMAL(5,2) NULL,
    notes          TEXT         NULL,
    decided_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_archived    BOOLEAN      NOT NULL DEFAULT FALSE,
    archived_at    TIMESTAMP    NULL,
    FOREIGN KEY (project_id)     REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (coordinator_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 17 — supervisor_notes
--  Follow-up notes a supervisor adds to a project
-- ============================================================
CREATE TABLE IF NOT EXISTS supervisor_notes (
    note_id      INT       PRIMARY KEY AUTO_INCREMENT,
    project_id   INT       NOT NULL,
    supervisor_id INT      NOT NULL COMMENT 'faculty_id',
    note_text    TEXT      NOT NULL,
    urgency      ENUM(
                   'on_track',
                   'needs_follow_up',
                   'urgent'
                 )         NOT NULL DEFAULT 'on_track',
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id)    REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (supervisor_id) REFERENCES faculty(faculty_id)  ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 18 — deadlines
--  Important dates per semester or per individual project
-- ============================================================
CREATE TABLE IF NOT EXISTS deadlines (
    deadline_id   INT          PRIMARY KEY AUTO_INCREMENT,
    semester_id   INT          NOT NULL,
    project_id    INT          NULL    COMMENT 'NULL = applies to whole semester',
    deadline_type VARCHAR(120) NOT NULL COMMENT 'e.g. final_report_submission',
    deadline_date DATE         NOT NULL,
    description   VARCHAR(500) NULL,
    FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id)  REFERENCES projects(project_id)   ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 19 — notifications
-- ============================================================
CREATE TABLE IF NOT EXISTS notifications (
    notification_id    INT          PRIMARY KEY AUTO_INCREMENT,
    recipient_id       INT          NOT NULL COMMENT 'user_id',
    sender_id          INT          NULL     COMMENT 'user_id or NULL for system',
    notification_type  ENUM(
                         'file_uploaded',
                         'feedback_received',
                         'committee_assigned',
                         'deadline_reminder',
                         'project_reviewed',
                         'status_changed',
                         'supervisor_assigned',
                         'urgent_alert',
                         'system'
                       )            NOT NULL,
    title              VARCHAR(250) NOT NULL,
    message            TEXT         NOT NULL,
    related_project_id INT          NULL,
    is_read            BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (recipient_id)       REFERENCES users(user_id)    ON DELETE CASCADE,
    FOREIGN KEY (sender_id)          REFERENCES users(user_id)    ON DELETE SET NULL,
    FOREIGN KEY (related_project_id) REFERENCES projects(project_id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 20 — challenges_reflections
--  Student-submitted challenges & lessons learned
-- ============================================================
CREATE TABLE IF NOT EXISTS challenges_reflections (
    challenge_id    INT       PRIMARY KEY AUTO_INCREMENT,
    project_id      INT       NOT NULL,
    student_id      INT       NOT NULL COMMENT 'user_id',
    type            ENUM(
                      'technical',
                      'administrative',
                      'reflection'
                    )         NOT NULL,
    title           VARCHAR(255) NOT NULL COMMENT 'Short title for the challenge or reflection',
    description     TEXT      NOT NULL,
    solution_lesson TEXT      NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(user_id)       ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 21 — supervisor_assignments
--  Head assigns a supervisor to a pending student group
-- ============================================================
CREATE TABLE IF NOT EXISTS supervisor_assignments (
    sa_id        INT       PRIMARY KEY AUTO_INCREMENT,
    faculty_id   INT       NOT NULL,
    project_id   INT       NOT NULL,
    semester_id  INT       NOT NULL,
    assigned_by  INT       NOT NULL COMMENT 'head of department user_id',
    notes        TEXT      NULL,
    assigned_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (faculty_id)  REFERENCES faculty(faculty_id)   ON DELETE RESTRICT,
    FOREIGN KEY (project_id)  REFERENCES projects(project_id)  ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(semester_id),
    FOREIGN KEY (assigned_by) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 22 — student_groups
--  Groups students into teams for duplicate-submission checks
-- ============================================================
CREATE TABLE IF NOT EXISTS student_groups (
    group_id    INT NOT NULL  COMMENT 'Shared group identifier for teammates',
    student_id  INT NOT NULL,
    PRIMARY KEY (group_id, student_id),
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='Maps students to their project groups for duplicate-submission checks';

-- ============================================================
--  TABLE 23 — ai_conversations
--  AI assistant chat history per user
--  Merged from: APMS.sql + AI_ARCHIVE_MIGRATION.sql
--  • session_id is NOT NULL (migration applied)
--  • Includes both indexes from the migration
-- ============================================================
CREATE TABLE IF NOT EXISTS ai_conversations (
    conv_id      INT           PRIMARY KEY AUTO_INCREMENT,
    user_id      INT           NOT NULL,
    session_id   VARCHAR(120)  NOT NULL COMMENT 'Client-generated conversation session ID',
    message_role ENUM(
                   'user',
                   'assistant'
                 )             NOT NULL,
    message_text MEDIUMTEXT    NOT NULL,
    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_ai_user_session (user_id, session_id, created_at),
    INDEX idx_ai_created (created_at)
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 23 — password_reset_tokens
--  Temporary tokens for password reset (valid for 1 hour)
-- ============================================================
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token_id    INT           PRIMARY KEY AUTO_INCREMENT,
    user_id     INT           NOT NULL,
    token       VARCHAR(100)  NOT NULL UNIQUE,
    expires_at  DATETIME      NOT NULL,
    used        BOOLEAN       NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_token   (token),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
--  INDEXES
-- ============================================================
CREATE INDEX idx_projects_semester   ON projects(semester_id);
CREATE INDEX idx_projects_supervisor ON projects(supervisor_id);
CREATE INDEX idx_projects_status     ON projects(status);
CREATE INDEX idx_feedback_project    ON feedback(project_id);
CREATE INDEX idx_feedback_reviewer   ON feedback(reviewer_id);
CREATE INDEX idx_notif_recipient     ON notifications(recipient_id, is_read);
CREATE INDEX idx_notif_project       ON notifications(related_project_id);
CREATE INDEX idx_members_project     ON project_members(project_id);
CREATE INDEX idx_members_student     ON project_members(student_id);
CREATE INDEX idx_files_project       ON project_files(project_id, file_type);
CREATE INDEX idx_lifecycle_project   ON project_lifecycle(project_id, stage);

-- ============================================================
--  VIEWS
-- ============================================================

-- Summary view per project
CREATE OR REPLACE VIEW vw_project_summary AS
SELECT
    p.project_id,
    p.title,
    p.title_en,
    p.project_type,
    p.status,
    p.submission_date,
    p.final_score,
    s.academic_year,
    s.semester_number,
    s.course_code,
    u_sup.full_name          AS supervisor_name,
    f_sup.specialization     AS supervisor_specialization,
    pp_overall.percentage    AS overall_progress,
    pp_report.percentage     AS report_progress,
    pp_code.percentage       AS code_progress,
    pp_slides.percentage     AS slides_progress,
    COUNT(DISTINCT pm.student_id) AS team_size
FROM projects p
JOIN semesters s       ON s.semester_id     = p.semester_id
LEFT JOIN faculty  f_sup  ON f_sup.faculty_id  = p.supervisor_id
LEFT JOIN users    u_sup  ON u_sup.user_id     = f_sup.user_id
LEFT JOIN project_members pm ON pm.project_id  = p.project_id
LEFT JOIN project_progress pp_overall ON pp_overall.project_id = p.project_id
                                     AND pp_overall.component  = 'overall'
LEFT JOIN project_progress pp_report  ON pp_report.project_id  = p.project_id
                                     AND pp_report.component   = 'final_report'
LEFT JOIN project_progress pp_code    ON pp_code.project_id    = p.project_id
                                     AND pp_code.component     = 'source_code'
LEFT JOIN project_progress pp_slides  ON pp_slides.project_id  = p.project_id
                                     AND pp_slides.component   = 'presentation'
GROUP BY p.project_id;

-- Supervisor performance view
CREATE OR REPLACE VIEW vw_supervisor_performance AS
SELECT
    f.faculty_id,
    u.full_name,
    f.specialization,
    f.years_experience,
    s.academic_year,
    COUNT(DISTINCT p.project_id)   AS total_projects,
    AVG(p.final_score)             AS avg_score,
    SUM(p.status = 'accepted')     AS accepted_count,
    SUM(p.status = 'rejected')     AS rejected_count
FROM faculty f
JOIN users u ON u.user_id = f.user_id
LEFT JOIN projects p  ON p.supervisor_id = f.faculty_id
LEFT JOIN semesters s ON s.semester_id   = p.semester_id
WHERE u.role = 'supervisor'
GROUP BY f.faculty_id, s.academic_year;

-- Committee results view
CREATE OR REPLACE VIEW vw_committee_results AS
SELECT
    c.committee_id,
    c.project_id,
    p.title                         AS project_title,
    c.discussion_date,
    c.discussion_time,
    c.room,
    c.status,
    c.final_average,
    COUNT(cm.cm_id)                  AS member_count,
    SUM(cm.evaluation_submitted)     AS evaluations_submitted
FROM committees c
JOIN projects p ON p.project_id = c.project_id
LEFT JOIN committee_members cm ON cm.committee_id = c.committee_id
GROUP BY c.committee_id;

-- ============================================================
--  SAMPLE DATA  (all text in English)
--  ID scheme:
--    Students    → 7-digit IDs starting from 1220000
--                  Email: {university_id}@students.birzeit.edu
--    Faculty     → 4-digit IDs starting from 1001
--                  Email: {university_id}@birzeit.edu
-- ============================================================

-- Semesters
INSERT IGNORE INTO semesters (academic_year, semester_number, course_code, start_date, end_date, is_active) VALUES
('2025/2026', 1, 'COMP4200', '2025-09-01', '2026-02-28', TRUE),
('2024/2025', 1, 'COMP4200', '2024-09-01', '2025-02-28', FALSE),
('2023/2024', 1, 'COMP4200', '2023-09-01', '2024-02-28', FALSE),
('2022/2023', 1, 'COMP4200', '2022-09-01', '2023-02-28', FALSE);

-- Users
-- Faculty IDs are 4 digits (1001–1007); student IDs start from 1220000
INSERT IGNORE INTO users (university_id, full_name, email, password_hash, role, avatar_initials, is_active) VALUES
-- Head of Department  (ID: 1001)
('1001', 'Dr. Iyad Jaber',          '1001@birzeit.edu', '$2b$12$EbPsSfvh6ScacL2l4uCkdOMwbfukrx0EdkL/0GBk/ntRtwRapvvBu',  'head_of_department', 'IJ', TRUE),
-- Coordinator         (ID: 1002)
('1002', 'Dr. Ruba Awadallah',      '1002@birzeit.edu', '$2b$12$l9Jz.shLtccTVJh5r700w.kCUlmwlba4YgUvs2HZGs2UBwuoonMci', 'coordinator',        'RA', TRUE),
-- Supervisors from the provided doctors list
('1003', 'Dr. Sobhi Ahmad',         '1003@birzeit.edu', '$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.',   'supervisor',         'SA', TRUE),
('1004', 'Dr. Radi Jarrar',         '1004@birzeit.edu', '$2b$12$ctwodGi2uo7.QC.r7Qlt.u5n6wVvy280mQ/LtyaIlIjQLIVpgB/MW',   'supervisor',         'RJ', TRUE),
('1005', 'Dr. Abdullah Krakeh',     '1005@birzeit.edu', '$2b$12$aKMFBXAIvKSNsOAUpU9N8.oYnCqeu07VJc/PBgyB.H7WIxxc4ew9C',   'supervisor',         'AK', TRUE),
('1006', 'Dr. Mamoun Nawahdah',     '1006@birzeit.edu', '$2b$12$ljZY7r8ALYi62IyesXQ84uieyNMz2MXVJK.QI4Eu7ot9abWAa7TAG',   'supervisor',         'MN', TRUE),
('1007', 'Dr. Hafez Barghouthi',    '1007@birzeit.edu', '$2b$12$.Uge.NmsvHbi9uSDgc1rhOYjO3Q1HAtYCLeN3YL1ctrGUKeRKo1ti',   'supervisor',         'HB', TRUE),
-- Students            (IDs: 1220xxx)
('1220654', 'Rahaf Badwan',         '1220654@students.birzeit.edu', '$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.', 'student', 'RB', TRUE),
('1220670', 'Amna Abu Muslim',      '1220670@students.birzeit.edu', '$2b$12$1ONCgGY62binf5lUfYs6qekRIUhkUObqIs55tu.89rGMGOAsp0Llu', 'student', 'AM', TRUE),
('1220174', 'Tima Abd',             '1220174@students.birzeit.edu', '$2b$12$OxHQ1TKrYWOQ6UUw8pN15.APXR8zjzAvrJkpUPpnkDtJFPPAo92Z.', 'student', 'TA', TRUE),
('1220110', 'Salma Al-Khatib',      '1220110@students.birzeit.edu', '$2b$12$vMKQhyFzsLAXJkchac2KyeS4L2N.cw9AWHSCnwupz/cfc8s3Tf43a', 'student', 'SK', TRUE),
('1220087', 'Karim Odeh',           '1220087@students.birzeit.edu', '$2b$12$aXSk8fIneFnOLmEnPH72CetVM9RwKecmo6YySgL8Td0V5M/ZNC6YC', 'student', 'KO', TRUE),
('1220500', 'Amjad Al-Rimawi',      '1220500@students.birzeit.edu', '$2b$12$KBaKlbUt93mL9.oY1xrFQ.U.kCXt2eqAOdTZDdWOGiKWm0AOPsjem', 'student', 'AR', TRUE),
('1220600', 'Sara Musa',            '1220600@students.birzeit.edu', '$2b$12$x46jpXoonqATaqjWSIZwvO4Mnx39j4YFAsl6TAxhw7m6xwbA4j3BK', 'student', 'SM', TRUE),
('1220700', 'Khaled Mansour',       '1220700@students.birzeit.edu', '$2b$12$UZ02VkxW0l/XRWRu/T5ireQ5fiRfRdS0IiRzxe5RlfqnSLAe59A9O', 'student', 'KM', TRUE),
('1220800', 'Dana Ibrahim',         '1220800@students.birzeit.edu', '$2b$12$km.HzoX0aw6nFjI2m3U8sezhKNDXZh7IBlpH.CEwqZx/ZSEv2DYqy', 'student', 'DI', TRUE),
('1220900', 'Mona Nassar',          '1220900@students.birzeit.edu', '$2b$12$m/RTVrKRx.lsECFuFa6yguuR1rRxZO8i0QAxQun/7ojQZjq6M7D3G', 'student', 'MN', TRUE);


ALTER TABLE semesters
ADD COLUMN distribution_open TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE semesters
ADD COLUMN distribution_opened_at DATETIME NULL;

ALTER TABLE semesters
ADD COLUMN distribution_closed_at DATETIME NULL;


-- Faculty records (user_ids 1–7 match insertion order above)
INSERT IGNORE INTO faculty (user_id, specialization, years_experience, title) VALUES
(1, 'software_engineering',    15, 'Dr.'),
(2, 'web_development',         10, 'Dr.'),
(3, 'software_engineering',     8, 'Dr.'),
(4, 'software_engineering',     8, 'Dr.'),
(5, 'databases',                8, 'Dr.'),
(6, 'mobile',                   8, 'Dr.'),
(7, 'security_networks',        8, 'Dr.');

-- Student records (user_ids 8–17)
INSERT IGNORE INTO students (user_id, enrollment_year) VALUES
( 8, 2022),  -- Rahaf Badwan
( 9, 2022),  -- Amna Abu Muslim
(10, 2022),  -- Tima Abd
(11, 2022),  -- Salma Al-Khatib
(12, 2022),  -- Karim Odeh
(13, 2021),  -- Amjad Al-Rimawi
(14, 2022),  -- Sara Musa
(15, 2022),  -- Khaled Mansour
(16, 2021),  -- Dana Ibrahim
(17, 2022);  -- Mona Nassar

-- Coordinator Assignment (faculty_id 2 = Dr. Ahmad, semester 1, assigned by user 1 = Prof. Raed)
INSERT IGNORE INTO coordinator_assignments (faculty_id, semester_id, assigned_by, notes) VALUES
(2, 1, 1, 'Official coordinator for Semester 1 — 2025/2026');

-- Project Members
INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES
-- Project 1: APMS team
(1, 2, FALSE),   -- Amna Abu Muslim
(1, 1, TRUE),    -- Rahaf Badwan (primary contact)
(1, 3, FALSE),   -- Tima Abd
-- Other projects
(2, 4, TRUE),    -- Salma Al-Khatib
(3, 5, TRUE),    -- Karim Odeh
(4, 6, TRUE),    -- Amjad Al-Rimawi
(5, 7, TRUE),    -- Sara Musa
(6, 8, TRUE),    -- Khaled Mansour
(9, 8, FALSE);   -- Khaled Mansour (also on project 9)

-- Project Files
-- (no seed files — students upload via the application)

-- Project Progress
INSERT IGNORE INTO project_progress (project_id, component, percentage, updated_by) VALUES
-- APMS
(1, 'final_report', 85, 3),
(1, 'source_code',  70, 3),
(1, 'presentation', 60, 3),
(1, 'overall',      78, 3),
-- Smart Delivery App
(3, 'final_report', 55, 5),
(3, 'source_code',  48, 5),
(3, 'overall',      31, 5);

-- Project Lifecycle
INSERT IGNORE INTO project_lifecycle (project_id, stage, status, scheduled_date, completed_date, notes) VALUES
-- APMS (project 1) — currently in initial review
(1, 'registration',         'completed',   '2026-01-25', '2026-01-25', 'Project registered successfully'),
(1, 'file_submission',      'completed',   '2026-02-01', '2026-02-01', 'Report and source code uploaded — slides still required'),
(1, 'initial_review',       'in_progress', '2026-02-03', NULL,         'Supervisor Dr. Naima is reviewing the final report; feedback expected within 48 hours'),
(1, 'supervisor_review',    'pending',     NULL,         NULL,         NULL),
(1, 'committee_evaluation', 'pending',     '2026-02-20', NULL,         NULL),
(1, 'final_result',         'pending',     '2026-02-28', NULL,         NULL),
(1, 'archiving',            'pending',     NULL,         NULL,         NULL),
-- AI Disease System (project 4) — fully completed
(4, 'registration',         'completed', '2025-01-15', '2025-01-15', NULL),
(4, 'file_submission',      'completed', '2025-02-01', '2025-02-01', NULL),
(4, 'initial_review',       'completed', '2025-02-05', '2025-02-05', NULL),
(4, 'committee_evaluation', 'completed', '2025-02-21', '2025-02-21', NULL),
(4, 'final_result',         'completed', '2025-02-28', '2025-02-28', NULL),
(4, 'archiving',            'completed', '2025-03-01', '2025-03-01', NULL);

-- Feedback
INSERT IGNORE INTO feedback (project_id, reviewer_id, feedback_type, feedback_text, score, priority, is_draft) VALUES
-- Supervisor feedback on APMS (reviewer = user 3, Dr. Naima)
(
  1, 3, 'final_report_review',
  'The report is generally well-written. I recommend clarifying the system architecture section further and adding detailed ERD diagrams. Please also ensure consistent use of technical terminology across all chapters.',
  78.00, 'important', FALSE
),
-- Committee member feedback on APMS (reviewer = user 4, Dr. Mahmoud)
(
  1, 4, 'committee_evaluation',
  'The AI section needs more detail, particularly regarding the chatbot training methodology and accuracy evaluation. I recommend adding a comparison table of the NLP models used.',
  75.00, 'normal', FALSE
),
-- Committee member feedback on APMS (reviewer = user 5, Dr. Lina)
(
  1, 5, 'committee_evaluation',
  'The proposed UI is well thought out and appropriate. I recommend addressing accessibility requirements (WCAG) and adding support for users with special needs.',
  82.00, 'normal', FALSE
),
-- Supervisor feedback on Student Records (reviewer = user 4, Dr. Mahmoud)
(
  2, 4, 'source_code_review',
  'The code is well-structured, but you need to add documentation comments to all major functions and write unit tests for sensitive operations such as authentication and role checking.',
  71.00, 'normal', FALSE
);

-- Feedback Improvement Points
INSERT IGNORE INTO feedback_improvement_points (feedback_id, point_text, is_resolved) VALUES
(1, 'Expand system architecture section with detailed ERD diagrams',       FALSE),
(1, 'Ensure consistent technical terminology across all chapters',         FALSE),
(2, 'Detail the chatbot training methodology and accuracy evaluation',     FALSE),
(2, 'Add a comparison table of NLP models used',                           FALSE),
(3, 'Implement WCAG accessibility standards in the UI',                    FALSE),
(3, 'Upload presentation slides before February 15',                       FALSE);

-- Committees
INSERT IGNORE INTO committees (project_id, committee_name, discussion_date, discussion_time, room, status, final_average, created_by) VALUES
(1, 'APMS Evaluation Committee',                     '2026-02-20', '10:00:00', 'A101', 'scheduled',  NULL,  2),
(4, 'AI Disease Recognition Evaluation Committee',   '2025-02-21', '14:00:00', 'B203', 'completed', 92.30,  2),
(5, 'E-Learning Platform Evaluation Committee',      '2024-02-22', '10:00:00', 'C105', 'completed', 87.00,  2);

-- Committee Members
INSERT IGNORE INTO committee_members (committee_id, faculty_id, role, evaluation_score, evaluation_comments, evaluation_submitted, evaluation_submitted_at) VALUES
-- Committee 1: APMS (scheduled — evaluations not yet submitted)
(1, 3, 'supervisor', NULL, NULL, FALSE, NULL),
(1, 4, 'member',     NULL, NULL, FALSE, NULL),
(1, 5, 'member',     NULL, NULL, FALSE, NULL),
(1, 6, 'member',     NULL, NULL, FALSE, NULL),
(1, 7, 'member',     NULL, NULL, FALSE, NULL),
-- Committee 2: AI Disease Recognition (completed)
(2, 4, 'supervisor', 92.00, 'Excellent implementation of CNN models with high accuracy results.',      TRUE, '2025-02-21 16:00:00'),
(2, 3, 'member',     93.00, 'Outstanding documentation and strong experimental results.',              TRUE, '2025-02-21 16:30:00'),
(2, 5, 'member',     91.00, 'Professional and clean user interface design.',                           TRUE, '2025-02-21 17:00:00'),
(2, 6, 'member',     93.50, 'Solid and well-normalized database architecture.',                        TRUE, '2025-02-21 17:30:00'),
(2, 7, 'member',     92.00, 'Security standards are well applied throughout the system.',              TRUE, '2025-02-21 18:00:00');

-- Supervisor Notes
INSERT IGNORE INTO supervisor_notes (project_id, supervisor_id, note_text, urgency) VALUES
(1, 3, 'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.', 'on_track'),
(3, 5, 'No files have been uploaded for two weeks — requires immediate follow-up.',                                                   'urgent'),
(2, 4, 'Progress is slightly slow but still within acceptable range. Awaiting source code update.',                                   'needs_follow_up');

-- Coordinator Decisions
INSERT IGNORE INTO coordinator_decisions (project_id, coordinator_id, decision, notes) VALUES
(4, 2, 'send_to_committee', 'Project accepted and forwarded to committee evaluation after a satisfactory initial review.'),
(5, 2, 'accepted',          'Excellent project — archiving completed successfully.'),
(7, 2, 'rejected',          'Project score is below the minimum required threshold of 60%.'),
(6, 2, 'needs_revision',    'Student must add a security and privacy section and clarify the patient data protection protocol.');

-- Final Decisions
INSERT IGNORE INTO final_decisions (project_id, coordinator_id, decision, final_score, notes, is_archived, archived_at) VALUES
(4, 2, 'accepted', 92.30, 'Outstanding project — archived successfully.',          TRUE,  '2025-03-01 09:00:00'),
(5, 2, 'accepted', 87.00, 'Very good project — archived successfully.',             TRUE,  '2024-03-01 09:00:00'),
(7, 2, 'rejected', 54.00, 'Score below minimum threshold — student notified.',      FALSE, NULL);

-- Deadlines
INSERT IGNORE INTO deadlines (semester_id, project_id, deadline_type, deadline_date, description) VALUES
(1, NULL, 'project_registration',    '2026-02-15', 'Deadline for all project registrations'),
(1, NULL, 'file_submission',         '2026-02-15', 'Deadline for uploading all required project files'),
(1, NULL, 'results_announcement',    '2026-02-28', 'Final results announcement date'),
(1, 1,    'final_report_submission', '2026-02-15', 'Final report submission deadline — APMS project'),
(1, 1,    'committee_discussion',    '2026-02-20', 'APMS project committee discussion date'),
(1, 1,    'supervisor_feedback',     '2026-02-08', 'Deadline for supervisor feedback on APMS report');

-- Notifications
INSERT IGNORE INTO notifications (recipient_id, sender_id, notification_type, title, message, related_project_id, is_read) VALUES
-- Student (Rahaf, user 8) notifications
(8, 3,    'feedback_received',  'Your project has been reviewed',          'Dr. Sobhi Ahmad has submitted new feedback on your project.',             1, FALSE),
(8, 2,    'committee_assigned', 'Committee discussion scheduled',          'Your project discussion is scheduled for February 20 at 10:00 AM.',         1, FALSE),
(8, NULL, 'deadline_reminder',  'Reminder: Upload source code',            'Please upload the source code files before February 15.',                   1, FALSE),
-- Supervisor (Dr. Naima, user 3) notifications
(3, 8,    'file_uploaded',      'Rahaf Badwan uploaded updated files',     'A new version of the final report has been uploaded — APMS project.',       1, FALSE),
(3, 2,    'committee_assigned', 'New committee membership assigned',       'You have been assigned as a member of a new evaluation committee.',          1, FALSE),
(3, NULL, 'urgent_alert',       'Karim Odeh — urgent follow-up needed',   'Karim Odeh has not uploaded any files for two weeks.',                       3, FALSE),
-- Coordinator (Dr. Ahmad, user 2) notifications
(2, NULL, 'file_uploaded',      'New project pending your review',         'Electronic Student Records Management System — Salma Al-Khatib.',            2, FALSE),
(2, 4,    'project_reviewed',   'Dr. Radi Jarrar completed evaluations', 'Dr. Radi Jarrar completed 3 project evaluations — avg score: 89.3.',      NULL, FALSE),
(2, NULL, 'deadline_reminder',  '7 projects awaiting your decision',       '7 projects are pending coordinator review — some exceeded 48 hours.',       NULL, TRUE);

-- ============================================================
--  STORED PROCEDURES
-- ============================================================

DELIMITER $$

-- Drop procedures if they exist
DROP PROCEDURE IF EXISTS sp_calculate_committee_average$$
DROP PROCEDURE IF EXISTS sp_submit_committee_evaluation$$
DROP PROCEDURE IF EXISTS sp_get_project_details$$

-- Calculate and update final committee average
CREATE PROCEDURE sp_calculate_committee_average(IN p_committee_id INT)
BEGIN
    DECLARE v_avg DECIMAL(5,2);

    SELECT AVG(evaluation_score)
    INTO   v_avg
    FROM   committee_members
    WHERE  committee_id        = p_committee_id
      AND  evaluation_submitted = TRUE;

    UPDATE committees
    SET    final_average = v_avg
    WHERE  committee_id  = p_committee_id;

    UPDATE projects p
    JOIN   committees c ON c.project_id = p.project_id
    SET    p.final_score = v_avg
    WHERE  c.committee_id = p_committee_id;
END$$

-- Submit a committee member evaluation
CREATE PROCEDURE sp_submit_committee_evaluation(
    IN p_committee_id   INT,
    IN p_faculty_id     INT,
    IN p_score          DECIMAL(5,2),
    IN p_comments       TEXT
)
BEGIN
    UPDATE committee_members
    SET    evaluation_score        = p_score,
           evaluation_comments     = p_comments,
           evaluation_submitted    = TRUE,
           evaluation_submitted_at = NOW()
    WHERE  committee_id = p_committee_id
      AND  faculty_id   = p_faculty_id;

    -- Recalculate average if all members submitted
    IF (
        SELECT COUNT(*) FROM committee_members
        WHERE committee_id = p_committee_id AND evaluation_submitted = FALSE
    ) = 0 THEN
        CALL sp_calculate_committee_average(p_committee_id);
    END IF;
END$$

-- Get full project details
CREATE PROCEDURE sp_get_project_details(IN p_project_id INT)
BEGIN
    SELECT * FROM vw_project_summary WHERE project_id = p_project_id;

    SELECT u.full_name, u.university_id
    FROM   project_members pm
    JOIN   students st ON st.student_id = pm.student_id
    JOIN   users    u  ON u.user_id     = st.user_id
    WHERE  pm.project_id = p_project_id;

    SELECT * FROM project_files     WHERE project_id = p_project_id;
    SELECT * FROM project_lifecycle WHERE project_id = p_project_id ORDER BY FIELD(stage,'registration','file_submission','initial_review','supervisor_review','committee_evaluation','final_result','archiving');
    SELECT f.*, u.full_name AS reviewer_name, u.role AS reviewer_role
    FROM   feedback f
    JOIN   users    u ON u.user_id = f.reviewer_id
    WHERE  f.project_id = p_project_id
    ORDER BY f.created_at DESC;
END$$

DELIMITER ;

-- ============================================================
--  TRIGGERS
-- ============================================================

DELIMITER $$

-- Drop triggers if they exist
DROP TRIGGER IF EXISTS trg_notify_on_feedback$$
DROP TRIGGER IF EXISTS trg_notify_on_status_change$$

-- Auto-notify student on new feedback
CREATE TRIGGER trg_notify_on_feedback
AFTER INSERT ON feedback
FOR EACH ROW
BEGIN
    DECLARE v_student_user_id INT;
    DECLARE v_reviewer_name   VARCHAR(120);

    SELECT u.full_name INTO v_reviewer_name
    FROM users u WHERE u.user_id = NEW.reviewer_id;

    -- Notify all students in the project
    INSERT IGNORE INTO notifications (recipient_id, sender_id, notification_type, title, message, related_project_id)
    SELECT st.user_id,
           NEW.reviewer_id,
           'feedback_received',
           'New feedback on your project',
           CONCAT(v_reviewer_name, ' has submitted new feedback on your project.'),
           NEW.project_id
    FROM   project_members pm
    JOIN   students st ON st.student_id = pm.student_id
    WHERE  pm.project_id = NEW.project_id;
END$$

-- Auto-notify team when project status changes
CREATE TRIGGER trg_notify_on_status_change
AFTER UPDATE ON projects
FOR EACH ROW
BEGIN
    IF OLD.status <> NEW.status THEN
        INSERT IGNORE INTO notifications (recipient_id, sender_id, notification_type, title, message, related_project_id)
        SELECT st.user_id,
               NULL,
               'status_changed',
               'Project status updated',
               CONCAT('Your project status has changed to: ', NEW.status),
               NEW.project_id
        FROM   project_members pm
        JOIN   students st ON st.student_id = pm.student_id
        WHERE  pm.project_id = NEW.project_id;
    END IF;
END$$

DELIMITER ;

-- ============================================================
--  AI CONVERSATIONS CLEANUP
--  Merged from: AI_ARCHIVE_MIGRATION.sql
--  Deletes all sessions whose first message is older than 30 days.
--  Run this block manually whenever a cleanup is needed,
--  or schedule it via a MySQL Event (requires Event Scheduler ON).
-- ============================================================

-- One-time cleanup on import (removes sessions older than 30 days)
SET SQL_SAFE_UPDATES = 0;

DELETE ac
FROM ai_conversations ac
JOIN (
    SELECT session_id
    FROM (
        SELECT session_id
        FROM ai_conversations
        GROUP BY session_id
        HAVING MIN(created_at) < (UTC_TIMESTAMP() - INTERVAL 30 DAY)
    ) expired_sessions
) expired ON expired.session_id = ac.session_id;

SET SQL_SAFE_UPDATES = 0;

-- Optional: Scheduled Event for automatic monthly cleanup
-- Uncomment the block below if your MySQL server has the Event Scheduler enabled
-- (SET GLOBAL event_scheduler = ON;)
--
-- DROP EVENT IF EXISTS evt_cleanup_ai_conversations;
-- DELIMITER $$
-- CREATE EVENT evt_cleanup_ai_conversations
--   ON SCHEDULE EVERY 1 DAY
--   STARTS CURRENT_TIMESTAMP
--   DO
--   BEGIN
--     DELETE ac
--     FROM ai_conversations ac
--     JOIN (
--         SELECT session_id
--         FROM (
--             SELECT session_id
--             FROM ai_conversations
--             GROUP BY session_id
--             HAVING MIN(created_at) < (UTC_TIMESTAMP() - INTERVAL 30 DAY)
--         ) expired_sessions
--     ) expired ON expired.session_id = ac.session_id;
--   END$$
-- DELIMITER ;

-- ============================================================
--  END OF SCHEMA

-- ============================================================
--  ASSIGN ROLE — COMP4300 Data
--  Adds second course (COMP4300) semester, coordinator
--  assignment, and sample projects for the Assign Roles page.
--  Merged from: assign_role_migration.sql
--  Uses NOT EXISTS guards to ensure safe re-run on any DB.
-- ============================================================

-- ── 1. COMP4300 Semester ─────────────────────────────────────────────────
INSERT IGNORE INTO semesters (academic_year, semester_number, course_code, start_date, end_date, is_active)
VALUES ('2025/2026', 2, 'COMP4300', '2026-03-01', '2026-07-01', TRUE);

-- ── 2. Coordinator for COMP4300 (Dr. Abdullah Krakeh, faculty_id=5) ─────────
--       Assigned by Prof. Raed (user_id=1). Skipped if already assigned.
INSERT IGNORE INTO coordinator_assignments (faculty_id, semester_id, assigned_by, notes)
SELECT
    5,
    s.semester_id,
    1,
    'Coordinator for COMP4300 — 2025/2026 Semester 2'
FROM semesters s
WHERE s.course_code    = 'COMP4300'
  AND s.academic_year  = '2025/2026'
  AND s.semester_number = 2
  AND NOT EXISTS (
      SELECT 1 FROM coordinator_assignments ca
      WHERE ca.semester_id = s.semester_id
  )
LIMIT 1;

-- ── 3. Sample Projects for COMP4300 (doctors overview panel) ─────────────

-- Dr. Radi Jarrar (faculty_id = 4)
INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT
    'Advanced AI Decision System', 'ai', s.semester_id, 4, 'submitted', CURDATE()
FROM semesters s
WHERE s.course_code   = 'COMP4300'
  AND s.academic_year = '2025/2026'
  AND NOT EXISTS (
      SELECT 1 FROM projects p
      WHERE p.supervisor_id = 4
        AND p.semester_id   = s.semester_id
        AND p.title         = 'Advanced AI Decision System'
  )
LIMIT 1;

-- Dr. Abdullah Krakeh (faculty_id = 5)
INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT
    'Enterprise Web Platform', 'web', s.semester_id, 5, 'submitted', CURDATE()
FROM semesters s
WHERE s.course_code   = 'COMP4300'
  AND s.academic_year = '2025/2026'
  AND NOT EXISTS (
      SELECT 1 FROM projects p
      WHERE p.supervisor_id = 5
        AND p.semester_id   = s.semester_id
        AND p.title         = 'Enterprise Web Platform'
  )
LIMIT 1;

-- Dr. Hafez Barghouthi (faculty_id = 7)
INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT
    'Cyber Security Audit Platform', 'security', s.semester_id, 7, 'submitted', CURDATE()
FROM semesters s
WHERE s.course_code   = 'COMP4300'
  AND s.academic_year = '2025/2026'
  AND NOT EXISTS (
      SELECT 1 FROM projects p
      WHERE p.supervisor_id = 7
        AND p.semester_id   = s.semester_id
        AND p.title         = 'Cyber Security Audit Platform'
  )
LIMIT 1;


-- ============================================================
--  END OF FILE
-- ============================================================

-- ============================================================
-- APPENDED MYSQL-COMPATIBLE DISTRIBUTION / FACULTY LOAD / DOCTORS MIGRATION
-- ============================================================

USE apms_db;

SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- 1) semesters: distribution window columns
-- ============================================================

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'semesters'
      AND COLUMN_NAME = 'distribution_open'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE semesters ADD COLUMN distribution_open TINYINT(1) NOT NULL DEFAULT 0',
    'SELECT "distribution_open already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'semesters'
      AND COLUMN_NAME = 'distribution_opened_at'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE semesters ADD COLUMN distribution_opened_at DATETIME NULL',
    'SELECT "distribution_opened_at already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'semesters'
      AND COLUMN_NAME = 'distribution_closed_at'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE semesters ADD COLUMN distribution_closed_at DATETIME NULL',
    'SELECT "distribution_closed_at already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================
-- 2) projects: preferred supervisors
-- ============================================================

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'projects'
      AND COLUMN_NAME = 'preferred_supervisor_1'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE projects ADD COLUMN preferred_supervisor_1 INT NULL AFTER supervisor_id',
    'SELECT "preferred_supervisor_1 already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'projects'
      AND COLUMN_NAME = 'preferred_supervisor_2'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE projects ADD COLUMN preferred_supervisor_2 INT NULL AFTER preferred_supervisor_1',
    'SELECT "preferred_supervisor_2 already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'projects'
      AND COLUMN_NAME = 'preferred_supervisor_3'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE projects ADD COLUMN preferred_supervisor_3 INT NULL AFTER preferred_supervisor_2',
    'SELECT "preferred_supervisor_3 already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'projects'
      AND CONSTRAINT_NAME = 'fk_projects_pref_sup_1'
);
SET @sql = IF(
    @fk_exists = 0,
    'ALTER TABLE projects ADD CONSTRAINT fk_projects_pref_sup_1 FOREIGN KEY (preferred_supervisor_1) REFERENCES faculty(faculty_id) ON DELETE SET NULL',
    'SELECT "fk_projects_pref_sup_1 already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'projects'
      AND CONSTRAINT_NAME = 'fk_projects_pref_sup_2'
);
SET @sql = IF(
    @fk_exists = 0,
    'ALTER TABLE projects ADD CONSTRAINT fk_projects_pref_sup_2 FOREIGN KEY (preferred_supervisor_2) REFERENCES faculty(faculty_id) ON DELETE SET NULL',
    'SELECT "fk_projects_pref_sup_2 already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @fk_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'projects'
      AND CONSTRAINT_NAME = 'fk_projects_pref_sup_3'
);
SET @sql = IF(
    @fk_exists = 0,
    'ALTER TABLE projects ADD CONSTRAINT fk_projects_pref_sup_3 FOREIGN KEY (preferred_supervisor_3) REFERENCES faculty(faculty_id) ON DELETE SET NULL',
    'SELECT "fk_projects_pref_sup_3 already exists"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================
-- 3) student distribution tables
-- ============================================================

CREATE TABLE IF NOT EXISTS student_distribution_sections (
    section_id     INT PRIMARY KEY AUTO_INCREMENT,
    section_name   VARCHAR(100) NOT NULL,
    supervisor_id  INT NOT NULL,
    entered_by     INT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supervisor_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
    FOREIGN KEY (entered_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS section_students (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    section_id  INT NOT NULL,
    student_id  INT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_section_student (section_id, student_id),
    FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 4) faculty yearly load settings
-- ============================================================

CREATE TABLE IF NOT EXISTS faculty_load_settings (
    load_id                   INT PRIMARY KEY AUTO_INCREMENT,
    faculty_id                INT NOT NULL,
    semester_id               INT NOT NULL,
    graduation_project_hours  DECIMAL(5,2) NOT NULL DEFAULT 0,
    min_hours                 DECIMAL(5,2) NOT NULL DEFAULT 12,
    max_hours                 DECIMAL(5,2) NOT NULL DEFAULT 36,
    employment_type           ENUM('full_time','part_time') NOT NULL DEFAULT 'full_time',
    intro_students            INT NOT NULL DEFAULT 0,
    extra_bonus               DECIMAL(5,2) NOT NULL DEFAULT 0,
    assigned_courses          TEXT NULL,
    updated_by       INT NULL,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_faculty_semester_load (faculty_id, semester_id),
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
    FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 5) ONLY COMP4200 + COMP4300 DOCTORS IN ENGLISH
--    Names are taken from the COMP4200 / COMP4300 schedule list.
--    Safe re-run: inserts only if the doctor does not already exist.
-- ============================================================

SET @pwd := '$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.';

INSERT IGNORE INTO users
(university_id, full_name, email, password_hash, role, avatar_initials, is_active)
SELECT * FROM (
    SELECT '3002' AS university_id, 'Dr. Sobhi Ahmad' AS full_name, 'sobhi.ahmad@birzeit.edu' AS email, @pwd AS password_hash, 'supervisor' AS role, 'SA' AS avatar_initials, TRUE AS is_active
    UNION ALL SELECT '3003', 'Dr. Radi Jarrar', 'radi.jarrar@birzeit.edu', @pwd, 'supervisor', 'RJ', TRUE
    UNION ALL SELECT '3004', 'Dr. Abdullah Krakeh', 'abdullah.krakeh@birzeit.edu', @pwd, 'supervisor', 'AK', TRUE
    UNION ALL SELECT '3006', 'Dr. Murad Njoum', 'murad.njoum@birzeit.edu', @pwd, 'supervisor', 'MN', TRUE
    UNION ALL SELECT '3007', 'Dr. Adel Taweel', 'adel.taweel@birzeit.edu', @pwd, 'supervisor', 'AT', TRUE
    UNION ALL SELECT '3008', 'Dr. Yousef Hassouneh', 'yousef.hassouneh@birzeit.edu', @pwd, 'supervisor', 'YH', TRUE
    UNION ALL SELECT '3009', 'Dr. Ruba Awadallah', 'ahmad.abusneina@birzeit.edu', @pwd, 'supervisor', 'AS', TRUE
    UNION ALL SELECT '3010', 'Dr. Bassem Alserafi', 'bassem.alserafi@birzeit.edu', @pwd, 'supervisor', 'BA', TRUE
    UNION ALL SELECT '3011', 'Dr. Mamoun Nawahdah', 'mamoun.nawahdah@birzeit.edu', @pwd, 'supervisor', 'MN', TRUE
    UNION ALL SELECT '3012', 'Dr. Tasneem Zayt', 'tasneem.zayt@birzeit.edu', @pwd, 'supervisor', 'TZ', TRUE
    UNION ALL SELECT '3013', 'Dr. Samer Zein', 'samer.zein@birzeit.edu', @pwd, 'supervisor', 'SZ', TRUE
    UNION ALL SELECT '3014', 'Dr. Hafez Barghouthi', 'hafez.barghouthi@birzeit.edu', @pwd, 'supervisor', 'HB', TRUE
    UNION ALL SELECT '3015', 'Dr. Abdullah Al-Natsheh', 'abdullah.alnatsheh@birzeit.edu', @pwd, 'supervisor', 'AN', TRUE
    UNION ALL SELECT '3016', 'Dr. Alaa Hasheesh', 'alaa.hasheesh@birzeit.edu', @pwd, 'supervisor', 'AH', TRUE
    UNION ALL SELECT '3017', 'Dr. Faisal Shehadeh', 'faisal.shehadeh@birzeit.edu', @pwd, 'supervisor', 'FS', TRUE
    UNION ALL SELECT '3018', 'Dr. Fadi Khalil', 'fadi.khalil@birzeit.edu', @pwd, 'supervisor', 'FK', TRUE
    UNION ALL SELECT '3019', 'Dr. Mohammad Helal', 'mohammad.helal@birzeit.edu', @pwd, 'supervisor', 'MH', TRUE
    UNION ALL SELECT '3020', 'Dr. Rashid Yousef', 'rashid.yousef@birzeit.edu', @pwd, 'supervisor', 'RY', TRUE
    UNION ALL SELECT '3021', 'Dr. Ehab Alshaer', 'ehab.alshaer@birzeit.edu', @pwd, 'supervisor', 'EA', TRUE
    UNION ALL SELECT '3022', 'Dr. Sobhi Ahmad', 'naima.harbawi@birzeit.edu', @pwd, 'supervisor', 'NH', TRUE
    UNION ALL SELECT '3023', 'Dr. Ahmad Fahl', 'ahmad.fahl@birzeit.edu', @pwd, 'supervisor', 'AF', TRUE
    UNION ALL SELECT '3024', 'Dr. Ahmad Sabbah', 'ahmad.sabbah@birzeit.edu', @pwd, 'supervisor', 'AS', TRUE
    UNION ALL SELECT '3025', 'Dr. Mohammad Alkhanafseh', 'mohammad.alkhanafseh@birzeit.edu', @pwd, 'supervisor', 'MA', TRUE
) AS doctors
WHERE NOT EXISTS (
    SELECT 1
    FROM users u
    WHERE u.full_name = doctors.full_name
       OR u.email = doctors.email
       OR u.university_id = doctors.university_id
);

INSERT IGNORE INTO faculty
(user_id, specialization, years_experience, title)
SELECT
    u.user_id,
    CASE u.full_name
        WHEN 'Dr. Iyad Jaber' THEN 'software_engineering'
        WHEN 'Dr. Sobhi Ahmad' THEN 'software_engineering'
        WHEN 'Dr. Radi Jarrar' THEN 'software_engineering'
        WHEN 'Dr. Abdullah Krakeh' THEN 'databases'
        WHEN 'Dr. Ruba Awadallah' THEN 'web_development'
        WHEN 'Dr. Murad Njoum' THEN 'databases'
        WHEN 'Dr. Adel Taweel' THEN 'software_engineering'
        WHEN 'Dr. Yousef Hassouneh' THEN 'web_development'
        WHEN 'Dr. Ruba Awadallah' THEN 'software_engineering'
        WHEN 'Dr. Bassem Alserafi' THEN 'databases'
        WHEN 'Dr. Mamoun Nawahdah' THEN 'mobile'
        WHEN 'Dr. Tasneem Zayt' THEN 'software_engineering'
        WHEN 'Dr. Samer Zein' THEN 'software_engineering'
        WHEN 'Dr. Hafez Barghouthi' THEN 'security_networks'
        WHEN 'Dr. Abdullah Al-Natsheh' THEN 'software_engineering'
        WHEN 'Dr. Alaa Hasheesh' THEN 'software_engineering'
        WHEN 'Dr. Faisal Shehadeh' THEN 'mobile'
        WHEN 'Dr. Fadi Khalil' THEN 'web_development'
        WHEN 'Dr. Mohammad Helal' THEN 'artificial_intelligence'
        WHEN 'Dr. Rashid Yousef' THEN 'software_engineering'
        WHEN 'Dr. Ehab Alshaer' THEN 'software_engineering'
        WHEN 'Dr. Sobhi Ahmad' THEN 'software_engineering'
        WHEN 'Dr. Ahmad Fahl' THEN 'software_engineering'
        WHEN 'Dr. Ahmad Sabbah' THEN 'artificial_intelligence'
        WHEN 'Dr. Mohammad Alkhanafseh' THEN 'security_networks'
        ELSE 'software_engineering'
    END AS specialization,
    8 AS years_experience,
    'Dr.' AS title
FROM users u
LEFT JOIN faculty f ON f.user_id = u.user_id
WHERE u.full_name IN (
    'Dr. Iyad Jaber',
    'Dr. Sobhi Ahmad',
    'Dr. Radi Jarrar',
    'Dr. Abdullah Krakeh',
    'Dr. Ruba Awadallah',
    'Dr. Murad Njoum',
    'Dr. Adel Taweel',
    'Dr. Yousef Hassouneh',
    'Dr. Ruba Awadallah',
    'Dr. Bassem Alserafi',
    'Dr. Mamoun Nawahdah',
    'Dr. Tasneem Zayt',
    'Dr. Samer Zein',
    'Dr. Hafez Barghouthi',
    'Dr. Abdullah Al-Natsheh',
    'Dr. Alaa Hasheesh',
    'Dr. Faisal Shehadeh',
    'Dr. Fadi Khalil',
    'Dr. Mohammad Helal',
    'Dr. Rashid Yousef',
    'Dr. Ehab Alshaer',
    'Dr. Sobhi Ahmad',
    'Dr. Ahmad Fahl',
    'Dr. Ahmad Sabbah',
    'Dr. Mohammad Alkhanafseh'
)
AND f.user_id IS NULL;

-- Keep existing rows aligned if the doctor already existed before this import.
UPDATE faculty f
JOIN users u ON u.user_id = f.user_id
SET f.specialization = CASE u.full_name
        WHEN 'Dr. Iyad Jaber' THEN 'software_engineering'
        WHEN 'Dr. Sobhi Ahmad' THEN 'software_engineering'
        WHEN 'Dr. Radi Jarrar' THEN 'software_engineering'
        WHEN 'Dr. Abdullah Krakeh' THEN 'databases'
        WHEN 'Dr. Ruba Awadallah' THEN 'web_development'
        WHEN 'Dr. Murad Njoum' THEN 'databases'
        WHEN 'Dr. Adel Taweel' THEN 'software_engineering'
        WHEN 'Dr. Yousef Hassouneh' THEN 'web_development'
        WHEN 'Dr. Ruba Awadallah' THEN 'software_engineering'
        WHEN 'Dr. Bassem Alserafi' THEN 'databases'
        WHEN 'Dr. Mamoun Nawahdah' THEN 'mobile'
        WHEN 'Dr. Tasneem Zayt' THEN 'software_engineering'
        WHEN 'Dr. Samer Zein' THEN 'software_engineering'
        WHEN 'Dr. Hafez Barghouthi' THEN 'security_networks'
        WHEN 'Dr. Abdullah Al-Natsheh' THEN 'software_engineering'
        WHEN 'Dr. Alaa Hasheesh' THEN 'software_engineering'
        WHEN 'Dr. Faisal Shehadeh' THEN 'mobile'
        WHEN 'Dr. Fadi Khalil' THEN 'web_development'
        WHEN 'Dr. Mohammad Helal' THEN 'artificial_intelligence'
        WHEN 'Dr. Rashid Yousef' THEN 'software_engineering'
        WHEN 'Dr. Ehab Alshaer' THEN 'software_engineering'
        WHEN 'Dr. Sobhi Ahmad' THEN 'software_engineering'
        WHEN 'Dr. Ahmad Fahl' THEN 'software_engineering'
        WHEN 'Dr. Ahmad Sabbah' THEN 'artificial_intelligence'
        WHEN 'Dr. Mohammad Alkhanafseh' THEN 'security_networks'
        ELSE f.specialization
    END,
    f.title = 'Dr.'
WHERE u.full_name IN (
    'Dr. Iyad Jaber',
    'Dr. Sobhi Ahmad',
    'Dr. Radi Jarrar',
    'Dr. Abdullah Krakeh',
    'Dr. Ruba Awadallah',
    'Dr. Murad Njoum',
    'Dr. Adel Taweel',
    'Dr. Yousef Hassouneh',
    'Dr. Ruba Awadallah',
    'Dr. Bassem Alserafi',
    'Dr. Mamoun Nawahdah',
    'Dr. Tasneem Zayt',
    'Dr. Samer Zein',
    'Dr. Hafez Barghouthi',
    'Dr. Abdullah Al-Natsheh',
    'Dr. Alaa Hasheesh',
    'Dr. Faisal Shehadeh',
    'Dr. Fadi Khalil',
    'Dr. Mohammad Helal',
    'Dr. Rashid Yousef',
    'Dr. Ehab Alshaer',
    'Dr. Sobhi Ahmad',
    'Dr. Ahmad Fahl',
    'Dr. Ahmad Sabbah',
    'Dr. Mohammad Alkhanafseh'
);

-- ============================================================
-- 6) Helpful verification
-- ============================================================

SELECT 'COMP4200/COMP4300 doctors migration completed successfully' AS status;

SELECT u.full_name, u.role, u.university_id, u.email, f.specialization
FROM users u
JOIN faculty f ON f.user_id = u.user_id
WHERE u.full_name IN (
    'Dr. Iyad Jaber',
    'Dr. Sobhi Ahmad',
    'Dr. Radi Jarrar',
    'Dr. Abdullah Krakeh',
    'Dr. Ruba Awadallah',
    'Dr. Murad Njoum',
    'Dr. Adel Taweel',
    'Dr. Yousef Hassouneh',
    'Dr. Ruba Awadallah',
    'Dr. Bassem Alserafi',
    'Dr. Mamoun Nawahdah',
    'Dr. Tasneem Zayt',
    'Dr. Samer Zein',
    'Dr. Hafez Barghouthi',
    'Dr. Abdullah Al-Natsheh',
    'Dr. Alaa Hasheesh',
    'Dr. Faisal Shehadeh',
    'Dr. Fadi Khalil',
    'Dr. Mohammad Helal',
    'Dr. Rashid Yousef',
    'Dr. Ehab Alshaer',
    'Dr. Sobhi Ahmad',
    'Dr. Ahmad Fahl',
    'Dr. Ahmad Sabbah',
    'Dr. Mohammad Alkhanafseh'
)
ORDER BY u.full_name;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
--  ADDITIONAL FACULTY MIGRATION REMOVED
--  Replaced by the COMP4200 + COMP4300 doctors-only English list above.
-- ============================================================

-- ============================================================
--  MIGRATION: student_course_results
--  Purpose: Shared table storing each student's result in COMP4200
--           Used by the coordinator (write) and head (read + promote)
--  Version 1.0 · May 2026
-- ============================================================

-- ============================================================
-- 1) Base Table: student_course_results
-- ============================================================
CREATE TABLE IF NOT EXISTS student_course_results (

    result_id               INT           PRIMARY KEY AUTO_INCREMENT,
    student_id              INT           NOT NULL
                                          COMMENT 'Foreign key from students table',
    semester_id             INT           NOT NULL
                                          COMMENT 'The semester in which the student is evaluated (COMP4200)',

    status                  ENUM('pending','passed','failed')
                                          NOT NULL DEFAULT 'pending',

    updated_by              INT           NULL
                                          COMMENT 'user_id of the coordinator',
    notes                   TEXT          NULL,

    promoted_to_semester_id INT           NULL
                                          COMMENT 'semester_id for COMP4300 after passing',
    promoted_by             INT           NULL
                                          COMMENT 'user_id of the head who promoted the student',
    promoted_at             TIMESTAMP     NULL
                                          COMMENT 'Actual promotion timestamp',

    created_at              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_student_semester (student_id, semester_id),

    FOREIGN KEY (student_id)
        REFERENCES students(student_id)   ON DELETE CASCADE,
    FOREIGN KEY (semester_id)
        REFERENCES semesters(semester_id) ON DELETE RESTRICT,
    FOREIGN KEY (updated_by)
        REFERENCES users(user_id)         ON DELETE SET NULL,
    FOREIGN KEY (promoted_to_semester_id)
        REFERENCES semesters(semester_id) ON DELETE SET NULL,
    FOREIGN KEY (promoted_by)
        REFERENCES users(user_id)         ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Student results in COMP4200 — shared between coordinator and head';

-- ============================================================
-- 2) Indexes
-- ============================================================
CREATE INDEX idx_scr_semester
    ON student_course_results(semester_id, status);

CREATE INDEX idx_scr_passed_not_promoted
    ON student_course_results(status, promoted_at);

-- ============================================================
-- 3) View for Coordinator: All students + their results
-- ============================================================
CREATE OR REPLACE VIEW vw_coordinator_student_results AS
SELECT
    scr.result_id,
    st.student_id,
    u.user_id,
    u.full_name          AS student_name,
    u.university_id,
    u.email,
    s_comp.academic_year,
    s_comp.course_code   AS comp_course,
    scr.semester_id,
    scr.status,
    scr.notes,
    scr.updated_at       AS result_updated_at,
    u_coord.full_name    AS updated_by_name,
    CASE
        WHEN scr.promoted_at IS NOT NULL THEN 'Promoted'
        WHEN scr.status = 'passed'       THEN 'Passed - Not Promoted Yet'
        ELSE NULL
    END                  AS promotion_status
FROM students st
JOIN users u                   ON u.user_id    = st.user_id
LEFT JOIN student_course_results scr
    ON scr.student_id          = st.student_id
LEFT JOIN semesters s_comp     ON s_comp.semester_id = scr.semester_id
LEFT JOIN users u_coord        ON u_coord.user_id    = scr.updated_by
ORDER BY u.full_name;

-- ============================================================
-- 4) View for Head: Passed students eligible for promotion
-- ============================================================
CREATE OR REPLACE VIEW vw_head_pending_promotion AS
SELECT
    scr.result_id,
    u.full_name          AS student_name,
    u.university_id,
    u.email,
    s_comp.academic_year,
    s_comp.course_code   AS from_course,
    s_next.course_code   AS to_course,
    s_next.semester_id   AS comp4300_semester_id,
    scr.status,
    scr.notes
FROM student_course_results scr
JOIN students st               ON st.student_id  = scr.student_id
JOIN users    u                ON u.user_id      = st.user_id
JOIN semesters s_comp          ON s_comp.semester_id = scr.semester_id
LEFT JOIN semesters s_next
    ON s_next.academic_year    = s_comp.academic_year
   AND s_next.course_code      = 'COMP4300'
WHERE scr.status               = 'passed'
  AND scr.promoted_at          IS NULL
ORDER BY u.full_name;

-- ============================================================
-- 5) Stored Procedure: Coordinator records a student's result
-- ============================================================
DROP PROCEDURE IF EXISTS sp_coordinator_set_result;

DELIMITER $$

CREATE PROCEDURE sp_coordinator_set_result (
    IN  p_student_id     INT,
    IN  p_semester_id    INT,
    IN  p_status         ENUM('pending','passed','failed'),
    IN  p_coordinator_id INT,
    IN  p_notes          TEXT
)
BEGIN
    INSERT INTO student_course_results
        (student_id, semester_id, status, updated_by, notes)
    VALUES
        (p_student_id, p_semester_id, p_status, p_coordinator_id, p_notes)
    ON DUPLICATE KEY UPDATE
        status     = p_status,
        updated_by = p_coordinator_id,
        notes      = p_notes;

    INSERT IGNORE INTO notifications
        (recipient_id, sender_id, notification_type, title, message)
    SELECT
        u.user_id,
        p_coordinator_id,
        'status_changed',
        CASE p_status
            WHEN 'passed' THEN 'Congratulations! You have passed COMP4200'
            WHEN 'failed' THEN 'COMP4200 Result'
            ELSE 'COMP4200 Result Update'
        END,
        CASE p_status
            WHEN 'passed' THEN 'You have successfully passed COMP4200 and will be moving to COMP4300 soon.'
            WHEN 'failed' THEN CONCAT('COMP4200 Result: Failed. ', IFNULL(p_notes, ''))
            ELSE 'Your result in COMP4200 has been updated.'
        END
    FROM students st
    JOIN users u ON u.user_id = st.user_id
    WHERE st.student_id = p_student_id;

    SELECT 'Result saved successfully' AS result;
END$$

DELIMITER ;

-- ============================================================
-- 6) Stored Procedure: Head promotes a passed student to COMP4300
-- ============================================================
DROP PROCEDURE IF EXISTS sp_head_promote_student;

DELIMITER $$

CREATE PROCEDURE sp_head_promote_student (
    IN  p_result_id             INT,
    IN  p_head_user_id          INT,
    IN  p_comp4300_semester_id  INT
)
BEGIN
    DECLARE v_student_id INT;
    DECLARE v_status     VARCHAR(20);

    SELECT student_id, status
    INTO   v_student_id, v_status
    FROM   student_course_results
    WHERE  result_id = p_result_id;

    IF v_status != 'passed' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Cannot promote a student who has not passed';
    END IF;

    UPDATE student_course_results
    SET
        promoted_to_semester_id = p_comp4300_semester_id,
        promoted_by             = p_head_user_id,
        promoted_at             = NOW()
    WHERE result_id = p_result_id;

    INSERT IGNORE INTO notifications
        (recipient_id, sender_id, notification_type, title, message)
    SELECT
        u.user_id,
        p_head_user_id,
        'status_changed',
        'You have officially been moved to COMP4300',
        'Congratulations! You have been successfully promoted to COMP4300 for the upcoming semester.'
    FROM students st
    JOIN users u ON u.user_id = st.user_id
    WHERE st.student_id = v_student_id;

    SELECT 'Student promoted successfully' AS result;
END$$

DELIMITER ;

-- ============================================================
-- 7) Seed Data: pending for all students in the active semester
-- ============================================================
INSERT INTO student_course_results (student_id, semester_id, status)
SELECT
    st.student_id,
    s.semester_id,
    'pending'
FROM students st
CROSS JOIN semesters s
WHERE s.is_active   = TRUE
  AND s.course_code = 'COMP4200'
ON DUPLICATE KEY UPDATE result_id = result_id;

SELECT st.student_id, u.full_name
FROM students st
JOIN users u ON u.user_id = st.user_id
ORDER BY st.student_id;


INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES
(10, 9, TRUE),
(10, 10, FALSE),

(11, 4, TRUE),
(11, 5, FALSE),

(12, 6, TRUE),
(12, 7, FALSE);

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact) VALUES
(12, 6, TRUE),
(12, 7, FALSE),
(12, 8, FALSE);


SELECT
    p.project_id,
    p.title,
    u1.full_name AS preferred_1,
    u2.full_name AS preferred_2,
    u3.full_name AS preferred_3
FROM projects p
LEFT JOIN faculty f1 ON f1.faculty_id = p.preferred_supervisor_1
LEFT JOIN users u1 ON u1.user_id = f1.user_id
LEFT JOIN faculty f2 ON f2.faculty_id = p.preferred_supervisor_2
LEFT JOIN users u2 ON u2.user_id = f2.user_id
LEFT JOIN faculty f3 ON f3.faculty_id = p.preferred_supervisor_3
LEFT JOIN users u3 ON u3.user_id = f3.user_id
WHERE p.project_id IN (10, 11, 12);
-- ============================================================
--  END OF MIGRATION: student_course_results
-- ============================================================

-- ============================================================
--  ADD 24 MORE STUDENTS
--  Safe re-run: skips existing university_id/user_id values
-- ============================================================

USE apms_db;

SET NAMES utf8mb4;

-- Temporary student password hash
SET @student_pwd := '$2b$12$eJmEAFs2Cci7.foj61N6tOthlgHqqs0XccNvIRuzvkK70jQixoWb.';

INSERT IGNORE INTO users (university_id, full_name, email, password_hash, role, avatar_initials, is_active)
SELECT *
FROM (
    SELECT '1221001' AS university_id, 'Yousef Hamdan'      AS full_name, '1221001@students.birzeit.edu' AS email, @student_pwd AS password_hash, 'student' AS role, 'YH' AS avatar_initials, TRUE AS is_active
    UNION ALL SELECT '1221002', 'Layan Daraghmeh',         '1221002@students.birzeit.edu', @student_pwd, 'student', 'LD', TRUE
    UNION ALL SELECT '1221003', 'Noor Sawafta',            '1221003@students.birzeit.edu', @student_pwd, 'student', 'NS', TRUE
    UNION ALL SELECT '1221004', 'Alaa Zakarneh',           '1221004@students.birzeit.edu', @student_pwd, 'student', 'AZ', TRUE
    UNION ALL SELECT '1221005', 'Raneem Jaradat',          '1221005@students.birzeit.edu', @student_pwd, 'student', 'RJ', TRUE
    UNION ALL SELECT '1221006', 'Malak Khoury',            '1221006@students.birzeit.edu', @student_pwd, 'student', 'MK', TRUE
    UNION ALL SELECT '1221007', 'Hana Qasem',              '1221007@students.birzeit.edu', @student_pwd, 'student', 'HQ', TRUE
    UNION ALL SELECT '1221008', 'Basil Jaber',             '1221008@students.birzeit.edu', @student_pwd, 'student', 'BJ', TRUE
    UNION ALL SELECT '1221009', 'Jana Taqatqa',            '1221009@students.birzeit.edu', @student_pwd, 'student', 'JT', TRUE
    UNION ALL SELECT '1221010', 'Omar Khatib',             '1221010@students.birzeit.edu', @student_pwd, 'student', 'OK', TRUE
    UNION ALL SELECT '1221011', 'Reem Hammad',             '1221011@students.birzeit.edu', @student_pwd, 'student', 'RH', TRUE
    UNION ALL SELECT '1221012', 'Yazan Abu Ayyash',        '1221012@students.birzeit.edu', @student_pwd, 'student', 'YA', TRUE
    UNION ALL SELECT '1221013', 'Farah Odeh',              '1221013@students.birzeit.edu', @student_pwd, 'student', 'FO', TRUE
    UNION ALL SELECT '1221014', 'Lina Barghouti',          '1221014@students.birzeit.edu', @student_pwd, 'student', 'LB', TRUE
    UNION ALL SELECT '1221015', 'Mariam Salameh',          '1221015@students.birzeit.edu', @student_pwd, 'student', 'MS', TRUE
    UNION ALL SELECT '1221016', 'Ali Shraim',              '1221016@students.birzeit.edu', @student_pwd, 'student', 'AS', TRUE
    UNION ALL SELECT '1221017', 'Sama Dweikat',            '1221017@students.birzeit.edu', @student_pwd, 'student', 'SD', TRUE
    UNION ALL SELECT '1221018', 'Husam Azzam',             '1221018@students.birzeit.edu', @student_pwd, 'student', 'HA', TRUE
    UNION ALL SELECT '1221019', 'Aseel Masri',             '1221019@students.birzeit.edu', @student_pwd, 'student', 'AM', TRUE
    UNION ALL SELECT '1221020', 'Rama Hamayel',            '1221020@students.birzeit.edu', @student_pwd, 'student', 'RH', TRUE
    UNION ALL SELECT '1221021', 'Mahmoud Shtayyeh',        '1221021@students.birzeit.edu', @student_pwd, 'student', 'MS', TRUE
    UNION ALL SELECT '1221022', 'Celine Nasser',           '1221022@students.birzeit.edu', @student_pwd, 'student', 'CN', TRUE
    UNION ALL SELECT '1221023', 'Adam Zaid',               '1221023@students.birzeit.edu', @student_pwd, 'student', 'AZ', TRUE
    UNION ALL SELECT '1221024', 'Shahd Abu Eisheh',        '1221024@students.birzeit.edu', @student_pwd, 'student', 'SA', TRUE
) AS new_students
WHERE NOT EXISTS (
    SELECT 1
    FROM users u
    WHERE u.university_id = new_students.university_id
);

INSERT IGNORE INTO students (user_id, enrollment_year)
SELECT u.user_id, 2022
FROM users u
WHERE u.university_id IN (
    '1221001','1221002','1221003','1221004','1221005','1221006',
    '1221007','1221008','1221009','1221010','1221011','1221012',
    '1221013','1221014','1221015','1221016','1221017','1221018',
    '1221019','1221020','1221021','1221022','1221023','1221024'
)
AND u.role = 'student'
AND NOT EXISTS (
    SELECT 1
    FROM students s
    WHERE s.user_id = u.user_id
);

-- Verification
SELECT u.user_id, u.university_id, u.full_name, u.email, s.student_id, s.enrollment_year
FROM users u
LEFT JOIN students s ON s.user_id = u.user_id
WHERE u.university_id IN (
    '1221001','1221002','1221003','1221004','1221005','1221006',
    '1221007','1221008','1221009','1221010','1221011','1221012',
    '1221013','1221014','1221015','1221016','1221017','1221018',
    '1221019','1221020','1221021','1221022','1221023','1221024'
)
ORDER BY u.university_id;


CREATE TABLE IF NOT EXISTS discussion_rooms (
    room_id    INT          PRIMARY KEY AUTO_INCREMENT,
    room_name  VARCHAR(120) NOT NULL UNIQUE,
    sort_order INT          NOT NULL DEFAULT 1,
    is_active  BOOLEAN      NOT NULL DEFAULT TRUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- ============================================================
-- Committee Plans (one committee can discuss multiple projects)
-- ============================================================
CREATE TABLE IF NOT EXISTS committee_plans (
    plan_id INT PRIMARY KEY AUTO_INCREMENT,
    committee_name VARCHAR(150) NOT NULL,
    academic_year VARCHAR(20) NOT NULL,
    discussion_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    room_id INT NOT NULL,
    responsible_faculty_id INT NULL,
    status ENUM('draft','scheduled','completed','cancelled') NOT NULL DEFAULT 'draft',
    created_by INT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES discussion_rooms(room_id),
    FOREIGN KEY (responsible_faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL,
    FOREIGN KEY (created_by) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Committee Members (4 doctors, different majors)
-- ============================================================
CREATE TABLE IF NOT EXISTS committee_plan_members (
    id INT PRIMARY KEY AUTO_INCREMENT,
    plan_id INT NOT NULL,
    faculty_id INT NOT NULL,
    role ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member',
    UNIQUE KEY uq_committee_plan_member (plan_id, faculty_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Projects assigned to each committee with time slots
-- Discussion per project = 30 min
-- Break after each project = 10 min
-- ============================================================
CREATE TABLE IF NOT EXISTS committee_plan_projects (
    id INT PRIMARY KEY AUTO_INCREMENT,
    plan_id INT NOT NULL,
    project_id INT NOT NULL,
    slot_order INT NOT NULL,
    slot_start TIME NOT NULL,
    slot_end TIME NOT NULL,
    UNIQUE KEY uq_committee_plan_project (plan_id, project_id),
    UNIQUE KEY uq_unique_project_committee (project_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- Seed rooms
-- ============================================================
INSERT IGNORE INTO discussion_rooms (room_name, is_active) VALUES
('Room 201 — Faculty of Engineering', TRUE),
('Room 202 — Faculty of Engineering', TRUE),
('Room 203 — Faculty of Engineering', TRUE),
('Room 204 — Faculty of Engineering', TRUE);

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- Verification
-- ============================================================
SELECT room_id, room_name, is_active FROM discussion_rooms ORDER BY room_name;
SHOW TABLES LIKE 'committee_plans';
SHOW TABLES LIKE 'committee_plan_members';
SHOW TABLES LIKE 'committee_plan_projects';



CREATE TABLE IF NOT EXISTS discussion_rooms (
    room_id      INT PRIMARY KEY AUTO_INCREMENT,
    room_name    VARCHAR(150) NOT NULL UNIQUE,
    sort_order   INT NOT NULL DEFAULT 1,
    is_active    TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS committee_plans (
    plan_id                 INT PRIMARY KEY AUTO_INCREMENT,
    committee_name          VARCHAR(200) NOT NULL,
    discussion_date         DATE NOT NULL,
    start_time              TIME NOT NULL,
    end_time                TIME NOT NULL,
    room_id                 INT NOT NULL,
    status                  ENUM('scheduled','ongoing','completed','cancelled') NOT NULL DEFAULT 'scheduled',
    created_by              INT NOT NULL,
    responsible_faculty_id  INT NULL,
    final_average           DECIMAL(5,2) NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES discussion_rooms(room_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (responsible_faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS committee_plan_members (
    id       INT PRIMARY KEY AUTO_INCREMENT,
    plan_id      INT NOT NULL,
    faculty_id   INT NOT NULL,
    role         ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member',
    UNIQUE KEY uq_plan_faculty (plan_id, faculty_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS committee_plan_projects (
    cpp_id       INT PRIMARY KEY AUTO_INCREMENT,
    plan_id      INT NOT NULL,
    project_id   INT NOT NULL,
    slot_order   INT NOT NULL,
    slot_start   TIME NOT NULL,
    slot_end     TIME NOT NULL,
    UNIQUE KEY uq_plan_project (plan_id, project_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 2) Default rooms
-- ============================================================

INSERT IGNORE INTO discussion_rooms (room_name, sort_order, is_active)
SELECT * FROM (
    SELECT 'Room 201 — Engineering Building' AS room_name, 1 AS sort_order, 1 AS is_active
    UNION ALL SELECT 'Room 202 — Engineering Building', 2, 1
    UNION ALL SELECT 'Room 203 — Engineering Building', 3, 1
    UNION ALL SELECT 'Room 204 — Engineering Building', 4, 1
    UNION ALL SELECT 'Lab 1 — Computer Science', 5, 1
    UNION ALL SELECT 'Lab 2 — Computer Science', 6, 1
    UNION ALL SELECT 'Hall A — New Building', 7, 1
    UNION ALL SELECT 'Hall B — New Building', 8, 1
) AS rooms
WHERE NOT EXISTS (
    SELECT 1 FROM discussion_rooms dr WHERE dr.room_name = rooms.room_name
);

-- ============================================================
-- 3) Add at least 8 more projects to the latest active semester
-- ============================================================

SET @target_semester_id := (
    SELECT semester_id
    FROM semesters
    WHERE is_active = TRUE
    ORDER BY semester_id DESC
    LIMIT 1
);

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Smart Clinic Management Platform', 'web', @target_semester_id, 5, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Smart Clinic Management Platform'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'AI Resume Screening System', 'ai', @target_semester_id, 4, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'AI Resume Screening System'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Secure Campus Access Control', 'security', @target_semester_id, 7, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Secure Campus Access Control'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Mobile Pharmacy Assistant', 'mobile', @target_semester_id, 5, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Mobile Pharmacy Assistant'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Intelligent Library Recommender', 'ai', @target_semester_id, 4, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Intelligent Library Recommender'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Cloud Attendance Tracker', 'web', @target_semester_id, 3, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Cloud Attendance Tracker'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Database Performance Analyzer', 'databases', @target_semester_id, 6, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Database Performance Analyzer'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Smart Graduation Project Marketplace', 'web', @target_semester_id, 3, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Smart Graduation Project Marketplace'
  );

-- ============================================================
-- 4) Optional team members for the new 8 projects
--    Safe re-run. Uses the extra students you added before.
-- ============================================================

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221001'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Clinic Management Platform'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221002'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Clinic Management Platform'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221003'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'AI Resume Screening System'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221004'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'AI Resume Screening System'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221005'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Secure Campus Access Control'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221006'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Secure Campus Access Control'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221007'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Mobile Pharmacy Assistant'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221008'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Mobile Pharmacy Assistant'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221009'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Intelligent Library Recommender'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221010'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Intelligent Library Recommender'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221011'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Cloud Attendance Tracker'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221012'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Cloud Attendance Tracker'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221013'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Database Performance Analyzer'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221014'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Database Performance Analyzer'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221015'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Graduation Project Marketplace'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221016'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Graduation Project Marketplace'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

-- ============================================================
-- 5) Verification
-- ============================================================

SELECT p.project_id, p.title, p.status, p.project_type
FROM projects p
WHERE p.semester_id = @target_semester_id
  AND p.title IN (
      'Smart Clinic Management Platform',
      'AI Resume Screening System',
      'Secure Campus Access Control',
      'Mobile Pharmacy Assistant',
      'Intelligent Library Recommender',
      'Cloud Attendance Tracker',
      'Database Performance Analyzer',
      'Smart Graduation Project Marketplace'
  )
ORDER BY p.project_id;

-- ============================================================
--  RANDOM COMMITTEE DISTRIBUTION APPENDIX
-- ============================================================

USE apms_db;

SET NAMES utf8mb4;

-- ============================================================
-- 1) Tables needed for multi-project committee scheduling
-- ============================================================

CREATE TABLE IF NOT EXISTS discussion_rooms (
    room_id      INT PRIMARY KEY AUTO_INCREMENT,
    room_name    VARCHAR(150) NOT NULL UNIQUE,
    sort_order   INT NOT NULL DEFAULT 1,
    is_active    TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS committee_plans (
    plan_id                 INT PRIMARY KEY AUTO_INCREMENT,
    committee_name          VARCHAR(200) NOT NULL,
    discussion_date         DATE NOT NULL,
    start_time              TIME NOT NULL,
    end_time                TIME NOT NULL,
    room_id                 INT NOT NULL,
    status                  ENUM('scheduled','ongoing','completed','cancelled') NOT NULL DEFAULT 'scheduled',
    created_by              INT NOT NULL,
    responsible_faculty_id  INT NULL,
    final_average           DECIMAL(5,2) NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES discussion_rooms(room_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (responsible_faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS committee_plan_members (
    id       INT PRIMARY KEY AUTO_INCREMENT,
    plan_id      INT NOT NULL,
    faculty_id   INT NOT NULL,
    role         ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member',
    UNIQUE KEY uq_plan_faculty (plan_id, faculty_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS committee_plan_projects (
    cpp_id       INT PRIMARY KEY AUTO_INCREMENT,
    plan_id      INT NOT NULL,
    project_id   INT NOT NULL,
    slot_order   INT NOT NULL,
    slot_start   TIME NOT NULL,
    slot_end     TIME NOT NULL,
    UNIQUE KEY uq_plan_project (plan_id, project_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 2) Default rooms
-- ============================================================

INSERT IGNORE INTO discussion_rooms (room_name, sort_order, is_active)
SELECT * FROM (
    SELECT 'Room 201 — Engineering Building' AS room_name, 1 AS sort_order, 1 AS is_active
    UNION ALL SELECT 'Room 202 — Engineering Building', 2, 1
    UNION ALL SELECT 'Room 203 — Engineering Building', 3, 1
    UNION ALL SELECT 'Room 204 — Engineering Building', 4, 1
    UNION ALL SELECT 'Lab 1 — Computer Science', 5, 1
    UNION ALL SELECT 'Lab 2 — Computer Science', 6, 1
    UNION ALL SELECT 'Hall A — New Building', 7, 1
    UNION ALL SELECT 'Hall B — New Building', 8, 1
) AS rooms
WHERE NOT EXISTS (
    SELECT 1 FROM discussion_rooms dr WHERE dr.room_name = rooms.room_name
);

-- ============================================================
-- 3) Add at least 8 more projects to the latest active semester
-- ============================================================

SET @target_semester_id := (
    SELECT semester_id
    FROM semesters
    WHERE is_active = TRUE
    ORDER BY semester_id DESC
    LIMIT 1
);

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Smart Clinic Management Platform', 'web', @target_semester_id, 5, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Smart Clinic Management Platform'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'AI Resume Screening System', 'ai', @target_semester_id, 4, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'AI Resume Screening System'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Secure Campus Access Control', 'security', @target_semester_id, 7, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Secure Campus Access Control'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Mobile Pharmacy Assistant', 'mobile', @target_semester_id, 5, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Mobile Pharmacy Assistant'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Intelligent Library Recommender', 'ai', @target_semester_id, 4, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Intelligent Library Recommender'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Cloud Attendance Tracker', 'web', @target_semester_id, 3, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Cloud Attendance Tracker'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Database Performance Analyzer', 'databases', @target_semester_id, 6, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Database Performance Analyzer'
  );

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT 'Smart Graduation Project Marketplace', 'web', @target_semester_id, 3, 'submitted', CURDATE()
WHERE @target_semester_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM projects
      WHERE semester_id = @target_semester_id
        AND title = 'Smart Graduation Project Marketplace'
  );

-- ============================================================
-- 4) Optional team members for the new 8 projects
--    Safe re-run. Uses the extra students you added before.
-- ============================================================

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221001'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Clinic Management Platform'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221002'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Clinic Management Platform'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221003'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'AI Resume Screening System'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221004'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'AI Resume Screening System'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221005'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Secure Campus Access Control'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221006'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Secure Campus Access Control'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221007'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Mobile Pharmacy Assistant'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221008'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Mobile Pharmacy Assistant'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221009'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Intelligent Library Recommender'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221010'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Intelligent Library Recommender'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221011'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Cloud Attendance Tracker'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221012'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Cloud Attendance Tracker'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221013'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Database Performance Analyzer'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221014'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Database Performance Analyzer'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 1
FROM projects p
JOIN users u ON u.university_id = '1221015'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Graduation Project Marketplace'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

INSERT IGNORE INTO project_members (project_id, student_id, is_primary_contact)
SELECT p.project_id, s.student_id, 0
FROM projects p
JOIN users u ON u.university_id = '1221016'
JOIN students s ON s.user_id = u.user_id
WHERE p.semester_id = @target_semester_id
  AND p.title = 'Smart Graduation Project Marketplace'
  AND NOT EXISTS (
      SELECT 1 FROM project_members pm
      WHERE pm.project_id = p.project_id AND pm.student_id = s.student_id
  );

-- ============================================================
-- 5) Verification
-- ============================================================

SELECT p.project_id, p.title, p.status, p.project_type
FROM projects p
WHERE p.semester_id = @target_semester_id
  AND p.title IN (
      'Smart Clinic Management Platform',
      'AI Resume Screening System',
      'Secure Campus Access Control',
      'Mobile Pharmacy Assistant',
      'Intelligent Library Recommender',
      'Cloud Attendance Tracker',
      'Database Performance Analyzer',
      'Smart Graduation Project Marketplace'
  )
ORDER BY p.project_id;

-- ============================================================
--  COMMITTEE RANDOM DISTRIBUTION REPAIR APPENDIX
--  Safe fixes for older databases / partial runs
-- ============================================================

USE apms_db;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- A) discussion_rooms safe repair
-- ============================================================

CREATE TABLE IF NOT EXISTS discussion_rooms (
    room_id      INT PRIMARY KEY AUTO_INCREMENT,
    room_name    VARCHAR(150) NOT NULL UNIQUE,
    sort_order   INT NOT NULL DEFAULT 1,
    is_active    TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'discussion_rooms'
      AND COLUMN_NAME = 'sort_order'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE discussion_rooms ADD COLUMN sort_order INT NOT NULL DEFAULT 1',
    'SELECT "discussion_rooms.sort_order already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'discussion_rooms'
      AND COLUMN_NAME = 'is_active'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE discussion_rooms ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1',
    'SELECT "discussion_rooms.is_active already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- B) committee_plans safe repair
-- ============================================================

CREATE TABLE IF NOT EXISTS committee_plans (
    plan_id                 INT PRIMARY KEY AUTO_INCREMENT,
    committee_name          VARCHAR(200) NOT NULL,
    discussion_date         DATE NOT NULL,
    start_time              TIME NOT NULL,
    end_time                TIME NOT NULL,
    room_id                 INT NOT NULL,
    status                  ENUM('scheduled','ongoing','completed','cancelled') NOT NULL DEFAULT 'scheduled',
    created_by              INT NOT NULL,
    responsible_faculty_id  INT NULL,
    final_average           DECIMAL(5,2) NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (room_id) REFERENCES discussion_rooms(room_id) ON DELETE RESTRICT,
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE RESTRICT,
    FOREIGN KEY (responsible_faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plans'
      AND COLUMN_NAME = 'end_time'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE committee_plans ADD COLUMN end_time TIME NOT NULL DEFAULT ''09:30:00'' AFTER start_time',
    'SELECT "committee_plans.end_time already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plans'
      AND COLUMN_NAME = 'room_id'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE committee_plans ADD COLUMN room_id INT NULL AFTER end_time',
    'SELECT "committee_plans.room_id already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plans'
      AND COLUMN_NAME = 'status'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE committee_plans ADD COLUMN status ENUM(''scheduled'',''ongoing'',''completed'',''cancelled'') NOT NULL DEFAULT ''scheduled'' AFTER room_id',
    'SELECT "committee_plans.status already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plans'
      AND COLUMN_NAME = 'created_by'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE committee_plans ADD COLUMN created_by INT NULL AFTER status',
    'SELECT "committee_plans.created_by already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plans'
      AND COLUMN_NAME = 'responsible_faculty_id'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE committee_plans ADD COLUMN responsible_faculty_id INT NULL AFTER created_by',
    'SELECT "committee_plans.responsible_faculty_id already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plans'
      AND COLUMN_NAME = 'final_average'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE committee_plans ADD COLUMN final_average DECIMAL(5,2) NULL AFTER responsible_faculty_id',
    'SELECT "committee_plans.final_average already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plans'
      AND COLUMN_NAME = 'created_at'
);
SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE committee_plans ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER final_average',
    'SELECT "committee_plans.created_at already exists"'
);
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- ============================================================
-- C) committee_plan_members safe repair
-- ============================================================

CREATE TABLE IF NOT EXISTS committee_plan_members (
    id       INT PRIMARY KEY AUTO_INCREMENT,
    plan_id      INT NOT NULL,
    faculty_id   INT NOT NULL,
    role         ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member',
    UNIQUE KEY uq_plan_faculty (plan_id, faculty_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- D) committee_plan_projects safe repair
-- ============================================================

CREATE TABLE IF NOT EXISTS committee_plan_projects (
    cpp_id       INT PRIMARY KEY AUTO_INCREMENT,
    plan_id      INT NOT NULL,
    project_id   INT NOT NULL,
    slot_order   INT NOT NULL,
    slot_start   TIME NOT NULL,
    slot_end     TIME NOT NULL,
    UNIQUE KEY uq_plan_project (plan_id, project_id),
    FOREIGN KEY (plan_id) REFERENCES committee_plans(plan_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- E) Default rooms safe insert
-- ============================================================

INSERT IGNORE INTO discussion_rooms (room_name, sort_order, is_active)
SELECT * FROM (
    SELECT 'Room 201 — Engineering Building' AS room_name, 1 AS sort_order, 1 AS is_active
    UNION ALL SELECT 'Room 202 — Engineering Building', 2, 1
    UNION ALL SELECT 'Room 203 — Engineering Building', 3, 1
    UNION ALL SELECT 'Room 204 — Engineering Building', 4, 1
    UNION ALL SELECT 'Lab 1 — Computer Science', 5, 1
    UNION ALL SELECT 'Lab 2 — Computer Science', 6, 1
    UNION ALL SELECT 'Hall A — New Building', 7, 1
    UNION ALL SELECT 'Hall B — New Building', 8, 1
) AS rooms
WHERE NOT EXISTS (
    SELECT 1
    FROM discussion_rooms dr
    WHERE dr.room_name = rooms.room_name
);


CREATE TABLE IF NOT EXISTS announcements (
    announcement_id  INT           PRIMARY KEY AUTO_INCREMENT,
    message          TEXT          NOT NULL,
    activation_url   VARCHAR(500)  NOT NULL  DEFAULT '/activate',
    created_by       INT           NOT NULL  COMMENT 'head_of_department user_id',
    expires_at       DATE          NOT NULL,
    is_active        BOOLEAN       NOT NULL  DEFAULT TRUE,
    created_at       TIMESTAMP     NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET FOREIGN_KEY_CHECKS = 1;






-- ============================================================
--  END OF REPAIR APPENDIX
-- ============================================================


-- Rescue migration for dashboard/review/notifications.
SET @db := DATABASE();

SET @sql := (SELECT IF(COUNT(*) = 0, 'ALTER TABLE semesters ADD COLUMN distribution_open TINYINT(1) NOT NULL DEFAULT 0', 'SELECT 1') FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='semesters' AND COLUMN_NAME='distribution_open');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(COUNT(*) = 0, 'ALTER TABLE semesters ADD COLUMN distribution_opened_at DATETIME NULL', 'SELECT 1') FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='semesters' AND COLUMN_NAME='distribution_opened_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(COUNT(*) = 0, 'ALTER TABLE semesters ADD COLUMN distribution_closed_at DATETIME NULL', 'SELECT 1') FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='semesters' AND COLUMN_NAME='distribution_closed_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(COUNT(*) = 0, 'ALTER TABLE semesters ADD COLUMN distribution_close_at DATETIME NULL', 'SELECT 1') FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='semesters' AND COLUMN_NAME='distribution_close_at');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS faculty_load_settings (
  faculty_id INT NOT NULL,
  semester_id INT NOT NULL,
  graduation_project_hours DECIMAL(5,2) NOT NULL DEFAULT 0,
  updated_by INT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (faculty_id, semester_id)
);

SET @sql := (SELECT IF(COUNT(*) = 0, 'ALTER TABLE faculty_load_settings ADD COLUMN graduation_project_hours DECIMAL(5,2) NOT NULL DEFAULT 0', 'SELECT 1') FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='faculty_load_settings' AND COLUMN_NAME='graduation_project_hours');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(COUNT(*) = 0, 'ALTER TABLE faculty_load_settings ADD COLUMN updated_by INT NULL', 'SELECT 1') FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='faculty_load_settings' AND COLUMN_NAME='updated_by');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (SELECT IF(COUNT(*) = 0, 'ALTER TABLE notifications ADD COLUMN sender_id INT NULL AFTER recipient_id', 'SELECT 1') FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=@db AND TABLE_NAME='notifications' AND COLUMN_NAME='sender_id');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE notifications ADD COLUMN course_scope ENUM(''introduction'',''graduation_project'',''both'') NOT NULL DEFAULT ''both'' AFTER message',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = @db
    AND TABLE_NAME = 'notifications'
    AND COLUMN_NAME = 'course_scope'
);PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS system_notices (
  notice_id INT PRIMARY KEY AUTO_INCREMENT,
  title VARCHAR(255) NOT NULL,
  body TEXT NOT NULL,
  highlight_text VARCHAR(255) NULL,
  button1_text VARCHAR(100) NULL,
  button2_text VARCHAR(100) NULL,
  button3_text VARCHAR(100) NULL,
  course_scope ENUM('introduction','graduation_project','both') NOT NULL DEFAULT 'both',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  updated_by INT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

UPDATE semesters
SET is_active = 1
WHERE semester_id = (SELECT semester_id FROM (SELECT semester_id FROM semesters ORDER BY semester_id DESC LIMIT 1) AS newest)
  AND NOT EXISTS (SELECT 1 FROM (SELECT semester_id FROM semesters WHERE is_active = 1 LIMIT 1) AS active_sem);
  
  
-- ============================================================
-- Archived Projects from Uploads (44 projects)
-- Run AFTER your main APMS.sql
-- Each project gets a supervisor assigned from existing faculty
-- ============================================================

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Smart Invoice', 'ai', s.semester_id, 3, 'archived', '2025-02-01', 82.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Smart Invoice' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Kitchen Station Management System', 'web', s.semester_id, 4, 'archived', '2025-02-01', 79.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Kitchen Station Management System' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'DreamsJob Recruitment Platform', 'web', s.semester_id, 5, 'archived', '2025-02-01', 85.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='DreamsJob Recruitment Platform' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'YallaRehla Travel App', 'mobile', s.semester_id, 6, 'archived', '2025-02-01', 88.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='YallaRehla Travel App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'StudentHub', 'web', s.semester_id, 7, 'archived', '2025-02-01', 76.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='StudentHub' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Wasselha Delivery System', 'mobile', s.semester_id, 3, 'archived', '2025-02-01', 83.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Wasselha Delivery System' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Home Sweet Home Real Estate', 'web', s.semester_id, 4, 'archived', '2025-02-01', 80.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Home Sweet Home Real Estate' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Birzeit University Insurance System', 'web', s.semester_id, 5, 'archived', '2024-02-01', 91.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Birzeit University Insurance System' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Sal7ly Maintenance App', 'mobile', s.semester_id, 6, 'archived', '2024-02-01', 78.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Sal7ly Maintenance App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Monitoring World News System', 'web', s.semester_id, 7, 'archived', '2024-02-01', 74.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Monitoring World News System' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Prediction of Anti-Cancer Peptide ACP-XG', 'ai', s.semester_id, 3, 'archived', '2025-02-01', 94.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Prediction of Anti-Cancer Peptide ACP-XG' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'FitScoop Fitness Platform', 'mobile', s.semester_id, 4, 'archived', '2025-02-01', 81.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='FitScoop Fitness Platform' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Wedding Planning System', 'web', s.semester_id, 5, 'archived', '2025-02-01', 77.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Wedding Planning System' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'PharmaApp Pharmacy Management', 'mobile', s.semester_id, 6, 'archived', '2025-02-01', 86.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='PharmaApp Pharmacy Management' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Student Digital Guide', 'web', s.semester_id, 7, 'archived', '2025-02-01', 80.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Student Digital Guide' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Palestine Charity Platform', 'web', s.semester_id, 3, 'archived', '2025-02-01', 75.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Palestine Charity Platform' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Gamified Trip Planner App', 'mobile', s.semester_id, 4, 'archived', '2025-02-01', 89.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Gamified Trip Planner App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'TechSpotter Tech News Platform', 'web', s.semester_id, 5, 'archived', '2025-02-01', 78.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='TechSpotter Tech News Platform' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Multi-Environment Video Game', 'other', s.semester_id, 6, 'archived', '2025-02-01', 83.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Multi-Environment Video Game' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Birzeit Library Chatbot', 'ai', s.semester_id, 7, 'archived', '2025-02-01', 92.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Birzeit Library Chatbot' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Policy Peek Policy Analyzer', 'ai', s.semester_id, 3, 'archived', '2025-02-01', 87.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Policy Peek Policy Analyzer' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'LifeActive Health Tracker', 'mobile', s.semester_id, 4, 'archived', '2025-02-01', 84.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='LifeActive Health Tracker' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Tronix Electronics Web Application', 'web', s.semester_id, 5, 'archived', '2025-02-01', 79.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Tronix Electronics Web Application' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Smart School Portal', 'web', s.semester_id, 6, 'archived', '2025-02-01', 88.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Smart School Portal' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'GoHelp Volunteer Platform', 'web', s.semester_id, 7, 'archived', '2025-02-01', 76.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='GoHelp Volunteer Platform' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'KhatClarifier AI Writing Tool', 'ai', s.semester_id, 3, 'archived', '2025-02-01', 90.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='KhatClarifier AI Writing Tool' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'ConvoConvert Communication Tool', 'ai', s.semester_id, 4, 'archived', '2025-02-01', 85.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='ConvoConvert Communication Tool' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Wasselni Transportation App', 'mobile', s.semester_id, 5, 'archived', '2025-02-01', 82.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Wasselni Transportation App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Ackerra Fitness Platform', 'mobile', s.semester_id, 6, 'archived', '2025-02-01', 87.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Ackerra Fitness Platform' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Darak Real Estate Marketplace', 'web', s.semester_id, 7, 'archived', '2025-02-01', 83.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Darak Real Estate Marketplace' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Flora Palestine Plant Guide', 'mobile', s.semester_id, 3, 'archived', '2025-02-01', 81.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Flora Palestine Plant Guide' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Max Scheduling System', 'web', s.semester_id, 4, 'archived', '2025-02-01', 77.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Max Scheduling System' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'PayWithPalKoin Payment System', 'web', s.semester_id, 5, 'archived', '2025-02-01', 86.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='PayWithPalKoin Payment System' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Nomad Travel Companion App', 'mobile', s.semester_id, 6, 'archived', '2025-02-01', 84.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Nomad Travel Companion App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'CarPal Car Sharing App', 'mobile', s.semester_id, 7, 'archived', '2025-02-01', 88.00
FROM semesters s
WHERE s.academic_year='2024/2025' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='CarPal Car Sharing App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'E-Voting System Using Blockchain', 'security', s.semester_id, 3, 'archived', '2024-02-01', 93.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='E-Voting System Using Blockchain' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Nossrah Arabic Learning App', 'mobile', s.semester_id, 4, 'archived', '2024-02-01', 80.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Nossrah Arabic Learning App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Wanderlust in Palestine Travel App', 'web', s.semester_id, 5, 'archived', '2024-02-01', 85.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Wanderlust in Palestine Travel App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Medica Healthcare App', 'mobile', s.semester_id, 6, 'archived', '2024-02-01', 82.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Medica Healthcare App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'BZU Note Share App', 'mobile', s.semester_id, 7, 'archived', '2024-02-01', 79.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='BZU Note Share App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Plestia Events Platform', 'web', s.semester_id, 3, 'archived', '2024-02-01', 83.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Plestia Events Platform' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Baby Voice Identification App', 'ai', s.semester_id, 4, 'archived', '2024-02-01', 88.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Baby Voice Identification App' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'Traffic Light Synchronization Optimizer', 'ai', s.semester_id, 5, 'archived', '2024-02-01', 91.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='Traffic Light Synchronization Optimizer' AND status='archived')
LIMIT 1;

INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date, final_score)
SELECT 'CampusConnect University Network', 'web', s.semester_id, 6, 'archived', '2024-02-01', 86.00
FROM semesters s
WHERE s.academic_year='2023/2024' AND s.course_code='COMP4200'
AND NOT EXISTS (SELECT 1 FROM projects WHERE title='CampusConnect University Network' AND status='archived')
LIMIT 1;

-- ============================================================
-- Link PDF files to projects
-- ============================================================

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'smart_invoice.pdf', 'archived_reports/smart_invoice.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Smart Invoice' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'kitchen_station.pdf', 'archived_reports/kitchen_station.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Kitchen Station Management System' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'dreamsjob.pdf', 'archived_reports/dreamsjob.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='DreamsJob Recruitment Platform' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'yallarehla.pdf', 'archived_reports/yallarehla.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='YallaRehla Travel App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'studenthub.pdf', 'archived_reports/studenthub.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='StudentHub' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'wasselha.pdf', 'archived_reports/wasselha.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Wasselha Delivery System' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'home_sweet_home.pdf', 'archived_reports/home_sweet_home.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Home Sweet Home Real Estate' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'bzu_insurance.pdf', 'archived_reports/bzu_insurance.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Birzeit University Insurance System' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'sal7ly.pdf', 'archived_reports/sal7ly.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Sal7ly Maintenance App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'monitoring_world_news.pdf', 'archived_reports/monitoring_world_news.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Monitoring World News System' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'anti_cancer_peptide.pdf', 'archived_reports/anti_cancer_peptide.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Prediction of Anti-Cancer Peptide ACP-XG' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'fitscoop.pdf', 'archived_reports/fitscoop.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='FitScoop Fitness Platform' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'wedding_planning.pdf', 'archived_reports/wedding_planning.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Wedding Planning System' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'pharmaapp.pdf', 'archived_reports/pharmaapp.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='PharmaApp Pharmacy Management' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'student_digital_guide.pdf', 'archived_reports/student_digital_guide.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Student Digital Guide' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'palestine_charity.pdf', 'archived_reports/palestine_charity.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Palestine Charity Platform' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'gamified_trip_planner.pdf', 'archived_reports/gamified_trip_planner.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Gamified Trip Planner App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'techspotter.pdf', 'archived_reports/techspotter.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='TechSpotter Tech News Platform' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'multi_env_videogame.pdf', 'archived_reports/multi_env_videogame.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Multi-Environment Video Game' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'bzu_library_chatbot.pdf', 'archived_reports/bzu_library_chatbot.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Birzeit Library Chatbot' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'policy_peek.pdf', 'archived_reports/policy_peek.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Policy Peek Policy Analyzer' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'lifeactive.pdf', 'archived_reports/lifeactive.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='LifeActive Health Tracker' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'tronix.pdf', 'archived_reports/tronix.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Tronix Electronics Web Application' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'smart_school_portal.pdf', 'archived_reports/smart_school_portal.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Smart School Portal' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'gohelp.pdf', 'archived_reports/gohelp.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='GoHelp Volunteer Platform' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'khatclarifier.pdf', 'archived_reports/khatclarifier.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='KhatClarifier AI Writing Tool' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'convoconvert.pdf', 'archived_reports/convoconvert.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='ConvoConvert Communication Tool' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'wasselni.pdf', 'archived_reports/wasselni.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Wasselni Transportation App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'ackerra.pdf', 'archived_reports/ackerra.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Ackerra Fitness Platform' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'darak.pdf', 'archived_reports/darak.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Darak Real Estate Marketplace' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'flora_palestine.pdf', 'archived_reports/flora_palestine.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Flora Palestine Plant Guide' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'max_scheduling.pdf', 'archived_reports/max_scheduling.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Max Scheduling System' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'paywithpalkoin.pdf', 'archived_reports/paywithpalkoin.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='PayWithPalKoin Payment System' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'nomad.pdf', 'archived_reports/nomad.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Nomad Travel Companion App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'carpal.pdf', 'archived_reports/carpal.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='CarPal Car Sharing App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'evoting_blockchain.pdf', 'archived_reports/evoting_blockchain.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='E-Voting System Using Blockchain' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'nossrah.pdf', 'archived_reports/nossrah.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Nossrah Arabic Learning App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'wanderlust_palestine.pdf', 'archived_reports/wanderlust_palestine.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Wanderlust in Palestine Travel App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'medica_app.pdf', 'archived_reports/medica_app.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Medica Healthcare App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'bzu_note_share.pdf', 'archived_reports/bzu_note_share.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='BZU Note Share App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'plestia_events.pdf', 'archived_reports/plestia_events.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Plestia Events Platform' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'baby_voice_id.pdf', 'archived_reports/baby_voice_id.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Baby Voice Identification App' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'traffic_light_optimizer.pdf', 'archived_reports/traffic_light_optimizer.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='Traffic Light Synchronization Optimizer' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;

INSERT INTO project_files (project_id, file_type, file_name, file_path, upload_status, uploaded_at)
SELECT p.project_id, 'final_report', 'campus_connect.pdf', 'archived_reports/campus_connect.pdf', 'uploaded', NOW()
FROM projects p
WHERE p.title='CampusConnect University Network' AND p.status='archived'
AND NOT EXISTS (SELECT 1 FROM project_files pf WHERE pf.project_id=p.project_id AND pf.file_type='final_report')
LIMIT 1;
-- ============================================================
-- COMP4200 Project Introduction Timeline Builder
-- Coordinator creates timeline in Exam Distribution page and publishes it to students.
-- ============================================================
CREATE TABLE IF NOT EXISTS comp4200_timelines (
    timeline_id  INT PRIMARY KEY AUTO_INCREMENT,
    semester_id  INT NOT NULL UNIQUE,
    title        VARCHAR(180) NOT NULL DEFAULT 'Project Introduction Timeline',
    note         TEXT NULL,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    published_at DATETIME NULL,
    created_by   INT NULL,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by)  REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS comp4200_timeline_items (
    item_id         INT PRIMARY KEY AUTO_INCREMENT,
    timeline_id     INT NOT NULL,
    item_order      INT NOT NULL DEFAULT 1,
    title           VARCHAR(180) NOT NULL,
    description     TEXT NULL,
    start_date      DATE NULL,
    start_time      VARCHAR(5) NULL,
    due_date        DATE NULL,
    due_time        VARCHAR(5) NULL,
    milestone_label VARCHAR(180) NULL,
    is_deadline     BOOLEAN NOT NULL DEFAULT TRUE,
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_to    VARCHAR(20) NOT NULL DEFAULT 'supervisor',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (timeline_id) REFERENCES comp4200_timelines(timeline_id) ON DELETE CASCADE,
    INDEX idx_comp4200_timeline_items_due (due_date),
    INDEX idx_comp4200_timeline_items_order (timeline_id, item_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


CREATE TABLE IF NOT EXISTS comp4200_timelines (
    timeline_id  INT PRIMARY KEY AUTO_INCREMENT,
    semester_id  INT NOT NULL UNIQUE,
    title        VARCHAR(180) NOT NULL DEFAULT 'Project Introduction Timeline',
    note         TEXT NULL,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    published_at DATETIME NULL,
    created_by   INT NULL,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
    FOREIGN KEY (created_by)  REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS comp4200_timeline_items (
    item_id         INT PRIMARY KEY AUTO_INCREMENT,
    timeline_id     INT NOT NULL,
    item_order      INT NOT NULL DEFAULT 1,
    title           VARCHAR(180) NOT NULL,
    description     TEXT NULL,
    start_date      DATE NULL,
    start_time      VARCHAR(5) NULL,
    due_date        DATE NULL,
    due_time        VARCHAR(5) NULL,
    milestone_label VARCHAR(180) NULL,
    is_deadline     BOOLEAN NOT NULL DEFAULT TRUE,
    is_archived     BOOLEAN NOT NULL DEFAULT FALSE,
    submitted_to    VARCHAR(20) NOT NULL DEFAULT 'supervisor',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (timeline_id) REFERENCES comp4200_timelines(timeline_id) ON DELETE CASCADE,
    INDEX idx_comp4200_timeline_items_due (due_date),
    INDEX idx_comp4200_timeline_items_order (timeline_id, item_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;








-- ============================================================
-- APMS Section Results Migration
-- Coordinator marks Project Introduction sections and Graduation Project groups.
-- Only succeeded sections appear for the Head of Department.
-- ============================================================

CREATE TABLE IF NOT EXISTS section_completion_status (
    status_id INT PRIMARY KEY AUTO_INCREMENT,
    course_scope ENUM('introduction','graduation_project') NOT NULL,
    reference_id INT NOT NULL,
    status ENUM('pending','succeeded','not_succeeded') NOT NULL DEFAULT 'pending',
    notes TEXT NULL,
    marked_by INT NULL,
    marked_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_section_completion (course_scope, reference_id),
    INDEX idx_section_completion_status (status),
    INDEX idx_section_completion_scope_status (course_scope, status),
    FOREIGN KEY (marked_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;







-- ============================================================
-- APMS Lectures & Deliverables working tables
-- Run this once in MySQL if you want to create the tables manually.
-- The Flask APIs also create these tables automatically if missing.
-- ============================================================

CREATE TABLE IF NOT EXISTS coordinator_lectures (
    lecture_id INT PRIMARY KEY AUTO_INCREMENT,
    semester_id INT NULL,
    course_scope ENUM('introduction','graduation_project') NOT NULL DEFAULT 'introduction',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    lecture_date DATE NULL,
    week_label VARCHAR(80),
    status ENUM('scheduled','completed','cancelled') NOT NULL DEFAULT 'scheduled',
    created_by INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_coord_lectures_semester_scope (semester_id, course_scope),
    CONSTRAINT fk_coord_lectures_semester
        FOREIGN KEY (semester_id) REFERENCES semesters(semester_id)
        ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS coordinator_deliverables (
    deliverable_id INT PRIMARY KEY AUTO_INCREMENT,
    semester_id INT NULL,
    course_scope ENUM('introduction','graduation_project') NOT NULL DEFAULT 'introduction',
    title VARCHAR(200) NOT NULL,
    description TEXT,
    due_date DATE NULL,
    mark_points DECIMAL(5,2) NOT NULL DEFAULT 0,
    status ENUM('not_open','open','in_progress','completed','closed') NOT NULL DEFAULT 'not_open',
    created_by INT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_coord_deliverables_semester_scope (semester_id, course_scope),
    CONSTRAINT fk_coord_deliverables_semester
        FOREIGN KEY (semester_id) REFERENCES semesters(semester_id)
        ON DELETE SET NULL
);


CREATE TABLE IF NOT EXISTS coordinator_deliverable_submissions (
    submission_id INT PRIMARY KEY AUTO_INCREMENT,
    deliverable_id INT NOT NULL,
    project_id INT NULL,
    student_id INT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(600) NULL,
    file_data LONGBLOB NULL,
    file_mime VARCHAR(120) NULL,
    file_size_mb DECIMAL(7,2) NULL,
    submitted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status ENUM('submitted','late','reviewed') NOT NULL DEFAULT 'submitted',
    notes TEXT NULL,

    UNIQUE KEY uq_deliverable_student (deliverable_id, student_id),

    FOREIGN KEY (deliverable_id)
        REFERENCES coordinator_deliverables(deliverable_id)
        ON DELETE CASCADE,

    FOREIGN KEY (project_id)
        REFERENCES projects(project_id)
        ON DELETE SET NULL,

    FOREIGN KEY (student_id)
        REFERENCES students(student_id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;



UPDATE committee_plans cp
JOIN (
    SELECT 
        cpp.plan_id,
        MIN(p.supervisor_id) AS supervisor_id
    FROM committee_plan_projects cpp
    JOIN projects p ON p.project_id = cpp.project_id
    WHERE p.supervisor_id IS NOT NULL
    GROUP BY cpp.plan_id
) x ON x.plan_id = cp.plan_id
SET cp.responsible_faculty_id = x.supervisor_id
WHERE cp.plan_id > 0;




INSERT INTO committee_plan_members (plan_id, faculty_id, role)
SELECT 
    cp.plan_id,
    cp.responsible_faculty_id,
    'member'
FROM committee_plans cp
WHERE cp.plan_id > 0
  AND cp.responsible_faculty_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM committee_plan_members cpm
      WHERE cpm.plan_id = cp.plan_id
        AND cpm.faculty_id = cp.responsible_faculty_id
  );


-- ============================================================
-- ============================================================
-- APMS FINAL ADDED EDITS — Committee Supervisor Distribution
-- Uses ONLY the COMP4200 + COMP4300 doctors in English.
-- Rules supported by the updated backend:
--   * Each generated committee is grouped by one project supervisor.
--   * The project supervisor is included in the committee and displayed as Supervisor.
--   * The project supervisor is NOT manually assigned as Responsible.
--   * Other doctors are displayed as Member.
--   * If a supervisor has 1 project, the committee has 1 project.
--   * If a supervisor has 2+ projects, they stay together in one committee.
-- ============================================================

USE apms_db;
SET NAMES utf8mb4;
SET SQL_SAFE_UPDATES = 0;

-- ------------------------------------------------------------
-- 0) Make sure there is an active semester
-- ------------------------------------------------------------
INSERT INTO semesters (academic_year, semester_number, course_code, start_date, end_date, is_active)
SELECT '2025/2026', 2, 'COMP4300', CURDATE(), DATE_ADD(CURDATE(), INTERVAL 120 DAY), TRUE
WHERE NOT EXISTS (SELECT 1 FROM semesters WHERE is_active = TRUE);

SET @target_semester_id := (
    SELECT semester_id
    FROM semesters
    WHERE is_active = TRUE
    ORDER BY semester_id DESC
    LIMIT 1
);

-- ------------------------------------------------------------
-- 1) Clear active generated committee plans so doctors/projects become available
-- ------------------------------------------------------------
UPDATE projects p
JOIN committee_plan_projects cpp ON cpp.project_id = p.project_id
JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
SET p.status = 'submitted'
WHERE cp.status IN ('draft', 'scheduled', 'ongoing', 'in_progress')
  AND p.status = 'committee_evaluation';

DELETE cpm
FROM committee_plan_members cpm
JOIN committee_plans cp ON cp.plan_id = cpm.plan_id
WHERE cp.status IN ('draft', 'scheduled', 'ongoing', 'in_progress');

DELETE cpp
FROM committee_plan_projects cpp
JOIN committee_plans cp ON cp.plan_id = cpp.plan_id
WHERE cp.status IN ('draft', 'scheduled', 'ongoing', 'in_progress');

DELETE FROM committee_plans
WHERE status IN ('draft', 'scheduled', 'ongoing', 'in_progress')
  AND plan_id > 0;

-- ------------------------------------------------------------
-- 2) Make sure committee_plan_members can store Supervisor label
-- ------------------------------------------------------------
SET @role_column_exists := (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'committee_plan_members'
      AND COLUMN_NAME = 'role'
);
SET @sql := IF(
    @role_column_exists > 0,
    'ALTER TABLE committee_plan_members MODIFY COLUMN role ENUM(''member'',''supervisor'',''responsible'') NOT NULL DEFAULT ''member''',
    'SELECT "committee_plan_members.role does not exist"'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE committee_plan_members
SET role = 'supervisor'
WHERE role = 'responsible';

-- ------------------------------------------------------------
-- 3) Ensure the COMP4200 + COMP4300 doctors exist
-- ------------------------------------------------------------
SET @pwd := '$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.';

INSERT IGNORE INTO users
(university_id, full_name, email, password_hash, role, avatar_initials, is_active)
SELECT * FROM (
    SELECT '3002' AS university_id, 'Dr. Sobhi Ahmad' AS full_name, 'sobhi.ahmad@birzeit.edu' AS email, @pwd AS password_hash, 'supervisor' AS role, 'SA' AS avatar_initials, TRUE AS is_active
    UNION ALL SELECT '3003', 'Dr. Radi Jarrar', 'radi.jarrar@birzeit.edu', @pwd, 'supervisor', 'RJ', TRUE
    UNION ALL SELECT '3004', 'Dr. Abdullah Krakeh', 'abdullah.krakeh@birzeit.edu', @pwd, 'supervisor', 'AK', TRUE
    UNION ALL SELECT '3006', 'Dr. Murad Njoum', 'murad.njoum@birzeit.edu', @pwd, 'supervisor', 'MN', TRUE
    UNION ALL SELECT '3007', 'Dr. Adel Taweel', 'adel.taweel@birzeit.edu', @pwd, 'supervisor', 'AT', TRUE
    UNION ALL SELECT '3008', 'Dr. Yousef Hassouneh', 'yousef.hassouneh@birzeit.edu', @pwd, 'supervisor', 'YH', TRUE
    UNION ALL SELECT '3009', 'Dr. Ruba Awadallah', 'ahmad.abusneina@birzeit.edu', @pwd, 'supervisor', 'AS', TRUE
    UNION ALL SELECT '3010', 'Dr. Bassem Alserafi', 'bassem.alserafi@birzeit.edu', @pwd, 'supervisor', 'BA', TRUE
    UNION ALL SELECT '3011', 'Dr. Mamoun Nawahdah', 'mamoun.nawahdah@birzeit.edu', @pwd, 'supervisor', 'MN', TRUE
    UNION ALL SELECT '3012', 'Dr. Tasneem Zayt', 'tasneem.zayt@birzeit.edu', @pwd, 'supervisor', 'TZ', TRUE
    UNION ALL SELECT '3013', 'Dr. Samer Zein', 'samer.zein@birzeit.edu', @pwd, 'supervisor', 'SZ', TRUE
    UNION ALL SELECT '3014', 'Dr. Hafez Barghouthi', 'hafez.barghouthi@birzeit.edu', @pwd, 'supervisor', 'HB', TRUE
    UNION ALL SELECT '3015', 'Dr. Abdullah Al-Natsheh', 'abdullah.alnatsheh@birzeit.edu', @pwd, 'supervisor', 'AN', TRUE
    UNION ALL SELECT '3016', 'Dr. Alaa Hasheesh', 'alaa.hasheesh@birzeit.edu', @pwd, 'supervisor', 'AH', TRUE
    UNION ALL SELECT '3017', 'Dr. Faisal Shehadeh', 'faisal.shehadeh@birzeit.edu', @pwd, 'supervisor', 'FS', TRUE
    UNION ALL SELECT '3018', 'Dr. Fadi Khalil', 'fadi.khalil@birzeit.edu', @pwd, 'supervisor', 'FK', TRUE
    UNION ALL SELECT '3019', 'Dr. Mohammad Helal', 'mohammad.helal@birzeit.edu', @pwd, 'supervisor', 'MH', TRUE
    UNION ALL SELECT '3020', 'Dr. Rashid Yousef', 'rashid.yousef@birzeit.edu', @pwd, 'supervisor', 'RY', TRUE
    UNION ALL SELECT '3021', 'Dr. Ehab Alshaer', 'ehab.alshaer@birzeit.edu', @pwd, 'supervisor', 'EA', TRUE
    UNION ALL SELECT '3022', 'Dr. Sobhi Ahmad', 'naima.harbawi@birzeit.edu', @pwd, 'supervisor', 'NH', TRUE
    UNION ALL SELECT '3023', 'Dr. Ahmad Fahl', 'ahmad.fahl@birzeit.edu', @pwd, 'supervisor', 'AF', TRUE
    UNION ALL SELECT '3024', 'Dr. Ahmad Sabbah', 'ahmad.sabbah@birzeit.edu', @pwd, 'supervisor', 'AS', TRUE
    UNION ALL SELECT '3025', 'Dr. Mohammad Alkhanafseh', 'mohammad.alkhanafseh@birzeit.edu', @pwd, 'supervisor', 'MA', TRUE
) AS doctors
WHERE NOT EXISTS (
    SELECT 1
    FROM users u
    WHERE u.full_name = doctors.full_name
       OR u.email = doctors.email
       OR u.university_id = doctors.university_id
);

INSERT IGNORE INTO faculty (user_id, specialization, years_experience, title)
SELECT
    u.user_id,
    CASE u.full_name
        WHEN 'Dr. Iyad Jaber' THEN 'software_engineering'
        WHEN 'Dr. Sobhi Ahmad' THEN 'software_engineering'
        WHEN 'Dr. Radi Jarrar' THEN 'software_engineering'
        WHEN 'Dr. Abdullah Krakeh' THEN 'databases'
        WHEN 'Dr. Ruba Awadallah' THEN 'web_development'
        WHEN 'Dr. Murad Njoum' THEN 'databases'
        WHEN 'Dr. Adel Taweel' THEN 'software_engineering'
        WHEN 'Dr. Yousef Hassouneh' THEN 'web_development'
        WHEN 'Dr. Ruba Awadallah' THEN 'software_engineering'
        WHEN 'Dr. Bassem Alserafi' THEN 'databases'
        WHEN 'Dr. Mamoun Nawahdah' THEN 'mobile'
        WHEN 'Dr. Tasneem Zayt' THEN 'software_engineering'
        WHEN 'Dr. Samer Zein' THEN 'software_engineering'
        WHEN 'Dr. Hafez Barghouthi' THEN 'security_networks'
        WHEN 'Dr. Abdullah Al-Natsheh' THEN 'software_engineering'
        WHEN 'Dr. Alaa Hasheesh' THEN 'software_engineering'
        WHEN 'Dr. Faisal Shehadeh' THEN 'mobile'
        WHEN 'Dr. Fadi Khalil' THEN 'web_development'
        WHEN 'Dr. Mohammad Helal' THEN 'artificial_intelligence'
        WHEN 'Dr. Rashid Yousef' THEN 'software_engineering'
        WHEN 'Dr. Ehab Alshaer' THEN 'software_engineering'
        WHEN 'Dr. Sobhi Ahmad' THEN 'software_engineering'
        WHEN 'Dr. Ahmad Fahl' THEN 'software_engineering'
        WHEN 'Dr. Ahmad Sabbah' THEN 'artificial_intelligence'
        WHEN 'Dr. Mohammad Alkhanafseh' THEN 'security_networks'
        ELSE 'software_engineering'
    END AS specialization,
    8 AS years_experience,
    'Dr.' AS title
FROM users u
LEFT JOIN faculty f ON f.user_id = u.user_id
WHERE u.full_name IN (
    'Dr. Iyad Jaber',
    'Dr. Sobhi Ahmad',
    'Dr. Radi Jarrar',
    'Dr. Abdullah Krakeh',
    'Dr. Ruba Awadallah',
    'Dr. Murad Njoum',
    'Dr. Adel Taweel',
    'Dr. Yousef Hassouneh',
    'Dr. Ruba Awadallah',
    'Dr. Bassem Alserafi',
    'Dr. Mamoun Nawahdah',
    'Dr. Tasneem Zayt',
    'Dr. Samer Zein',
    'Dr. Hafez Barghouthi',
    'Dr. Abdullah Al-Natsheh',
    'Dr. Alaa Hasheesh',
    'Dr. Faisal Shehadeh',
    'Dr. Fadi Khalil',
    'Dr. Mohammad Helal',
    'Dr. Rashid Yousef',
    'Dr. Ehab Alshaer',
    'Dr. Sobhi Ahmad',
    'Dr. Ahmad Fahl',
    'Dr. Ahmad Sabbah',
    'Dr. Mohammad Alkhanafseh'
)
AND f.user_id IS NULL;

-- ------------------------------------------------------------
-- 4) Add eligible projects grouped by real supervisors from the schedule
-- ------------------------------------------------------------
SET @sup_ai  := (SELECT f.faculty_id FROM faculty f JOIN users u ON u.user_id=f.user_id WHERE u.full_name='Dr. Mohammad Helal' LIMIT 1);
SET @sup_web := (SELECT f.faculty_id FROM faculty f JOIN users u ON u.user_id=f.user_id WHERE u.full_name='Dr. Ruba Awadallah' LIMIT 1);
SET @sup_se  := (SELECT f.faculty_id FROM faculty f JOIN users u ON u.user_id=f.user_id WHERE u.full_name='Dr. Iyad Jaber' LIMIT 1);
SET @sup_sec := (SELECT f.faculty_id FROM faculty f JOIN users u ON u.user_id=f.user_id WHERE u.full_name='Dr. Hafez Barghouthi' LIMIT 1);
SET @sup_db  := (SELECT f.faculty_id FROM faculty f JOIN users u ON u.user_id=f.user_id WHERE u.full_name='Dr. Abdullah Krakeh' LIMIT 1);
SET @sup_mob := (SELECT f.faculty_id FROM faculty f JOIN users u ON u.user_id=f.user_id WHERE u.full_name='Dr. Mamoun Nawahdah' LIMIT 1);

INSERT IGNORE INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
SELECT * FROM (
    SELECT 'Committee Demo AI Project 01' AS title, 'ai' AS project_type, @target_semester_id AS semester_id, @sup_ai AS supervisor_id, 'submitted' AS status, CURDATE() AS submission_date
    UNION ALL SELECT 'Committee Demo AI Project 02', 'ai', @target_semester_id, @sup_ai, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Web Project 01', 'web', @target_semester_id, @sup_web, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Web Project 02', 'web', @target_semester_id, @sup_web, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo SE Project 01', 'software_engineering', @target_semester_id, @sup_se, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo SE Project 02', 'software_engineering', @target_semester_id, @sup_se, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Security Project 01', 'security', @target_semester_id, @sup_sec, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Security Project 02', 'security', @target_semester_id, @sup_sec, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Database Project 01', 'databases', @target_semester_id, @sup_db, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Database Project 02', 'databases', @target_semester_id, @sup_db, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Mobile Project 01', 'mobile', @target_semester_id, @sup_mob, 'submitted', CURDATE()
    UNION ALL SELECT 'Committee Demo Mobile Project 02', 'mobile', @target_semester_id, @sup_mob, 'submitted', CURDATE()
) AS new_projects
WHERE new_projects.semester_id IS NOT NULL
  AND new_projects.supervisor_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM projects p
      WHERE p.semester_id = new_projects.semester_id
        AND p.title = new_projects.title
  );

UPDATE projects
SET status = 'submitted'
WHERE semester_id = @target_semester_id
  AND title LIKE 'Committee Demo % Project %'
  AND status IN ('committee_evaluation', 'under_review', 'needs_revision', 'draft');

-- ------------------------------------------------------------
-- 5) Verification
-- ------------------------------------------------------------
SELECT
    'Available active doctors from COMP4200/COMP4300 list' AS check_name,
    COUNT(*) AS total_doctors
FROM faculty f
JOIN users u ON u.user_id = f.user_id
WHERE u.full_name IN (
    'Dr. Iyad Jaber',
    'Dr. Sobhi Ahmad',
    'Dr. Radi Jarrar',
    'Dr. Abdullah Krakeh',
    'Dr. Ruba Awadallah',
    'Dr. Murad Njoum',
    'Dr. Adel Taweel',
    'Dr. Yousef Hassouneh',
    'Dr. Ruba Awadallah',
    'Dr. Bassem Alserafi',
    'Dr. Mamoun Nawahdah',
    'Dr. Tasneem Zayt',
    'Dr. Samer Zein',
    'Dr. Hafez Barghouthi',
    'Dr. Abdullah Al-Natsheh',
    'Dr. Alaa Hasheesh',
    'Dr. Faisal Shehadeh',
    'Dr. Fadi Khalil',
    'Dr. Mohammad Helal',
    'Dr. Rashid Yousef',
    'Dr. Ehab Alshaer',
    'Dr. Sobhi Ahmad',
    'Dr. Ahmad Fahl',
    'Dr. Ahmad Sabbah',
    'Dr. Mohammad Alkhanafseh'
)
  AND u.is_active = TRUE;

SELECT
    f.faculty_id,
    u.full_name AS supervisor_name,
    f.specialization,
    COUNT(p.project_id) AS eligible_projects
FROM projects p
JOIN faculty f ON f.faculty_id = p.supervisor_id
JOIN users u ON u.user_id = f.user_id
WHERE p.semester_id = @target_semester_id
  AND p.status IN ('submitted', 'under_review', 'needs_revision', 'committee_evaluation')
  AND p.title LIKE 'Committee Demo % Project %'
GROUP BY f.faculty_id, u.full_name, f.specialization
ORDER BY u.full_name;

SELECT
    'Demo projects ready' AS check_name,
    COUNT(*) AS total_demo_projects
FROM projects
WHERE semester_id = @target_semester_id
  AND status IN ('submitted', 'under_review', 'needs_revision', 'committee_evaluation')
  AND title LIKE 'Committee Demo % Project %';

SET SQL_SAFE_UPDATES = 0;



CREATE TABLE IF NOT EXISTS grade_entry_sessions (
    session_id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NULL,
    section_id INT NULL,
    course_scope ENUM('introduction','graduation_project') NOT NULL,
    status ENUM('closed','open','completed') NOT NULL DEFAULT 'open',
    opened_by INT NOT NULL,
    opened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME NULL,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE,
    FOREIGN KEY (opened_by) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS grade_entries (
    entry_id INT PRIMARY KEY AUTO_INCREMENT,
    session_id INT NOT NULL,
    faculty_id INT NOT NULL,
    project_id INT NULL,
    section_id INT NULL,

    grade_type ENUM(
        'report_reader',
        'coordinator',
        'supervisor',
        'discussion_member',
        'committee_member'
    ) NOT NULL,

    max_mark DECIMAL(5,2) NOT NULL,
    mark DECIMAL(5,2) NULL,
    comments TEXT NULL,

    submitted_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_grade_entry (session_id, faculty_id, grade_type),

    FOREIGN KEY (session_id) REFERENCES grade_entry_sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE
);



CREATE TABLE IF NOT EXISTS project_evaluation_windows (
    window_id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    course_scope ENUM('introduction','graduation_project') NOT NULL,
    is_open TINYINT(1) NOT NULL DEFAULT 0,
    opened_by INT NULL,
    opened_at DATETIME NULL,
    closed_at DATETIME NULL,
    due_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_eval_window_project_course (project_id, course_scope),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (opened_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS project_grade_entries (
    grade_id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    course_scope ENUM('introduction','graduation_project') NOT NULL,
    component ENUM(
        'intro_report_reader',
        'intro_coordinator',
        'intro_supervisor',
        'intro_discussion_member',
        'grad_report_reader',
        'grad_supervisor',
        'grad_committee_member'
    ) NOT NULL,
    evaluator_user_id INT NOT NULL,
    evaluator_faculty_id INT NULL,
    mark DECIMAL(6,2) NULL,
    max_mark DECIMAL(6,2) NOT NULL,
    notes TEXT NULL,
    is_submitted TINYINT(1) NOT NULL DEFAULT 0,
    submitted_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_grade_once (project_id, course_scope, component, evaluator_user_id),
    INDEX idx_grade_project_course (project_id, course_scope),
    INDEX idx_grade_evaluator (evaluator_user_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (evaluator_user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (evaluator_faculty_id) REFERENCES faculty(faculty_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS project_final_evaluation_results (
    result_id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    course_scope ENUM('introduction','graduation_project') NOT NULL,
    report_score DECIMAL(6,2) NULL,
    supervisor_score DECIMAL(6,2) NULL,
    coordinator_score DECIMAL(6,2) NULL,
    discussion_score DECIMAL(6,2) NULL,
    committee_score DECIMAL(6,2) NULL,
    final_score DECIMAL(6,2) NULL,
    decision ENUM('pending','accepted','rejected','archived') NOT NULL DEFAULT 'pending',
    notes TEXT NULL,
    published_by INT NULL,
    published_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_eval_result_project_course (project_id, course_scope),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (published_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;





-- Add group_name to projects so the coordinator sees the group name written by students.
SET @db := DATABASE();
SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE projects ADD COLUMN group_name VARCHAR(120) NULL AFTER project_id',
        'SELECT "projects.group_name already exists"'
    )
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'projects'
      AND COLUMN_NAME = 'group_name'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;




-- Allow committee members to be labeled as supervisor / responsible / member.
ALTER TABLE committee_plan_members
MODIFY COLUMN role ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member';

-- Two report readers for each project.
CREATE TABLE IF NOT EXISTS project_report_readers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    faculty_id INT NOT NULL,
    reader_order TINYINT NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_project_reader_order (project_id, reader_order),
    UNIQUE KEY uq_project_reader_faculty (project_id, faculty_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Mark the current responsible doctor as responsible in committee_plan_members,
-- without removing the supervisor label where it already exists.
SET SQL_SAFE_UPDATES = 0;

UPDATE committee_plan_members cpm
JOIN (
    SELECT cpm2.id
    FROM committee_plan_members cpm2
    JOIN committee_plans cp2 ON cp2.plan_id = cpm2.plan_id
    WHERE cp2.responsible_faculty_id = cpm2.faculty_id
      AND cpm2.role <> 'supervisor'
) x ON x.id = cpm.id
SET cpm.role = 'responsible';

SET SQL_SAFE_UPDATES = 0;


-- Optional cleanup: remove committee demo projects that were only test data.
-- Keep this commented if you still need them for committee testing.
-- DELETE FROM projects
-- WHERE title LIKE 'Committee Demo % Project %'
--   AND project_id NOT IN (SELECT DISTINCT project_id FROM project_members);

-- ============================================================
--  END OF FILE
-- ============================================================




-- Add group_name to projects so the coordinator sees the group name written by students.
SET @db := DATABASE();
SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE projects ADD COLUMN group_name VARCHAR(120) NULL AFTER project_id',
        'SELECT "projects.group_name already exists"'
    )
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = @db
      AND TABLE_NAME = 'projects'
      AND COLUMN_NAME = 'group_name'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;


-- Allow committee members to be labeled as supervisor / responsible / member.
ALTER TABLE committee_plan_members
MODIFY COLUMN role ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member';

-- Two report readers for each project.
CREATE TABLE IF NOT EXISTS project_report_readers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    faculty_id INT NOT NULL,
    reader_order TINYINT NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_project_reader_order (project_id, reader_order),
    UNIQUE KEY uq_project_reader_faculty (project_id, faculty_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Mark the current responsible doctor as responsible in committee_plan_members,
-- without removing the supervisor label where it already exists.
SET SQL_SAFE_UPDATES = 0;

UPDATE committee_plan_members cpm
JOIN (
    SELECT cpm2.id
    FROM committee_plan_members cpm2
    JOIN committee_plans cp2 ON cp2.plan_id = cpm2.plan_id
    WHERE cp2.responsible_faculty_id = cpm2.faculty_id
      AND cpm2.role <> 'supervisor'
) x ON x.id = cpm.id
SET cpm.role = 'responsible';

SET SQL_SAFE_UPDATES = 0;


-- Optional cleanup: remove committee demo projects that were only test data.
-- Keep this commented if you still need them for committee testing.
-- DELETE FROM projects
-- WHERE title LIKE 'Committee Demo % Project %'
--   AND project_id NOT IN (SELECT DISTINCT project_id FROM project_members);

CREATE TABLE IF NOT EXISTS project_report_readers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    faculty_id INT NOT NULL,
    reader_order TINYINT NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_project_reader_order (project_id, reader_order),
    UNIQUE KEY uq_project_reader_faculty (project_id, faculty_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Mark the current responsible doctor as responsible in committee_plan_members,
-- without removing the supervisor label where it already exists.
SET SQL_SAFE_UPDATES = 0;

UPDATE committee_plan_members cpm
JOIN (
    SELECT cpm2.id
    FROM committee_plan_members cpm2
    JOIN committee_plans cp2 ON cp2.plan_id = cpm2.plan_id
    WHERE cp2.responsible_faculty_id = cpm2.faculty_id
      AND cpm2.role <> 'supervisor'
) x ON x.id = cpm.id
SET cpm.role = 'responsible';

SET SQL_SAFE_UPDATES = 0;
  
  
  
  -- Allow committee members to be labeled as supervisor / responsible / member.
ALTER TABLE committee_plan_members
MODIFY COLUMN role ENUM('member','supervisor','responsible') NOT NULL DEFAULT 'member';

-- Two report readers for each project.
CREATE TABLE IF NOT EXISTS project_report_readers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    project_id INT NOT NULL,
    faculty_id INT NOT NULL,
    reader_order TINYINT NOT NULL,
    assigned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_project_reader_order (project_id, reader_order),
    UNIQUE KEY uq_project_reader_faculty (project_id, faculty_id),
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Mark the current responsible doctor as responsible in committee_plan_members,
-- without removing the supervisor label where it already exists.
SET SQL_SAFE_UPDATES = 0;

UPDATE committee_plan_members cpm
JOIN (
    SELECT cpm2.id
    FROM committee_plan_members cpm2
    JOIN committee_plans cp2 ON cp2.plan_id = cpm2.plan_id
    WHERE cp2.responsible_faculty_id = cpm2.faculty_id
      AND cpm2.role <> 'supervisor'
) x ON x.id = cpm.id
SET cpm.role = 'responsible';

SET SQL_SAFE_UPDATES = 0;








-- ============================================================
--  FINAL SAFE PROJECT READING FIX — NO DELETE VERSION
-- ============================================================
-- This block fixes the pages that were reading demo/empty projects.
-- It DOES NOT delete any project.
-- It only marks demo/empty projects as draft and creates views that the backend can read.

USE apms_db;
SET NAMES utf8mb4;
SET SQL_SAFE_UPDATES = 0;
SET FOREIGN_KEY_CHECKS = 0;

-- 1) Keep Committee Demo projects in the database, but do not let them appear as real graduation groups.
UPDATE projects p
LEFT JOIN project_members pm ON pm.project_id = p.project_id
SET p.status = 'draft'
WHERE p.title LIKE 'Committee Demo%'
  AND pm.project_id IS NULL;

-- 2) Keep any zero-student project in the DB, but hide it from pages that require real students.
UPDATE projects p
LEFT JOIN project_members pm ON pm.project_id = p.project_id
SET p.status = 'draft'
WHERE pm.project_id IS NULL;

-- 3) View used by Student Distribution / Section Results / Committee pages.
-- Real graduation projects = projects that have at least one student in project_members.
CREATE OR REPLACE VIEW vw_real_graduation_projects AS
SELECT
    p.project_id,
    COALESCE(NULLIF(p.group_name, ''), CONCAT('Group ', p.project_id)) AS section_name,
    p.title,
    p.title_en,
    p.project_type,
    p.semester_id,
    p.supervisor_id,
    u_sup.full_name AS supervisor_name,
    p.status,
    p.submission_date,
    COUNT(DISTINCT pm.student_id) AS student_count,
    GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', ') AS students
FROM projects p
JOIN project_members pm ON pm.project_id = p.project_id
JOIN students st ON st.student_id = pm.student_id
JOIN users u_st ON u_st.user_id = st.user_id
LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
WHERE p.title NOT LIKE 'Committee Demo%'
GROUP BY
    p.project_id,
    p.group_name,
    p.title,
    p.title_en,
    p.project_type,
    p.semester_id,
    p.supervisor_id,
    u_sup.full_name,
    p.status,
    p.submission_date;

-- 4) View for Coordinator Section Results page.
CREATE OR REPLACE VIEW vw_graduation_section_results AS
SELECT
    'graduation_project' AS course_scope,
    v.project_id AS reference_id,
    v.section_name,
    v.supervisor_id,
    v.supervisor_name,
    v.student_count,
    v.students,
    COALESCE(scs.status, 'pending') AS result_status,
    scs.notes,
    scs.marked_at,
    marker.full_name AS marked_by_name
FROM vw_real_graduation_projects v
LEFT JOIN section_completion_status scs
       ON scs.course_scope = 'graduation_project'
      AND scs.reference_id = v.project_id
LEFT JOIN users marker ON marker.user_id = scs.marked_by;

-- 5) View for Student Distribution page.
CREATE OR REPLACE VIEW vw_distribution_real_groups AS
SELECT
    v.project_id,
    v.section_name AS group_name,
    v.students AS team_members,
    v.title AS idea_title,
    v.supervisor_id AS final_supervisor_id,
    v.supervisor_name AS final_supervisor_name,
    v.status,
    v.student_count
FROM vw_real_graduation_projects v;

SET FOREIGN_KEY_CHECKS = 1;
SET SQL_SAFE_UPDATES = 0;

-- Final check: only real projects with real students should appear here.
SELECT
    project_id,
    section_name,
    title,
    supervisor_name,
    student_count,
    students
FROM vw_real_graduation_projects
ORDER BY project_id;

-- ============================================================
--  END OF CLEAN FULL SQL FILE
-- ============================================================

-- Re-enable safe update mode after the full import.
SET SQL_SAFE_UPDATES = 1;




SET SQL_SAFE_UPDATES = 0;
SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;

-- ============================================================
-- 1) Make sure section_completion_status has the correct column names
--    Frontend expects result_status, but the table column is status.
--    Views below expose it as result_status.
-- ============================================================

CREATE TABLE IF NOT EXISTS section_completion_status (
    status_id INT PRIMARY KEY AUTO_INCREMENT,
    course_scope ENUM('introduction','graduation_project') NOT NULL,
    reference_id INT NOT NULL,
    status ENUM('pending','succeeded','not_succeeded') NOT NULL DEFAULT 'pending',
    notes TEXT NULL,
    marked_by INT NULL,
    marked_at DATETIME NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_section_completion (course_scope, reference_id),
    INDEX idx_section_completion_status (status),
    INDEX idx_section_completion_scope_status (course_scope, status),
    FOREIGN KEY (marked_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 2) Make sure Project Introduction sections tables exist
-- ============================================================

CREATE TABLE IF NOT EXISTS student_distribution_sections (
    section_id     INT PRIMARY KEY AUTO_INCREMENT,
    section_name   VARCHAR(100) NOT NULL,
    supervisor_id  INT NOT NULL,
    entered_by     INT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supervisor_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
    FOREIGN KEY (entered_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS section_students (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    section_id  INT NOT NULL,
    student_id  INT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_section_student (section_id, student_id),
    FOREIGN KEY (section_id) REFERENCES student_distribution_sections(section_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 3) Optional safe seed:
--    If after the full reset there are ZERO intro sections,
--    create three COMP4200 introduction sections using your real doctors.
--    This does NOT delete or overwrite anything.
-- ============================================================

INSERT INTO student_distribution_sections (section_name, supervisor_id, entered_by)
SELECT x.section_name, f.faculty_id, NULL
FROM (
    SELECT 'COMP4200 Introduction Section 1' AS section_name, 'Dr. Ruba Awadallah' AS doctor_name
    UNION ALL SELECT 'COMP4200 Introduction Section 2', 'Dr. Iyad Jaber'
    UNION ALL SELECT 'COMP4200 Introduction Section 3', 'Dr. Abdullah Krakeh'
) x
JOIN users u ON u.full_name = x.doctor_name
JOIN faculty f ON f.user_id = u.user_id
WHERE NOT EXISTS (
    SELECT 1 FROM student_distribution_sections
);

-- ============================================================
-- 4) Real Graduation Project view
--    Keeps demo projects in DB, but hides them from section results.
-- ============================================================

CREATE OR REPLACE VIEW vw_real_graduation_projects AS
SELECT
    p.project_id,
    CONCAT('Group ', p.project_id) AS section_name,
    p.supervisor_id,
    u_sup.full_name AS supervisor_name,
    COUNT(DISTINCT pm.student_id) AS student_count,
    GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', ') AS students
FROM projects p
JOIN semesters sem ON sem.semester_id = p.semester_id
JOIN project_members pm ON pm.project_id = p.project_id
JOIN students st ON st.student_id = pm.student_id
JOIN users u_st ON u_st.user_id = st.user_id
LEFT JOIN faculty f_sup ON f_sup.faculty_id = p.supervisor_id
LEFT JOIN users u_sup ON u_sup.user_id = f_sup.user_id
WHERE sem.course_code IN ('COMP4300', 'COMP4201')
  AND p.title NOT LIKE 'Committee Demo%'
GROUP BY
    p.project_id,
    p.supervisor_id,
    u_sup.full_name;

-- ============================================================
-- 5) Graduation section results view
--    IMPORTANT: reads scs.status and exposes result_status.
-- ============================================================

CREATE OR REPLACE VIEW vw_graduation_section_results AS
SELECT
    'graduation_project' AS course_scope,
    v.project_id AS reference_id,
    v.section_name,
    v.supervisor_id,
    v.supervisor_name,
    v.student_count,
    v.students,
    COALESCE(scs.status, 'pending') AS result_status,
    scs.notes,
    scs.marked_at,
    marker.full_name AS marked_by_name
FROM vw_real_graduation_projects v
LEFT JOIN section_completion_status scs
       ON scs.course_scope = 'graduation_project'
      AND scs.reference_id = v.project_id
LEFT JOIN users marker ON marker.user_id = scs.marked_by;

-- ============================================================
-- 6) Project Introduction section results view
--    This is the part that fixes the broken Introduction tab.
--    It reads from student_distribution_sections, NOT projects.
-- ============================================================

CREATE OR REPLACE VIEW vw_introduction_section_results AS
SELECT
    'introduction' AS course_scope,
    sds.section_id AS reference_id,
    sds.section_name,
    sds.supervisor_id,
    u_sup.full_name AS supervisor_name,
    COUNT(DISTINCT ss.student_id) AS student_count,
    COALESCE(
        GROUP_CONCAT(DISTINCT u_st.full_name ORDER BY u_st.full_name SEPARATOR ', '),
        ''
    ) AS students,
    COALESCE(scs.status, 'pending') AS result_status,
    scs.notes,
    scs.marked_at,
    marker.full_name AS marked_by_name
FROM student_distribution_sections sds
JOIN faculty f_sup ON f_sup.faculty_id = sds.supervisor_id
JOIN users u_sup ON u_sup.user_id = f_sup.user_id
LEFT JOIN section_students ss ON ss.section_id = sds.section_id
LEFT JOIN students st ON st.student_id = ss.student_id
LEFT JOIN users u_st ON u_st.user_id = st.user_id
LEFT JOIN section_completion_status scs
       ON scs.course_scope = 'introduction'
      AND scs.reference_id = sds.section_id
LEFT JOIN users marker ON marker.user_id = scs.marked_by
GROUP BY
    sds.section_id,
    sds.section_name,
    sds.supervisor_id,
    u_sup.full_name,
    scs.status,
    scs.notes,
    scs.marked_at,
    marker.full_name;

-- ============================================================
-- 7) Quick test queries
-- ============================================================

SELECT * FROM vw_introduction_section_results ORDER BY reference_id;
SELECT * FROM vw_graduation_section_results ORDER BY reference_id DESC;

SET FOREIGN_KEY_CHECKS = 1;
SET SQL_SAFE_UPDATES = 1;




USE apms_db;

SET SQL_SAFE_UPDATES = 0;

SET @col_exists = (
    SELECT COUNT(*)
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'faculty'
      AND COLUMN_NAME = 'office_number'
);

SET @sql = IF(
    @col_exists = 0,
    'ALTER TABLE faculty ADD COLUMN office_number VARCHAR(120) NULL AFTER title',
    'SELECT "office_number already exists"'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE faculty
SET office_number = COALESCE(office_number, 'Science Building — 214');

SET SQL_SAFE_UPDATES = 1;
