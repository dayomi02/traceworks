import logging
import time

from fastapi import APIRouter, File, HTTPException, Path, UploadFile

from app.core.normalizer.rfp_extractor import UnsupportedRfpFormat
from app.core.services import rfp_service
from app.schemas.rfp import (
    RfpAnalysisPatch,
    RfpAnalyzeResponse,
    RfpChunkAnalyzeRequest,
    RfpConfirmResponse,
    RfpDetail,
    RfpPatchResponse,
    RfpSummary,
    RfpUploadResponse,
    RfpWbsRegenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rfp", tags=["RFP 분석"])

ID_PATTERN = r"^[A-Za-z0-9_-]+$"
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload", response_model=RfpUploadResponse, status_code=201)
async def upload_rfp(file: UploadFile = File(...)) -> RfpUploadResponse:
    """
    **[화면 1 - 프로젝트 개요 / RFP 업로드]** RFP 파일을 업로드하고 텍스트를 추출합니다.

    - 지원 형식: PDF, DOCX, HWP, HWPX, TXT (최대 20MB)
    - 업로드 후 반환되는 `rfp_id`를 이후 분석·조회 API에 사용합니다.
    - 텍스트 추출만 수행하며, AI 분석은 `/rfp/{rfp_id}/analyze` 또는 `/rfp/{rfp_id}/analyze-staged`를 별도 호출해야 합니다.
    - Fuseki에 RFP 메타데이터(파일명, 추출 텍스트, 페이지 수)가 저장됩니다.
    """
    started = time.perf_counter()
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"파일 크기 초과 ({len(content)} > {MAX_FILE_SIZE} bytes)",
        )

    try:
        result = rfp_service.upload_rfp(content, file.filename or "unnamed")
    except UnsupportedRfpFormat as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    elapsed = round(time.perf_counter() - started, 3)
    logger.info("RFP 업로드: rfp_id=%s file=%s size=%d page_count=%d elapsed=%.3fs",
                result["rfp_id"], file.filename, len(content), result["page_count"], elapsed)
    return RfpUploadResponse(**result, elapsed_seconds=elapsed)


@router.post("/{rfp_id}/analyze", response_model=RfpAnalyzeResponse)
async def analyze_rfp(
    rfp_id: str = Path(..., pattern=ID_PATTERN),
) -> RfpAnalyzeResponse:
    """
    **[화면 1 - 프로젝트 개요 / AI 분석 실행]** 업로드된 RFP 텍스트를 AI로 분석합니다.

    - 분석 결과: 프로젝트 개요, 요구사항 목록, WBS 일정, 필요 인력 구성을 한 번에 반환합니다.
    - 분석 결과는 Fuseki에 저장되며, 이후 `/rfp/{rfp_id}`로 재조회할 수 있습니다.
    - **⚠️ LLM 호출로 처리 시간이 30초~2분 소요될 수 있습니다.** 로딩 UI를 표시하세요.
    - WBS 각 항목에 `planned_start` / `planned_end` 날짜가 포함됩니다 (프로젝트 startDate 기준 산정).
    - 단순 분석용으로, 대용량 RFP는 `/analyze-staged` 사용을 권장합니다.
    """
    logger.info("RFP 분석 시작: rfp_id=%s", rfp_id)
    result = await rfp_service.analyze_rfp(rfp_id)
    logger.info("RFP 분석 완료: rfp_id=%s requirements=%d wbs=%d confidence=%.2f",
                rfp_id,
                len(result.get("requirements") or []),
                len(result.get("wbs") or []),
                result.get("confidence_score") or 0.0)
    return RfpAnalyzeResponse(**result)


