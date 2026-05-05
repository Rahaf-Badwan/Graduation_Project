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

SET FOREIGN_KEY_CHECKS = 0;
SET NAMES utf8mb4;

-- Drop all tables if they exist (safe re-run)
DROP TABLE IF EXISTS ai_conversations;
DROP TABLE IF EXISTS challenges_reflections;
DROP TABLE IF EXISTS supervisor_assignments;
DROP TABLE IF EXISTS notifications;
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
CREATE TABLE users (
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
CREATE TABLE faculty (
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
CREATE TABLE students (
    student_id      INT  PRIMARY KEY AUTO_INCREMENT,
    user_id         INT  UNIQUE NOT NULL,
    enrollment_year YEAR NULL,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 4 — semesters
--  Academic semesters (COMP4200 course)
-- ============================================================
CREATE TABLE semesters (
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
CREATE TABLE coordinator_assignments (
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
CREATE TABLE projects (
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
CREATE TABLE project_members (
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
CREATE TABLE project_files (
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
    file_size_mb  DECIMAL(7,2)    NULL,
    upload_status ENUM(
                    'not_uploaded',
                    'uploaded',
                    'required'
                  )               NOT NULL DEFAULT 'not_uploaded',
    uploaded_by   INT             NULL                    COMMENT 'student user_id',
    uploaded_at   TIMESTAMP       NULL,
    version       TINYINT         NOT NULL DEFAULT 1,
    FOREIGN KEY (project_id)  REFERENCES projects(project_id)  ON DELETE CASCADE,
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id)        ON DELETE SET NULL
) ENGINE=InnoDB;

-- ============================================================
--  TABLE 9 — project_progress
--  Completion percentage per component and overall
-- ============================================================
CREATE TABLE project_progress (
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
CREATE TABLE project_lifecycle (
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
CREATE TABLE feedback (
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
CREATE TABLE feedback_improvement_points (
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
CREATE TABLE committees (
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
CREATE TABLE committee_members (
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
CREATE TABLE coordinator_decisions (
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
CREATE TABLE final_decisions (
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
CREATE TABLE supervisor_notes (
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
CREATE TABLE deadlines (
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
CREATE TABLE notifications (
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
CREATE TABLE challenges_reflections (
    challenge_id    INT       PRIMARY KEY AUTO_INCREMENT,
    project_id      INT       NOT NULL,
    student_id      INT       NOT NULL COMMENT 'user_id',
    type            ENUM(
                      'technical',
                      'administrative',
                      'reflection'
                    )         NOT NULL,
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
CREATE TABLE supervisor_assignments (
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
--  TABLE 22 — ai_conversations
--  AI assistant chat history per user
--  Merged from: APMS.sql + AI_ARCHIVE_MIGRATION.sql
--  • session_id is NOT NULL (migration applied)
--  • Includes both indexes from the migration
-- ============================================================
CREATE TABLE ai_conversations (
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
CREATE TABLE password_reset_tokens (
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
INSERT INTO semesters (academic_year, semester_number, course_code, start_date, end_date, is_active) VALUES
('2025/2026', 1, 'COMP4200', '2025-09-01', '2026-02-28', TRUE),
('2024/2025', 1, 'COMP4200', '2024-09-01', '2025-02-28', FALSE),
('2023/2024', 1, 'COMP4200', '2023-09-01', '2024-02-28', FALSE),
('2022/2023', 1, 'COMP4200', '2022-09-01', '2023-02-28', FALSE);

-- Users
-- Faculty IDs are 4 digits (1001–1007); student IDs start from 1220000
INSERT INTO users (university_id, full_name, email, password_hash, role, avatar_initials, is_active) VALUES
-- Head of Department  (ID: 1001)
('1001', 'Prof. Raed Al-Qadi',     '1001@birzeit.edu', '$2b$12$EbPsSfvh6ScacL2l4uCkdOMwbfukrx0EdkL/0GBk/ntRtwRapvvBu',  'head_of_department', 'RQ', TRUE),
-- Coordinator         (ID: 1002)
('1002', 'Dr. Ahmad Abu Sneina',   '1002@birzeit.edu', '$2b$12$l9Jz.shLtccTVJh5r700w.kCUlmwlba4YgUvs2HZGs2UBwuoonMci', 'coordinator',        'AA', TRUE),
-- Supervisors         (IDs: 1003–1007)
('1003', 'Dr. Naima Harbawi',      '1003@birzeit.edu', '$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.',   'supervisor',         'NH', TRUE),
('1004', 'Dr. Mahmoud Salem',      '1004@birzeit.edu', '$2b$12$ctwodGi2uo7.QC.r7Qlt.u5n6wVvy280mQ/LtyaIlIjQLIVpgB/MW',   'supervisor',         'MS', TRUE),
('1005', 'Dr. Lina Haddad',        '1005@birzeit.edu', '$2b$12$aKMFBXAIvKSNsOAUpU9N8.oYnCqeu07VJc/PBgyB.H7WIxxc4ew9C',   'supervisor',         'LH', TRUE),
('1006', 'Dr. Samer Darwish',      '1006@birzeit.edu', '$2b$12$ljZY7r8ALYi62IyesXQ84uieyNMz2MXVJK.QI4Eu7ot9abWAa7TAG',   'supervisor',         'SD', TRUE),
('1007', 'Dr. Osama Arikat',       '1007@birzeit.edu', '$2b$12$.Uge.NmsvHbi9uSDgc1rhOYjO3Q1HAtYCLeN3YL1ctrGUKeRKo1ti',   'supervisor',         'OA', TRUE),
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
INSERT INTO faculty (user_id, specialization, years_experience, title) VALUES
(1, 'software_engineering',    15, 'Prof.'),
(2, 'software_engineering',    10, 'Dr.'),
(3, 'software_engineering',     6, 'Dr.'),
(4, 'artificial_intelligence', 12, 'Dr.'),
(5, 'web_development',          8, 'Dr.'),
(6, 'databases',                9, 'Dr.'),
(7, 'security_networks',        7, 'Dr.');

-- Student records (user_ids 8–17)
INSERT INTO students (user_id, enrollment_year) VALUES
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
INSERT INTO coordinator_assignments (faculty_id, semester_id, assigned_by, notes) VALUES
(2, 1, 1, 'Official coordinator for Semester 1 — 2025/2026');

-- Projects
INSERT INTO projects (title, title_en, abstract, keywords, project_type, semester_id, supervisor_id, status, submission_date, final_score) VALUES
(
  'Academic Project Lifecycle Management System (APMS)',
  'Academic Project Lifecycle Management System',
  'Most educational institutions lack an efficient way to centrally manage graduation projects from submission through archiving. This system provides a comprehensive web-based solution with AI features and automatic notifications, supporting more than 300 projects annually.',
  'project management, lifecycle, web application, AI, COMP4200',
  'web,ai',
  1, 3, 'under_review', '2026-02-01', NULL
),
(
  'Electronic Student Records Management System',
  'Electronic Student Records Management System',
  'A digital system for managing student academic records and grades with multi-role access control and academic performance reporting.',
  'student records, academic, grades, permissions',
  'web',
  1, 4, 'submitted', '2026-02-03', NULL
),
(
  'Smart Order Delivery Application',
  'Smart Order Delivery Application',
  'A mobile application for order delivery using intelligent routing algorithms to optimize delivery time and cost.',
  'mobile, delivery, smart routing, GPS',
  'mobile',
  1, 5, 'under_review', '2026-01-20', NULL
),
(
  'AI-Based Disease Recognition System',
  'AI-Based Disease Recognition System',
  'A system that uses deep learning techniques to recognize diseases from medical images with high accuracy using CNN architectures.',
  'AI, deep learning, medical imaging, CNN, classification',
  'ai',
  2, 4, 'accepted', '2025-02-01', 92.30
),
(
  'Adaptive E-Learning Platform',
  'Adaptive E-Learning Platform',
  'An e-learning platform that adapts to each student\'s learning level and delivers personalized content based on performance analytics.',
  'e-learning, adaptive, personalization, education',
  'web',
  3, 5, 'archived', '2024-02-01', 87.00
),
(
  'Mobile Patient Tracking Application',
  'Mobile Patient Tracking Application',
  'A mobile application for tracking patient records and treatment appointments, with strong data protection protocols compliant with privacy standards.',
  'mobile, healthcare, security, HIPAA, patient records',
  'mobile',
  1, 7, 'needs_revision', '2026-02-02', NULL
),
(
  'Smart Medical Appointment Booking System',
  'Smart Medical Appointment Booking System',
  'A web-based system for booking medical appointments with automated reminders and queue congestion analysis.',
  'web, appointments, healthcare, AI, notifications',
  'web',
  2, 3, 'rejected', '2025-01-15', 54.00
),
(
  'Digital Library Management System',
  'Digital Library Management System',
  'An integrated system for managing digital library resources with an advanced full-text search engine and borrowing workflow.',
  'library, digital, search engine, web, resources',
  'web',
  1, 6, 'accepted', '2026-01-18', 88.00
),
(
  'Cyber Infrastructure Protection System',
  'Cyber Infrastructure Protection System',
  'An integrated system for monitoring and protecting digital infrastructure against cyberattacks using real-time threat detection.',
  'cybersecurity, infrastructure, monitoring, intrusion detection',
  'security',
  1, 7, 'rejected', '2026-01-25', NULL
);

-- Project Members
INSERT INTO project_members (project_id, student_id, is_primary_contact) VALUES
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
INSERT INTO project_files (project_id, file_type, file_name, file_size_mb, upload_status, uploaded_by, uploaded_at, version) VALUES
-- APMS (project 1)
(1, 'final_report',  'APMS_Final_Report.pdf',        4.20, 'uploaded',     8, '2026-02-01 10:00:00', 2),
(1, 'source_code',   'APMS_SourceCode.zip',          18.50, 'uploaded',    8, '2026-02-01 10:05:00', 1),
(1, 'presentation',  'APMS_Presentation.pptx',        NULL, 'not_uploaded', NULL, NULL, 1),
-- Student Records (project 2)
(2, 'final_report',  'StudentRecords_Report.pdf',     3.10, 'uploaded',    11, '2026-02-03 09:00:00', 1),
(2, 'source_code',   'StudentRecords_Code.zip',       9.80, 'uploaded',    11, '2026-02-03 09:05:00', 1),
(2, 'presentation',  'StudentRecords_Slides.pptx',    NULL, 'not_uploaded', NULL, NULL, 1);

-- Project Progress
INSERT INTO project_progress (project_id, component, percentage, updated_by) VALUES
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
INSERT INTO project_lifecycle (project_id, stage, status, scheduled_date, completed_date, notes) VALUES
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
INSERT INTO feedback (project_id, reviewer_id, feedback_type, feedback_text, score, priority, is_draft) VALUES
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
INSERT INTO feedback_improvement_points (feedback_id, point_text, is_resolved) VALUES
(1, 'Expand system architecture section with detailed ERD diagrams',       FALSE),
(1, 'Ensure consistent technical terminology across all chapters',         FALSE),
(2, 'Detail the chatbot training methodology and accuracy evaluation',     FALSE),
(2, 'Add a comparison table of NLP models used',                           FALSE),
(3, 'Implement WCAG accessibility standards in the UI',                    FALSE),
(3, 'Upload presentation slides before February 15',                       FALSE);

-- Committees
INSERT INTO committees (project_id, committee_name, discussion_date, discussion_time, room, status, final_average, created_by) VALUES
(1, 'APMS Evaluation Committee',                     '2026-02-20', '10:00:00', 'A101', 'scheduled',  NULL,  2),
(4, 'AI Disease Recognition Evaluation Committee',   '2025-02-21', '14:00:00', 'B203', 'completed', 92.30,  2),
(5, 'E-Learning Platform Evaluation Committee',      '2024-02-22', '10:00:00', 'C105', 'completed', 87.00,  2);

-- Committee Members
INSERT INTO committee_members (committee_id, faculty_id, role, evaluation_score, evaluation_comments, evaluation_submitted, evaluation_submitted_at) VALUES
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
INSERT INTO supervisor_notes (project_id, supervisor_id, note_text, urgency) VALUES
(1, 3, 'Team is working diligently and progress is satisfactory. Presentation slides still need to be uploaded before the deadline.', 'on_track'),
(3, 5, 'No files have been uploaded for two weeks — requires immediate follow-up.',                                                   'urgent'),
(2, 4, 'Progress is slightly slow but still within acceptable range. Awaiting source code update.',                                   'needs_follow_up');

-- Coordinator Decisions
INSERT INTO coordinator_decisions (project_id, coordinator_id, decision, notes) VALUES
(4, 2, 'send_to_committee', 'Project accepted and forwarded to committee evaluation after a satisfactory initial review.'),
(5, 2, 'accepted',          'Excellent project — archiving completed successfully.'),
(7, 2, 'rejected',          'Project score is below the minimum required threshold of 60%.'),
(6, 2, 'needs_revision',    'Student must add a security and privacy section and clarify the patient data protection protocol.');

-- Final Decisions
INSERT INTO final_decisions (project_id, coordinator_id, decision, final_score, notes, is_archived, archived_at) VALUES
(4, 2, 'accepted', 92.30, 'Outstanding project — archived successfully.',          TRUE,  '2025-03-01 09:00:00'),
(5, 2, 'accepted', 87.00, 'Very good project — archived successfully.',             TRUE,  '2024-03-01 09:00:00'),
(7, 2, 'rejected', 54.00, 'Score below minimum threshold — student notified.',      FALSE, NULL);

-- Deadlines
INSERT INTO deadlines (semester_id, project_id, deadline_type, deadline_date, description) VALUES
(1, NULL, 'project_registration',    '2026-02-15', 'Deadline for all project registrations'),
(1, NULL, 'file_submission',         '2026-02-15', 'Deadline for uploading all required project files'),
(1, NULL, 'results_announcement',    '2026-02-28', 'Final results announcement date'),
(1, 1,    'final_report_submission', '2026-02-15', 'Final report submission deadline — APMS project'),
(1, 1,    'committee_discussion',    '2026-02-20', 'APMS project committee discussion date'),
(1, 1,    'supervisor_feedback',     '2026-02-08', 'Deadline for supervisor feedback on APMS report');

-- Notifications
INSERT INTO notifications (recipient_id, sender_id, notification_type, title, message, related_project_id, is_read) VALUES
-- Student (Rahaf, user 8) notifications
(8, 3,    'feedback_received',  'Your project has been reviewed',          'Dr. Naima Harbawi has submitted new feedback on your project.',             1, FALSE),
(8, 2,    'committee_assigned', 'Committee discussion scheduled',          'Your project discussion is scheduled for February 20 at 10:00 AM.',         1, FALSE),
(8, NULL, 'deadline_reminder',  'Reminder: Upload source code',            'Please upload the source code files before February 15.',                   1, FALSE),
-- Supervisor (Dr. Naima, user 3) notifications
(3, 8,    'file_uploaded',      'Rahaf Badwan uploaded updated files',     'A new version of the final report has been uploaded — APMS project.',       1, FALSE),
(3, 2,    'committee_assigned', 'New committee membership assigned',       'You have been assigned as a member of a new evaluation committee.',          1, FALSE),
(3, NULL, 'urgent_alert',       'Karim Odeh — urgent follow-up needed',   'Karim Odeh has not uploaded any files for two weeks.',                       3, FALSE),
-- Coordinator (Dr. Ahmad, user 2) notifications
(2, NULL, 'file_uploaded',      'New project pending your review',         'Electronic Student Records Management System — Salma Al-Khatib.',            2, FALSE),
(2, 4,    'project_reviewed',   'Dr. Mahmoud Salem completed evaluations', 'Dr. Mahmoud Salem completed 3 project evaluations — avg score: 89.3.',      NULL, FALSE),
(2, NULL, 'deadline_reminder',  '7 projects awaiting your decision',       '7 projects are pending coordinator review — some exceeded 48 hours.',       NULL, TRUE);

-- Student Challenges & Reflections (all linked to APMS project, submitted by Rahaf, user 8)
INSERT INTO challenges_reflections (project_id, student_id, type, description, solution_lesson) VALUES
(
  1, 8, 'technical',
  'We struggled to efficiently integrate the NLP model with the MySQL database without degrading system performance under a large number of concurrent project queries.',
  'We implemented query caching for frequent lookups and decoupled the AI service as an independent microservice to isolate performance bottlenecks.'
),
(
  1, 8, 'administrative',
  'Based on our meeting with Dr. Abu Sneina, fairly distributing supervisors across projects every semester is one of the biggest coordination challenges handled manually each term.',
  'We designed an automatic distribution algorithm that considers each supervisor''s specialization and enforces a balanced workload across all faculty members.'
),
(
  1, 8, 'reflection',
  'We learned that thorough documentation from the very beginning saves a significant amount of time later, especially when drawing UML diagrams and defining system requirements.',
  'Early and continuous documentation from the analysis phase is the key to a successful project delivery.'
);

-- AI Assistant Conversations (sample — coordinator session)
INSERT INTO ai_conversations (user_id, session_id, message_role, message_text) VALUES
(2, 'sess-coord-001', 'user',      'Show me projects similar to APMS'),
(2, 'sess-coord-001', 'assistant', 'Found 4 similar projects in the archive: Academic Task Management System (2024/2025), Electronic Supervision Platform (2023/2024), PhD Thesis Tracking System (2022/2023), and Scientific Review Management System (2022/2023).');

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
    INSERT INTO notifications (recipient_id, sender_id, notification_type, title, message, related_project_id)
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
        INSERT INTO notifications (recipient_id, sender_id, notification_type, title, message, related_project_id)
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

SET SQL_SAFE_UPDATES = 1;

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

-- ── 2. Coordinator for COMP4300 (Dr. Lina Haddad, faculty_id=5) ─────────
--       Assigned by Prof. Raed (user_id=1). Skipped if already assigned.
INSERT INTO coordinator_assignments (faculty_id, semester_id, assigned_by, notes)
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

-- Dr. Mahmoud Salem (faculty_id = 4)
INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
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

-- Dr. Lina Haddad (faculty_id = 5)
INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
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

-- Dr. Osama Arikat (faculty_id = 7)
INSERT INTO projects (title, project_type, semester_id, supervisor_id, status, submission_date)
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

SELECT 'APMS_MERGED.sql imported successfully — COMP4300 data applied.' AS status;

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
    load_id          INT PRIMARY KEY AUTO_INCREMENT,
    faculty_id       INT NOT NULL,
    semester_id      INT NOT NULL,
    min_hours        DECIMAL(5,2) NOT NULL DEFAULT 12,
    max_hours        DECIMAL(5,2) NOT NULL DEFAULT 36,
    employment_type  ENUM('full_time','part_time') NOT NULL DEFAULT 'full_time',
    intro_students   INT NOT NULL DEFAULT 0,
    extra_bonus      DECIMAL(5,2) NOT NULL DEFAULT 0,
    assigned_courses TEXT NULL,
    updated_by       INT NULL,
    updated_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_faculty_semester_load (faculty_id, semester_id),
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id) ON DELETE CASCADE,
    FOREIGN KEY (semester_id) REFERENCES semesters(semester_id) ON DELETE CASCADE,
    FOREIGN KEY (updated_by) REFERENCES users(user_id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ============================================================
-- 5) Add CS doctors to users/faculty
--    Temporary IDs/emails; edit later if needed.
-- ============================================================

SET @pwd := '$2b$12$Wvdyz6MS0G3hhhh.M5PxxOk556cP4HZZ6gs068VOWsGZ1MDEgU1i.';

INSERT INTO users (university_id, full_name, email, password_hash, role, avatar_initials, is_active)
SELECT * FROM (
    SELECT '2101' AS university_id, 'Dr. Iyad Jaber' AS full_name, 'iyad.jaber.temp@birzeit.edu' AS email, @pwd AS password_hash, 'supervisor' AS role, 'IJ' AS avatar_initials, TRUE AS is_active
    UNION ALL SELECT '2102', 'Dr. Adel Taweel', 'adel.taweel.temp@birzeit.edu', @pwd, 'supervisor', 'AT', TRUE
    UNION ALL SELECT '2103', 'Dr. Mustafa Jarrar', 'mustafa.jarrar.temp@birzeit.edu', @pwd, 'supervisor', 'MJ', TRUE
    UNION ALL SELECT '2104', 'Dr. Majdi Mafarja', 'majdi.mafarja.temp@birzeit.edu', @pwd, 'supervisor', 'MM', TRUE
    UNION ALL SELECT '2105', 'Dr. Radi Jarrar', 'radi.jarrar.temp@birzeit.edu', @pwd, 'supervisor', 'RJ', TRUE
    UNION ALL SELECT '2106', 'Dr. Mohammad Alkhanafseh', 'mohammad.alkhanafseh.temp@birzeit.edu', @pwd, 'supervisor', 'MA', TRUE
    UNION ALL SELECT '2107', 'Dr. Ahmed Abusnaina', 'ahmed.abusnaina.temp@birzeit.edu', @pwd, 'supervisor', 'AA', TRUE
    UNION ALL SELECT '2108', 'Dr. Ali Jaber', 'ali.jaber.temp@birzeit.edu', @pwd, 'supervisor', 'AJ', TRUE
    UNION ALL SELECT '2109', 'Dr. Mohammed Helal', 'mohammed.helal.temp@birzeit.edu', @pwd, 'supervisor', 'MH', TRUE
    UNION ALL SELECT '2110', 'Dr. Tamer Alkhouli', 'tamer.alkhouli.temp@birzeit.edu', @pwd, 'supervisor', 'TA', TRUE
    UNION ALL SELECT '2111', 'Dr. Mohammed Khalilia', 'mohammed.khalilia.temp@birzeit.edu', @pwd, 'supervisor', 'MK', TRUE
) AS new_users
WHERE NOT EXISTS (
    SELECT 1
    FROM users u
    WHERE u.full_name = new_users.full_name
);

INSERT INTO faculty (user_id, specialization, years_experience, title)
SELECT
    u.user_id,
    CASE u.full_name
        WHEN 'Dr. Mustafa Jarrar' THEN 'artificial_intelligence'
        WHEN 'Dr. Majdi Mafarja' THEN 'artificial_intelligence'
        WHEN 'Dr. Mohammad Alkhanafseh' THEN 'security_networks'
        WHEN 'Dr. Adel Taweel' THEN 'software_engineering'
        WHEN 'Dr. Radi Jarrar' THEN 'software_engineering'
        WHEN 'Dr. Ahmed Abusnaina' THEN 'software_engineering'
        WHEN 'Dr. Ali Jaber' THEN 'software_engineering'
        WHEN 'Dr. Mohammed Helal' THEN 'software_engineering'
        WHEN 'Dr. Tamer Alkhouli' THEN 'artificial_intelligence'
        WHEN 'Dr. Mohammed Khalilia' THEN 'artificial_intelligence'
        ELSE 'other'
    END AS specialization,
    8 AS years_experience,
    'Dr.' AS title
FROM users u
LEFT JOIN faculty f ON f.user_id = u.user_id
WHERE u.full_name IN (
    'Dr. Iyad Jaber',
    'Dr. Adel Taweel',
    'Dr. Mustafa Jarrar',
    'Dr. Majdi Mafarja',
    'Dr. Radi Jarrar',
    'Dr. Mohammad Alkhanafseh',
    'Dr. Ahmed Abusnaina',
    'Dr. Ali Jaber',
    'Dr. Mohammed Helal',
    'Dr. Tamer Alkhouli',
    'Dr. Mohammed Khalilia'
)
AND f.user_id IS NULL;

-- ============================================================
-- 6) Helpful verification
-- ============================================================

SELECT 'Migration completed successfully' AS status;

SELECT full_name, role, university_id, email
FROM users
WHERE full_name IN (
    'Dr. Iyad Jaber',
    'Dr. Adel Taweel',
    'Dr. Mustafa Jarrar',
    'Dr. Majdi Mafarja',
    'Dr. Radi Jarrar',
    'Dr. Mohammad Alkhanafseh',
    'Dr. Ahmed Abusnaina',
    'Dr. Ali Jaber',
    'Dr. Mohammed Helal',
    'Dr. Tamer Alkhouli',
    'Dr. Mohammed Khalilia'
)
ORDER BY full_name;

SET FOREIGN_KEY_CHECKS = 1;
