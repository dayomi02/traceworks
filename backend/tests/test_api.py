from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.interpreter.llm_client import LLMUnavailable
from app.db.fuseki import FusekiUnavailable
from tests.fixtures import sparql_responses as S


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ──────────────────────────────────────────────────────────────
# GET /projects
# ──────────────────────────────────────────────────────────────

def test_list_projects_ok(client: TestClient) -> None:
    responses = iter([S.LIST_PROJECTS_BASE, S.LIST_PROJECTS_AGG])
    with patch("app.db.fuseki.query_safe", side_effect=lambda _: next(responses)):
        response = client.get("/projects")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    prj001 = next(p for p in body if p["project_id"] == "PRJ001")
    assert prj001["project_name"] == "페이플로우 v2"
    assert prj001["domain"] == "핀테크"
    assert prj001["status"] == "ACTIVE"
    # SimpleAverage: (55+10+70+80+0)/5 = 43.0
    assert prj001["overall_progress"] == 43.0

    prj002 = next(p for p in body if p["project_id"] == "PRJ002")
    assert prj002["overall_progress"] == 0.0  # 집계 없음
    assert prj002["domain"] is None


# ──────────────────────────────────────────────────────────────
# GET /projects/{id}/wbs
# ──────────────────────────────────────────────────────────────

def test_get_wbs_ok(client: TestClient) -> None:
    with patch("app.db.fuseki.ask", return_value=True), \
         patch("app.db.fuseki.query_safe", return_value=S.WBS_PRJ001):
        response = client.get("/projects/PRJ001/wbs")

    assert response.status_code == 200
    rows = response.json()
    assert [r["task_id"] for r in rows] == ["T001", "T002"]
    t001 = rows[0]
    assert t001["wbs_code"] == "1.0"
    assert t001["task_name"] == "로그인 화면 UI 구현"
    assert t001["progress"] == 55
    assert t001["assignee"] == "김태양"
    assert t001["due_date"] == "2025-04-25"
    assert t001["planned_hours"] == 40.0
    assert t001["actual_hours"] == 24.0
    # T002 OPTIONAL 필드 누락 허용
    assert rows[1]["assignee"] is None
    assert rows[1]["due_date"] is None


def test_get_wbs_404_when_project_missing(client: TestClient) -> None:
    with patch("app.db.fuseki.ask", return_value=False):
        response = client.get("/projects/NOPE/wbs")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "ProjectNotFound"
    assert body["identifier"] == "NOPE"


# ──────────────────────────────────────────────────────────────
# GET /tasks/{id}
# ──────────────────────────────────────────────────────────────

def test_get_task_ok(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.TASK_T001):
        response = client.get("/tasks/T001")

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "T001"
    assert body["task_name"] == "로그인 화면 UI 구현"
    assert body["progress"] == 55
    assert body["assignee"] == {"person_id": "P003", "person_name": "김태양"}
    assert set(body["source_files"]) == {
        "src/screens/auth/LoginScreen.tsx",
        "src/components/auth/LoginForm.tsx",
        "src/components/auth/SocialLoginButton.tsx",
    }


def test_get_task_404(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.TASK_EMPTY):
        response = client.get("/tasks/T999")
    assert response.status_code == 404
    assert response.json()["code"] == "TaskNotFound"


# ──────────────────────────────────────────────────────────────
# GET /persons
# ──────────────────────────────────────────────────────────────

def test_list_persons_ok(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.LIST_PERSONS):
        response = client.get("/persons")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    taeyang = next(p for p in body if p["person_id"] == "P003")
    assert taeyang["person_name"] == "김태양"
    assert taeyang["role"] == "프론트엔드 개발자"
    assert len(taeyang["skills"]) == 4
    skill_names = {s["name"] for s in taeyang["skills"]}
    assert skill_names == {"React", "TypeScript", "React Native", "핀테크 도메인"}


# ──────────────────────────────────────────────────────────────
# GET /persons/{id}
# ──────────────────────────────────────────────────────────────

def test_get_person_ok(client: TestClient) -> None:
    responses = iter([S.PERSON_P003, S.PERSON_P003_PROJECTS])
    with patch("app.db.fuseki.query_safe", side_effect=lambda _: next(responses)):
        response = client.get("/persons/P003")

    assert response.status_code == 200
    body = response.json()
    assert body["person_id"] == "P003"
    assert body["person_name"] == "김태양"
    assert len(body["skills"]) == 4
    assert body["participates_in"] == [
        {"project_id": "PRJ001", "project_name": "페이플로우 v2"},
    ]


def test_get_person_404(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.PERSON_EMPTY):
        response = client.get("/persons/P999")
    assert response.status_code == 404
    assert response.json()["code"] == "PersonNotFound"


# ──────────────────────────────────────────────────────────────
# Fuseki unavailable → 503
# ──────────────────────────────────────────────────────────────

def test_fuseki_unavailable_503(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe",
               side_effect=FusekiUnavailable("connection refused")):
        response = client.get("/projects")
    assert response.status_code == 503
    assert response.json()["detail"] == "triple store unavailable"


# ──────────────────────────────────────────────────────────────
# snake_case response contract
# ──────────────────────────────────────────────────────────────

def test_snake_case_response(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.LIST_PERSONS):
        response = client.get("/persons")
    body = response.json()
    assert "person_name" in body[0]
    assert "personName" not in body[0]


