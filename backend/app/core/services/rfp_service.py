import asyncio
import json
import logging
import math
import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from app.core.exceptions import IntegrationError, RfpNotFound, RfpStateError
from app.core.services import gitlab_service, google_slides_service
from app.core.interpreter import llm_client
from app.core.interpreter.prompts import (
    CHUNK_PROJECT_EXTRACT_SYSTEM,
    CHUNK_REQ_EXTRACT_SYSTEM,
    CHUNK_WBS_GEN_SYSTEM,
    RFP_ANALYSIS_SYSTEM,
    STAGE1_TOC_SYSTEM,
    STAGE2_REQ_EXTRACT_SYSTEM,
    STAGE3_WBS_GEN_SYSTEM,
    WBS_REGEN_SYSTEM,
    select_relevant_sections,
)
from app.core.normalizer import rfp_extractor
from app.db import sparql_repo

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_rfp_id() -> str:
    return "RFP_" + uuid.uuid4().hex[:10].upper()


_REQ_CATEGORY_MAP = {
    "기능요구사항": "기능",
    "비기능요구사항": "비기능",
    "functional": "기능",
    "non-functional": "비기능",
    "nonfunctional": "비기능",
}

def _normalize_req_category(value: str | None) -> str | None:
    if not value:
        return value
    return _REQ_CATEGORY_MAP.get(value.strip(), value.strip())


def upload_rfp(file_bytes: bytes, file_name: str) -> dict:
    text, page_count = rfp_extractor.extract(file_bytes, file_name)
    rfp_id = _new_rfp_id()
    sparql_repo.create_rfp(
        rfp_id=rfp_id,
        file_name=file_name,
        extracted_text=text,
        page_count=page_count,
        created_at_iso=_now_iso(),
    )
    return {
        "rfp_id": rfp_id,
        "file_name": file_name,
        "extracted_text": text,
        "page_count": page_count,
        "status": "extracted",
    }


def _load_rfp_or_404(rfp_id: str) -> dict:
    rfp = sparql_repo.get_rfp(rfp_id)
    if rfp is None:
        raise RfpNotFound(rfp_id)
    return rfp


async def analyze_rfp(rfp_id: str) -> dict:
    rfp = _load_rfp_or_404(rfp_id)
    if rfp["status"] == "confirmed":
        raise RfpStateError(rfp_id, rfp["status"], "analyze")

    text = rfp.get("extracted_text") or ""
    selected = select_relevant_sections(text)
    payload = await llm_client.complete_json(RFP_ANALYSIS_SYSTEM, selected, max_tokens=16000)
    payload = _normalize_analysis(payload)

    sparql_repo.update_rfp_analysis(
        rfp_id=rfp_id,
        analysis_json=json.dumps(payload, ensure_ascii=False),
        project_name=(payload.get("project") or {}).get("project_name"),
        confidence=payload.get("confidence_score"),
        status="analyzed",
    )
    return {
        "rfp_id": rfp_id,
        "status": "analyzed",
        **payload,
    }


def _normalize_analysis(payload: dict) -> dict:
    """LLM 결과 키를 snake_case로 정규화 (camelCase 혼재 대비)."""
    project_raw = payload.get("project") or {}

    def pick(d: dict, *keys):
        for k in keys:
            if d.get(k) is not None:
                return d[k]
        return None

    project = {
        "project_name": pick(project_raw, "project_name", "projectName") or "",
        "project_amount": pick(project_raw, "project_amount", "projectAmount"),
        "client_name": pick(project_raw, "client_name", "clientName"),
        "project_theme": pick(project_raw, "project_theme", "projectTheme"),
        "description": project_raw.get("description"),
        "start_date": pick(project_raw, "start_date", "startDate"),
        "end_date": pick(project_raw, "end_date", "endDate"),
        "contract_type": pick(project_raw, "contract_type", "contractType"),
        "business_type": pick(project_raw, "business_type", "businessType"),
        "budget": project_raw.get("budget"),
        "lead_company": pick(project_raw, "lead_company", "leadCompany"),
        "partner_companies": pick(project_raw, "partner_companies", "partnerCompanies") or [],
    }

    requirements = []
    for req in payload.get("requirements") or []:
        requirements.append({
            "req_id": req.get("req_id") or req.get("reqId") or "",
            "assignee_type": _to_list(req.get("assignee_type") or req.get("assigneeType")),
            "user_type": req.get("user_type") or req.get("userType") or [],
            "requirement_type": req.get("requirement_type") or req.get("requirementType"),
            "req_category": _normalize_req_category(req.get("req_category") or req.get("reqCategory")),
            "req_name": req.get("req_name") or req.get("reqName"),
            "req_description": req.get("req_description") or req.get("reqDescription"),
            "req_detail": req.get("req_detail") or req.get("reqDetail"),
            "notes": req.get("notes"),
            "importance": req.get("importance"),
            "priority": req.get("priority"),
            "deliverables": req.get("deliverables") or [],
            "related_req_ids": req.get("related_req_ids") or req.get("relatedReqIds") or [],
            "source_text": req.get("source_text") or req.get("sourceText"),
            "source_chunk_index": req.get("source_chunk_index"),
            "source_chunk_text": req.get("source_chunk_text"),
            "inferred_from_context": bool(
                req.get("inferred_from_context") or req.get("inferredFromContext")
            ),
        })

    wbs = []
    for item in payload.get("wbs") or []:
        evidence_raw = item.get("evidence") or {}
        evidence = {
            "source_req_id": evidence_raw.get("source_req_id") or evidence_raw.get("sourceReqId"),
            "source_text": evidence_raw.get("source_text") or evidence_raw.get("sourceText"),
            "reasoning_step": evidence_raw.get("reasoning_step") or evidence_raw.get("reasoningStep"),
        } if evidence_raw else None

        raw_deliverables = item.get("deliverables") or item.get("deliverable")
        if isinstance(raw_deliverables, str):
            deliverables = [raw_deliverables] if raw_deliverables else []
        else:
            deliverables = raw_deliverables or []

        wbs.append({
            "wbs_code": item.get("wbs_code") or item.get("wbsCode") or "",
            "req_id": item.get("req_id") or item.get("reqId"),
            "task_name": item.get("task_name") or item.get("taskName") or "",
            "assignee_role": item.get("assignee_role") or item.get("assigneeRole"),
            "task_description": item.get("task_description") or item.get("taskDescription"),
            "required_skills": item.get("required_skills") or item.get("requiredSkills") or [],
            "estimated_days": item.get("estimated_days") or item.get("estimatedDays"),
            "planned_hours": item.get("planned_hours") or item.get("plannedHours"),
            "planned_start": item.get("planned_start") or item.get("plannedStart"),
            "planned_end": item.get("planned_end") or item.get("plannedEnd"),
            "deliverables": deliverables,
            "depends_on": item.get("depends_on") or item.get("dependsOn") or [],
            "evidence": evidence,
        })

    roles = []
    for r in payload.get("required_roles") or payload.get("requiredRoles") or []:
        roles.append({
            "role": r.get("role") or "",
            "count": int(r.get("count") or 1),
            "skills": r.get("skills") or [],
        })

    metadata_raw = payload.get("analysisMetadata") or payload.get("analysis_metadata") or {}
    confidence = (
        pick(metadata_raw, "confidence_score", "confidenceScore")
        or pick(payload, "confidence_score", "confidenceScore")
        or 0.0
    )
    # LLM이 breakdown을 반환하지 않으면 직접 계산
    breakdown_raw = metadata_raw.get("confidenceBreakdown") or metadata_raw.get("confidence_breakdown") or {}
    if breakdown_raw:
        breakdown = {
            "project_extraction": float(breakdown_raw.get("projectExtraction") or breakdown_raw.get("project_extraction") or 0.0),
            "requirements_classification": float(breakdown_raw.get("requirementsClassification") or breakdown_raw.get("requirements_classification") or 0.0),
            "wbs_accuracy": float(breakdown_raw.get("wbsAccuracy") or breakdown_raw.get("wbs_accuracy") or 0.0),
        }
    else:
        _, breakdown = _calc_confidence(requirements, wbs, project)

    analysis_metadata = {
        "total_requirements": metadata_raw.get("totalRequirements") or len(requirements),
        "total_wbs_tasks": metadata_raw.get("totalWbsTasks") or len(wbs),
        "wbs_tasks_by_role": metadata_raw.get("wbsTasksByRole") or {},
        "total_estimated_days": float(metadata_raw.get("totalEstimatedDays") or 0),
        "total_planned_hours": float(metadata_raw.get("totalPlannedHours") or 0),
        "confidence_score": float(confidence),
        "confidence_breakdown": breakdown,
        "low_confidence_items": metadata_raw.get("lowConfidenceItems") or [],
        "assumptions": metadata_raw.get("assumptions") or [],
    }

    return {
        "project": project,
        "requirements": requirements,
        "wbs": wbs,
        "required_roles": roles,
        "confidence_score": float(confidence),
        "analysis_metadata": analysis_metadata,
    }


async def regenerate_wbs(rfp_id: str) -> dict:
    rfp = _load_rfp_or_404(rfp_id)
    if rfp["status"] == "confirmed":
        raise RfpStateError(rfp_id, rfp["status"], "regenerate_wbs")
    if not rfp.get("analysis_json"):
        raise RfpStateError(rfp_id, rfp["status"], "analyze 선행")

    current = json.loads(rfp["analysis_json"])
    requirements = current.get("requirements") or []
    user_message = json.dumps({"requirements": requirements}, ensure_ascii=False)

    payload = await llm_client.complete_json(WBS_REGEN_SYSTEM, user_message, max_tokens=16000)
    new_wbs = _normalize_wbs(payload.get("wbs") or [])
    current["wbs"] = new_wbs

    sparql_repo.update_rfp_analysis(
        rfp_id=rfp_id,
        analysis_json=json.dumps(current, ensure_ascii=False),
        project_name=(current.get("project") or {}).get("project_name"),
        confidence=current.get("confidence_score"),
        status=rfp["status"],
    )
    return {
        "rfp_id": rfp_id,
        "status": rfp["status"],
        "wbs": new_wbs,
        "analysis_metadata": current.get("analysis_metadata"),
    }


