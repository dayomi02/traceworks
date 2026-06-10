from datetime import UTC, datetime

from app.core.exceptions import ProjectNotFound
from app.core.interpreter import llm_client
from app.core.interpreter.prompts import STAFFING_SKILL_EXTRACTION_SYSTEM
from app.db import sparql_repo

MAX_CAPACITY = 3.0
REASON_TOP_SKILLS = 5

_SAMPLE_CANDIDATES: list[dict] = [
    {
        "rank": 1, "person_id": "PM001", "person_name": "홍길동",
        "role": "PM", "grade": "수석",
        "similarity_score": 0.91, "availability_score": 0.85,
        "matched_skills": [
            {"skill": "프로젝트 관리", "proficiency": 0.95},
            {"skill": "리스크 관리", "proficiency": 0.90},
            {"skill": "일정 관리", "proficiency": 0.88},
        ],
        "reason": "프로젝트 관리(0.95)·리스크 관리(0.90)·일정 관리(0.88) 역량 보유. 가용성 0.85.",
    },
    {
        "rank": 2, "person_id": "PL001", "person_name": "이수연",
        "role": "기획자", "grade": "선임",
        "similarity_score": 0.88, "availability_score": 0.90,
        "matched_skills": [
            {"skill": "요구사항 분석", "proficiency": 0.92},
            {"skill": "UX 기획", "proficiency": 0.87},
            {"skill": "화면 정의서", "proficiency": 0.85},
        ],
        "reason": "요구사항 분석(0.92)·UX 기획(0.87)·화면 정의서(0.85) 역량 보유. 가용성 0.90.",
    },
    {
        "rank": 3, "person_id": "BE001", "person_name": "김철수",
        "role": "백엔드", "grade": "수석",
        "similarity_score": 0.93, "availability_score": 0.75,
        "matched_skills": [
            {"skill": "Spring Boot", "proficiency": 0.95},
            {"skill": "Java", "proficiency": 0.93},
            {"skill": "REST API", "proficiency": 0.90},
        ],
        "reason": "Spring Boot(0.95)·Java(0.93)·REST API(0.90) 역량 보유. 가용성 0.75.",
    },
    {
        "rank": 4, "person_id": "BE003", "person_name": "정다은",
        "role": "백엔드", "grade": "선임",
        "similarity_score": 0.85, "availability_score": 0.95,
        "matched_skills": [
            {"skill": "FastAPI", "proficiency": 0.88},
            {"skill": "Python", "proficiency": 0.90},
            {"skill": "PostgreSQL", "proficiency": 0.82},
        ],
        "reason": "FastAPI(0.88)·Python(0.90)·PostgreSQL(0.82) 역량 보유. 가용성 0.95.",
    },
    {
        "rank": 5, "person_id": "FE001", "person_name": "최예린",
        "role": "프론트엔드", "grade": "선임",
        "similarity_score": 0.90, "availability_score": 0.80,
        "matched_skills": [
            {"skill": "React", "proficiency": 0.95},
            {"skill": "TypeScript", "proficiency": 0.92},
            {"skill": "Next.js", "proficiency": 0.88},
        ],
        "reason": "React(0.95)·TypeScript(0.92)·Next.js(0.88) 역량 보유. 가용성 0.80.",
    }
    # ,
    # {
    #     "rank": 6, "person_id": "FE002", "person_name": "한승우",
    #     "role": "프론트엔드", "grade": "주임",
    #     "similarity_score": 0.82, "availability_score": 1.00,
    #     "matched_skills": [
    #         {"skill": "Vue.js", "proficiency": 0.88},
    #         {"skill": "JavaScript", "proficiency": 0.85},
    #         {"skill": "CSS/SCSS", "proficiency": 0.80},
    #     ],
    #     "reason": "Vue.js(0.88)·JavaScript(0.85)·CSS/SCSS(0.80) 역량 보유. 가용성 1.00.",
    # },
    # {
    #     "rank": 7, "person_id": "DBA001", "person_name": "오현석",
    #     "role": "DBA", "grade": "수석",
    #     "similarity_score": 0.87, "availability_score": 0.70,
    #     "matched_skills": [
    #         {"skill": "Oracle", "proficiency": 0.93},
    #         {"skill": "쿼리 최적화", "proficiency": 0.90},
    #         {"skill": "DB 설계", "proficiency": 0.88},
    #     ],
    #     "reason": "Oracle(0.93)·쿼리 최적화(0.90)·DB 설계(0.88) 역량 보유. 가용성 0.70.",
    # },
    # {
    #     "rank": 8, "person_id": "QA001", "person_name": "윤서연",
    #     "role": "QA", "grade": "선임",
    #     "similarity_score": 0.86, "availability_score": 0.88,
    #     "matched_skills": [
    #         {"skill": "테스트 케이스 설계", "proficiency": 0.92},
    #         {"skill": "자동화 테스트", "proficiency": 0.85},
    #         {"skill": "Selenium", "proficiency": 0.80},
    #     ],
    #     "reason": "테스트 케이스 설계(0.92)·자동화 테스트(0.85)·Selenium(0.80) 역량 보유. 가용성 0.88.",
    # },
    # {
    #     "rank": 9, "person_id": "INFRA001", "person_name": "임태양",
    #     "role": "인프라", "grade": "선임",
    #     "similarity_score": 0.84, "availability_score": 0.92,
    #     "matched_skills": [
    #         {"skill": "Kubernetes", "proficiency": 0.90},
    #         {"skill": "Docker", "proficiency": 0.92},
    #         {"skill": "CI/CD", "proficiency": 0.87},
    #     ],
    #     "reason": "Kubernetes(0.90)·Docker(0.92)·CI/CD(0.87) 역량 보유. 가용성 0.92.",
    # },
    # {
    #     "rank": 10, "person_id": "DS001", "person_name": "강나현",
    #     "role": "디자이너", "grade": "선임",
    #     "similarity_score": 0.89, "availability_score": 0.83,
    #     "matched_skills": [
    #         {"skill": "Figma", "proficiency": 0.95},
    #         {"skill": "UI 디자인", "proficiency": 0.90},
    #         {"skill": "디자인 시스템", "proficiency": 0.85},
    #     ],
    #     "reason": "Figma(0.95)·UI 디자인(0.90)·디자인 시스템(0.85) 역량 보유. 가용성 0.83.",
    # },
]


