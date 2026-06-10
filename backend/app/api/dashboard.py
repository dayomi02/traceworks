import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.services.project_service import derive_status
from app.db import sparql_repo
from app.db.models import User, WbsTaskHistory
from app.db.postgres import get_db
from app.schemas.dashboard import (
    AlertItem,
    AlertsResponse,
    DashboardSummaryResponse,
    MyProject,
    MyProjectsResponse,
    ProgressByRoleResponse,
    RoleProgress,
    TaskSummary,
    TeamMember,
    TeamStatusResponse,
    TodoItem,
    TodosResponse,
    WbsOverviewItem,
    WbsOverviewResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["대시보드"])


@router.get("/summary", response_model=DashboardSummaryResponse)
async def get_summary(
    project_id: str | None = Query(None, description="프로젝트 ID — 지정 시 해당 프로젝트 데이터만 집계"),
    current_user: User = Depends(get_current_user),
) -> DashboardSummaryResponse:
    """
    **[대시보드 - 상단 요약 카드]** 전체 업무 현황 수치를 한 번에 반환합니다.

    - `task_summary`: 전체·완료·진행·지연·미진행 태스크 수
    - `my_project_count`: 전체 프로젝트 수 (project_id 지정 시 1 또는 0)
    - `team_member_count`: Fuseki에 등록된 전체 인력 수
    - `project_id` 쿼리 파라미터를 지정하면 해당 프로젝트 데이터만 집계합니다.
    - **인증 필요**
    """
    task_summary = sparql_repo.get_task_summary(project_id=project_id)
    my_projects = sparql_repo.list_all_projects()
    team_count = sparql_repo.get_team_member_count()
    return DashboardSummaryResponse(
        task_summary=TaskSummary(**task_summary),
        my_project_count=len(my_projects),
        team_member_count=team_count,
    )


@router.get("/projects", response_model=MyProjectsResponse)
async def get_my_projects(
    current_user: User = Depends(get_current_user),
) -> MyProjectsResponse:
    """
    **[대시보드 - 프로젝트 목록 패널]** 로그인 사용자가 참여한 프로젝트 목록을 반환합니다.

    - 로그인 사용자의 `name`과 Fuseki Person의 `personName`이 일치하는 태스크가 있는 프로젝트만 조회됩니다.
    - **완료된 프로젝트(`COMPLETED`)는 제외되며, `PLANNING` / `ACTIVE` 상태만 반환합니다.**
    - `progress`: 해당 프로젝트 내 내 태스크들의 평균 진행률 (%)
    - `my_task_count`: 해당 프로젝트에서 내가 담당한 태스크 수
    - **⚠️ 전체 프로젝트 목록(완료 포함)은 `GET /projects`를 사용하세요.**
    - **인증 필요**
    """
    # rows = sparql_repo.list_my_projects(current_user.name)
    all_projects = sparql_repo.list_all_projects()
    for r in all_projects:
        r["status"] = derive_status(r.get("status"), r.get("start_date"))
    # 완료된 프로젝트는 대시보드에서 제외 (PLANNING / ACTIVE만 노출)
    active_projects = [r for r in all_projects if r["status"] != "COMPLETED"]
    projects = [MyProject(**r) for r in active_projects]
    return MyProjectsResponse(projects=projects, total=len(projects))


@router.get("/todos", response_model=TodosResponse)
async def get_todos(
    project_id: str | None = Query(None, description="프로젝트 ID — 지정 시 해당 프로젝트 할 일만 조회"),
    current_user: User = Depends(get_current_user),
) -> TodosResponse:
    """
    **[대시보드 - TO DO LIST 패널]** 로그인 사용자에게 배정된 미완료 WBS 태스크 목록을 반환합니다.

    - `완료` 상태인 태스크는 제외됩니다 (`미진행` / `진행` 상태만 포함).
    - `project_id` 지정 시 해당 프로젝트의 할 일만 반환합니다.
    - **인증 필요**
    """
    rows = sparql_repo.list_my_todos(current_user.name, project_id=project_id)
    todos = [TodoItem(**r) for r in rows]
    return TodosResponse(todos=todos, total=len(todos))


@router.get("/progress", response_model=ProgressByRoleResponse)
async def get_progress_by_role(
    project_id: str | None = Query(None, description="프로젝트 ID — 지정 시 해당 프로젝트 공정률만 집계"),
    current_user: User = Depends(get_current_user),
) -> ProgressByRoleResponse:
    """
    **[대시보드 - 공정률 바 차트]** 역할별 태스크 완료율을 반환합니다.

    - `completion_rate`: 0.0~1.0 값 (프론트에서 % 변환 필요, 예: 0.6 → 60%)
    - `overall_progress`: 전체 평균 완료율
    - `project_id` 지정 시 해당 프로젝트 태스크만 집계합니다.
    - **인증 필요**
    """
    rows = sparql_repo.get_progress_by_role(project_id=project_id)
    roles = [RoleProgress(**r) for r in rows]
    if rows:
        total_tasks = sum(r["total_tasks"] for r in rows)
        total_completed = sum(r["completed"] for r in rows)
        overall = round(total_completed / total_tasks, 2) if total_tasks > 0 else 0.0
    else:
        overall = 0.0
    return ProgressByRoleResponse(roles=roles, overall_progress=overall)


