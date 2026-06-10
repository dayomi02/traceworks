-- wbs_task_history: note 삭제, extra_work_date → extra_work_start / extra_work_end 분리
ALTER TABLE wbs_task_history
    DROP COLUMN IF EXISTS note,
    DROP COLUMN IF EXISTS extra_work_date,
    ADD COLUMN extra_work_start VARCHAR(20) NULL COMMENT '완료→변경 시 추가 작업 시작일 (YYYY-MM-DD)' AFTER change_reason,
    ADD COLUMN extra_work_end   VARCHAR(20) NULL COMMENT '완료→변경 시 추가 작업 종료일 (YYYY-MM-DD)' AFTER extra_work_start;