def _normalize(name: str) -> str:
    return name.strip().lower()


def compute_load_availability(active_tasks: int, avg_progress: float | None) -> float:
    progress = (avg_progress or 0) / 100.0
    load = active_tasks * max(0.0, 1.0 - progress)
    return round(max(0.0, 1.0 - load / MAX_CAPACITY), 2)


async def _extract_required_skills(profile: dict) -> list[str]:
    user = (
        f"tech stack: {', '.join(profile['tech_stack']) or '-'}\n"
        f"domain: {profile.get('domain') or '-'}\n"
        f"difficulty: {profile.get('difficulty') or '-'}"
    )
    payload = await llm_client.complete_json(STAFFING_SKILL_EXTRACTION_SYSTEM, user)
    skills = payload.get("required_skills") or []
    cleaned = [s.strip() for s in skills if isinstance(s, str) and s.strip()]
    if cleaned:
        return cleaned
    # Fallback: techStack 원소 그대로 사용
    return list(profile["tech_stack"])


def _similarity(person_skills: list[dict], required: list[str]) -> tuple[float, list[dict]]:
    required_set = {_normalize(r) for r in required}
    matched: list[dict] = []
    for s in person_skills:
        if _normalize(s["name"]) in required_set:
            matched.append({"skill": s["name"], "proficiency": float(s["proficiency"])})
    if not matched or not required:
        return 0.0, matched
    score = sum(m["proficiency"] for m in matched) / len(required)
    return round(score, 2), matched


def _build_reason(person: dict, matched: list[dict]) -> str:
    if not matched:
        return "매칭된 역량 없음."
    sorted_matched = sorted(matched, key=lambda m: m["proficiency"], reverse=True)
    head = sorted_matched[:REASON_TOP_SKILLS]
    skill_str = "·".join(f"{m['skill']}({m['proficiency']:.2f})" for m in head)
    tail = len(sorted_matched) - len(head)
    if tail > 0:
        skill_str += f" 외 {tail}건"
    avail = person.get("availability_score")
    avail_str = f"{float(avail):.2f}" if avail is not None else "정보 없음"
    return f"{skill_str} 역량 보유. " #가용성 {avail_str}."


def _rank_candidates(persons: list[dict], required: list[str]) -> list[dict]:
    scored = []
    for person in persons:
        similarity, matched = _similarity(person.get("skills", []), required)
        if similarity <= 0:
            continue
        scored.append({
            "person_id": person["person_id"],
            "person_name": person["person_name"],
            "role": person.get("role"),
            "grade": person.get("grade"),
            "similarity_score": similarity,
            "availability_score": person.get("availability_score"),
            "synergy_score": person.get("synergy_score") or 0.0,
            "matched_skills": matched,
            "reason": _build_reason(person, matched),
        })

    scored.sort(
        key=lambda x: (
            -x["similarity_score"],
            -(x["availability_score"] or 0.0),
            -(x["synergy_score"] or 0.0),
            x["person_id"],
        )
    )

    for rank, item in enumerate(scored, start=1):
        item["rank"] = rank
        item.pop("synergy_score", None)
    return scored