@router.post("/{rfp_id}/analyze-chunked", response_model=RfpAnalyzeResponse)
async def analyze_rfp_chunked(
    body: RfpChunkAnalyzeRequest = RfpChunkAnalyzeRequest(),
    rfp_id: str = Path(..., pattern=ID_PATTERN),
) -> RfpAnalyzeResponse:
    """
    **[화면 1 - 청킹 기반 AI 분석]** RFP 텍스트를 요구사항 번호 헤딩 기준으로 분할하여 분석합니다.

    - 단계: ① 요구사항 번호 기반 청킹 → ② 청크별 프로젝트 정보 추출 → ③ 청크별 요구사항 추출(병렬) → ④ 요구사항 배치별 WBS 생성
    - 청크 크기·오버랩은 서버 내부에서 자동 결정합니다 (FUN-01, PER-02 등 요구사항 헤딩을 경계로 분할).
    - `start_date`, `end_date`는 선택 입력. 입력 시 LLM 추출값을 덮어씁니다.
    - 응답 구조는 `/analyze`와 동일합니다.
    """
    started = time.perf_counter()
    logger.info("RFP 청킹 분석 시작: rfp_id=%s start=%s end=%s",
                rfp_id, body.start_date, body.end_date)
    result = await rfp_service.analyze_rfp_chunked(
        rfp_id,
        start_date=body.start_date, end_date=body.end_date,
    )
    elapsed = round(time.perf_counter() - started, 3)
    logger.info("RFP 청킹 분석 완료: rfp_id=%s requirements=%d wbs=%d confidence=%.2f elapsed=%.3fs",
                rfp_id,
                len(result.get("requirements") or []),
                len(result.get("wbs") or []),
                result.get("confidence_score") or 0.0,
                elapsed)
    return RfpAnalyzeResponse(**result, elapsed_seconds=elapsed)


@router.post("/{rfp_id}/analyze-staged", response_model=RfpAnalyzeResponse)
async def analyze_rfp_staged(
    rfp_id: str = Path(..., pattern=ID_PATTERN),
) -> RfpAnalyzeResponse:
    """
    **[화면 1 - 프로젝트 개요 / AI 분석 실행 (대용량)]** RFP를 섹션별로 나눠 단계적으로 분석합니다.

    - 3단계 분석: ① 문서 구조 파악 → ② 섹션별 요구사항 추출 → ③ 역할별 WBS 생성
    - 대용량 RFP(20페이지 이상)에서 `/analyze`보다 정확도가 높습니다.
    - **⚠️ LLM 다중 호출로 처리 시간이 더 길 수 있습니다 (1~5분).** 단계별 진행 상태 표시를 권장합니다.
    - 응답 구조는 `/analyze`와 동일합니다.
    """
    logger.info("RFP 스테이지드 분석 시작: rfp_id=%s", rfp_id)
    result = await rfp_service.analyze_rfp_staged(rfp_id)
    logger.info("RFP 스테이지드 분석 완료: rfp_id=%s requirements=%d wbs=%d confidence=%.2f",
                rfp_id,
                len(result.get("requirements") or []),
                len(result.get("wbs") or []),
                result.get("confidence_score") or 0.0)
    return RfpAnalyzeResponse(**result)


@router.post("/{rfp_id}/regenerate-wbs", response_model=RfpWbsRegenResponse)
async def regenerate_wbs(
    rfp_id: str = Path(..., pattern=ID_PATTERN),
) -> RfpWbsRegenResponse:
    """
    **[화면 3 - WBS 일정 분석 / AI 재생성]** 기존 요구사항을 기반으로 WBS만 재생성합니다.

    - 요구사항을 수정한 뒤 WBS를 다시 뽑아야 할 때 사용합니다.
    - 프로젝트 개요·요구사항은 변경되지 않으며, WBS 항목만 덮어씁니다.
    - **⚠️ LLM 호출로 기존 WBS가 완전히 교체됩니다.** 수동 수정 내용이 있다면 미리 저장하세요.
    - `confirmed` 상태의 RFP에는 사용할 수 없습니다.
    """
    logger.info("WBS 재생성 시작: rfp_id=%s", rfp_id)
    result = await rfp_service.regenerate_wbs(rfp_id)
    logger.info("WBS 재생성 완료: rfp_id=%s wbs=%d", rfp_id, len(result.get("wbs") or []))
    return RfpWbsRegenResponse(**result)


