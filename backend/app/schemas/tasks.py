from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from app.schemas.persons import PersonRef


class WbsRow(BaseModel):
    task_id: str
    wbs_code: str
    task_name: str
    progress: int
    status: str
    assignee_role: str | None = None
    assignee: str | None = None
    planned_start: str | None = None
    planned_end: str | None = None
    planned_hours: float | None = None
    actual_hours: float | None = None
    estimated_days: float | None = None
    req_id: str | None = None
    req_name: str | None = None
    depends_on: list[str] = []


class TaskHistoryEntry(BaseModel):
    history_id: str
    old_status: str | None
    new_status: str
    change_reason: str | None
    extra_work_start: str | None
    extra_work_end: str | None
    changed_by_name: str
    created_at: str


class TaskIssue(BaseModel):
    issue_id: str
    title: str
    description: str | None
    status: Literal["open", "monitoring", "resolved"]
    created_at: str
    resolved_at: str | None


class TaskDetail(BaseModel):
    task_id: str
    task_name: str
    wbs_code: str
    status: str
    progress: int
    planned_hours: float | None = None
    actual_hours: float | None = None
    planned_start: str | None = None
    planned_end: str | None = None
    due_date: str | None = None
    assignee_role: str | None = None
    assignee: PersonRef | None = None
    req_id: str | None = None
    req_name: str | None = None
    source_files: list[str] = []
    history: list[TaskHistoryEntry] = []
    issues: list[TaskIssue] = []


class TaskCreate(BaseModel):
    wbs_code: str
    task_name: str
    description: str | None = None
    assignee_id: str | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    planned_hours: float | None = None


class TaskStatusUpdate(BaseModel):
    status: Literal["미진행", "진행", "완료"]
    change_reason: str | None = None
    extra_work_start: date | None = None
    extra_work_end: date | None = None


class TaskApprovalRequest(BaseModel):
    notification_event_id: int
    is_approved: bool
    rejection_reason: str | None = None
    reschedule_wbs: bool = True  # 추가 태스크 생성 시 후속/충돌 태스크 일정 자동 재산출 여부


class TaskApprovalResponse(BaseModel):
    task_id: str
    result: Literal["approved", "rejected"]
    new_task_id: str | None = None
