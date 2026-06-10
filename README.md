# Traceworks

> **AI 기반 SI 프로젝트 실행 관리 자동화 플랫폼.**
> RFP 문서 한 건을 업로드하면 요구사항 추출 · WBS 생성 · 일정 산정 · 인력 추천까지 자동으로 처리하고, 운영 단계에서는 외부 도구(GitLab/Slides 등) 변경을 자동 감지해 PM에게 맥락 알림을 전달합니다.

---

## 🎯 어떤 문제를 해결하나

기존 SI/수주형 프로젝트에서 PM은 **RFP를 받은 후 며칠씩** 요구사항을 엑셀로 정리하고, WBS를 짜고, 인력 스케줄을 수동으로 맞춥니다. 그리고 프로젝트가 시작되면 GitLab·Figma·Slack 등 흩어진 도구를 직접 뒤져 진행 상황을 파악해야 합니다.

Traceworks는 이 두 가지 페인 포인트를 해결합니다.

1. **시작 단계 자동화** — RFP 업로드 한 번으로 요구사항·WBS·인력 계획 초안을 분 단위로 생성
2. **운영 단계 자동화** — 작업 변경을 자동 수집·분석해 PM에게 정리된 맥락을 전달

---

## 🏗️ 핵심 설계 포인트

### 1. "LLM은 콘텐츠, 코드는 구조" 원칙

LLM에 ID 부여·중복 제거·일정 산정 같은 **구조적 작업을 맡기면 환각·비결정성** 문제가 발생합니다. 그래서 LLM의 책임을 **콘텐츠 추출**(요구사항 텍스트·분류)로만 한정하고, 모든 식별자 부여·정렬·중복 제거·일정 산정은 **코드가 결정적으로** 처리합니다. → AI가 흔들려도 시스템 일관성은 깨지지 않음.

### 2. 온톨로지 기반 지식 그래프 (4-Layer 아키텍처)

```
┌─────────────────────────────────────────────────────┐
│ Layer 4 — Service (실행)                            │
│  Alert · WBSSnapshot · Report · Recommendation      │
├─────────────────────────────────────────────────────┤
│ Layer 3 — SemanticUnit (해석)                       │
│  Progress · Issue · Competency · Collaboration      │
├─────────────────────────────────────────────────────┤
│ Layer 2 — WorkEvent (기록)                          │
│  Git · Design · Document · Message Events           │
├─────────────────────────────────────────────────────┤
│ Layer 1 — Core Entities (정의)                      │
│  Project · Person · Task · Requirement · Skill ...  │
└─────────────────────────────────────────────────────┘
```

**정의 → 기록 → 해석 → 실행** 의 4단계 추상화. 새로운 외부 도구나 기능이 추가되어도 기존 구조를 깨지 않고, 흩어진 모든 데이터가 단일 지식 그래프로 통합됩니다.

### 3. 우선순위 기반 WBS 자동 일정 산출

단순 위상 정렬이 아니라 **5가지 기준의 가중 점수**로 작업 순서를 결정합니다.

```
priority = phase × 10 + criticality × 8 + risk × 15 + fan_out × 1 + bottleneck × 5
```

의존성 · 인원 풀 · 영업일 제약을 동시에 만족하는 **최적 일정**이 자동 산출됩니다.

### 4. 신뢰도 정량화 + 출처 추적

AI 분석 결과에는 **3축 신뢰도 점수**(프로젝트 추출 / 요구사항 분류 / WBS 정확도)와 **모든 요구사항의 RFP 원문 출처**가 함께 저장됩니다. PM이 'AI가 어디서 가져온 결과인지'를 즉시 검증할 수 있어 — 결과를 그대로 믿지 않아도 됩니다.

### 5. 폴리글랏 영속성 (Fuseki + MariaDB)

- **도메인 데이터** (Project · Requirement · Task · Person · Skill) → **Fuseki (RDF/SPARQL)**
- **운영 데이터** (사용자 인증 · 작업 이력 · 알림 이벤트) → **MariaDB**

각자 강점에 맞는 영역만 처리해 두 도구의 약점을 모두 피하는 구조.

