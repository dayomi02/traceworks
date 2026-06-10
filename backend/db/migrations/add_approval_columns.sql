ALTER TABLE wbs_task_history
  ADD COLUMN notification_event_id INT NULL,
  ADD COLUMN approval_status VARCHAR(20) NULL;