def _normalize_wbs(raw_wbs: list) -> list:
    result = []
    for item in raw_wbs:
        evidence_raw = item.get("evidence") or {}
        evidence = {
            "source_req_id": evidence_raw.get("source_req_id") or evidence_raw.get("sourceReqId"),
            "source_text": evidence_raw.get("source_text") or evidence_raw.get("sourceText"),
            "reasoning_step": evidence_raw.get("reasoning_step") or evidence_raw.get("reasoningStep"),
        } if evidence_raw else None

        raw_deliverables = item.get("deliverables") or item.get("deliverable")
        if isinstance(raw_deliverables, str):
            deliverables = [raw_deliverables] if raw_deliverables else []
        else:
            deliverables = raw_deliverables or []

        result.append({
            "wbs_code": item.get("wbs_code") or item.get("wbsCode") or "",
            "req_id": item.get("req_id") or item.get("reqId"),
            "task_name": item.get("task_name") or item.get("taskName") or "",
            "assignee_role": item.get("assignee_role") or item.get("assigneeRole"),
            "task_description": item.get("task_description") or item.get("taskDescription"),
            "required_skills": item.get("required_skills") or item.get("requiredSkills") or [],
            "estimated_days": item.get("estimated_days") or item.get("estimatedDays"),
            "planned_hours": item.get("planned_hours") or item.get("plannedHours"),
            "planned_start": item.get("planned_start") or item.get("plannedStart"),
            "planned_end": item.get("planned_end") or item.get("plannedEnd"),
            "deliverables": deliverables,
            "depends_on": item.get("depends_on") or item.get("dependsOn") or [],
            "evidence": evidence,
            "phase": item.get("phase"),
            "criticality": item.get("criticality"),
            "risk": item.get("risk"),
        })
    return result


def patch_analysis(rfp_id: str, patch: dict) -> dict:
    rfp = _load_rfp_or_404(rfp_id)
    if rfp["status"] == "confirmed":
        raise RfpStateError(rfp_id, rfp["status"], "patch")
    if not rfp.get("analysis_json"):
        raise RfpStateError(rfp_id, rfp["status"], "analyze 선행")

    current = json.loads(rfp["analysis_json"])
    if patch.get("project") is not None:
        # 빈 리스트/None은 제외하고 실제 값만 업데이트
        current["project"].update({
            k: v for k, v in patch["project"].items()
            if v is not None and v != []
        })
    if patch.get("requirements") is not None:
        current["requirements"] = patch["requirements"]
    if patch.get("wbs") is not None:
        current["wbs"] = patch["wbs"]
    if patch.get("required_roles") is not None:
        current["required_roles"] = patch["required_roles"]
    if patch.get("consortium") is not None:
        current["consortium"] = patch["consortium"]

    sparql_repo.update_rfp_analysis(
        rfp_id=rfp_id,
        analysis_json=json.dumps(current, ensure_ascii=False),
        project_name=current["project"].get("project_name"),
        confidence=current.get("confidence_score"),
        status="reviewed",
    )
    return {"rfp_id": rfp_id, "status": "reviewed"}


def confirm_rfp(rfp_id: str) -> dict:
    rfp = _load_rfp_or_404(rfp_id)
    if not rfp.get("analysis_json"):
        raise RfpStateError(rfp_id, rfp["status"], "analyze 선행")
    if rfp["status"] == "confirmed":
        raise RfpStateError(rfp_id, rfp["status"], "이미 확정됨")

    analysis = json.loads(rfp["analysis_json"])
    project_id = _generate_project_id(rfp_id)
    triples_count = sparql_repo.insert_project_with_wbs(
        project_id=project_id,
        project=analysis["project"],
        wbs=analysis.get("wbs") or [],
        requirements=analysis.get("requirements") or [],
        required_roles=analysis.get("required_roles") or [],
    )
    sparql_repo.mark_rfp_confirmed(rfp_id, project_id)

    project_name = analysis["project"].get("project_name", project_id)

    try:
        slide_id = google_slides_service.create_presentation(project_name)
    except Exception as e:
        sparql_repo.delete_project(project_id)
        sparql_repo.unmark_rfp_confirmed(rfp_id)
        raise IntegrationError(f"Google Slides 생성 실패: {e}") from e

    try:
        gitlab_result = gitlab_service.create_repository(project_name, project_id)
    except Exception as e:
        sparql_repo.delete_project(project_id)
        sparql_repo.unmark_rfp_confirmed(rfp_id)
        raise IntegrationError(f"GitLab 저장소 생성 실패: {e}") from e

    sparql_repo.update_project_integration_ids(
        project_id=project_id,
        google_slide_id=slide_id,
        gitlab_project_id=gitlab_result["id"],
        gitlab_repo_url=gitlab_result["url"],
    )

    return {
        "project_id": project_id,
        "tasks_created": len(analysis.get("wbs") or []),
        "requirements_created": len(analysis.get("requirements") or []),
        "triples_inserted": triples_count,
        "fuseki_graph_uri": f"https://ontology.example.org/instances#project_{project_id.lower()}",
        "next_step": f"인력 추천 API를 실행하세요: POST /projects/{project_id}/recommend-staff",
        "google_slide_id": slide_id,
        "gitlab_project_id": gitlab_result["id"],
        "gitlab_repo_url": gitlab_result["url"],
    }


def _generate_project_id(rfp_id: str) -> str:
    """RFP_ABC123 → PRJ_ABC123 형태로 변환."""
    suffix = rfp_id.removeprefix("RFP_")
    return f"PRJ_{suffix}"


def get_rfp_detail(rfp_id: str) -> dict:
    rfp = _load_rfp_or_404(rfp_id)
    detail: dict = {
        "rfp_id": rfp_id,
        "file_name": rfp.get("file_name") or "",
        "status": rfp["status"],
        "page_count": rfp.get("page_count") or 0,
        "created_at": rfp.get("created_at") or "",
        "project": None,
        "requirements": [],
        "wbs": [],
        "required_roles": [],
        "consortium": None,
        "confidence_score": rfp.get("confidence_score"),
        "analysis_metadata": None,
        "confirmed_project_id": None,
    }

    analysis_json = rfp.get("analysis_json")
    if analysis_json:
        try:
            parsed = json.loads(analysis_json)
            detail["project"] = parsed.get("project")
            detail["requirements"] = parsed.get("requirements") or []
            detail["wbs"] = parsed.get("wbs") or []
            detail["required_roles"] = parsed.get("required_roles") or []
            detail["consortium"] = parsed.get("consortium")
            if parsed.get("confidence_score") is not None:
                detail["confidence_score"] = parsed["confidence_score"]
            detail["analysis_metadata"] = parsed.get("analysis_metadata")
        except json.JSONDecodeError:
            pass

    confirmed_uri = rfp.get("confirmed_project")
    if confirmed_uri:
        local = confirmed_uri.rsplit("#", 1)[-1].removeprefix("project_").upper()
        detail["confirmed_project_id"] = local

    return detail


def list_rfps() -> list[dict]:
    return sparql_repo.list_rfps()


# ──────────────────────────────────────────────────────────────────────────────
# 3단계 스테이지드 분석
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# 청킹 기반 분석 파이프라인 (analyze-chunked)
# ──────────────────────────────────────────────────────────────────────────────