---

## 💡 핵심 기술 결정과 그 이유

| 기술 | 선택 이유 |
|------|----------|
| **Apache Jena Fuseki (RDF/SPARQL)** | 인력 매칭·의존성 추적·영향도 분석 같은 N-hop 관계 탐색이 그래프 쿼리 한 줄로 표현 가능. 관계형 DB 대비 재귀 SQL·N+1 폭증 회피 |
| **FastAPI (async)** | 외부 시스템(LLM·GitLab·Slides·알림 API) 호출이 많아 비동기 I/O 필수. OpenAPI 자동 생성으로 프론트 협업 비용 절감 |
| **OpenAI GPT-4 / 4o-mini 분리 사용** | 복잡한 분석은 GPT-4, 단순 분류는 GPT-4o-mini로 비용 최적화. JSON mode로 구조화 출력 강제 |
| **MariaDB (SQLAlchemy async)** | 사용자 인증·작업 이력 같은 ACID 트랜잭션과 시계열 데이터에 적합. 그래프 DB로 처리하기엔 비효율적인 영역 분리 |
| **uv (Python 의존성 관리)** | pip/venv 대비 10~100배 빠른 설치 속도. lockfile 기반 재현 가능한 환경 |
| **Docker Compose** | Fuseki · MariaDB · FastAPI 등 다중 서비스 통합 실행. 로컬·서버 환경 통일 |

---

## 🔄 전체 처리 흐름

```
[RFP PDF/Text]
    │
    ▼
① 청킹 (요구사항 번호 헤딩 기준)
    │
    ▼
② 청크별 병렬 LLM 호출 → 요구사항·프로젝트 정보 추출
    │
    ▼
③ 코드: 중복 제거, ID 부여 (REQ-001, REQ-001-001)
    │
    ▼
④ LLM 배치 → WBS 스켈레톤 생성
    │
    ▼
⑤ 코드: priority-aware 스케줄러 → 일정 산정
    │
    ▼
⑥ 신뢰도 3축 측정 + 출처 추적
    │
    ▼
[PM 검토] → 수정/확정
    │
    ▼
⑦ 온톨로지 적재 + GitLab 저장소 · Google Slides 자동 생성
    │
    ▼
⑧ 운영 단계 — 외부 도구 변경 자동 감지 → AI 제언 · 맥락 알림
```

---

## 📁 프로젝트 구조

```
traceworks/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI 엔드포인트 (RFP·Project·Task·Recommendation 등)
│   │   ├── core/
│   │   │   ├── services/     # 비즈니스 로직 (rfp_service · recommend_service · insight_service 등)
│   │   │   └── interpreter/  # LLM 프롬프트 및 호출
│   │   ├── db/
│   │   │   ├── sparql_repo.py    # Fuseki/SPARQL 데이터 액세스 레이어
│   │   │   ├── models.py         # SQLAlchemy ORM (MariaDB)
│   │   │   └── fuseki.py         # Fuseki HTTP 클라이언트
│   │   └── schemas/          # Pydantic 모델
│   ├── db/seeds/             # 온톨로지 시드 데이터 (TTL)
│   └── pyproject.toml
├── docs/
│   ├── api-guide/            # API 가이드 문서
│   └── ...
├── docker-compose.yml
└── README.md
```

---

## 🚀 실행 방법

### 사전 준비

