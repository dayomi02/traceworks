import asyncio
import json
import logging
from collections import defaultdict

from app.core.interpreter import llm_client
from app.db import sparql_repo
from app.db.sparql_repo import PREFIX
from app.db import fuseki

logger = logging.getLogger(__name__)

_INSIGHT_SYSTEM = """\
당신은 IT 프로젝트 관리 전문가입니다.
아래 프로젝트 분석 데이터를 바탕으로 프로젝트 관리자에게 전달할 제언을 작성하세요.
- 한국어로 1~2문장
- 구체적인 수치(역할명, 건수, 시간 등)를 반드시 포함
- 조치 방향을 간결하게 제시
- JSON 없이 텍스트만 반환"""


def _q(body: str) -> list[dict]:
    return fuseki.bindings(fuseki.query_safe(PREFIX + body))


def _short_name(name: str | None) -> str:
    """공백 정리된 이름을 반환. 빈 입력은 빈 문자열."""
    if not name:
        return ""
    return str(name).strip()


# ──────────────────────────────────────────────────────────────
# 1. 역할별 병목
# ──────────────────────────────────────────────────────────────

def _detect_role_bottleneck(project_id: str) -> list[dict]:
    rows = _q(f"""
SELECT ?role
       (COUNT(?task) AS ?taskCount)
       (AVG(?progress) AS ?avgProgress)
       (SUM(?hours) AS ?totalHours)
WHERE {{
  ?proj pm:projectId "{project_id}" ; pm:hasTask ?task .
  ?task pm:assigneeRole ?role ;
        pm:progressPercent ?progress ;
        pm:plannedHours ?hours ;
        pm:taskStatus ?status .
  FILTER(?status != "완료")
}}
GROUP BY ?role
""")
    results = []
    for r in rows:
        task_count = int(r.get("taskCount") or 0)
        avg_progress = float(r.get("avgProgress") or 0)
        total_hours = float(r.get("totalHours") or 0)
        if task_count < 2:
            continue
        if avg_progress < 15:
            severity = "critical"
        elif avg_progress < 30:
            severity = "warning"
        else:
            continue
        results.append({
            "role": r["role"],
            "task_count": task_count,
            "avg_progress": round(avg_progress, 1),
            "total_hours": round(total_hours, 1),
            "severity": severity,
        })
    return results


# ──────────────────────────────────────────────────────────────
# 2. 요구사항 미구현 감지
# ──────────────────────────────────────────────────────────────

def _detect_unimplemented_requirements(project_id: str) -> list[dict]:
    rows = _q(f"""
SELECT ?reqId ?reqName ?reqPriority
WHERE {{
  ?req pm:requirementStatus "APPROVED" ;
       pm:requirementId ?reqId ;
       pm:requirementName ?reqName ;
       pm:relatedToProject ?proj .
  OPTIONAL {{ ?req pm:requirementPriority ?reqPriority . }}
  ?proj pm:projectId "{project_id}" .
  FILTER NOT EXISTS {{ ?task pm:implementsRequirement ?req }}
}}
""")
    if not rows:
        return []
    has_high = any(r.get("reqPriority") in ("HIGH", "CRITICAL") for r in rows)
    return [{
        "items": [{"req_id": r["reqId"], "req_name": r.get("reqName"), "priority": r.get("reqPriority")} for r in rows],
        "count": len(rows),
        "has_high_priority": has_high,
        "severity": "critical" if has_high else "warning",
    }]


# ──────────────────────────────────────────────────────────────
# 3. 의존성 연쇄 지연 위험
# ──────────────────────────────────────────────────────────────

def _detect_dependency_chain_risk(project_id: str) -> list[dict]:
    rows = _q(f"""
SELECT ?rootTaskId ?rootTaskName ?rootStatus
       ?blockedTaskId ?blockedTaskName ?blockedRole
WHERE {{
  ?proj pm:projectId "{project_id}" ; pm:hasTask ?root .
  ?root pm:taskId ?rootTaskId ;
        pm:taskName ?rootTaskName ;
        pm:taskStatus ?rootStatus .
  FILTER(?rootStatus = "미진행")
  ?blocked pm:dependsOn+ ?root ;
           pm:taskId ?blockedTaskId ;
           pm:taskName ?blockedTaskName ;
           pm:assigneeRole ?blockedRole ;
           pm:taskStatus ?blockedStatus .
  FILTER(?blockedStatus != "완료")
}}
""")
    # 루트 태스크별로 블록된 태스크 집계
    chain: dict[str, dict] = {}
    for r in rows:
        root_id = r["rootTaskId"]
        if root_id not in chain:
            chain[root_id] = {
                "root_task_id": root_id,
                "root_task_name": r["rootTaskName"],
                "root_status": r["rootStatus"],
                "blocked": [],
            }
        chain[root_id]["blocked"].append({
            "task_id": r["blockedTaskId"],
            "task_name": r["blockedTaskName"],
            "role": r.get("blockedRole"),
        })

    results = []
    for item in chain.values():
        blocked_count = len(item["blocked"])
        if blocked_count < 2:
            continue
        severity = "critical" if blocked_count >= 3 else "warning"
        item["blocked_count"] = blocked_count
        item["severity"] = severity
        results.append(item)
    return results