def _to_list(value) -> list[str]:
    """LLM이 단일 문자열을 줘도 list로, list면 그대로 정규화한다."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    if isinstance(value, str):
        # 파이프(|)/콤마/슬래시 구분자도 허용
        parts = [p.strip() for p in value.replace("|", ",").replace("/", ",").split(",")]
        return [p for p in parts if p]
    return [str(value)]


def _snake_to_camel(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(p.title() for p in parts[1:])


def _to_camel_keys(obj):
    """dict의 snake_case 키를 camelCase로 재귀 변환."""
    if isinstance(obj, dict):
        return {_snake_to_camel(k): _to_camel_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_camel_keys(v) for v in obj]
    return obj


# 요구사항 번호 패턴 — 한국 RFP에서 자주 쓰이는 prefix
# 새 prefix가 발견되면 여기에 추가
_REQ_PREFIXES = (
    "FUN", "PER", "INT", "DAR", "TER", "SER", "QUR",
    "COR", "PMR", "PSR", "ECR", "CNR", "NFR", "UIR", "REQ",
    "SFR"
)
_REQ_HEADING_PATTERN = re.compile(
    r"(?=(?:" + "|".join(_REQ_PREFIXES) + r")-\d+)"
)

# 단일 청크 최대 문자 수 (한국어 기준 약 2000~3000 토큰)
_MAX_CHARS_PER_CHUNK = 8000


def _split_by_requirement(text: str, max_chars: int = _MAX_CHARS_PER_CHUNK) -> list[str]:
    """요구사항 번호(FUN-01, PER-02 등) 헤딩을 경계로 청크를 나눈다.

    - **각 요구사항 = 1 청크** (병합 없음, 오버랩 없음)
    - 첫 요구사항 이전 텍스트(사업 개요·목차 등)는 별도 청크로 유지 (projectInfo 추출용)
    - 단일 요구사항이 max_chars를 초과해도 자르지 않고 단일 청크 유지 (잘림 방지)
    - 요구사항 패턴이 전혀 없으면 max_chars 단위로 단순 분할 (안전망)
    """
    if not text:
        return []

    sections = _REQ_HEADING_PATTERN.split(text)
    # 의미 있는 섹션만 (빈/공백 제거하면서 순서 유지)
    sections = [s.strip() for s in sections if s and s.strip()]

    if not sections:
        return []

    # 요구사항 패턴이 전혀 안 잡힌 경우 안전망: 단순 길이 기반 분할
    if len(sections) == 1 and len(text) > max_chars:
        return [text[i : i + max_chars] for i in range(0, len(text), max_chars)]

    return sections


def _merge_project_info(partials: list[dict]) -> dict:
    """청크별 추출된 projectInfo들을 병합. 필드별로 가장 먼저 채워진 non-empty 값 우선."""
    merged: dict = {}
    list_fields = {"partnerCompanies", "partner_companies"}
    for partial in partials:
        for key, value in (partial or {}).items():
            if value in (None, "", []):
                continue
            if key in list_fields:
                existing = merged.get(key) or []
                # 중복 없이 합치되 순서 유지
                seen = set(existing)
                for v in value:
                    if v not in seen:
                        existing.append(v)
                        seen.add(v)
                merged[key] = existing
            elif key not in merged:
                merged[key] = value
    return merged


async def _extract_project_info_chunk(chunk: str, chunk_index: int, total: int) -> dict:
    """단일 청크에서 프로젝트 정보 추출."""
    user_message = json.dumps(
        {"chunkIndex": chunk_index, "totalChunks": total, "chunkText": chunk},
        ensure_ascii=False,
    )
    try:
        result = await llm_client.complete_json(
            CHUNK_PROJECT_EXTRACT_SYSTEM, user_message, max_tokens=2000
        )
        project = result.get("project") or {}
        filled_keys = [k for k, v in project.items() if v not in (None, "", [])]
        logger.info(
            "[PROJECT-EXTRACT] chunk=%d/%d filled_fields=%d keys=%s",
            chunk_index + 1, total, len(filled_keys), filled_keys,
        )
        return project
    except Exception as exc:
        logger.warning("[PROJECT-EXTRACT] 실패 chunk=%d/%d: %s", chunk_index + 1, total, exc)
        return {}


async def _extract_project_info_from_chunks(chunks: list[str]) -> dict:
    """모든 청크에서 프로젝트 정보를 병렬 추출하고 병합한다."""
    tasks = [_extract_project_info_chunk(c, i, len(chunks)) for i, c in enumerate(chunks)]
    partials = await asyncio.gather(*tasks, return_exceptions=False)
    merged = _merge_project_info(partials)
    logger.info(
        "[PROJECT-EXTRACT] 병합 완료: project_name=%s theme=%s amount=%s client=%s lead=%s partners=%s",
        merged.get("projectName") or merged.get("project_name"),
        merged.get("projectTheme") or merged.get("project_theme"),
        merged.get("projectAmount") or merged.get("project_amount"),
        merged.get("clientName") or merged.get("client_name"),
        merged.get("leadCompany") or merged.get("lead_company"),
        merged.get("partnerCompanies") or merged.get("partner_companies") or [],
    )
    return merged


async def _extract_requirements_chunk(
    chunk: str, chunk_index: int, total: int, project_context: dict
) -> list[dict]:
    """단일 청크에서 요구사항 추출."""
    user_message = json.dumps(
        {
            "chunkIndex": chunk_index,
            "totalChunks": total,
            "chunkText": chunk,
            "projectContext": project_context,
        },
        ensure_ascii=False,
    )
    try:
        result = await llm_client.complete_json(
            CHUNK_REQ_EXTRACT_SYSTEM, user_message, max_tokens=8000
        )
        reqs = result.get("requirements") or []
        # 추출 출처 청크 정보를 각 요구사항에 첨부 (UI에서 사용자가 추적 가능)
        for r in reqs:
            r["source_chunk_index"] = chunk_index
            r["source_chunk_text"] = chunk
        logger.info("[REQ-EXTRACT] chunk=%d/%d count=%d", chunk_index + 1, total, len(reqs))
        for r in reqs:
            req_id = r.get("reqId") or r.get("req_id") or "?"
            req_name = r.get("reqName") or r.get("req_name") or "?"
            assignee = r.get("assigneeType") or r.get("assignee_type") or "?"
            req_type = r.get("requirementType") or r.get("requirement_type") or "?"
            logger.info(
                "[REQ-EXTRACT]   - %s | %s | type=%s assignee=%s",
                req_id, req_name, req_type, assignee,
            )
        return reqs
    except Exception as exc:
        logger.warning("[REQ-EXTRACT] 실패 chunk=%d/%d: %s", chunk_index + 1, total, exc)
        return []


async def _extract_requirements_from_chunks(
    chunks: list[str], project_info: dict
) -> list[dict]:
    """모든 청크에서 요구사항을 병렬 추출하고 flat list로 반환한다.

    LLM은 tempId/parentTempId/isLarge로 식별하므로 청크별 그룹화가 불필요하다.
    후속 `_assign_req_ids`가 tempId 기반으로 dedup + reqId 부여를 처리한다.
    """
    project_context = {
        "projectName": project_info.get("projectName") or project_info.get("project_name"),
        "projectTheme": project_info.get("projectTheme") or project_info.get("project_theme"),
        "description": project_info.get("description"),
    }
    tasks = [
        _extract_requirements_chunk(c, i, len(chunks), project_context)
        for i, c in enumerate(chunks)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    all_reqs: list[dict] = []
    for reqs in results:
        all_reqs.extend(reqs)
    logger.info("[REQ-EXTRACT] 전체 추출 합계: %d (assign 전)", len(all_reqs))
    return all_reqs


def _normalize_requirement(req: dict) -> dict:
    """단일 요구사항 dict를 camelCase → snake_case로 정규화한다.

    LLM은 reqId를 출력하지 않고 tempId/parentTempId/isLarge만 출력한다.
    req_id는 후속 `_assign_req_ids`가 부여하므로 여기서는 빈 문자열로 둔다.
    """
    return {
        "req_id": "",  # 코드가 후처리로 부여
        "temp_id": (req.get("temp_id") or req.get("tempId") or "").strip(),
        "parent_temp_id": (req.get("parent_temp_id") or req.get("parentTempId") or "").strip(),
        "is_large": bool(req.get("is_large") if "is_large" in req else req.get("isLarge")),
        "assignee_type": _to_list(req.get("assignee_type") or req.get("assigneeType")),
        "user_type": req.get("user_type") or req.get("userType") or [],
        "requirement_type": req.get("requirement_type") or req.get("requirementType"),
        "req_category": _normalize_req_category(req.get("req_category") or req.get("reqCategory")),
        "req_name": req.get("req_name") or req.get("reqName"),
        "req_description": req.get("req_description") or req.get("reqDescription"),
        "req_detail": req.get("req_detail") or req.get("reqDetail"),
        "notes": req.get("notes"),
        "importance": req.get("importance"),
        "priority": req.get("priority"),
        "deliverables": req.get("deliverables") or [],
        "related_req_ids": req.get("related_req_ids") or req.get("relatedReqIds") or [],
        "source_text": req.get("source_text") or req.get("sourceText"),
        "source_chunk_index": req.get("source_chunk_index"),
        "source_chunk_text": req.get("source_chunk_text"),
        "inferred_from_context": bool(
            req.get("inferred_from_context") or req.get("inferredFromContext")
        ),
    }


def _normalize_temp_id_format(tid: str) -> str:
    """tempId 정규화 — 공백 제거, 대문자, 'FUN 02'/'FUN02' → 'FUN-02' 통일."""
    if not tid:
        return ""
    normalized = re.sub(r"\s+", "", tid).upper()
    # 접두사+숫자 패턴이면 하이픈 표준화 (FUN02 / FUN-2 / FUN-002 → FUN-002 형태로 padding은 그대로 둠)
    m = re.fullmatch(r"([A-Z]+)-?0*(\d+)", normalized)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):03d}"
    return normalized


def _assign_req_ids(all_reqs: list[dict]) -> list[dict]:
    """LLM이 추출한 요구사항에 코드가 reqId를 부여한다.

    LLM 출력 필드: tempId, parentTempId, isLarge (+ 일반 콘텐츠 필드)
    → 코드가 reqId를 부여하고 tempId/parentTempId/isLarge 제거.

    동작:
    1. 입력 정규화 (snake_case + temp_id/parent_temp_id 형식 통일)
    2. dedup: 같은 temp_id가 여러 청크에서 나오면 req_detail이 더 풍부한 쪽 채택
    3. Large vs Mid 분리 (is_large 플래그)
    4. Large에 REQ-001, REQ-002... 순차 부여 + (temp_id → req_id) 매핑 구성
    5. Mid에 REQ-{parent}-{seq} 부여 (부모 없는 Mid는 Large로 승격)
    6. related_req_ids 안의 tempId 형식 참조를 가능한 한 새 reqId로 변환
    7. 내부 필드(temp_id/parent_temp_id/is_large) 제거
    """
    # ① 정규화
    normalized: list[dict] = []
    for r in all_reqs:
        nr = _normalize_requirement(r)
        nr["temp_id"] = _normalize_temp_id_format(nr["temp_id"])
        nr["parent_temp_id"] = _normalize_temp_id_format(nr["parent_temp_id"])
        # temp_id가 없으면 reqName/sourceText로 fallback 식별자 생성
        if not nr["temp_id"]:
            fallback = f"_FB:{(nr.get('req_name') or '').strip()}|{(nr.get('source_text') or '')[:50].strip()}"
            nr["temp_id"] = fallback
            if not nr["parent_temp_id"]:
                nr["parent_temp_id"] = fallback
            # tempId가 없는 경우 일단 Large로 간주 (안전한 fallback)
            if "is_large" not in r and "isLarge" not in r:
                nr["is_large"] = True
        normalized.append(nr)

    # ② tempId 기반 dedup (reqDetail이 더 풍부한 쪽 채택)
    seen: dict[str, dict] = {}
    dropped = 0
    for req in normalized:
        tid = req["temp_id"]
        if tid not in seen:
            seen[tid] = req
        else:
            existing = seen[tid]
            new_detail = len(req.get("req_detail") or "")
            old_detail = len(existing.get("req_detail") or "")
            new_desc = len(req.get("req_description") or "")
            old_desc = len(existing.get("req_description") or "")
            if (new_detail + new_desc) > (old_detail + old_desc):
                seen[tid] = req
                logger.info("[REQ-ASSIGN] dedup 교체 (더 풍부한 내용): temp_id=%s", tid)
            else:
                dropped += 1
                logger.info("[REQ-ASSIGN] dedup 제거: temp_id=%s name=%s", tid, req.get("req_name"))

    deduped = list(seen.values())

    # ③ Large / Mid 분리. 부모 없는 Mid는 Large로 승격
    large_temp_ids = {r["temp_id"] for r in deduped if r.get("is_large")}
    larges: list[dict] = []
    mids: list[dict] = []
    for r in deduped:
        if r.get("is_large"):
            larges.append(r)
        elif r["parent_temp_id"] and r["parent_temp_id"] in large_temp_ids:
            mids.append(r)
        else:
            # 부모 없음 → Large로 승격
            r["is_large"] = True
            r["parent_temp_id"] = r["temp_id"]
            larges.append(r)
            logger.warning(
                "[REQ-ASSIGN] 부모 없는 Mid → Large 승격: temp_id=%s parent_was=%s",
                r["temp_id"], r["parent_temp_id"],
            )

    # ④ Large reqId 부여 (등장 순서 기반, temp_id 알파벳 순으로 안정 정렬)
    larges.sort(key=lambda r: r["temp_id"])
    temp_to_req_id: dict[str, str] = {}
    for i, req in enumerate(larges, start=1):
        new_id = f"REQ-{i:03d}"
        req["req_id"] = new_id
        temp_to_req_id[req["temp_id"]] = new_id

    # ⑤ Mid reqId 부여 (부모별 시퀀스 분리)
    # Mid를 (parent_temp_id, temp_id) 순으로 안정 정렬해 동일 부모 그룹 내에서 순서 안정화
    mids.sort(key=lambda r: (r["parent_temp_id"], r["temp_id"]))
    mid_counters: dict[str, int] = {}
    for req in mids:
        parent_req_id = temp_to_req_id.get(req["parent_temp_id"])
        if not parent_req_id:
            # 정상 흐름에선 발생 안 함 (위에서 처리됨). 안전망.
            parent_req_id = f"REQ-{len(larges) + len(mid_counters) + 1:03d}"
        mid_counters[parent_req_id] = mid_counters.get(parent_req_id, 0) + 1
        req["req_id"] = f"{parent_req_id}-{mid_counters[parent_req_id]:03d}"

    # ⑥ related_req_ids에 포함된 tempId 형식 참조를 reqId로 변환 가능한 만큼 변환
    all_final = larges + mids
    for req in all_final:
        related = req.get("related_req_ids") or []
        mapped: list[str] = []
        for rid in related:
            normalized_ref = _normalize_temp_id_format(rid)
            mapped.append(temp_to_req_id.get(normalized_ref, rid))
        req["related_req_ids"] = mapped

    # ⑦ 내부 필드 제거
    for req in all_final:
        req.pop("temp_id", None)
        req.pop("parent_temp_id", None)
        req.pop("is_large", None)

    # ⑧ reqId 기준 정렬 (Large는 REQ-001, REQ-002, ... Mid는 그 다음에 REQ-001-001, ...)
    all_final.sort(key=lambda r: r["req_id"])

    logger.info(
        "[REQ-ASSIGN] 총 %d개 입력 → dedup %d개 → 최종 %d개 (Large %d, Mid %d)",
        len(all_reqs), dropped, len(all_final), len(larges), len(mids),
    )
    return all_final


# ──────────────────────────────────────────────────────────────────────────────
# WBS 생성: 코드가 분해+wbsCode 부여, LLM은 내용만 채움
# ──────────────────────────────────────────────────────────────────────────────

# assigneeType → assigneeRole 매핑. 개발-화면/비화면은 모두 "개발자"
ASSIGNEE_TYPE_TO_ROLE: dict[str, str] = {
    "PM": "PM",
    "기획": "기획자",
    "개발-화면": "개발자",
    "개발-비화면": "개발자",
}


def _is_mid(req: dict) -> bool:
    """Mid 요구사항인지 판정 (req_id에 '-'가 2개 이상 → 'REQ-001-001' 형태)."""
    rid = req.get("req_id") or ""
    return rid.count("-") >= 2


def _expand_to_wbs_skeletons(mid_req: dict) -> list[dict]:
    """Mid 요구사항 1개 → assigneeType별 WBS task 스켈레톤 N개.

    예:
      assignee_type=["기획", "개발-화면", "개발-비화면"]
      → skeleton 3개 (기획자 / 개발자(화면) / 개발자(비화면))

    "전체"가 포함되면 4개 역할로 분해.
    """
    assignee_types = list(mid_req.get("assignee_type") or [])
    if "전체" in assignee_types:
        expanded: list[str] = []
        for t in assignee_types:
            if t == "전체":
                for full in ("PM", "기획", "개발-화면", "개발-비화면"):
                    if full not in expanded:
                        expanded.append(full)
            elif t not in expanded:
                expanded.append(t)
        assignee_types = expanded

    skeletons: list[dict] = []
    for atype in assignee_types:
        role = ASSIGNEE_TYPE_TO_ROLE.get(atype, "개발자")
        skeletons.append({
            "sourceReqId": mid_req.get("req_id"),
            "assigneeRole": role,
            "devType": atype,
            # LLM 컨텍스트용 (밑줄 접두 = 입력 전용)
            "_reqName": mid_req.get("req_name"),
            "_reqDescription": mid_req.get("req_description"),
            "_reqDetail": mid_req.get("req_detail"),
            "_notes": mid_req.get("notes"),
        })
    return skeletons


def _build_dependency_map(skeletons: list[dict]) -> dict[str, list[str]]:
    """같은 sourceReqId 안에서 개발자 task는 기획자 task에 의존하도록 자동 매핑.

    반환: {tempTaskId: [선행 tempTaskId, ...]}
    """
    by_req: dict[str, list[dict]] = defaultdict(list)
    for sk in skeletons:
        by_req[sk["sourceReqId"]].append(sk)

    deps: dict[str, list[str]] = {}
    for _req_id, group in by_req.items():
        planner = next((s for s in group if s["assigneeRole"] == "기획자"), None)
        if not planner:
            continue
        for s in group:
            if s["assigneeRole"] == "개발자":
                deps.setdefault(s["tempTaskId"], []).append(planner["tempTaskId"])
    return deps


async def _generate_wbs_chunked(
    requirements: list[dict], project_info: dict
) -> list[dict]:
    """Mid 요구사항을 assigneeType별 WBS task로 분해하고 LLM에 내용 채움을 요청.

    1. Mid 요구사항만 필터링
    2. assigneeType별로 task 스켈레톤 생성 (코드가 결정)
    3. tempTaskId 부여 (T001, T002, ...)
    4. 배치별 LLM 호출 → LLM은 taskName/description/일정 등만 채움
    5. 코드가 wbsCode 순차 부여 (WBS-001, WBS-002, ...)
    6. dependsOn 해소: tempTaskId 참조 → wbsCode 매핑, 자동 dep(개발→기획) 추가
    """
    mids = [r for r in requirements if _is_mid(r)]
    logger.info("[WBS-GEN] Mid 요구사항 %d개에서 스켈레톤 생성", len(mids))

    # 1~3. 스켈레톤 + tempTaskId
    all_skeletons: list[dict] = []
    for mid in mids:
        all_skeletons.extend(_expand_to_wbs_skeletons(mid))
    for i, sk in enumerate(all_skeletons, start=1):
        sk["tempTaskId"] = f"T{i:03d}"

    if not all_skeletons:
        logger.info("[WBS-GEN] 생성할 task 없음 (Mid 요구사항 없음)")
        return []

    logger.info("[WBS-GEN] 총 task 스켈레톤 %d개 (Mid %d개 분해)",
                len(all_skeletons), len(mids))

    # 4. 배치별 LLM 호출 — 스케줄링 컨텍스트(기간 + 권장 평균 일수) 포함
    batch_size = 12
    total_batches = (len(all_skeletons) + batch_size - 1) // batch_size

    # 프로젝트 기간 정보
    project_start_str = project_info.get("startDate") or project_info.get("start_date")
    project_end_str = project_info.get("endDate") or project_info.get("end_date")
    project_start_dt = _parse_iso_date(project_start_str)
    project_end_dt = _parse_iso_date(project_end_str)
    project_biz_days = (
        _count_business_days(project_start_dt, project_end_dt)
        if (project_start_dt and project_end_dt) else 0
    )

    # 역할별 task 분포
    skeletons_by_role: dict[str, int] = defaultdict(int)
    for sk in all_skeletons:
        skeletons_by_role[sk["assigneeRole"]] += 1

    # 역할별 권장 평균 일수
    # 가정: 영업일 × 가용률(0.8)이 역할별 task에 분배되며, 각 task는 평균 (유효일수 / task수) 일.
    # LLM은 task 복잡도에 따라 이 평균 기준 ±조정.
    UTILIZATION = 0.8
    guidance_avg_days: dict[str, float] = {}
    if project_biz_days > 0:
        effective_days = project_biz_days * UTILIZATION
        for role, cnt in skeletons_by_role.items():
            if cnt > 0:
                guidance_avg_days[role] = max(0.5, round(effective_days / cnt, 1))

    period_str = (
        f"{project_start_str} ~ {project_end_str}"
        if project_start_str and project_end_str else "미정"
    )
    project_context = (
        f"프로젝트명: {project_info.get('projectName') or project_info.get('project_name') or '미상'}, "
        f"주제: {project_info.get('projectTheme') or project_info.get('project_theme') or '미상'}, "
        f"기간: {period_str} (영업일 {project_biz_days}일), "
        f"설명: {project_info.get('description') or '미상'}"
    )

    scheduling_guide = {
        "projectStart": project_start_str,
        "projectEnd": project_end_str,
        "projectBizDays": project_biz_days,
        "totalSkeletons": len(all_skeletons),
        "skeletonsByRole": dict(skeletons_by_role),
        "guidanceAvgDaysByRole": guidance_avg_days,
        "utilizationRate": UTILIZATION,
        "guidanceNote": (
            "각 task의 estimatedDays는 guidanceAvgDaysByRole의 해당 역할 평균값을 기준으로, "
            "task 복잡도(reqDescription/reqDetail)에 따라 0.5x ~ 2x 범위에서 조정하세요. "
            "plannedStart/plannedEnd는 반드시 projectStart ~ projectEnd 범위 내여야 하며, "
            "주말은 건너뜁니다. 동일 sourceReqId 내에서 기획자 task가 개발자 task보다 먼저 끝나야 합니다."
        ),
    }

    logger.info(
        "[WBS-GEN] 스케줄링 가이드: bizDays=%d totalSkeletons=%d guidance=%s",
        project_biz_days, len(all_skeletons), guidance_avg_days,
    )

    # tempTaskId → LLM 응답 매핑
    filled_by_temp: dict[str, dict] = {}

    for batch_idx in range(0, len(all_skeletons), batch_size):
        batch = all_skeletons[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1

        logger.info(
            "[WBS-GEN] 배치 시작 batch=%d/%d tasks=%d",
            batch_num, total_batches, len(batch),
        )

        user_message = json.dumps(
            {
                "projectContext": project_context,
                "schedulingGuide": scheduling_guide,
                "taskSkeletons": batch,
                "batchNumber": batch_num,
                "totalBatches": total_batches,
            },
            ensure_ascii=False,
        )
        try:
            result = await llm_client.complete_json(
                CHUNK_WBS_GEN_SYSTEM, user_message, max_tokens=16000
            )
            items = result.get("wbs") or result.get("tasks") or []
            for item in items:
                tid = (item.get("tempTaskId") or item.get("temp_task_id") or "").strip()
                if tid:
                    filled_by_temp[tid] = item
            logger.info(
                "[WBS-GEN] 배치 완료 batch=%d/%d filled=%d",
                batch_num, total_batches, len(items),
            )
        except Exception as exc:
            logger.warning("[WBS-GEN] 배치 실패 batch=%d/%d: %s",
                           batch_num, total_batches, exc)

    # 5. 스켈레톤 + LLM 응답 병합 + wbsCode 순차 부여
    final_wbs: list[dict] = []
    temp_to_wbs_code: dict[str, str] = {}
    for i, sk in enumerate(all_skeletons, start=1):
        wbs_code = f"WBS-{i:03d}"
        temp_to_wbs_code[sk["tempTaskId"]] = wbs_code
        llm_item = filled_by_temp.get(sk["tempTaskId"], {})

        # LLM이 응답하지 않은 경우 fallback: sourceReqId의 reqName 기반 기본값
        task_name = (
            llm_item.get("taskName") or llm_item.get("task_name")
            or f"[{sk['devType']}] {sk.get('_reqName') or sk['sourceReqId']}"
        )

        raw_deliverables = llm_item.get("deliverables") or llm_item.get("deliverable")
        if isinstance(raw_deliverables, str):
            deliverables = [raw_deliverables] if raw_deliverables else []
        else:
            deliverables = raw_deliverables or []

        evidence_raw = llm_item.get("evidence") or {}
        evidence = {
            "source_req_id": (evidence_raw.get("source_req_id")
                              or evidence_raw.get("sourceReqId")
                              or sk["sourceReqId"]),
            "source_text": (evidence_raw.get("source_text")
                            or evidence_raw.get("sourceText")
                            or sk.get("_reqDescription")),
            "reasoning_step": (evidence_raw.get("reasoning_step")
                               or evidence_raw.get("reasoningStep")),
        }

        final_wbs.append({
            "wbs_code": wbs_code,
            "req_id": sk["sourceReqId"],
            "task_name": task_name,
            "assignee_role": sk["assigneeRole"],  # 코드가 부여한 값 우선
            "task_description": (llm_item.get("taskDescription") or llm_item.get("task_description")),
            "required_skills": (llm_item.get("requiredSkills") or llm_item.get("required_skills") or []),
            "estimated_days": (llm_item.get("estimatedDays") or llm_item.get("estimated_days")),
            # planned_hours/start/end는 코드가 _schedule_wbs_tasks에서 후처리로 산정
            # (LLM이 보내도 무시 — 겹침·의존성 보장을 위해 결정적 스케줄러 사용)
            "planned_hours": None,
            "planned_start": None,
            "planned_end": None,
            "deliverables": deliverables,
            # dependsOn은 임시로 LLM 응답(tempTaskId 형태)를 보관, 아래에서 wbsCode로 변환
            "_raw_depends_on": (llm_item.get("dependsOn") or llm_item.get("depends_on") or []),
            "evidence": evidence,
            # 우선순위 분류 (스케줄러용) — LLM 응답에서 추출
            "phase": llm_item.get("phase"),
            "criticality": llm_item.get("criticality"),
            "risk": llm_item.get("risk"),
            # 디버그용 (최종 제거)
            "_temp_task_id": sk["tempTaskId"],
            "_dev_type": sk["devType"],
        })

    # 6. dependsOn 해소 + 자동 dep 추가
    auto_deps = _build_dependency_map(all_skeletons)
    for wbs in final_wbs:
        tid = wbs["_temp_task_id"]
        # LLM이 준 dependsOn: tempTaskId → wbsCode
        raw = wbs.pop("_raw_depends_on", [])
        resolved: list[str] = []
        for ref in raw:
            ref_s = str(ref).strip()
            if ref_s in temp_to_wbs_code:
                resolved.append(temp_to_wbs_code[ref_s])
            elif ref_s.startswith("WBS-") or ref_s.startswith("REQ-"):
                resolved.append(ref_s)
            # 그 외(잘못된 참조)는 무시

        # 자동 dep (개발자 → 기획자) 추가 (LLM이 빠뜨려도 보강)
        for auto_tid in auto_deps.get(tid, []):
            auto_code = temp_to_wbs_code.get(auto_tid)
            if auto_code and auto_code not in resolved:
                resolved.append(auto_code)

        wbs["depends_on"] = resolved

    # 일정(planned_start/end/hours)은 _schedule_wbs_tasks가 호출부에서 채움.
    # 디버그용 임시 키 제거
    for wbs in final_wbs:
        wbs.pop("_temp_task_id", None)
        wbs.pop("_dev_type", None)

    logger.info("[WBS-GEN] 최종 WBS task %d개 생성 (wbsCode WBS-001 ~ WBS-%03d)",
                len(final_wbs), len(final_wbs))
    for w in final_wbs:
        logger.info(
            "[WBS-GEN]   - %s <- %s | %s | role=%s days=%s deps=%s",
            w["wbs_code"], w["req_id"], w.get("task_name") or "?",
            w["assignee_role"], w.get("estimated_days") or "?",
            w["depends_on"],
        )
    return final_wbs


async def analyze_rfp_chunked(
    rfp_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """요구사항 번호 기반 청킹으로 RFP 분석.

    Step 1: 요구사항 번호(FUN-01, PER-02 등) 헤딩을 경계로 청크 분할 (LLM 호출 없음)
    Step 2: 청크별 프로젝트 정보 추출 → 병합
    Step 3: 청크별 요구사항 추출 (병렬) → dedup
    Step 4: 요구사항 배치별 WBS 생성 (순차)

    start_date / end_date가 명시되면 LLM 추출값을 덮어쓴다.
    """
    rfp = _load_rfp_or_404(rfp_id)
    if rfp["status"] == "confirmed":
        raise RfpStateError(rfp_id, rfp["status"], "analyze")

    full_text = rfp.get("extracted_text") or ""
    logger.info("=" * 60)
    logger.info("[ANALYZE-CHUNKED] 시작 rfp_id=%s text_len=%d",
                rfp_id, len(full_text))
    logger.info("=" * 60)

    # Step 1 — 요구사항 번호 기반 청킹
    chunks = _split_by_requirement(full_text)
    logger.info(
        "[ANALYZE-CHUNKED] Step 1/4 청킹 완료: chunks=%d (요구사항 번호 헤딩 기반, max_chars=%d)",
        len(chunks), _MAX_CHARS_PER_CHUNK,
    )

    # Step 2 — 프로젝트 정보
    logger.info("[ANALYZE-CHUNKED] Step 2/4 프로젝트 정보 추출 시작")
    project_info_raw = await _extract_project_info_from_chunks(chunks)

    # 입력 파라미터로 받은 기간이 있으면 LLM 추출값을 덮어쓴다
    if start_date:
        prev = project_info_raw.get("startDate") or project_info_raw.get("start_date")
        project_info_raw["startDate"] = start_date
        project_info_raw.pop("start_date", None)
        logger.info("[ANALYZE-CHUNKED] start_date 입력값으로 덮어씀: %s → %s", prev, start_date)
    if end_date:
        prev = project_info_raw.get("endDate") or project_info_raw.get("end_date")
        project_info_raw["endDate"] = end_date
        project_info_raw.pop("end_date", None)
        logger.info("[ANALYZE-CHUNKED] end_date 입력값으로 덮어씀: %s → %s", prev, end_date)

    # Step 3 — 요구사항 추출 + reqId 부여 (코드가 담당, LLM은 tempId만 출력)
    logger.info("[ANALYZE-CHUNKED] Step 3/4 요구사항 추출 시작")
    raw_reqs = await _extract_requirements_from_chunks(chunks, project_info_raw)
    requirements = _assign_req_ids(raw_reqs)
    logger.info(
        "[ANALYZE-CHUNKED] Step 3/4 reqId 부여 완료: %d → %d",
        len(raw_reqs), len(requirements),
    )
    logger.info("[ANALYZE-CHUNKED] 최종 요구사항 목록:")
    for r in requirements:
        logger.info(
            "[ANALYZE-CHUNKED]   * %s | %s | type=%s assignee=%s user=%s notes=%s",
            r.get("req_id"), r.get("req_name"),
            r.get("requirement_type") or r.get("req_category"),
            r.get("assignee_type"), r.get("user_type"),
            r.get("notes"),
        )

    # Step 4 — WBS
    logger.info("[ANALYZE-CHUNKED] Step 4/4 WBS 생성 시작")
    wbs = await _generate_wbs_chunked(requirements, project_info_raw)

    # 요구사항 → WBS 매핑 요약
    req_to_wbs: dict[str, list[str]] = {}
    for w in wbs:
        req_to_wbs.setdefault(w.get("req_id") or "(없음)", []).append(w.get("wbs_code") or "?")
    logger.info("[ANALYZE-CHUNKED] 요구사항 → WBS 매핑:")
    for req_id, wbs_codes in req_to_wbs.items():
        logger.info("[ANALYZE-CHUNKED]   %s → %d개: %s", req_id, len(wbs_codes), wbs_codes)
    unmapped_reqs = [r.get("req_id") for r in requirements if r.get("req_id") not in req_to_wbs]
    if unmapped_reqs:
        logger.warning("[ANALYZE-CHUNKED] WBS가 생성되지 않은 요구사항 %d개: %s",
                       len(unmapped_reqs), unmapped_reqs)

    _validate_analysis_result(requirements, wbs)

    project = _normalize_project_info(project_info_raw)
    required_roles = _aggregate_required_roles(
        wbs,
        project_start=project.get("start_date"),
        project_end=project.get("end_date"),
    )

    # ── Step 5: 일정 스케줄링 (의존성 토폴로지 + 인원 풀 기반) ──
    schedule_assumptions: list[str] = []
    project_start_dt = _parse_iso_date(project.get("start_date"))
    project_end_dt = _parse_iso_date(project.get("end_date"))
    if project_start_dt:
        role_headcounts = {r["role"]: r["count"] for r in required_roles}
        sched_result = _schedule_wbs_tasks(
            wbs, role_headcounts, project_start_dt, project_end_dt,
        )
        logger.info(
            "[WBS-SCHEDULE] %d개 task 배치 완료, 실제 종료=%s, 기간초과=%d",
            sched_result["scheduled"], sched_result["actual_end"],
            sched_result["overflow"],
        )
        if sched_result["overflow"] > 0 and project_end_dt:
            msg = (
                f"인원 부족: {sched_result['overflow']}개 task가 프로젝트 종료일"
                f"({project_end_dt.isoformat()})을 초과하여 배치되었습니다 "
                f"(실제 종료: {sched_result['actual_end'].isoformat()})."
            )
            logger.warning("[WBS-SCHEDULE] %s", msg)
            schedule_assumptions.append(msg)
    else:
        logger.warning("[WBS-SCHEDULE] project_start 없음 — 일정 산정 skip (planned_* = None)")

    confidence, breakdown = _calc_confidence(requirements, wbs, project)
    analysis_metadata = {
        "total_requirements": len(requirements),
        "total_wbs_tasks": len(wbs),
        "wbs_tasks_by_role": {
            role: sum(1 for w in wbs if w.get("assignee_role") == role)
            for role in {w.get("assignee_role") for w in wbs if w.get("assignee_role")}
        },
        "total_estimated_days": sum(w.get("estimated_days") or 0 for w in wbs),
        "total_planned_hours": sum(w.get("planned_hours") or 0 for w in wbs),
        "confidence_score": confidence,
        "confidence_breakdown": breakdown,
        "low_confidence_items": [],
        "assumptions": schedule_assumptions,
    }

    payload = {
        "project": project,
        "requirements": requirements,
        "wbs": wbs,
        "required_roles": required_roles,
        "confidence_score": confidence,
        "analysis_metadata": analysis_metadata,
    }

    sparql_repo.update_rfp_analysis(
        rfp_id=rfp_id,
        analysis_json=json.dumps(payload, ensure_ascii=False),
        project_name=project.get("project_name"),
        confidence=confidence,
        status="analyzed",
    )
    logger.info("=" * 60)
    logger.info(
        "[ANALYZE-CHUNKED] 완료 rfp_id=%s reqs=%d wbs=%d roles=%s confidence=%.2f",
        rfp_id, len(requirements), len(wbs),
        analysis_metadata["wbs_tasks_by_role"], confidence,
    )
    logger.info(
        "[ANALYZE-CHUNKED] 합계 estimated_days=%.1f planned_hours=%.1f breakdown=%s",
        analysis_metadata["total_estimated_days"],
        analysis_metadata["total_planned_hours"],
        breakdown,
    )
    logger.info("=" * 60)
    return {"rfp_id": rfp_id, "status": "analyzed", **payload}


# ──────────────────────────────────────────────────────────────────────────────
# 섹션 기반 분석 파이프라인 (analyze-staged) — 레거시
# ──────────────────────────────────────────────────────────────────────────────

async def analyze_rfp_staged(rfp_id: str) -> dict:
    """3단계 파이프라인으로 RFP를 분석한다.

    Stage 1: 문서 구조 파악 (섹션 헤더 + 프로젝트 기본 정보)
    Stage 2: 섹션별 요구사항 추출 (병렬)
    Stage 3: 요구사항 배치별 WBS 생성 (순차)
    """
    rfp = _load_rfp_or_404(rfp_id)
    if rfp["status"] == "confirmed":
        raise RfpStateError(rfp_id, rfp["status"], "analyze")

    full_text = rfp.get("extracted_text") or ""

    # Stage 1
    stage1 = await _stage1_parse_structure(full_text)
    sections = stage1.get("sections") or []
    project_info_raw = stage1.get("projectInfo") or {}
    logger.info("Stage 1 완료: rfp_id=%s sections=%d req_sections=%d",
                rfp_id, len(sections),
                sum(1 for s in sections if s.get("containsRequirements")))

    # Stage 2
    section_chunks = _split_text_by_headers(full_text, sections)
    if not section_chunks:
        logger.warning("헤더 기반 분할 실패 — 고정 크기 청킹으로 폴백: rfp_id=%s", rfp_id)
        raw_chunks = _chunk_text_fixed(full_text)
        section_chunks = {f"섹션-{i+1}": chunk for i, chunk in enumerate(raw_chunks)}

    requirements = await _stage2_extract_all(section_chunks, project_info_raw)
    requirements = _deduplicate_requirements(requirements)
    logger.info("Stage 2 완료: rfp_id=%s requirements=%d", rfp_id, len(requirements))

    # Stage 3
    wbs = await _stage3_generate_wbs(requirements, project_info_raw)
    logger.info("Stage 3 완료: rfp_id=%s wbs=%d", rfp_id, len(wbs))

    _validate_analysis_result(requirements, wbs)

    project = _normalize_project_info(project_info_raw)
    required_roles = _aggregate_required_roles(
        wbs,
        project_start=project.get("start_date"),
        project_end=project.get("end_date"),
    )
    confidence, breakdown = _calc_confidence(requirements, wbs, project)
    analysis_metadata = {
        "total_requirements": len(requirements),
        "total_wbs_tasks": len(wbs),
        "wbs_tasks_by_role": {
            role: sum(1 for w in wbs if w.get("assignee_role") == role)
            for role in {w.get("assignee_role") for w in wbs if w.get("assignee_role")}
        },
        "total_estimated_days": sum(w.get("estimated_days") or 0 for w in wbs),
        "total_planned_hours": sum(w.get("planned_hours") or 0 for w in wbs),
        "confidence_score": confidence,
        "confidence_breakdown": breakdown,
        "low_confidence_items": [],
        "assumptions": [],
    }

    payload = {
        "project": project,
        "requirements": requirements,
        "wbs": wbs,
        "required_roles": required_roles,
        "confidence_score": confidence,
        "analysis_metadata": analysis_metadata,
    }

    sparql_repo.update_rfp_analysis(
        rfp_id=rfp_id,
        analysis_json=json.dumps(payload, ensure_ascii=False),
        project_name=project.get("project_name"),
        confidence=confidence,
        status="analyzed",
    )
    return {"rfp_id": rfp_id, "status": "analyzed", **payload}


async def _stage1_parse_structure(text: str) -> dict:
    """Stage 1: 문서 구조 파악. 실패 시 빈 sections 반환."""
    truncated = select_relevant_sections(text, max_chars=40_000)
    try:
        result = await llm_client.complete_json(
            STAGE1_TOC_SYSTEM, truncated, max_tokens=2000
        )
        return result
    except Exception as exc:
        logger.warning("Stage 1 실패, 빈 섹션으로 계속 진행: %s", exc)
        return {"sections": [], "projectInfo": {}}


def _split_text_by_headers(full_text: str, sections: list[dict]) -> dict[str, str]:
    """Stage 1이 반환한 headerText를 기준으로 텍스트를 섹션별로 분할한다.

    반환 dict의 키: "{sectionNumber}:{sectionTitle}", 값: 해당 섹션 텍스트.
    요구사항 포함 섹션만 처리한다.
    헤더를 하나도 찾지 못하면 빈 dict 반환 → 호출부에서 고정 청킹으로 폴백.
    """
    req_sections = [s for s in sections if s.get("containsRequirements")]
    if not req_sections:
        return {}

    # 헤더 위치 탐색
    positions: list[tuple[int, dict]] = []
    for section in req_sections:
        header = (section.get("headerText") or "").strip()
        if not header:
            continue
        idx = full_text.find(header)
        if idx != -1:
            positions.append((idx, section))

    if not positions:
        return {}

    positions.sort(key=lambda x: x[0])

    result: dict[str, str] = {}
    for i, (start_idx, section) in enumerate(positions):
        end_idx = positions[i + 1][0] if i + 1 < len(positions) else len(full_text)
        key = f"{section.get('sectionNumber', i+1)}:{section.get('sectionTitle', '')}"
        result[key] = full_text[start_idx:end_idx]

    return result


def _chunk_text_fixed(
    text: str, chunk_size: int = 10_000, overlap: int = 500
) -> list[str]:
    """고정 크기 청킹 (헤더 기반 분할 폴백용)."""
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += chunk_size - overlap
    return chunks


async def _stage2_extract_all(section_chunks: dict[str, str], project_info: dict) -> list[dict]:
    """Stage 2: 섹션별 요구사항 추출을 병렬로 실행하고 결과를 병합한다."""
    tasks = []
    keys = list(section_chunks.keys())
    for key in keys:
        chunk = section_chunks[key]
        parts = key.split(":", 1)
        section_num = parts[0]
        section_title = parts[1] if len(parts) > 1 else key
        tasks.append(_stage2_extract_section(section_title, section_num, chunk, project_info))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_reqs: list[dict] = []
    for key, result in zip(keys, results):
        if isinstance(result, Exception):
            logger.warning("Stage 2 섹션 처리 실패 section=%s: %s", key, result)
            continue
        reqs = result.get("requirements") or []
        logger.info("Stage 2 섹션 완료: section=%s requirements=%d", key, len(reqs))
        all_reqs.extend(reqs)

    return all_reqs


async def _stage2_extract_section(
    section_title: str, section_num: str, chunk: str, project_info: dict
) -> dict:
    """단일 섹션 청크에서 요구사항을 추출한다."""
    project_context = {
        "projectName": project_info.get("projectName") or project_info.get("project_name"),
        "projectDomain": project_info.get("projectDomain") or project_info.get("project_domain"),
        "description": project_info.get("description"),
        "techStack": project_info.get("techStack") or project_info.get("tech_stack") or [],
    }
    user_message = json.dumps(
        {
            "projectContext": project_context,
            "sectionTitle": section_title,
            "sectionNumber": section_num,
            "sectionText": chunk,
            "existingReqIds": [],
        },
        ensure_ascii=False,
    )
    return await llm_client.complete_json(
        STAGE2_REQ_EXTRACT_SYSTEM, user_message, max_tokens=8000
    )


def _deduplicate_requirements(requirements: list[dict]) -> list[dict]:
    """reqId 기준으로 중복 요구사항을 제거한다 (먼저 나온 것 유지)."""
    seen: set[str] = set()
    result: list[dict] = []
    for req in requirements:
        req_id = (req.get("req_id") or req.get("reqId") or "").strip()
        if not req_id or req_id in seen:
            continue
        seen.add(req_id)
        # snake_case 정규화
        result.append({
            "req_id": req_id,
            "assignee_type": _to_list(req.get("assignee_type") or req.get("assigneeType")),
            "user_type": req.get("user_type") or req.get("userType") or [],
            "requirement_type": req.get("requirement_type") or req.get("requirementType"),
            "req_category": _normalize_req_category(req.get("req_category") or req.get("reqCategory")),
            "req_name": req.get("req_name") or req.get("reqName"),
            "req_description": req.get("req_description") or req.get("reqDescription"),
            "req_detail": req.get("req_detail") or req.get("reqDetail"),
            "notes": req.get("notes"),
            "importance": req.get("importance"),
            "priority": req.get("priority"),
            "deliverables": req.get("deliverables") or [],
            "related_req_ids": req.get("related_req_ids") or req.get("relatedReqIds") or [],
            "source_text": req.get("source_text") or req.get("sourceText"),
            "source_chunk_index": req.get("source_chunk_index"),
            "source_chunk_text": req.get("source_chunk_text"),
            "inferred_from_context": bool(
                req.get("inferred_from_context") or req.get("inferredFromContext")
            ),
        })
    return result


async def _stage3_generate_wbs(
    requirements: list[dict], project_info_raw: dict
) -> list[dict]:
    """Stage 3: 요구사항을 12개씩 배치로 나눠 순차적으로 WBS를 생성한다."""
    batch_size = 12
    all_wbs: list[dict] = []
    last_wbs_code = ""
    project_context = (
        f"프로젝트명: {project_info_raw.get('projectName') or '미상'}, "
        f"도메인: {project_info_raw.get('projectDomain') or '미상'}, "
        f"기술스택: {', '.join(project_info_raw.get('techStack') or [])}, "
        f"기간: {project_info_raw.get('estimatedDuration') or '미상'}"
    )
    total_batches = (len(requirements) + batch_size - 1) // batch_size

    for batch_idx in range(0, len(requirements), batch_size):
        batch = requirements[batch_idx : batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        last_items = all_wbs[-3:] if all_wbs else []

        user_message = json.dumps(
            {
                "projectContext": project_context,
                "lastWbsItems": last_items,
                "requirementsBatch": batch,
                "batchNumber": batch_num,
                "totalBatches": total_batches,
                "lastWbsCode": last_wbs_code,
            },
            ensure_ascii=False,
        )
        try:
            result = await llm_client.complete_json(
                STAGE3_WBS_GEN_SYSTEM, user_message, max_tokens=16000
            )
            new_wbs = _normalize_wbs(result.get("wbs") or [])
            if new_wbs:
                last_wbs_code = new_wbs[-1].get("wbs_code") or last_wbs_code
            all_wbs.extend(new_wbs)
            logger.info("Stage 3 배치 완료: batch=%d/%d wbs=%d",
                        batch_num, total_batches, len(new_wbs))
        except Exception as exc:
            logger.warning("Stage 3 배치 실패 batch=%d/%d: %s",
                           batch_num, total_batches, exc)

    return all_wbs


def _validate_analysis_result(requirements: list[dict], wbs: list[dict]) -> None:
    """분석 결과의 참조 무결성을 검증하고 문제를 경고 로그로 출력한다."""
    req_ids = {r.get("req_id") for r in requirements if r.get("req_id")}
    wbs_codes = {w.get("wbs_code") for w in wbs if w.get("wbs_code")}

    dup_req_ids = [r for r in (r.get("req_id") for r in requirements) if r]
    if len(dup_req_ids) != len(set(dup_req_ids)):
        logger.warning("reqId 중복 발견: %s", [x for x in dup_req_ids if dup_req_ids.count(x) > 1])

    for w in wbs:
        if w.get("req_id") and w["req_id"] not in req_ids:
            logger.warning("WBS reqId 참조 오류: wbs_code=%s req_id=%s",
                           w.get("wbs_code"), w["req_id"])
        for dep in w.get("depends_on") or []:
            if dep not in wbs_codes:
                logger.warning("WBS dependsOn 참조 오류: wbs_code=%s depends_on=%s",
                               w.get("wbs_code"), dep)


def _normalize_project_info(raw: dict) -> dict:
    """Stage 1 projectInfo(camelCase)를 snake_case로 정규화한다."""
    def pick(*keys):
        for k in keys:
            if raw.get(k) is not None:
                return raw[k]
        return None

    return {
        "project_name": pick("project_name", "projectName") or "",
        "project_amount": pick("project_amount", "projectAmount"),
        "client_name": pick("client_name", "clientName"),
        "project_theme": pick("project_theme", "projectTheme"),
        "description": raw.get("description"),
        "start_date": pick("start_date", "startDate"),
        "end_date": pick("end_date", "endDate"),
        "contract_type": pick("contract_type", "contractType"),
        "business_type": pick("business_type", "businessType"),
        "budget": raw.get("budget"),
        "lead_company": pick("lead_company", "leadCompany"),
        "partner_companies": pick("partner_companies", "partnerCompanies") or [],
    }


def _count_business_days(start: date, end: date) -> int:
    """주말(토·일) 제외 영업일 수. start/end 양 끝 포함."""
    if end < start:
        return 0
    total = 0
    current = start
    while current <= end:
        if current.weekday() < 5:  # 0=월 ~ 4=금
            total += 1
        current += timedelta(days=1)
    return total


def _parse_iso_date(value) -> date | None:
    """문자열/date 객체를 date로 변환. 실패하면 None."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def _add_business_days(start: date, days: int) -> date:
    """start로부터 days 영업일 후의 날짜 (start는 0번째 영업일로 카운트하지 않음).

    예: _add_business_days(금요일, 1) → 다음 월요일.
    days=0이면 start 그대로 반환.
    """
    if days <= 0:
        return start
    current = start
    added = 0
    while added < days:
        current = current + timedelta(days=1)
        if current.weekday() < 5:  # 0=월 ~ 4=금
            added += 1
    return current