@router.get("/team", response_model=TeamStatusResponse)
async def get_team_status(
    project_id: str | None = Query(None, description="프로젝트 ID — 지정 시 해당 프로젝트 팀원 현황만 조회"),
    _: User = Depends(get_current_user),
) -> TeamStatusResponse:
    """
    **[대시보드 - 팀원 현황 패널]** 팀원별 진행 중·완료 태스크 수와 가용성을 반환합니다.

    - `active_task_count`: 현재 `미진행` + `진행` 상태인 태스크 수
    - `completed_task_count`: `완료` 상태인 태스크 수
    - `project_id` 지정 시 해당 프로젝트에 배정된 팀원의 태스크 수만 집계합니다.
    - **인증 필요**
    """
    rows = sparql_repo.get_team_status(project_id=project_id)
    members = [TeamMember(**r) for r in rows]
    return TeamStatusResponse(members=members, total=len(members))


@router.get("/wbs-overview", response_model=WbsOverviewResponse)
async def get_wbs_overview(
    page: int = Query(1, ge=1, description="페이지 번호 (1부터 시작)"),
    page_size: int = Query(50, ge=1, le=200, description="페이지당 항목 수 (최대 200)"),
    project_id: str | None = Query(None, description="프로젝트 ID — 지정 시 해당 프로젝트 WBS만 조회"),
    _: User = Depends(get_current_user),
) -> WbsOverviewResponse:
    """
    **[대시보드 - 프로젝트 진행 현황 테이블]** 전체 WBS 태스크 목록을 페이지네이션으로 반환합니다.

    - `project_id` 지정 시 해당 프로젝트의 WBS만 반환합니다.
    - `assignee_role`: AI 분석 시 지정된 담당 역할 (담당자 배정 전에도 표시)
    - `assignee_name`: 실제 배정된 담당자 이름 (미배정이면 null)
    - `page` / `page_size` 쿼리 파라미터로 페이지네이션을 제어합니다.
    - **인증 필요**
    """
    offset = (page - 1) * page_size
    items_raw, total = sparql_repo.list_wbs_overview(limit=page_size, offset=offset, project_id=project_id)
    items = [WbsOverviewItem(**r) for r in items_raw]
    return WbsOverviewResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    limit: int = Query(20, ge=1, le=100, description="최대 반환 건수 (기본 20, 최대 100)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertsResponse:
    """
    **[대시보드 - 최근 알림 / 활동 피드]** 최근 WBS 상태 변경 이력을 반환합니다.

    - MariaDB `wbs_task_history` 테이블에서 최신 순으로 조회합니다.
    - `task_name`: Fuseki에서 조회한 태스크명 (태스크가 삭제된 경우 null)
    - `old_status` → `new_status`: 상태 변경 내용
    - `changed_by_name`: 상태를 변경한 사용자 이름
    - `limit` 파라미터로 최대 반환 건수를 조정할 수 있습니다 (기본 20, 최대 100).
    - **인증 필요**
    """
    rows = await db.execute(
        select(WbsTaskHistory, User.name.label("changer_name"))
        .join(User, WbsTaskHistory.changed_by == User.id)
        .order_by(WbsTaskHistory.created_at.desc())
        .limit(limit)
    )
    all_rows = rows.all()

    task_meta: dict[str, dict] = {}
    for row in all_rows:
        tid = row.WbsTaskHistory.task_id
        if tid not in task_meta:
            task_data = sparql_repo.get_task_by_id(tid)
            if task_data:
                task_meta[tid] = {"task_name": task_data.get("task_name")}
            else:
                task_meta[tid] = {"task_name": None}

    alerts = [
        AlertItem(
            history_id=row.WbsTaskHistory.id,
            task_id=row.WbsTaskHistory.task_id,
            task_name=task_meta[row.WbsTaskHistory.task_id].get("task_name"),
            project_name=None,
            old_status=row.WbsTaskHistory.old_status,
            new_status=row.WbsTaskHistory.new_status,
            changed_by_name=row.changer_name,
            note=None,
            created_at=row.WbsTaskHistory.created_at.isoformat(),
        )
        for row in all_rows
    ]
    return AlertsResponse(alerts=alerts, total=len(alerts))
