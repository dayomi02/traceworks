-- Traceworks MVP - Auth & WBS 관리 테이블
-- DB: MySQL 8.x

-- 1. 사용자 계정 테이블
CREATE TABLE IF NOT EXISTS users (
    id          VARCHAR(36)  NOT NULL,
    email       VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name        VARCHAR(100) NOT NULL,
    role        ENUM('pm', 'planner', 'developer') NOT NULL,
    is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. WBS 작업 진행 히스토리 테이블
--    (Fuseki RDF에 저장되는 WBS task 상태 변경 이력을 MySQL에 보완 저장)
CREATE TABLE IF NOT EXISTS wbs_task_history (
    id              VARCHAR(36)  NOT NULL,
    task_id         VARCHAR(255) NOT NULL COMMENT 'Fuseki RDF task URI or wbs_code',
    changed_by      VARCHAR(36)  NOT NULL COMMENT 'users.id',
    old_status      VARCHAR(50)  NULL,
    new_status      VARCHAR(50)  NOT NULL,
    note            TEXT         NULL     COMMENT '진행 메모',
    change_reason   TEXT         NULL     COMMENT '완료→변경 시 변경 사유 (필수)',
    extra_work_date DATE         NULL     COMMENT '완료→변경 시 추가 작업 일자 (필수)',
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_wbs_task_history_task_id (task_id),
    KEY idx_wbs_task_history_changed_by (changed_by),
    CONSTRAINT fk_wbs_history_user FOREIGN KEY (changed_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. WBS 이슈 사항 테이블
CREATE TABLE IF NOT EXISTS wbs_issues (
    id          VARCHAR(36)  NOT NULL,
    task_id     VARCHAR(255) NOT NULL COMMENT 'Fuseki RDF task URI or wbs_code',
    title       VARCHAR(255) NOT NULL,
    description TEXT         NULL,
    status      ENUM('open', 'monitoring', 'resolved') NOT NULL DEFAULT 'open',
    created_by  VARCHAR(36)  NULL COMMENT 'users.id',
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME     NULL,
    PRIMARY KEY (id),
    KEY idx_wbs_issues_task_id (task_id),
    CONSTRAINT fk_wbs_issues_user FOREIGN KEY (created_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