# ────────────────────────────────────────────────────────────────
# 우선순위 기반 WBS 스케줄러
# ────────────────────────────────────────────────────────────────

_PHASE_WEIGHT: dict[str, int] = {
    "foundation": 4,
    "core": 3,
    "feature": 2,
    "closing": 1,
}
_CRIT_WEIGHT: dict[str, int] = {
    "blocker": 3,
    "core": 2,
    "normal": 1,
}


def _compute_fan_out(wbs: list[dict]) -> dict[str, int]:
    """각 task의 transitive descendant count를 계산한다.

    descendant가 많을수록 후속 작업에 미치는 영향이 큰 task.
    """
    # 정방향 그래프: code → [후행 code들]
    children: dict[str, list[str]] = defaultdict(list)
    codes = {w.get("wbs_code") for w in wbs if w.get("wbs_code")}
    for w in wbs:
        code = w.get("wbs_code")
        if not code:
            continue
        for dep in (w.get("depends_on") or []):
            if dep in codes:
                children[dep].append(code)  # dep가 끝나야 code가 실행 → dep의 child

    fan_out: dict[str, int] = {}
    for w in wbs:
        code = w.get("wbs_code")
        if not code:
            continue
        # BFS로 transitive descendants 카운트
        seen: set[str] = set()
        stack = list(children.get(code, []))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(children.get(cur, []))
        fan_out[code] = len(seen)
    return fan_out


