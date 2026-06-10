from typing import Any, Literal

from pydantic import BaseModel, Field

RfpStatus = Literal["extracted", "analyzed", "reviewed", "confirmed"]


# ────────────────────────────────────────────────────────────
# 분석 결과 서브 모델
# ────────────────────────────────────────────────────────────

class ProjectInfo(BaseModel):
    project_name: str
    project_amount: int | None = None         # 프로젝트 금액 (원 단위)
    client_name: str | None = None            # 발주사
    project_theme: str | None = None          # 프로젝트 주제
    description: str | None = None            # 프로젝트 설명 (자세한)
    start_date: str | None = None
    end_date: str | None = None
    contract_type: str | None = None          # 계약 방식
    business_type: str | None = None          # 사업 유형
    budget: str | None = None                 # 기존 budget 문자열 (예산 표현)
    lead_company: str | None = None           # 주관사
    partner_companies: list[str] = []         # 협력사 목록


class Requirement(BaseModel):
    req_id: str
    assignee_type: list[str] = []             # 담당: ["기획", "개발-화면", "개발-비화면", "PM"] 복수 가능
    user_type: list[str] = []                 # 사용자 유형: ["사용자", "관리자"] 등
    requirement_type: str | None = None       # 기능 | 비기능
    req_category: str | None = None           # (레거시) 기능/비기능 라벨 — requirement_type으로 대체 예정
    req_name: str | None = None
    req_description: str | None = None        # 요구사항 내용
    req_detail: str | None = None             # 요구사항 세부 내용
    notes: str | None = None                  # 비고
    importance: str | None = None
    priority: str | None = None
    deliverables: list[str] = []
    related_req_ids: list[str] = []
    source_text: str | None = None              # LLM이 발췌한 원문 짧은 인용 (최대 200자)
    source_chunk_index: int | None = None       # 추출 출처 청크 번호 (0-based)
    source_chunk_text: str | None = None        # 추출 출처 청크 전체 원문 (UI에서 추적용)
    inferred_from_context: bool = False


class WbsEvidence(BaseModel):
    source_req_id: str | None = None
    source_text: str | None = None
    reasoning_step: str | None = None


class WbsItem(BaseModel):
    wbs_code: str
    req_id: str | None = None
    task_name: str
    assignee_role: str | None = None
    task_description: str | None = None
    required_skills: list[str] = []
    estimated_days: float | None = None
    planned_hours: float | None = None
    planned_start: str | None = None  # YYYY-MM-DD
    planned_end: str | None = None    # YYYY-MM-DD
    deliverables: list[str] = []
    depends_on: list[str] = []
    evidence: WbsEvidence | None = None
    # ─── 우선순위 분류 (스케줄러가 사용) ───
    phase: str | None = None          # foundation | core | feature | closing
    criticality: str | None = None    # blocker | core | normal
    risk: str | None = None           # high | low


class RoleBreakdown(BaseModel):
    project_biz_days: int                # 프로젝트 영업일 수
    utilization_rate: float              # 가용률 (예: 0.8)
    effective_days: float                # 영업일 × 가용률
    parallel_buffer: float               # 병렬 작업 여유율 (예: 1.2)
    raw_count: float                     # 버퍼 적용 전 인원


class RequiredRole(BaseModel):
    role: str
    count: int = 1
    skills: list[str] = []
    mm: float | None = None              # 총 M/M (22 영업일 = 1 M/M)
    total_days: float | None = None      # 역할 총 M/D
    total_hours: float | None = None     # 역할 총 M/H
    task_count: int | None = None        # 담당 WBS task 수
    breakdown: RoleBreakdown | None = None  # 산정 근거


class ConfidenceBreakdown(BaseModel):
    project_extraction: float = Field(default=0.0, ge=0.0, le=1.0)
    requirements_classification: float = Field(default=0.0, ge=0.0, le=1.0)
    wbs_accuracy: float = Field(default=0.0, ge=0.0, le=1.0)


class AnalysisMetadata(BaseModel):
    total_requirements: int = 0
    total_wbs_tasks: int = 0
    wbs_tasks_by_role: dict[str, int] = {}
    total_estimated_days: float = 0.0
    total_planned_hours: float = 0.0
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence_breakdown: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    low_confidence_items: list[dict[str, Any]] = []
    assumptions: list[str] = []


class AnalysisResult(BaseModel):
    project: ProjectInfo
    requirements: list[Requirement] = []
    wbs: list[WbsItem] = []
    required_roles: list[RequiredRole] = []
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    analysis_metadata: AnalysisMetadata | None = None


# ────────────────────────────────────────────────────────────
# API 응답
# ────────────────────────────────────────────────────────────

class RfpUploadResponse(BaseModel):
    rfp_id: str
    file_name: str
    extracted_text: str
    page_count: int
    status: RfpStatus
    elapsed_seconds: float | None = None


class RfpAnalyzeResponse(AnalysisResult):
    rfp_id: str
    status: RfpStatus
    elapsed_seconds: float | None = None


class RfpChunkAnalyzeRequest(BaseModel):
    start_date: str | None = Field(default=None, description="프로젝트 시작일 (YYYY-MM-DD). 미입력 시 LLM 추출값 사용")
    end_date: str | None = Field(default=None, description="프로젝트 종료일 (YYYY-MM-DD). 미입력 시 LLM 추출값 사용")


class ConsortiumInfo(BaseModel):
    lead_company: str | None = None
    partner_companies: list[str] = []


class RfpAnalysisPatch(BaseModel):
    project: ProjectInfo | None = None
    requirements: list[Requirement] | None = None
    wbs: list[WbsItem] | None = None
    required_roles: list[RequiredRole] | None = None
    consortium: ConsortiumInfo | None = None


class RfpPatchResponse(BaseModel):
    rfp_id: str
    status: RfpStatus


class RfpConfirmResponse(BaseModel):
    project_id: str
    tasks_created: int
    triples_inserted: int
    fuseki_graph_uri: str
    next_step: str
    google_slide_id: str | None = None
    gitlab_project_id: str | None = None
    gitlab_repo_url: str | None = None


class RfpSummary(BaseModel):
    rfp_id: str
    file_name: str
    project_name: str | None = None
    status: RfpStatus
    created_at: str


class RfpWbsRegenResponse(BaseModel):
    rfp_id: str
    status: RfpStatus
    wbs: list[WbsItem] = []
    analysis_metadata: AnalysisMetadata | None = None


class RfpDetail(BaseModel):
    rfp_id: str
    file_name: str
    status: RfpStatus
    page_count: int
    created_at: str
    project: ProjectInfo | None = None
    requirements: list[Requirement] = []
    wbs: list[WbsItem] = []
    required_roles: list[RequiredRole] = []
    consortium: ConsortiumInfo | None = None
    confidence_score: float | None = None
    analysis_metadata: AnalysisMetadata | None = None
    confirmed_project_id: str | None = None