# ──────────────────────────────────────────────────────────────
# Path regex guard
# ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_id", ["../etc", "x y", "id' OR 1=1"])
def test_invalid_id_422(client: TestClient, bad_id: str) -> None:
    response = client.get(f"/tasks/{bad_id}")
    assert response.status_code in (404, 422)  # URL-level mismatch or validation


# ──────────────────────────────────────────────────────────────
# POST /projects/{id}/recommend-staff (Phase 5)
# ──────────────────────────────────────────────────────────────

_LLM_SKILLS = {"required_skills": ["React", "TypeScript", "Python", "데이터 애널리틱스"]}


def _recommend_mocks(llm_payload=None):
    """Returns context manager setup for recommend-staff tests."""
    llm_mock = AsyncMock(return_value=llm_payload or _LLM_SKILLS)
    read_iter = iter([S.PROJECT_PROFILE_PRJ002, S.PERSONS_FOR_MATCHING])
    return llm_mock, read_iter


def test_recommend_staff_default_does_not_persist(client: TestClient) -> None:
    llm_mock, read_iter = _recommend_mocks()
    with patch("app.core.interpreter.llm_client.complete_json", llm_mock), \
         patch("app.db.fuseki.query_safe", side_effect=lambda _: next(read_iter)), \
         patch("app.db.fuseki.update") as update_mock:
        response = client.post("/projects/PRJ002/recommend-staff")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["person_id"] == "P005"
    assert body[0]["rank"] == 1
    assert body[0]["similarity_score"] == 0.82
    assert update_mock.call_count == 0  # 적재 안 됨


def test_recommend_staff_persist_true_inserts_to_fuseki(client: TestClient) -> None:
    llm_mock, read_iter = _recommend_mocks()
    with patch("app.core.interpreter.llm_client.complete_json", llm_mock), \
         patch("app.db.fuseki.query_safe", side_effect=lambda _: next(read_iter)), \
         patch("app.db.fuseki.update") as update_mock:
        response = client.post(
            "/projects/PRJ002/recommend-staff",
            json={"persist": True, "top_k": 2},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) <= 2
    assert update_mock.call_count == 1
    inserted_sparql = update_mock.call_args[0][0]
    assert "pm:StaffingRecommendation" in inserted_sparql
    assert '"PRJ002-01"' in inserted_sparql
    assert '"P005"' in inserted_sparql


def test_recommend_staff_404_when_project_missing(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.PROJECT_PROFILE_EMPTY):
        response = client.post("/projects/NOPE/recommend-staff")
    assert response.status_code == 404
    assert response.json()["code"] == "ProjectNotFound"


def test_recommend_staff_llm_unavailable_503(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.PROJECT_PROFILE_PRJ002), \
         patch("app.core.interpreter.llm_client.complete_json",
               AsyncMock(side_effect=LLMUnavailable("api key invalid"))):
        response = client.post("/projects/PRJ002/recommend-staff")
    assert response.status_code == 503
    assert response.json()["detail"] == "llm unavailable"


def test_recommend_staff_empty_skills_fallback(client: TestClient) -> None:
    llm_mock = AsyncMock(return_value={"required_skills": []})
    read_iter = iter([S.PROJECT_PROFILE_PRJ002, S.PERSONS_FOR_MATCHING])
    with patch("app.core.interpreter.llm_client.complete_json", llm_mock), \
         patch("app.db.fuseki.query_safe", side_effect=lambda _: next(read_iter)):
        response = client.post("/projects/PRJ002/recommend-staff")
    # LLM empty → techStack fallback → React/TypeScript/Python/PostgreSQL
    # → P005가 3개 매칭(React/TS/Python), P003은 2개 매칭
    assert response.status_code == 200
    body = response.json()
    assert body[0]["person_id"] == "P005"


# ──────────────────────────────────────────────────────────────
# GET /persons/availability
# ──────────────────────────────────────────────────────────────

def test_availability_basic(client: TestClient) -> None:
    with patch("app.db.fuseki.query_safe", return_value=S.ACTIVE_TASK_COUNTS):
        response = client.get("/persons/availability")

    assert response.status_code == 200
    body = response.json()
    p003 = next(p for p in body if p["person_id"] == "P003")
    assert p003["person_name"] == "김태양"
    assert p003["active_tasks"] == 2
    assert p003["availability_score"] == 0.35     # 저장값 그대로
    assert p003["computed_availability"] == 0.7   # 2 × (1 - 0.55) / 3 = 0.30 → 1 - 0.30 = 0.70

    p001 = next(p for p in body if p["person_id"] == "P001")
    assert p001["active_tasks"] == 0
    assert p001["computed_availability"] == 1.0


def test_availability_with_project_filter(client: TestClient) -> None:
    captured = {}

    def spy(sparql: str):
        captured["sparql"] = sparql
        return S.ACTIVE_TASK_COUNTS

    with patch("app.db.fuseki.query_safe", side_effect=spy):
        response = client.get("/persons/availability?projectId=PRJ001")

    assert response.status_code == 200
    assert '"PRJ001"' in captured["sparql"]


def test_availability_invalid_project_id_422(client: TestClient) -> None:
    response = client.get("/persons/availability?projectId=bad id")
    assert response.status_code == 422


def test_availability_does_not_shadow_person_route(client: TestClient) -> None:
    """GET /persons/availability should not be captured as /persons/{person_id}."""
    with patch("app.db.fuseki.query_safe", return_value=S.ACTIVE_TASK_COUNTS):
        response = client.get("/persons/availability")
    # Availability 경로가 맞다면 list 반환, person detail이면 dict 반환
    assert isinstance(response.json(), list)
