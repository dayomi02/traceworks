"""SPARQLWrapper JSON 응답 형식 샘플 — Fuseki 모킹용.

실제 SPARQLWrapper 응답 구조:
    {
      "head": {"vars": [...]},
      "results": {"bindings": [{"var": {"type": "literal", "value": "...", "datatype": "..."}, ...}]}
    }
"""

XSD = "http://www.w3.org/2001/XMLSchema#"


def _lit(value: str, datatype: str | None = None) -> dict:
    node: dict = {"type": "literal", "value": value}
    if datatype:
        node["datatype"] = datatype
    return node


def _str(value: str) -> dict:
    return _lit(value)


def _int(value: int) -> dict:
    return _lit(str(value), f"{XSD}integer")


def _dec(value: float) -> dict:
    return _lit(str(value), f"{XSD}decimal")


def _date(value: str) -> dict:
    return _lit(value, f"{XSD}date")


def wrap(bindings: list[dict]) -> dict:
    vars_set: set[str] = set()
    for row in bindings:
        vars_set.update(row.keys())
    return {
        "head": {"vars": sorted(vars_set)},
        "results": {"bindings": bindings},
    }


# ── list_projects: Pass 1 ──────────────────────────────────────
LIST_PROJECTS_BASE = wrap([
    {
        "projectId": _str("PRJ001"),
        "projectName": _str("페이플로우 v2"),
        "domain": _str("핀테크"),
        "status": _str("ACTIVE"),
    },
    {
        "projectId": _str("PRJ002"),
        "projectName": _str("마케팅 애널리틱스 대시보드"),
        "status": _str("PLANNING"),
    },
])

# ── list_projects: Pass 2 (task aggregate) ────────────────────
LIST_PROJECTS_AGG = wrap([
    {"projectId": _str("PRJ001"), "progress": _int(55), "planned": _dec(40), "status": _str("IN_PROGRESS")},
    {"projectId": _str("PRJ001"), "progress": _int(10), "planned": _dec(56), "status": _str("TODO")},
    {"projectId": _str("PRJ001"), "progress": _int(70), "planned": _dec(64), "status": _str("IN_PROGRESS")},
    {"projectId": _str("PRJ001"), "progress": _int(80), "planned": _dec(32), "status": _str("REVIEW")},
    {"projectId": _str("PRJ001"), "progress": _int(0),  "planned": _dec(24), "status": _str("TODO")},
])

# ── /projects/PRJ001/wbs ──────────────────────────────────────
WBS_PRJ001 = wrap([
    {
        "taskId": _str("T001"),
        "wbsCode": _str("1.0"),
        "taskName": _str("로그인 화면 UI 구현"),
        "progress": _int(55),
        "status": _str("IN_PROGRESS"),
        "assigneeName": _str("김태양"),
        "dueDate": _date("2025-04-25"),
        "plannedHours": _dec(40),
        "actualHours": _dec(24),
    },
    {
        "taskId": _str("T002"),
        "wbsCode": _str("2.0"),
        "taskName": _str("결제 API 연동"),
        "progress": _int(10),
        "status": _str("TODO"),
        "plannedHours": _dec(56),
    },
])

# ── /tasks/T001 — multi-row (sourceFile cartesian) ────────────
TASK_T001 = wrap([
    {
        "taskName": _str("로그인 화면 UI 구현"),
        "wbsCode": _str("1.0"),
        "status": _str("IN_PROGRESS"),
        "progress": _int(55),
        "plannedHours": _dec(40),
        "actualHours": _dec(24),
        "dueDate": _date("2025-04-25"),
        "assigneeId": _str("P003"),
        "assigneeName": _str("김태양"),
        "sourceFile": _str("src/screens/auth/LoginScreen.tsx"),
    },
    {
        "taskName": _str("로그인 화면 UI 구현"),
        "wbsCode": _str("1.0"),
        "status": _str("IN_PROGRESS"),
        "progress": _int(55),
        "plannedHours": _dec(40),
        "actualHours": _dec(24),
        "dueDate": _date("2025-04-25"),
        "assigneeId": _str("P003"),
        "assigneeName": _str("김태양"),
        "sourceFile": _str("src/components/auth/LoginForm.tsx"),
    },
    {
        "taskName": _str("로그인 화면 UI 구현"),
        "wbsCode": _str("1.0"),
        "status": _str("IN_PROGRESS"),
        "progress": _int(55),
        "plannedHours": _dec(40),
        "actualHours": _dec(24),
        "dueDate": _date("2025-04-25"),
        "assigneeId": _str("P003"),
        "assigneeName": _str("김태양"),
        "sourceFile": _str("src/components/auth/SocialLoginButton.tsx"),
    },
])

TASK_EMPTY = wrap([])

