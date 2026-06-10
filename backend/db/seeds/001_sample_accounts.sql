-- 예시 계정 seed (MySQL)
-- 비밀번호: traceworks1!
-- password_hash는 bcrypt로 생성. Python 스크립트(scripts/seed_users.py)로 자동 삽입 권장.
-- 아래 해시는 참고용 샘플값 (bcrypt cost=12, traceworks1!)

INSERT INTO users (id, email, password_hash, name, role, is_active) VALUES
  (UUID(), 'pm@traceworks.com',      '$2b$12$PLACEHOLDER_PM_HASH',      '홍길동', 'pm',        TRUE),
  (UUID(), 'planner@traceworks.com', '$2b$12$PLACEHOLDER_PLANNER_HASH', '이수연', 'planner',   TRUE),
  (UUID(), 'dev@traceworks.com',     '$2b$12$PLACEHOLDER_DEV_HASH',     '김철수', 'developer', TRUE)
ON DUPLICATE KEY UPDATE name=VALUES(name);

-- NOTE: 실제 해시값은 scripts/seed_users.py 실행으로 삽입하세요.