# ──────────────────────────────────────────────────────────────
# 4. 멀티 프로젝트 인력 과부하
# ──────────────────────────────────────────────────────────────

def _detect_overloaded_persons(project_id: str) -> list[dict]:
    rows = _q(f"""
SELECT ?personId ?personName
       (COUNT(DISTINCT ?otherProj) AS ?projectCount)
       (SUM(?hours) AS ?totalHours)
WHERE {{
  ?proj pm:projectId "{project_id}" .
  ?person pm:participatesIn ?proj ;
          pm:personId ?personId ;
          pm:personName ?personName ;
          pm:participatesIn ?otherProj .
  ?task pm:assignedTo ?person ;
        pm:taskStatus "진행" ;
        pm:plannedHours ?hours .
}}
GROUP BY ?personId ?personName
""")
    results = []
    for r in rows:
        total_hours = float(r.get("totalHours") or 0)
        project_count = int(r.get("projectCount") or 0)
        if total_hours <= 40 and project_count <= 2:
            continue
        severity = "critical" if (total_hours > 60 or project_count > 3) else "warning"
        results.append({
            "person_id": r["personId"],
            "person_name": r["personName"],
            "project_count": project_count,
            "total_hours": round(total_hours, 1),
            "severity": severity,
        })
    return results


# ──────────────────────────────────────────────────────────────
# 5. 인력-스킬 불일치
# ──────────────────────────────────────────────────────────────

def _detect_skill_mismatch(project_id: str) -> list[dict]:
    rows = _q(f"""
SELECT ?taskId ?taskName ?requiredSkill ?personName
WHERE {{
  ?proj pm:projectId "{project_id}" ; pm:hasTask ?task .
  ?task pm:taskId ?taskId ;
        pm:taskName ?taskName ;
        pm:requiresSkill ?skill ;
        pm:assignedTo ?person ;
        pm:taskStatus ?status .
  ?skill pm:skillName ?requiredSkill .
  ?person pm:personName ?personName .
  FILTER(?status != "완료")
  FILTER NOT EXISTS {{
    ?person pm:hasSkill ?ps .
    ?ps pm:skillName ?requiredSkill .
  }}
}}
""")
    if not rows:
        return []
    return [{
        "items": [{"task_id": r["taskId"], "task_name": r.get("taskName"), "person_name": r.get("personName"), "skill": r.get("requiredSkill")} for r in rows],
        "count": len(rows),
        "severity": "warning",
    }]


# ──────────────────────────────────────────────────────────────
# LLM 자연어 변환
# ──────────────────────────────────────────────────────────────

async def _to_message(data: dict) -> str:
    try:
        return await llm_client.complete(_INSIGHT_SYSTEM, json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.warning("제언 LLM 변환 실패: %s", e)
        return ""


# ──────────────────────────────────────────────────────────────
# 메인 진입점
# ──────────────────────────────────────────────────────────────

async def generate_insights(project_id: str) -> list[dict]:
    # SPARQL 분석 (동기, 순차)
    bottlenecks = _detect_role_bottleneck(project_id)
    unimplemented = _detect_unimplemented_requirements(project_id)
    dep_risks = _detect_dependency_chain_risk(project_id)
    overloaded = _detect_overloaded_persons(project_id)
    skill_gaps = _detect_skill_mismatch(project_id)

    pending: list[tuple[str, str, str, list[str], dict]] = []
    # (type, title, severity, affected_entities, raw_data)

    for b in bottlenecks:
        pending.append((
            "role_bottleneck",
            f"{b['role']} 파트 일정 지연 위험이 있어 일정을 확인하세요.",
            b["severity"],
            [],
            b,
        ))

    for u in unimplemented:
        pending.append((
            "unimplemented_requirement",
            f"구현되지 않은 요구사항이 {u['count']}건 있어 확인이 필요합니다.",
            u["severity"],
            [_short_name(i.get("req_name") or i.get("req_id")) for i in u["items"]],
            u,
        ))

    for d in dep_risks:
        pending.append((
            "dependency_chain_risk",
            f"'{d['root_task_name']}' 작업이 후속 {d['blocked_count']}개 작업의 진행을 막고 있어 조치가 필요합니다.",
            d["severity"],
            [_short_name(b.get("task_name") or b.get("task_id")) for b in d["blocked"]],
            d,
        ))

    for o in overloaded:
        pending.append((
            "person_overload",
            f"{o['person_name']} 님의 업무 부하가 높아 일정 재조정이 필요합니다.",
            o["severity"],
            [_short_name(o.get("person_name") or o.get("person_id"))],
            o,
        ))

    for s in skill_gaps:
        pending.append((
            "skill_mismatch",
            f"담당자의 보유 스킬과 작업 요구 스킬이 일치하지 않는 항목이 {s['count']}건 있습니다.",
            s["severity"],
            [_short_name(i.get("task_name") or i.get("task_id")) for i in s["items"]],
            s,
        ))

    if not pending:
        return []

    # LLM 변환 병렬 실행
    messages = await asyncio.gather(*[_to_message(p[4]) for p in pending])

    results = []
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    for (type_, title, severity, entities, _), message in zip(pending, messages):
        results.append({
            "type": type_,
            "severity": severity,
            "title": title,
            "message": message,
            "affected_entities": entities,
        })

    results.sort(key=lambda x: severity_order.get(x["severity"], 9))
    return results
