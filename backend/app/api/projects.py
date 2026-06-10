import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status

from app.core.deps import get_current_user
from app.core.exceptions import ProjectNotFound
from app.core.services import insight_service, wbs_service
from app.core.services.project_service import derive_status
from app.db import sparql_repo
from app.db.models import User
from app.schemas.insights import InsightItem, InsightsResponse
from app.schemas.projects import ProjectDetail, ProjectStatus, ProjectSummary
from app.schemas.tasks import TaskCreate, WbsRow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["프로젝트 / WBS"])

ID_PATTERN = r"^[A-Za-z0-9_-]+$"


@router.get("", response_model=list[ProjectSummary])
def list_projects(
    status: ProjectStatus | None = Query(None, description="상태 필터 (PLANNING/ACTIVE/COMPLETED)"),
) -> list[ProjectSummary]:
    """
    **[대시보드 / 프로젝트 선택]** 전체 프로젝트 목록과 공정률을 반환합니다.

    - Fuseki에 등록된 모든 프로젝트의 요약 정보(프로젝트명, 상태, 전체 공정률)를 반환합니다.
    - `status` 쿼리 파라미터로 `PLANNING` / `ACTIVE` / `COMPLETED` 필터링이 가능합니다.
    - 상태는 시작일과 현재 날짜를 비교해 파생됩니다 (COMPLETED는 별도 API로 명시적 전환).
    - 대시보드 프로젝트 선택 드롭다운, 또는 프로젝트 목록 페이지에서 사용합니다.
    - 내가 참여한 프로젝트만 보려면 `GET /dashboard/projects`를 사용하세요.
    """
    rows = wbs_service.list_projects_with_progress(status=status)
    logger.info("프로젝트 목록 조회: count=%d status=%s", len(rows), status)
    return [ProjectSummary(**p) for p in rows]


@router.post("", status_code=501, include_in_schema=False)
def create_project() -> dict:
    """
    **[미구현]** 프로젝트 직접 생성 API입니다.

    - 현재 미구현 상태입니다. 프로젝트 생성은 RFP 확정(`POST /rfp/{rfp_id}/confirm`)을 통해서만 가능합니다.
    """
    raise HTTPException(status_code=501, detail="create_project not implemented")


@router.get("/{project_id}/wbs", response_model=list[WbsRow])
def get_project_wbs(
    project_id: str = Path(..., pattern=ID_PATTERN),
) -> list[WbsRow]:
    """
    **[화면 3 - WBS 일정 / 프로젝트 관리]** 특정 프로젝트의 WBS 태스크 목록을 반환합니다.

    - wbs_code 순으로 정렬하여 반환합니다.
    - 간트 차트 렌더링에 필요한 `planned_start`, `planned_end`, `depends_on` 정보를 포함합니다.
    - 태스크 상태: `미진행` → `진행` → `완료`
    - 담당자가 배정되지 않은 태스크는 `assignee`가 null입니다.
    """
    rows = wbs_service.get_wbs(project_id)
    logger.info("WBS 조회: project_id=%s tasks=%d", project_id, len(rows))
    return [WbsRow(**row) for row in rows]


@router.post("/{project_id}/tasks", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreate,
    project_id: str = Path(..., pattern=ID_PATTERN),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    **[화면 3 - WBS 일정 / 태스크 추가]** WBS에 새 태스크를 수동으로 추가합니다.

    - 초기 상태는 항상 `미진행`으로 설정됩니다.
    - `wbs_code`는 중복되지 않아야 합니다 (예: `1.1`, `2.3`).
    - `planned_start` / `planned_end`는 YYYY-MM-DD 형식이며, 간트 차트 날짜 표시에 사용됩니다.
    - **인증 필요** (`Authorization: Bearer <token>`)
    """
    if not sparql_repo.project_exists(project_id):
        raise ProjectNotFound(project_id)

    task_id = f"{project_id}-T{uuid.uuid4().hex[:8].upper()}"
    sparql_repo.insert_single_task(
        project_id=project_id,
        task_id=task_id,
        wbs_code=body.wbs_code,
        task_name=body.task_name,
        planned_start=str(body.planned_start) if body.planned_start else None,
        planned_end=str(body.planned_end) if body.planned_end else None,
        planned_hours=body.planned_hours,
        description=body.description,
    )
    logger.info("WBS 작업 추가: project_id=%s task_id=%s by %s", project_id, task_id, current_user.email)
    return {"task_id": task_id, "wbs_code": body.wbs_code, "status": "미진행"}


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: str = Path(..., pattern=ID_PATTERN),
) -> ProjectDetail:
    """
    **[프로젝트 상세 조회]** 특정 프로젝트의 전체 정보와 요구사항 목록을 반환합니다.

    - `pm:Project`의 모든 속성 (이름, 도메인, 기술 스택, 일정, Slide ID, GitLab ID 등)
    - 해당 프로젝트에 연결된 `pm:Requirement` 목록 포함
    """
    data = sparql_repo.get_project_detail(project_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    data["project_status"] = derive_status(data.get("project_status"), data.get("start_date"))
    return ProjectDetail(**data)


@router.post("/{project_id}/complete", response_model=ProjectDetail)
def complete_project(
    project_id: str = Path(..., pattern=ID_PATTERN),
    current_user: User = Depends(get_current_user),
) -> ProjectDetail:
    """
    **[프로젝트 완료 처리]** 프로젝트를 `COMPLETED` 상태로 전환합니다.

    - Fuseki의 `pm:projectStatus`를 `"COMPLETED"`로 교체합니다.
    - 이미 COMPLETED인 경우 멱등하게 동작합니다.
    - 종료일이 지나도 자동으로 완료되지 않으므로 이 API로 명시적 전환이 필요합니다.
    - **해당 프로젝트의 PM만 호출 가능합니다.** (그 외 사용자는 403)
    - **인증 필요** (`Authorization: Bearer <token>`)
    """
    if not sparql_repo.project_exists(project_id):
        raise ProjectNotFound(project_id)

    # 권한 체크: 해당 프로젝트의 PM만 허용
    pm_names = sparql_repo.get_project_pm_names(project_id)
    if not current_user.name or current_user.name not in pm_names:
        logger.warning(
            "[PROJECT-COMPLETE] 권한 거부: project_id=%s user=%s pm_names=%s",
            project_id, current_user.name, pm_names,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="프로젝트 완료 처리는 해당 프로젝트의 PM만 가능합니다.",
        )

    sparql_repo.update_project_status(project_id, "COMPLETED")
    logger.info("프로젝트 완료 처리: project_id=%s by %s", project_id, current_user.email)
    data = sparql_repo.get_project_detail(project_id)
    data["project_status"] = "COMPLETED"
    return ProjectDetail(**data)


@router.get("/{project_id}/insights", response_model=InsightsResponse)
async def get_project_insights(
    project_id: str = Path(..., pattern=ID_PATTERN),
) -> InsightsResponse:
    """
    **[AI 제언]** 프로젝트 온톨로지 데이터를 분석하여 관리 제언을 반환합니다.

    - 역할별 병목, 요구사항 미구현, 의존성 연쇄 지연, 인력 과부하, 스킬 불일치를 감지합니다.
    - severity: `critical` > `warning` > `info` 순으로 정렬됩니다.
    - 인증 불필요 (공개 조회)
    """
    if not sparql_repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    raw = await insight_service.generate_insights(project_id)
    insights = [InsightItem(**item) for item in raw]
    return InsightsResponse(
        project_id=project_id,
        insights=insights,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