def _priority_score(
    task: dict,
    fan_out: dict[str, int],
    bottleneck_roles: set[str],
) -> float:
    """task 우선순위 점수. 높을수록 먼저 배치된다.

    공식: phase(×10) + criticality(×8) + risk(×15 if high) + fan_out + bottleneck(×5)
    """
    phase = task.get("phase") or "feature"
    crit = task.get("criticality") or "normal"
    risk_high = (task.get("risk") == "high")
    bottleneck = task.get("assignee_role") in bottleneck_roles
    code = task.get("wbs_code") or ""
    return (
        _PHASE_WEIGHT.get(phase, 2) * 10
        + _CRIT_WEIGHT.get(crit, 1) * 8
        + fan_out.get(code, 0)
        + (15 if risk_high else 0)
        + (5 if bottleneck else 0)
    )


def _schedule_wbs_tasks(
    wbs: list[dict],
    role_headcounts: dict[str, int],
    project_start: date,
    project_end: date | None = None,
    pinned_codes: set[str] | None = None,
) -> dict:
    """우선순위 기반 WBS 일정 산정.

    의존성(`depends_on`)을 충족한 task 중 priority score가 높은 task부터 배치한다.
    Priority Score는 phase / criticality / risk / fan-out / resource bottleneck을 종합.

    - 같은 역할의 task는 인원 수만큼 동시 진행 가능 (다른 인원에 배정)
    - 같은 인원이 처리하는 task는 시간상 직렬
    - 의존성을 만족하지 못한 task는 score가 높아도 절대 먼저 배치 안 됨
    - 모든 일정은 영업일(월~금)만 사용

    pinned_codes에 포함된 wbs_code는 일정을 변경하지 않고 기존 dates로 role pool만 점유시킨다.
    부분 재산출(예: 추가 태스크 생성 후 후속 task만 갱신) 시 사용.

    Returns:
        {"scheduled": int, "overflow": int, "actual_end": date}
    """
    if not wbs:
        return {"scheduled": 0, "overflow": 0, "actual_end": project_start}

    pinned: set[str] = pinned_codes or set()

    # 0. 역할별 인원 풀 초기화 (각 인원의 "다음 가능 영업일")
    pool: dict[str, list[date]] = {
        role: [project_start] * max(1, count)
        for role, count in role_headcounts.items()
    }
    bottleneck_roles: set[str] = {
        role for role, count in role_headcounts.items() if count <= 1
    }

    wbs_by_code = {w["wbs_code"]: w for w in wbs if w.get("wbs_code")}
    all_codes = set(wbs_by_code.keys())

    # 1. 사전 계산: fan-out + remaining_deps
    fan_out = _compute_fan_out(wbs)
    remaining_deps: dict[str, int] = {
        code: sum(1 for d in (w.get("depends_on") or []) if d in all_codes)
        for code, w in wbs_by_code.items()
    }
    # 후행 task 인덱스 (의존성 충족 시 카운터 감소용)
    children: dict[str, list[str]] = defaultdict(list)
    for w in wbs:
        code = w.get("wbs_code")
        if not code:
            continue
        for dep in (w.get("depends_on") or []):
            if dep in all_codes:
                children[dep].append(code)

    # 2. executable queue 방식으로 배치
    completed: set[str] = set()
    scheduled_count = 0
    overflow_count = 0
    actual_end_overall = project_start
    cycle_fallback_warned = False

    # 2-pre. 핀(고정) 태스크 처리 — 일정 변경 없이 pool pre-charge + 의존성 해소
    pinned_tasks = [wbs_by_code[c] for c in pinned if c in wbs_by_code]
    pinned_tasks.sort(
        key=lambda t: _parse_iso_date(t.get("planned_end")) or project_start
    )
    for t in pinned_tasks:
        end_d = _parse_iso_date(t.get("planned_end"))
        # 일정이 있는 핀 태스크만 pool 점유 (없으면 의존성 해소만)
        if end_d:
            role = t.get("assignee_role") or "기타"
            if role not in pool:
                pool[role] = [project_start]
            next_avail = _add_business_days(end_d, 1)
            idx = min(range(len(pool[role])), key=lambda i: pool[role][i])
            if next_avail > pool[role][idx]:
                pool[role][idx] = next_avail
            if end_d > actual_end_overall:
                actual_end_overall = end_d
        completed.add(t["wbs_code"])
        # 핀 태스크가 의존하던 후행 카운터 감소
        for child_code in children.get(t["wbs_code"], []):
            if child_code in remaining_deps:
                remaining_deps[child_code] -= 1

    while len(completed) < len(wbs_by_code):
        # 2-1. dependency 만족한 미완료 task 추출
        ready_codes = [
            c for c in wbs_by_code
            if c not in completed and remaining_deps[c] == 0
        ]
        if not ready_codes:
            # deadlock — 남은 task를 임의 순서로 처리
            if not cycle_fallback_warned:
                logger.warning(
                    "[WBS-SCHEDULE] 의존성 deadlock 감지 — 남은 %d개 task를 priority 순으로 처리",
                    len(wbs_by_code) - len(completed),
                )
                cycle_fallback_warned = True
            ready_codes = [c for c in wbs_by_code if c not in completed]

        # 2-2. priority score로 정렬 (높은 순) — 동점 시 wbs_code 알파벳 순
        ready_codes.sort(
            key=lambda c: (
                -_priority_score(wbs_by_code[c], fan_out, bottleneck_roles),
                c,
            )
        )
        wbs_code = ready_codes[0]
        w = wbs_by_code[wbs_code]

        # 2-3. 배정
        role = w.get("assignee_role") or "기타"
        est_days = max(0.5, float(w.get("estimated_days") or 1))

        # 선행 task의 다음 영업일
        earliest = project_start
        for dep_code in (w.get("depends_on") or []):
            dep = wbs_by_code.get(dep_code)
            if not dep:
                continue
            dep_end = _parse_iso_date(dep.get("planned_end"))
            if dep_end:
                next_day = _add_business_days(dep_end, 1)
                if next_day > earliest:
                    earliest = next_day

        if role not in pool:
            pool[role] = [project_start]
        person_idx = min(range(len(pool[role])), key=lambda i: pool[role][i])
        actual_start = max(earliest, pool[role][person_idx])

        # 시작일이 주말이면 다음 영업일로
        while actual_start.weekday() >= 5:
            actual_start = actual_start + timedelta(days=1)

        days_to_add = max(0, int(math.ceil(est_days)) - 1)
        actual_end_task = _add_business_days(actual_start, days_to_add)

        w["planned_start"] = actual_start.isoformat()
        w["planned_end"] = actual_end_task.isoformat()
        w["planned_hours"] = round(est_days * 8, 1)

        pool[role][person_idx] = _add_business_days(actual_end_task, 1)
        completed.add(wbs_code)
        scheduled_count += 1
        if actual_end_task > actual_end_overall:
            actual_end_overall = actual_end_task
        if project_end and actual_end_task > project_end:
            overflow_count += 1

        # 2-4. 후행 task의 remaining_deps 감소
        for child_code in children.get(wbs_code, []):
            if child_code in remaining_deps:
                remaining_deps[child_code] -= 1

    return {
        "scheduled": scheduled_count,
        "overflow": overflow_count,
        "actual_end": actual_end_overall,
    }