- Docker / Docker Compose
- Python 3.11+ (로컬 개발 시)
- [uv](https://github.com/astral-sh/uv) (Python 의존성 관리)
- 외부 API 키: OpenAI, (선택) GitLab, Google Slides

### 1. 환경 변수 설정

`backend/.env` 파일을 생성하고 다음 값을 채웁니다.

```env
# LLM
OPENAI_API_KEY=sk-...

# Fuseki (Triple store)
FUSEKI_URL=http://fuseki:3030/traceworks

# MariaDB
DATABASE_URL=mysql+aiomysql://user:password@mariadb:3306/traceworks

# 외부 통합 (선택)
GITLAB_URL=http://your-gitlab.example.com
GITLAB_TOKEN=glpat-...
GITLAB_NAMESPACE=your-group
GOOGLE_SLIDES_CREDENTIALS=path/to/credentials.json

# 알림 API
ALERT_API_URL=http://your-alert-api.example.com
ALERT_API_INTERNAL_TOKEN=...
```

> 예시 파일은 `backend/.env.example` 참조

### 2. Docker Compose로 전체 스택 실행

```bash
docker compose up -d
```

실행 후 다음 서비스가 기동됩니다.

| 서비스 | 포트 | 설명 |
|--------|------|------|
| Backend API | `8005` | FastAPI 서버 |
| Fuseki | `3030` | RDF/SPARQL 트리플 스토어 |
| MariaDB | `3306` | 운영 데이터 저장소 |

### 3. 시드 데이터 적재 (선택)

```bash
cd backend
uv run python scripts/load_seeds.py
```

샘플 인력 풀과 데모 프로젝트가 온톨로지에 적재됩니다.

### 4. 접속 확인

- API 문서 (Swagger UI): http://localhost:8005/docs
- Fuseki 콘솔: http://localhost:3030

### 5. 로컬 개발 모드 (Docker 없이)

```bash
cd backend
uv venv --python 3.11
uv sync
uv run uvicorn app.main:app --reload --port 8005
```

---

## 🧪 테스트

```bash
cd backend
uv run pytest -q
```

---

## 📚 주요 문서

- [RFP 분석 화면 가이드](docs/api-guide/rfp-analyze-chunked-ui-guide.md)
- [프로젝트 상세 — 요구사항 트리 UI 가이드](docs/api-guide/project-detail-requirements-ui-guide.md)
- [WBS 3단계 트리 가이드](docs/api-guide/wbs-gantt-3level-ui-guide.md)
- [API 가이드 모음](docs/api-guide/)
- [상세 설계 회고 (포트폴리오용)](docs/resume-portfolio.md)

---

## 🛠️ 사용 기술

| 영역 | 스택 |
|------|------|
| **언어/프레임워크** | Python 3.11+, FastAPI (async), Pydantic v2 |
| **데이터 저장** | Apache Jena Fuseki (RDF/SPARQL), MariaDB, SQLAlchemy (async) |
| **LLM** | OpenAI Chat Completions (GPT-4 / GPT-4o-mini), JSON mode |
| **외부 통합** | GitLab API, Google Slides API |
| **인프라** | Docker, Docker Compose |
| **의존성 관리** | uv |
| **문서 처리** | PyMuPDF, python-docx, pyhwp |

---

## ✨ 핵심 기능 한눈에

| 기능 | 설명 |
|------|------|
| **RFP 자동 분석** | 청킹 기반 병렬 LLM 호출 + 코드 정규화로 요구사항·WBS·인력 계획 자동 생성 |
| **AI 인력 추천** | 온톨로지 기반 스킬·가용성·시너지 3축 가중 평균 매칭 |
| **WBS 자동 일정 산출** | Priority-aware 스케줄러로 의존성·자원·달력 제약 동시 충족 |
| **자동 일정 재산출** | 추가 태스크 생성 시 완료 작업은 보존하고 후속 일정만 자동 재배치 |
| **AI 제언** | 운영 중 병목·의존성 지연 위험을 SPARQL 패턴 매칭으로 자동 감지 |
| **외부 도구 통합** | GitLab 저장소·Google Slides 자동 생성, 변경 이벤트 웹훅 자동 수집 |
| **권한·승인 흐름** | PM/담당자 권한 분리, 승인 요청·반려 흐름과 알림 라우팅 통합 |

---

## 📌 개발 회고

> **LLM이 흔들려도 시스템은 안정적으로 동작한다.**
>
> 이 한 줄을 만들기 위해 어떤 책임을 LLM에 맡기고, 어떤 책임을 코드가 잡아야 하는지를 매 단계에서 결정한 경험이 가장 큰 자산이 됐습니다.

자세한 설계 의사결정 회고는 [docs/resume-portfolio.md](docs/resume-portfolio.md)를 참고해주세요.

---

## 📄 라이선스

MIT