async def _resolve_required_skills_for_role(
    role: str | None,
    required_roles_db: list[dict],
    profile: dict,
) -> list[str]:
    """역할별 필요 스킬 결정 — ontology의 required_roles 우선, 없으면 LLM fallback.

    1순위: pm:RequiredRole에 저장된 해당 role의 requiredSkill 목록 (RFP 분석 결과)
    2순위: project_id 전체의 모든 RequiredRole 스킬 합집합 (역할 지정 안 된 경우)
    3순위: LLM이 profile(tech_stack/domain/difficulty)에서 추출 (레거시 호환)
    """
    if role:
        match = next((r for r in required_roles_db if r["role"] == role), None)
        if match and match.get("skills"):
            return match["skills"]

    # 역할 매칭 안 됐거나 role=None이면 모든 역할의 스킬 합집합 시도
    if required_roles_db:
        merged: list[str] = []
        seen: set[str] = set()
        for rr in required_roles_db:
            for s in rr.get("skills") or []:
                if s not in seen:
                    merged.append(s)
                    seen.add(s)
        if merged:
            return merged

    # 최종 fallback: LLM
    return await _extract_required_skills(profile)


async def recommend_staff(
    project_id: str,
    top_k: int | None = None,
    persist: bool = False,
) -> list[dict]:
    profile = sparql_repo.get_project_profile(project_id)
    if profile is None:
        raise ProjectNotFound(project_id)

    required_roles_db = sparql_repo.get_project_required_roles(project_id)
    required = await _resolve_required_skills_for_role(
        role=None, required_roles_db=required_roles_db, profile=profile,
    )

    persons = sparql_repo.list_persons_for_matching()
    ranked = _rank_candidates(persons, required)

    if top_k is not None:
        ranked = ranked[:top_k]

    if not ranked:
        sample = _SAMPLE_CANDIDATES[:top_k] if top_k is not None else _SAMPLE_CANDIDATES
        return [dict(c, is_sample=True) for c in sample]

    if persist and ranked:
        created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        sparql_repo.insert_recommendations(project_id, ranked, created_at)

    return ranked


async def recommend_staff_by_role(
    project_id: str,
    role_headcounts: list[dict],
    top_k: int | None = None,
    persist: bool = False,
) -> dict:
    profile = sparql_repo.get_project_profile(project_id)
    if profile is None:
        raise ProjectNotFound(project_id)

    required_roles_db = sparql_repo.get_project_required_roles(project_id)
    persons = sparql_repo.list_persons_for_matching()

    by_role = []
    all_ranked: list[dict] = []
    total_required = sum(rh["count"] for rh in role_headcounts)

    for rh in role_headcounts:
        role = rh["role"]
        count = rh["count"]

        # 역할별 필요 스킬: ontology의 RequiredRole 우선, 없으면 LLM fallback
        required = await _resolve_required_skills_for_role(
            role=role, required_roles_db=required_roles_db, profile=profile,
        )

        role_persons = [p for p in persons if (p.get("role") or "").lower() == role.lower()]
        ranked = _rank_candidates(role_persons, required)
        limit = top_k if top_k is not None else count * 3
        candidates = ranked[:limit]
        for c in candidates:
            c["role"] = role

        if not candidates:
            sample_pool = [c for c in _SAMPLE_CANDIDATES if (c.get("role") or "").lower() == role.lower()]
            if not sample_pool:
                sample_pool = _SAMPLE_CANDIDATES
            candidates = [dict(c, role=role, is_sample=True) for c in sample_pool[:limit]]

        by_role.append({
            "role": role,
            "required_count": count,
            "candidates": candidates,
        })
        all_ranked.extend(candidates)

    if persist and all_ranked:
        created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        sparql_repo.insert_recommendations(project_id, all_ranked, created_at)

    return {"by_role": by_role, "total_required": total_required}


def assign_staff(project_id: str, assignments: list[dict]) -> dict:
    profile = sparql_repo.get_project_profile(project_id)
    if profile is None:
        raise ProjectNotFound(project_id)

    created_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    # 1) Fuseki에 StaffingRecommendation 트리플 저장
    ranked = [
        {
            "rank": idx + 1,
            "person_id": a["person_id"],
            "person_name": a.get("person_name", ""),
            "similarity_score": 1.0,
            "matched_skills": [],
            "reason": "수동 배정",
            "role": a["role"],
        }
        for idx, a in enumerate(assignments)
    ]
    sparql_repo.insert_recommendations(project_id, ranked, created_at)

    # 2) 역할별 WBS 태스크에 담당자 자동 배정 + 상태 "미진행" 전환
    wbs_assigned = sparql_repo.assign_wbs_by_role(project_id, assignments)

    return {
        "project_id": project_id,
        "assigned_count": len(assignments),
        "wbs_tasks_assigned": wbs_assigned,
    }