def reschedule_wbs_after_extra_task(project_id: str, new_task_id: str) -> dict:
    """추가 태스크 생성으로 영향받는 후속 태스크들의 일정을 재산출하고 Fuseki에 반영.

    핀(고정) 대상:
      - 완료(`완료`) 상태 태스크 — 절대 변경 금지
      - 새로 추가된 태스크 본인 — 사용자가 입력한 날짜를 기준점으로 유지
      - 새 태스크의 시작일(cutoff) 이전에 완전히 끝나는 진행/미진행 태스크 — 영향 없음

    핀이 아닌 태스크는 `_schedule_wbs_tasks(pinned_codes=...)`로 재산출하여
    `planned_start` / `planned_end` / `planned_hours` 를 Fuseki에 update.

    Returns:
        {"affected": int, "skipped_completed": int, "overflow": int, "total": int}
    """
    project = sparql_repo.get_project_detail(project_id)
    if not project:
        raise ValueError(f"프로젝트를 찾을 수 없습니다: {project_id}")

    tasks = sparql_repo.list_tasks_by_project(project_id)
    if not tasks:
        return {"affected": 0, "skipped_completed": 0, "overflow": 0, "total": 0}

    roles = sparql_repo.get_project_required_roles(project_id) or []
    role_headcounts = {r["role"]: int(r["count"]) for r in roles if r.get("count")}
    if not role_headcounts:
        # 역할 정보가 없으면 task에서 추론 (각 역할 1명씩)
        role_headcounts = {
            (t.get("assignee_role") or "기타"): 1 for t in tasks
        }

    project_start = _parse_iso_date(project.get("start_date")) or date.today()
    project_end = _parse_iso_date(project.get("end_date"))

    new_task = next((t for t in tasks if t["task_id"] == new_task_id), None)
    if not new_task:
        raise ValueError(f"새 태스크를 찾을 수 없습니다: {new_task_id}")
    cutoff = _parse_iso_date(new_task.get("planned_start"))
    if not cutoff:
        # 새 태스크에 시작일이 없으면 재산출 불가
        return {"affected": 0, "skipped_completed": 0, "overflow": 0, "total": len(tasks)}

    # 핀 태스크 집합
    pinned: set[str] = set()
    skipped_completed = 0
    for t in tasks:
        code = t.get("wbs_code")
        if not code:
            continue
        if t.get("status") == "완료":
            pinned.add(code)
            skipped_completed += 1
            continue
        if t["task_id"] == new_task_id:
            pinned.add(code)
            continue
        end_d = _parse_iso_date(t.get("planned_end"))
        if end_d and end_d < cutoff:
            pinned.add(code)

    # 변경 전 일정 스냅샷 (Fuseki update를 위해)
    before: dict[str, tuple] = {
        t["wbs_code"]: (
            t.get("planned_start"), t.get("planned_end"), t.get("planned_hours"),
        )
        for t in tasks if t.get("wbs_code")
    }

    result = _schedule_wbs_tasks(
        wbs=tasks,
        role_headcounts=role_headcounts,
        project_start=project_start,
        project_end=project_end,
        pinned_codes=pinned,
    )

    # 변경된 태스크만 Fuseki update
    affected = 0
    for t in tasks:
        code = t.get("wbs_code")
        if not code or code in pinned:
            continue
        new_start = t.get("planned_start")
        new_end = t.get("planned_end")
        new_hours = t.get("planned_hours")
        if before.get(code) == (new_start, new_end, new_hours):
            continue  # 일정이 동일하면 update skip
        try:
            sparql_repo.update_task_schedule(
                task_id=t["task_id"],
                planned_start=new_start,
                planned_end=new_end,
                planned_hours=float(new_hours) if new_hours is not None else None,
            )
            affected += 1
        except Exception as e:
            logger.warning(
                "[RESCHEDULE] task update 실패: task_id=%s err=%s",
                t["task_id"], e,
            )

    return {
        "affected": affected,
        "skipped_completed": skipped_completed,
        "overflow": result["overflow"],
        "total": len(tasks),
    }


