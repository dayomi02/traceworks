from pydantic import BaseModel


class TaskSummary(BaseModel):
    total: int
    completed: int
    in_progress: int
    delayed: int
    not_started: int


class MyProject(BaseModel):
    project_id: str
    project_name: str
    domain: str | None = None
    status: str
    progress: float
    my_task_count: int


class TodoItem(BaseModel):
    task_id: str
    task_name: str
    wbs_code: str
    project_id: str
    project_name: str
    status: str
    progress: float
    due_date: str | None = None
    planned_hours: float | None = None


class RoleProgress(BaseModel):
    role: str
    total_tasks: int
    completed: int
    in_progress: int
    completion_rate: float


class TeamMember(BaseModel):
    person_id: str
    person_name: str
    role: str | None = None
    grade: str | None = None
    active_task_count: int
    completed_task_count: int
    availability_score: float | None = None


class WbsOverviewItem(BaseModel):
    project_id: str
    project_name: str
    task_id: str
    task_name: str
    wbs_code: str
    assignee_role: str | None = None
    assignee_name: str | None = None
    status: str
    progress: float
    planned_start: str | None = None
    due_date: str | None = None
    planned_hours: float | None = None


class AlertItem(BaseModel):
    history_id: str
    task_id: str
    task_name: str | None = None
    project_name: str | None = None
    old_status: str | None = None
    new_status: str
    changed_by_name: str
    note: str | None = None
    created_at: str


class DashboardSummaryResponse(BaseModel):
    task_summary: TaskSummary
    my_project_count: int
    team_member_count: int


class MyProjectsResponse(BaseModel):
    projects: list[MyProject]
    total: int


class TodosResponse(BaseModel):
    todos: list[TodoItem]
    total: int


class ProgressByRoleResponse(BaseModel):
    roles: list[RoleProgress]
    overall_progress: float


class TeamStatusResponse(BaseModel):
    members: list[TeamMember]
    total: int


class WbsOverviewResponse(BaseModel):
    items: list[WbsOverviewItem]
    total: int
    page: int
    page_size: int


class AlertsResponse(BaseModel):
    alerts: list[AlertItem]
    total: int
