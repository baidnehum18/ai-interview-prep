-- MySQL schema for the AI-Based Interview Preparation and Mock Interview System.
-- The FastAPI backend also creates these tables automatically on startup
-- (SQLAlchemy create_all), so running this file is optional.

CREATE DATABASE IF NOT EXISTS interview_prep CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE interview_prep;

CREATE TABLE IF NOT EXISTS users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    username    VARCHAR(80)  NOT NULL UNIQUE,
    full_name   VARCHAR(120) NULL,
    email       VARCHAR(160) NULL,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interview_sessions (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    user_id              INT          NOT NULL,
    job_role             VARCHAR(80)  NOT NULL,
    skill_level          VARCHAR(20)  NOT NULL,
    interview_type       VARCHAR(20)  NOT NULL,           -- technical | hr | mixed
    answer_mode          VARCHAR(10)  NOT NULL DEFAULT 'text',
    status               VARCHAR(20)  NOT NULL DEFAULT 'in_progress',
    overall_score        FLOAT        NULL,
    technical_score      FLOAT        NULL,
    communication_score  FLOAT        NULL,
    summary              JSON         NULL,                -- feedback, weak areas, recommendations
    started_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at         DATETIME     NULL,
    INDEX idx_sessions_user (user_id),
    CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_questions (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    session_id      INT          NOT NULL,
    position        INT          NOT NULL,
    question_key    VARCHAR(40)  NOT NULL,
    question_type   VARCHAR(20)  NOT NULL,                 -- technical | hr
    topic           VARCHAR(80)  NOT NULL,
    question        TEXT         NOT NULL,
    ideal_answer    TEXT         NOT NULL,
    keywords        JSON         NULL,
    answer_text     TEXT         NULL,
    answer_mode     VARCHAR(10)  NULL,
    relevance       FLOAT        NULL,
    completeness    FLOAT        NULL,
    correctness     FLOAT        NULL,
    communication   FLOAT        NULL,
    score           FLOAT        NULL,
    speech_metrics  JSON         NULL,
    feedback        JSON         NULL,
    answered_at     DATETIME     NULL,
    INDEX idx_questions_session (session_id),
    CONSTRAINT fk_questions_session FOREIGN KEY (session_id) REFERENCES interview_sessions(id) ON DELETE CASCADE
);

-- Dedicated application user (change the password!)
-- CREATE USER IF NOT EXISTS 'interview_user'@'%' IDENTIFIED BY 'change_me';
-- GRANT ALL PRIVILEGES ON interview_prep.* TO 'interview_user'@'%';
-- FLUSH PRIVILEGES;