def _aggregate_required_roles(
    wbs: list[dict],
    project_start: date | str | None = None,
    project_end: date | str | None = None,
    utilization_rate: float = 0.8,
    parallel_buffer: float = 1.2,
) -> list[dict]:
    """WBS 기반 역할별 필요 인원을 산정한다.

    공식:
        effective_days = project_biz_days × utilization_rate
        raw_count      = role.total_days / effective_days
        head_count     = max(1, ceil(raw_count × parallel_buffer))

    프로젝트 기간을 모르면(또는 영업일=0) head_count는 1로 fallback.
    """
    start = _parse_iso_date(project_start)
    end = _parse_iso_date(project_end)
    total_biz_days = _count_business_days(start, end) if (start and end) else 0

    # 역할별 집계
    role_data: dict[str, dict] = defaultdict(lambda: {
        "total_days": 0.0,
        "total_hours": 0.0,
        "task_count": 0,
        "skills": set(),
    })
    for item in wbs:
        role = item.get("assignee_role")
        if not role:
            continue
        rd = role_data[role]
        rd["total_days"] += float(item.get("estimated_days") or 0)
        rd["total_hours"] += float(item.get("planned_hours") or 0)
        rd["task_count"] += 1
        for skill in item.get("required_skills") or []:
            rd["skills"].add(skill)

    # 산정
    result: list[dict] = []
    effective_days = total_biz_days * utilization_rate if total_biz_days else 0

    for role, data in sorted(role_data.items()):
        total_days = data["total_days"]

        if effective_days > 0:
            raw_count = total_days / effective_days
            head_count = max(1, math.ceil(raw_count * parallel_buffer))
        else:
            raw_count = 0.0
            head_count = 1  # 프로젝트 기간 모를 때 fallback

        breakdown = {
            "project_biz_days": total_biz_days,
            "utilization_rate": utilization_rate,
            "effective_days": round(effective_days, 1),
            "parallel_buffer": parallel_buffer,
            "raw_count": round(raw_count, 2),
        }

        result.append({
            "role": role,
            "count": head_count,
            "mm": round(total_days / 22, 1),
            "total_days": round(total_days, 1),
            "total_hours": round(data["total_hours"], 1),
            "task_count": data["task_count"],
            "skills": sorted(data["skills"]),
            "breakdown": breakdown,
        })

    return result