@router.patch("/{rfp_id}/analysis", response_model=RfpPatchResponse)
def patch_analysis(
    patch: RfpAnalysisPatch,
    rfp_id: str = Path(..., pattern=ID_PATTERN),
) -> RfpPatchResponse:
    """
    **[화면 1·2·3 - 프로젝트 개요·요구사항·WBS 수정]** AI 분석 결과를 사용자가 직접 수정합니다.

    - `project` / `requirements` / `wbs` / `required_roles` 중 변경할 필드만 포함하면 됩니다 (부분 수정 가능).
    - 수정 후 상태(status)가 `reviewed`로 변경됩니다.
    - **⚠️ `requirements`·`wbs`는 배열 전체를 교체합니다.** 일부 수정 시에도 전체 배열을 전송해야 합니다.
    - `confirmed` 상태의 RFP는 수정할 수 없습니다.
    - 리스트 필드(`partner_companies` 등)를 빈 배열 `[]`로 보내면 기존 값이 유지됩니다 (덮어쓰기 방지).
    """
    result = rfp_service.patch_analysis(rfp_id, patch.model_dump(exclude_none=True))
    logger.info("RFP 분석 수정: rfp_id=%s status=%s", rfp_id, result["status"])
    return RfpPatchResponse(**result)


@router.post("/{rfp_id}/confirm", response_model=RfpConfirmResponse)
def confirm_rfp(
    rfp_id: str = Path(..., pattern=ID_PATTERN),
) -> RfpConfirmResponse:
    """
    **[화면 3 - WBS 일정 분석 / 프로젝트 확정]** 분석 결과를 확정하여 실제 프로젝트와 WBS 태스크를 생성합니다.

    - `analyzed` 또는 `reviewed` 상태의 RFP에만 사용할 수 있습니다.
    - 확정 후 Fuseki에 프로젝트·태스크 트리플이 저장되며, 모든 태스크 초기 상태는 `미진행`입니다.
    - 반환되는 `project_id`를 인력 추천(`/projects/{project_id}/recommend-staff`) API에 사용합니다.
    - **⚠️ 확정 이후에는 분석 결과를 수정할 수 없습니다.**
    """
    result = rfp_service.confirm_rfp(rfp_id)
    logger.info("RFP 확정: rfp_id=%s → project_id=%s tasks=%d triples=%d",
                rfp_id, result["project_id"], result["tasks_created"], result["triples_inserted"])
    return RfpConfirmResponse(**result)


@router.get("", response_model=list[RfpSummary])
def list_rfps() -> list[RfpSummary]:
    """
    **[화면 1 - RFP 목록]** 업로드된 RFP 목록을 반환합니다.

    - 각 RFP의 `rfp_id`, 파일명, 프로젝트명, 현재 상태(`extracted` / `analyzed` / `reviewed` / `confirmed`)를 포함합니다.
    - 목록에서 항목을 선택하면 `/rfp/{rfp_id}`로 상세 데이터를 조회해 분석 화면을 복원합니다.
    """
    rows = rfp_service.list_rfps()
    logger.info("RFP 목록 조회: count=%d", len(rows))
    return [RfpSummary(**r) for r in rows]


@router.get("/{rfp_id}", response_model=RfpDetail)
def get_rfp(
    rfp_id: str = Path(..., pattern=ID_PATTERN),
) -> RfpDetail:
    """
    **[화면 1·2·3 - 분석 결과 재진입]** 특정 RFP의 전체 분석 결과를 조회합니다.

    - 프로젝트 개요, 요구사항, WBS, 필요 인력을 모두 포함합니다.
    - 화면 재진입(새로고침, 뒤로가기) 시 기존 분석 데이터를 복원하는 데 사용합니다.
    - `confirmed_project_id`가 있으면 이미 프로젝트로 확정된 RFP입니다.
    """
    detail = rfp_service.get_rfp_detail(rfp_id)
    logger.info("RFP 상세 조회: rfp_id=%s status=%s", rfp_id, detail["status"])
    return RfpDetail(**detail)
