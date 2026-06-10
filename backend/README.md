# Traceworks Backend

온톨로지 기반 AI 프로젝트 관리 시스템 백엔드 (FastAPI).

## 아키텍처

```
[GitHub / Figma / Slack 웹훅]
        ↓
Layer 1  Normalizer   (app/core/normalizer)   → WorkEvent 정규화
        ↓
Layer 2  Interpreter  (app/core/interpreter)  → OpenAI 기반 Signal 분류
        ↓
Layer 3  Inference    (app/core/inference)    → 규칙 기반 추론 (WBS/Issue/Skill/Alert)
        ↓
Layer 4  Services     (app/core/services)     → WBS / Alert / Recommend / Report
        ↓
[PostgreSQL] + [Fuseki Triple Store] + [Redis / Celery]
```

## 로컬 실행 (uv)

```bash
cd backend
uv venv --python 3.11
uv pip install -e ".[dev]"
cp .env.example .env   # 값 채우기

uv run uvicorn app.main:app --reload
curl http://localhost:8000/health
```

## 테스트

```bash
uv run pytest -q
```

## Docker Compose (전체 스택)

루트에서:

```bash
docker compose up -d postgres redis fuseki
docker compose up backend worker
```