def _calc_confidence(
    requirements: list[dict], wbs: list[dict], project: dict | None = None
) -> tuple[float, dict]:
    """추출 품질 신호 기반 신뢰도 점수.

    해석:
    - 1.0에 가까우면 분석을 그대로 활용 가능
    - 0.5 이하면 재실행 또는 수동 보완 권장

    가중치: 프로젝트(20%) + 요구사항(30%) + WBS(50%)
    """
    # ── 1. 프로젝트 추출 품질 (project_extraction) ─────────────
    # 필수: project_name + description (있어야 baseline 0.5)
    # 보조 10개 필드 채움 시 각 +0.05 (최대 +0.5)
    # 필수 누락 → 0점 (RFP 인식 실패 신호)
    project_score = 0.0
    if project:
        required = ["project_name", "description"]
        has_required = all(
            project.get(f) and str(project[f]).strip() for f in required
        )
        if has_required:
            project_score = 0.5
            bonus_fields = [
                "project_amount", "client_name", "project_theme",
                "start_date", "end_date", "budget",
                "contract_type", "business_type",
                "lead_company", "partner_companies",
            ]
            for f in bonus_fields:
                v = project.get(f)
                if v and v != [] and str(v).strip():
                    project_score += 0.05
            project_score = round(min(project_score, 1.0), 2)

    # ── 2. 요구사항 추출 품질 (requirements_classification) ────
    # 요구사항별로 (req_description, source_text, assignee_type) 채움 비율의 평균
    # 빈 description/sourceText가 많으면 LLM이 청크 해석에 실패한 신호
    if requirements:
        per_req_scores: list[float] = []
        for r in requirements:
            filled = 0
            if r.get("req_description") and str(r["req_description"]).strip():
                filled += 1
            if r.get("source_text") and str(r["source_text"]).strip():
                filled += 1
            if r.get("assignee_type"):  # 빈 list가 아닌 경우
                filled += 1
            per_req_scores.append(filled / 3)
        req_score = round(sum(per_req_scores) / len(per_req_scores), 2)
    else:
        req_score = 0.0

    # ── 3. WBS 채움 품질 (wbs_accuracy) ─────────────────────────
    # LLM이 task_name, task_description, estimated_days를 모두 채운 비율.
    # task_name이 fallback 패턴("[devType] reqName")이면 LLM이 응답 못 한 것.
    if wbs:
        complete = 0
        for w in wbs:
            name = (w.get("task_name") or "").strip()
            desc = (w.get("task_description") or "").strip() if w.get("task_description") else ""
            days = w.get("estimated_days")
            is_fallback_name = name.startswith("[") and "] " in name
            if name and not is_fallback_name and desc and days:
                complete += 1
        wbs_score = round(complete / len(wbs), 2)
    else:
        wbs_score = 0.0

    # ── 가중 평균 ────────────────────────────────────────────────
    overall = round(
        project_score * 0.2 + req_score * 0.3 + wbs_score * 0.5,
        2,
    )

    breakdown = {
        "project_extraction": project_score,
        "requirements_classification": req_score,
        "wbs_accuracy": wbs_score,
    }
    return overall, breakdown
