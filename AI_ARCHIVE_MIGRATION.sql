-- ============================================================
-- APMS AI Archive Migration
-- Adds persistent chatbot history and prepares automatic 30-day cleanup.
-- Run this once on an existing apms_db database if you do not re-import APMS.sql.
-- ============================================================

USE apms_db;

CREATE TABLE IF NOT EXISTS ai_conversations (
    conv_id      INT           PRIMARY KEY AUTO_INCREMENT,
    user_id      INT           NOT NULL,
    session_id   VARCHAR(120)  NULL COMMENT 'Client-generated conversation session ID',
    message_role ENUM('user','assistant') NOT NULL,
    message_text MEDIUMTEXT    NOT NULL,
    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB;

UPDATE ai_conversations
SET session_id = CONCAT('legacy-', conv_id)
WHERE session_id IS NULL OR session_id = '';

ALTER TABLE ai_conversations
    MODIFY session_id VARCHAR(120) NOT NULL COMMENT 'Client-generated conversation session ID',
    MODIFY message_text MEDIUMTEXT NOT NULL;

DELIMITER $$
CREATE PROCEDURE apms_add_ai_archive_indexes()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'ai_conversations'
          AND INDEX_NAME = 'idx_ai_user_session'
    ) THEN
        CREATE INDEX idx_ai_user_session ON ai_conversations(user_id, session_id, created_at);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'ai_conversations'
          AND INDEX_NAME = 'idx_ai_created'
    ) THEN
        CREATE INDEX idx_ai_created ON ai_conversations(created_at);
    END IF;
END$$
DELIMITER ;

CALL apms_add_ai_archive_indexes();
DROP PROCEDURE apms_add_ai_archive_indexes;

-- Immediate cleanup for sessions older than 30 days.
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
