import logging

from fastapi import APIRouter, Path

from app.core.services import recommend_service
from app.schemas.recommendations import (
    AssignStaffRequest,
    AssignStaffResponse,
    RecommendationItem,
    RecommendStaffRefreshRequest,
    RecommendStaffRefreshResponse,
    RecommendStaffRequest,
    RoleRecommendation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["인력 추천"])

ID_PATTERN = r"^[A-Za-z0-9_-]+$"


@router.post(
    "/{project_id}/recommend-staff",
    response_model=list[RecommendationItem],
)
async def recommend_staff(
    project_id: str = Path(..., pattern=ID_PATTERN),
    body: RecommendStaffRequest | None = None,
) -> list[RecommendationItem]:
    """
    **[화면 4 - 인력 추천 / AI 추천 조회]** 프로젝트 기술 스택·도메인 기반으로 적합한 인력을 AI가 추천합니다.

    - 프로젝트의 기술 스택과 도메인을 분석해 인력 풀에서 유사도 순으로 후보를 정렬합니다.
    - `top_k`: 최대 반환 인원 수 (기본값: 전체)
    - `persist: true`로 설정하면 추천 결과가 Fuseki에 저장됩니다 (기본값: false, 계산만 수행)
    - 매칭되는 인력이 없으면 샘플 데이터(`is_sample: true`)를 반환합니다.
    - **⚠️ LLM 호출로 처리 시간이 수 초 소요될 수 있습니다.**
    - 역할별로 분리된 추천이 필요하면 `POST /projects/{project_id}/recommend-staff/refresh`를 사용하세요.
    """
    req = body or RecommendStaffRequest()
    logger.info("인력 추천 시작: project_id=%s top_k=%s persist=%s",
                project_id, req.top_k, req.persist)
    items = await recommend_service.recommend_staff(
        project_id,
        top_k=req.top_k,
        persist=req.persist,
    )
    logger.info("인력 추천 완료: project_id=%s candidates=%d", project_id, len(items))
    return [RecommendationItem(**it) for it in items]


@router.post(
    "/{project_id}/recommend-staff/refresh",
    response_model=RecommendStaffRefreshResponse,
)
async def recommend_staff_by_role(
    project_id: str = Path(..., pattern=ID_PATTERN),
    body: RecommendStaffRefreshRequest = ...,
) -> RecommendStaffRefreshResponse:
    """
    **[화면 4 - 인력 추천 / 역할별 재추천]** 역할별 필요 인원 수를 지정하여 역할 필터링된 추천 결과를 반환합니다.

    - 화면의 "AI 인력 추천 재조회" 버튼에 대응합니다.
    - `role_headcounts`: 역할명과 필요 인원 수 배열 (예: `[{"role": "PM", "count": 1}, {"role": "개발자", "count": 3}]`)
    - 역할별로 후보 목록이 분리되어 반환됩니다 (`by_role` 배열).
    - 해당 역할의 인력이 없으면 샘플 데이터로 대체됩니다.
    - `persist: true`로 설정하면 추천 결과가 Fuseki에 저장됩니다.
    - **⚠️ LLM 호출 포함으로 처리 시간이 수 초 소요될 수 있습니다.**
    """
    logger.info("역할별 인력 추천 시작: project_id=%s roles=%d top_k=%s persist=%s",
                project_id, len(body.role_headcounts), body.top_k, body.persist)
    result = await recommend_service.recommend_staff_by_role(
        project_id,
        role_headcounts=[rh.model_dump() for rh in body.role_headcounts],
        top_k=body.top_k,
        persist=body.persist,
    )
    by_role = [
        RoleRecommendation(
            role=r["role"],
            required_count=r["required_count"],
            candidates=[RecommendationItem(**c) for c in r["candidates"]],
        )
        for r in result["by_role"]
    ]
    logger.info("역할별 인력 추천 완료: project_id=%s total_required=%d",
                project_id, result["total_required"])
    return RecommendStaffRefreshResponse(
        by_role=by_role,
        total_required=result["total_required"],
    )


@router.post(
    "/{project_id}/staff",
    response_model=AssignStaffResponse,
    status_code=201,
)
def assign_staff(
    project_id: str = Path(..., pattern=ID_PATTERN),
    body: AssignStaffRequest = ...,
) -> AssignStaffResponse:
    """
    **[화면 4 - 인력 추천 / 인력 확정 등록]** 선택한 인력을 프로젝트에 최종 배정합니다.

    - 추천 목록에서 선택한 인력을 확정하는 "등록 완료" 버튼에 대응합니다.
    - `assignments`: 배정할 인력 목록 (예: `[{"person_id": "P001", "role": "PM", "person_name": "홍길동"}]`)
    - 배정 결과가 Fuseki에 `StaffingRecommendation` 트리플로 저장됩니다.
    - 역할에 맞는 WBS 태스크에 자동으로 담당자가 배정됩니다.
    - **⚠️ 역할 매핑은 WBS `assigneeRole`과 배정 `role`의 별칭(alias) 기준으로 처리됩니다.**
      (예: "개발자"는 "BE", "FE", "백엔드", "프론트엔드" 등을 포함)
    """
    result = recommend_service.assign_staff(
        project_id,
        assignments=[a.model_dump() for a in body.assignments],
    )
    logger.info("인력 배정: project_id=%s assignments=%d", project_id, len(body.assignments))
    return AssignStaffResponse(**result)