# ── /persons ──────────────────────────────────────────────────
LIST_PERSONS = wrap([
    {"personId": _str("P001"), "personName": _str("박지수"), "role": _str("PM"),
     "skillName": _str("프로젝트 매니지먼트"), "proficiency": _dec(0.88)},
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("React"), "proficiency": _dec(0.91)},
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("TypeScript"), "proficiency": _dec(0.85)},
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("React Native"), "proficiency": _dec(0.90)},
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("핀테크 도메인"), "proficiency": _dec(0.75)},
])

# ── /persons/P003: pass 1 (person+skills) ─────────────────────
PERSON_P003 = wrap([
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("React"), "proficiency": _dec(0.91)},
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("TypeScript"), "proficiency": _dec(0.85)},
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("React Native"), "proficiency": _dec(0.90)},
    {"personId": _str("P003"), "personName": _str("김태양"), "role": _str("프론트엔드 개발자"),
     "skillName": _str("핀테크 도메인"), "proficiency": _dec(0.75)},
])

# ── /persons/P003: pass 2 (participatesIn) ────────────────────
PERSON_P003_PROJECTS = wrap([
    {"projectId": _str("PRJ001"), "projectName": _str("페이플로우 v2")},
])

PERSON_EMPTY = wrap([])

# ──────────────────────────────────────────────────────────────
# Phase 5 — 추천/가용성
# ──────────────────────────────────────────────────────────────

PROJECT_PROFILE_PRJ002 = wrap([
    {"projectName": _str("마케팅 애널리틱스 대시보드"),
     "domain": _str("데이터 애널리틱스"), "difficulty": _str("MEDIUM"),
     "techStack": _str("React")},
    {"projectName": _str("마케팅 애널리틱스 대시보드"),
     "domain": _str("데이터 애널리틱스"), "difficulty": _str("MEDIUM"),
     "techStack": _str("TypeScript")},
    {"projectName": _str("마케팅 애널리틱스 대시보드"),
     "domain": _str("데이터 애널리틱스"), "difficulty": _str("MEDIUM"),
     "techStack": _str("Python")},
    {"projectName": _str("마케팅 애널리틱스 대시보드"),
     "domain": _str("데이터 애널리틱스"), "difficulty": _str("MEDIUM"),
     "techStack": _str("PostgreSQL")},
])

PROJECT_PROFILE_EMPTY = wrap([])


# 매칭용 Person 풀 (P003 김태양, P005 최민준)
PERSONS_FOR_MATCHING = wrap([
    # P003 — 페이플로우 투입 중, availability 낮음
    {"personId": _str("P003"), "personName": _str("김태양"),
     "role": _str("프론트엔드 개발자"),
     "availabilityScore": _dec(0.35), "synergyScore": _dec(0.88),
     "skillName": _str("React"), "proficiency": _dec(0.91)},
    {"personId": _str("P003"), "personName": _str("김태양"),
     "role": _str("프론트엔드 개발자"),
     "availabilityScore": _dec(0.35), "synergyScore": _dec(0.88),
     "skillName": _str("TypeScript"), "proficiency": _dec(0.87)},
    # P005 — 애널리틱스 1순위 후보
    {"personId": _str("P005"), "personName": _str("최민준"),
     "role": _str("풀스택 개발자"),
     "availabilityScore": _dec(0.80), "synergyScore": _dec(0.70),
     "skillName": _str("React"), "proficiency": _dec(0.91)},
    {"personId": _str("P005"), "personName": _str("최민준"),
     "role": _str("풀스택 개발자"),
     "availabilityScore": _dec(0.80), "synergyScore": _dec(0.70),
     "skillName": _str("TypeScript"), "proficiency": _dec(0.87)},
    {"personId": _str("P005"), "personName": _str("최민준"),
     "role": _str("풀스택 개발자"),
     "availabilityScore": _dec(0.80), "synergyScore": _dec(0.70),
     "skillName": _str("Python"), "proficiency": _dec(0.74)},
    {"personId": _str("P005"), "personName": _str("최민준"),
     "role": _str("풀스택 개발자"),
     "availabilityScore": _dec(0.80), "synergyScore": _dec(0.70),
     "skillName": _str("데이터 애널리틱스"), "proficiency": _dec(0.76)},
])


# /persons/availability — P003 active_tasks=2, avg_progress=55
ACTIVE_TASK_COUNTS = wrap([
    {"personId": _str("P001"), "personName": _str("박지수"),
     "role": _str("PM"), "availabilityScore": _dec(0.45),
     "activeTasks": _int(0), "avgProgress": _dec(0.0)},
    {"personId": _str("P003"), "personName": _str("김태양"),
     "role": _str("프론트엔드 개발자"), "availabilityScore": _dec(0.35),
     "activeTasks": _int(2), "avgProgress": _dec(55.0)},
    {"personId": _str("P005"), "personName": _str("최민준"),
     "role": _str("풀스택 개발자"), "availabilityScore": _dec(0.80),
     "activeTasks": _int(0), "avgProgress": _dec(0.0)},
])
