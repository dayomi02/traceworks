"""RFP API 통합 테스트 — Fuseki + LLM 전 구간 모킹."""
import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from tests.fixtures.rfp_samples import (
    SAMPLE_ANALYSIS,
    make_docx_bytes,
    make_pdf_bytes,
)


def _fixed_rfp_id(monkeypatch_obj=None):
    """테스트 결정론을 위해 rfp_id 생성 고정."""
    from app.core.services import rfp_service

    rfp_service._new_rfp_id.__wrapped__ = None  # type: ignore[attr-defined]
    return "TEST01"


# ──────────────────────────────────────────────────────────────
# POST /rfp/upload
# ──────────────────────────────────────────────────────────────

def test_upload_pdf_creates_rfp(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.services.rfp_service._new_rfp_id",
        lambda: "RFP_TEST001",
    )
    with patch("app.db.fuseki.update") as fuseki_update:
        response = client.post(
            "/rfp/upload",
            files={"file": ("sample.pdf", make_pdf_bytes(), "application/pdf")},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["rfp_id"] == "RFP_TEST001"
    assert body["file_name"] == "sample.pdf"
    assert body["status"] == "extracted"
    assert body["page_count"] == 1
    assert fuseki_update.call_count == 1


def test_upload_docx_creates_rfp(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.services.rfp_service._new_rfp_id",
        lambda: "RFP_DOC002",
    )
    with patch("app.db.fuseki.update"):
        response = client.post(
            "/rfp/upload",
            files={
                "file": (
                    "rfp.docx",
                    make_docx_bytes("요구사항 분석서"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
    assert response.status_code == 201
    body = response.json()
    assert "요구사항" in body["extracted_text"]


def test_upload_unsupported_format_415(client: TestClient) -> None:
    response = client.post(
        "/rfp/upload",
        files={"file": ("readme.txt", b"plain", "text/plain")},
    )
    assert response.status_code == 415


def test_upload_empty_file_400(client: TestClient) -> None:
    response = client.post(
        "/rfp/upload",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


# ──────────────────────────────────────────────────────────────
# POST /rfp/{id}/analyze
# ──────────────────────────────────────────────────────────────

def _mock_rfp_row(status: str = "extracted", analysis: dict | None = None) -> dict:
    return {
        "rfp_id": "RFP_T1",
        "file_name": "a.pdf",
        "extracted_text": "MES 프로젝트 요구사항 요약",
        "page_count": 1,
        "status": status,
        "analysis_json": json.dumps(analysis, ensure_ascii=False) if analysis else None,
        "confidence_score": None,
        "created_at": "2025-04-19T12:00:00Z",
        "confirmed_project": None,
    }


def test_analyze_success(client: TestClient) -> None:
    llm_mock = AsyncMock(return_value=SAMPLE_ANALYSIS)
    with patch("app.db.sparql_repo.get_rfp", return_value=_mock_rfp_row()), \
         patch("app.core.interpreter.llm_client.complete_json", llm_mock), \
         patch("app.db.fuseki.update") as fuseki_update:
        response = client.post("/rfp/RFP_T1/analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analyzed"
    assert body["project"]["project_name"] == "스마트팩토리 MES 시스템 구축"
    assert len(body["wbs"]) == 3
    assert body["confidence_score"] == 0.91
    # analysis 저장을 위해 update 호출됨 (delete + insert)
    assert fuseki_update.call_count >= 1


def test_analyze_404_when_rfp_missing(client: TestClient) -> None:
    with patch("app.db.sparql_repo.get_rfp", return_value=None):
        response = client.post("/rfp/NOPE/analyze")
    assert response.status_code == 404
    assert response.json()["code"] == "RfpNotFound"


def test_analyze_409_when_already_confirmed(client: TestClient) -> None:
    with patch("app.db.sparql_repo.get_rfp",
               return_value=_mock_rfp_row(status="confirmed")):
        response = client.post("/rfp/RFP_T1/analyze")
    assert response.status_code == 409
    assert response.json()["code"] == "RfpStateError"


# ──────────────────────────────────────────────────────────────
# PATCH /rfp/{id}/analysis
# ──────────────────────────────────────────────────────────────

def test_patch_updates_analysis(client: TestClient) -> None:
    existing = _mock_rfp_row(status="analyzed", analysis=SAMPLE_ANALYSIS)
    with patch("app.db.sparql_repo.get_rfp", return_value=existing), \
         patch("app.db.fuseki.update"):
        response = client.patch(
            "/rfp/RFP_T1/analysis",
            json={
                "project": {
                    "project_name": "수정된 프로젝트명",
                    "tech_stack": ["Java"],
                },
            },
        )
    assert response.status_code == 200
    assert response.json()["status"] == "reviewed"


def test_patch_without_prior_analyze_409(client: TestClient) -> None:
    with patch("app.db.sparql_repo.get_rfp", return_value=_mock_rfp_row()):
        response = client.patch(
            "/rfp/RFP_T1/analysis",
            json={"project": {"project_name": "x"}},
        )
    assert response.status_code == 409


# ──────────────────────────────────────────────────────────────
# POST /rfp/{id}/confirm
# ──────────────────────────────────────────────────────────────

def test_confirm_inserts_project_and_wbs(client: TestClient) -> None:
    existing = _mock_rfp_row(status="reviewed", analysis=SAMPLE_ANALYSIS)
    with patch("app.db.sparql_repo.get_rfp", return_value=existing), \
         patch("app.db.fuseki.update") as fuseki_update:
        response = client.post("/rfp/RFP_T1/confirm")

    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "PRJ_T1"
    assert body["tasks_created"] == 3
    assert body["triples_inserted"] > 0
    assert "PRJ_T1" in body["next_step"]
    # insert + mark_rfp_confirmed (delete+insert) → 최소 2건
    assert fuseki_update.call_count >= 2


def test_confirm_without_analysis_409(client: TestClient) -> None:
    with patch("app.db.sparql_repo.get_rfp", return_value=_mock_rfp_row()):
        response = client.post("/rfp/RFP_T1/confirm")
    assert response.status_code == 409


# ──────────────────────────────────────────────────────────────
# GET /rfp, GET /rfp/{id}
# ──────────────────────────────────────────────────────────────

def test_list_rfps(client: TestClient) -> None:
    with patch("app.db.sparql_repo.list_rfps", return_value=[
        {"rfp_id": "RFP_A", "file_name": "a.pdf", "project_name": None,
         "status": "extracted", "created_at": "2025-04-19T12:00:00Z"},
        {"rfp_id": "RFP_B", "file_name": "b.docx", "project_name": "x",
         "status": "analyzed", "created_at": "2025-04-19T13:00:00Z"},
    ]):
        response = client.get("/rfp")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["rfp_id"] == "RFP_A"


def test_get_rfp_detail(client: TestClient) -> None:
    existing = _mock_rfp_row(status="analyzed", analysis=SAMPLE_ANALYSIS)
    with patch("app.db.sparql_repo.get_rfp", return_value=existing):
        response = client.get("/rfp/RFP_T1")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analyzed"
    assert body["project"]["project_name"] == "스마트팩토리 MES 시스템 구축"
    assert len(body["wbs"]) == 3


def test_get_rfp_404(client: TestClient) -> None:
    with patch("app.db.sparql_repo.get_rfp", return_value=None):
        response = client.get("/rfp/NOPE")
    assert response.status_code == 404
