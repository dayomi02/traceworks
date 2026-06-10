import logging

from fastapi import APIRouter, HTTPException, Path, Query

from app.core.exceptions import PersonNotFound
from app.core.services.recommend_service import compute_load_availability
from app.db import sparql_repo
from app.schemas.persons import PersonDetail, PersonSummary
from app.schemas.recommendations import AvailabilityItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/persons", tags=["인력"])

ID_PATTERN = r"^[A-Za-z0-9_-]+$"


@router.get("", response_model=list[PersonSummary])
def list_persons() -> list[PersonSummary]:
    """
    **[화면 4 - 인력 추천 / 인력 풀 조회]** Fuseki에 등록된 전체 인력 목록과 보유 스킬을 반환합니다.

    - 각 인력의 역할(role), 보유 스킬(skills), 숙련도(proficiency)를 포함합니다.
    - 인력 추천 화면에서 후보 풀을 직접 탐색할 때 사용합니다.
    - 인증 불필요 (공개 조회)
    """
    rows = sparql_repo.list_persons_with_skills()
    logger.info("인력 목록 조회: count=%d", len(rows))
    return [PersonSummary(**p) for p in rows]


@router.post("", status_code=501, include_in_schema=False)
def create_person() -> dict:
    """
    **[미구현]** 인력 직접 등록 API입니다.

    - 현재 미구현 상태입니다. 인력 데이터는 Fuseki seed 스크립트로 적재합니다.
    """
    raise HTTPException(status_code=501, detail="create_person not implemented")


# NOTE: /availability MUST be defined before /{person_id} — FastAPI matches routes
# in registration order, otherwise "availability" would be captured as person_id.
@router.get("/availability", response_model=list[AvailabilityItem])
def list_availability(
    project_id: str | None = Query(default=None, alias="projectId", pattern=ID_PATTERN),
) -> list[AvailabilityItem]:
    """
    **[화면 4 - 인력 추천 / 가용성 조회]** 인력별 현재 가용성 점수를 반환합니다.

    - `computed_availability`: 현재 진행 중인 태스크 수와 평균 진행률로 계산한 실시간 가용성 (0.0~1.0)
    - `availability_score`: Fuseki에 사전 등록된 기준 가용성 점수
    - `projectId` 쿼리 파라미터로 특정 프로젝트의 태스크만 기준으로 필터링할 수 있습니다.
    - 인증 불필요 (공개 조회)

    **가용성 계산식:** `max(0, 1 - (진행중 태스크 수 × (1 - 평균진행률)) / 3.0)`
    """
    rows = sparql_repo.active_task_counts(project_id)
    enriched = []
    for r in rows:
        enriched.append({
            "person_id": r["person_id"],
            "person_name": r["person_name"],
            "role": r.get("role"),
            "active_tasks": r["active_tasks"],
            "availability_score": r.get("availability_score"),
            "computed_availability": compute_load_availability(
                r["active_tasks"], r.get("avg_progress")
            ),
        })
    logger.info("가용성 조회: project_id=%s count=%d", project_id, len(enriched))
    return [AvailabilityItem(**e) for e in enriched]


@router.get("/{person_id}", response_model=PersonDetail)
def get_person(
    person_id: str = Path(..., pattern=ID_PATTERN),
) -> PersonDetail:
    """
    **[화면 4 - 인력 추천 / 인력 상세]** 특정 인력의 상세 정보를 반환합니다.

    - 보유 스킬 전체 목록, 참여 프로젝트 이력(`participates_in`)을 포함합니다.
    - 인력 추천 목록에서 특정 후보를 클릭했을 때 상세 팝업/사이드패널에 사용합니다.
    - `person_id`는 `GET /persons` 응답의 `person_id` 값 또는 추천 결과의 `person_id`를 사용합니다.
    - 인증 불필요 (공개 조회)
    """
    data = sparql_repo.get_person_by_id(person_id)
    if data is None:
        raise PersonNotFound(person_id)
    logger.info("인력 상세 조회: person_id=%s name=%s", person_id, data.get("name"))
    return PersonDetail(**data)
