# TraceWorks

> **AI 기반 SI 프로젝트 실행 관리 자동화 플랫폼**
> RFP 한 건을 업로드하면 요구사항 추출 · WBS 생성 · 일정 산정 · 인력 계획까지 자동으로 처리됩니다.

---

## 프로젝트 소개

### 왜 만들었는가

SI/수주형 프로젝트 현장에서 PM은 **RFP를 받은 직후부터 며칠씩** 같은 작업을 반복합니다 — 요구사항을 엑셀로 쪼개고, WBS를 짜고, 인력 스케줄을 손으로 맞추는 일. 정작 중요한 의사결정에 써야 할 시간이 **셋업 잡일에 다 잡아먹히는 구조**입니다.

게다가 프로젝트가 시작되면 GitLab·Figma·Slack 같은 **흩어진 도구를 PM이 직접 뒤져** 진행 상황을 파악해야 합니다. "지금 어디까지 됐고, 누가 막혔고, 어떤 일정이 밀렸는지" 같은 기본 질문조차 매일 시간을 들여야 답할 수 있습니다.

TraceWorks는 이 두 가지 페인을 해결하려고 만들었습니다 — **시작 단계는 RFP 한 번 업로드로 자동화하고**, **운영 단계는 흩어진 도구의 변경을 자동 수집·해석해서 PM에게 정리된 맥락을 전달**하는 시스템입니다.

---

## 해결하려는 문제

SI 프로젝트 수주 시 **RFP → 요구사항 정리 → WBS 작성 → 인력 계획**까지의 전 과정이 PM의 수작업으로 이뤄지며, 보통 **며칠~일주일**이 소요됩니다.

| 기존 방식 | TraceWorks |
|----------|-----------|
| PM이 RFP를 직접 읽고 요구사항을 엑셀로 정리 | RFP 업로드 → 요구사항 자동 추출 |
| WBS를 손으로 작성 + 일정 수동 배치 | WBS 자동 생성 + 의존성·자원 기반 일정 자동 산출 |
| 가용 인력을 찾아 수동 매칭 | 온톨로지 기반 인력 자동 추천 (스킬·가용성·시너지) |
| 진행 상황 파악 위해 여러 도구 수동 점검 | 외부 도구 변경 자동 감지 + AI 제언 |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (사용자 인터페이스)              │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                  FastAPI (async) — API Layer                │
│   · RFP · Projects · Tasks · Recommendations · Insights     │
└───────────┬──────────────────────────────────┬──────────────┘
            │                                  │
            ▼                                  ▼
   ┌────────────────────┐         ┌─────────────────────────┐
   │  LLM Interpreter   │         │  Business Logic Layer   │
   │  (OpenAI GPT-4)    │         │  · RFP 분석 파이프라인   │
   │  · 콘텐츠 추출만   │         │  · WBS 스케줄러         │
   │  · JSON Mode       │         │  · 인력 매칭 알고리즘    │
   └─────────┬──────────┘         └────────────┬────────────┘
             │                                 │
             └──────────────┬──────────────────┘
                            ▼
        ┌───────────────────────────────────────┐
        │   Knowledge Graph (Apache Jena Fuseki)│
        │  ┌─────────────────────────────────┐  │
        │  │ Layer 4 — Service               │  │
        │  │ Alert · Snapshot · Report       │  │
        │  ├─────────────────────────────────┤  │
        │  │ Layer 3 — SemanticUnit (해석)   │  │
        │  │ Progress · Issue · Competency   │  │
        │  ├─────────────────────────────────┤  │
        │  │ Layer 2 — WorkEvent (기록)      │  │
        │  │ Git · Design · Doc · Message    │  │
        │  ├─────────────────────────────────┤  │
        │  │ Layer 1 — Core Entities (정의)  │  │
        │  │ Project · Person · Task · Skill │  │
        │  └─────────────────────────────────┘  │
        └────────────────────┬──────────────────┘
                             │
                             ▼
              ┌─────────────────────────────┐
              │  MariaDB (운영 데이터)       │
              │  · 사용자 인증·세션          │
              │  · 작업 이력                 │
              │  · 알림 이벤트               │
              └─────────────────────────────┘

   외부 통합 (Webhook · API):
   GitLab ──→ │                       │ ──→ Google Slides
   Figma  ──→ │  → WorkEvent 정규화 →  │ ──→ 알림 시스템
   Slack  ──→ │                       │
```

**핵심 흐름**: RFP 업로드 → 청킹 → LLM 콘텐츠 추출 → 코드 정규화 → WBS 자동 산출 → 온톨로지 적재 → 운영 단계 자동 감지

---

## 주요 기능

### 📄 RFP 분석
RFP 문서를 요구사항 번호 헤딩 기준으로 청킹하고, 청크별로 병렬 LLM 호출해 **프로젝트 개요·요구사항·필요 인력**을 자동 추출합니다. 모든 항목에 **원문 출처(source_text + chunk)** 가 함께 저장되어 PM이 검증할 수 있습니다.

### 🗂️ 업무 추출
추출된 요구사항을 **대분류/중분류 2-depth 트리**로 자동 구조화. 같은 요구사항 ID 충돌·중복은 코드가 결정적으로 제거하고, LLM은 텍스트 분류만 담당해 환각 위험을 차단합니다.

### 📊 WBS 생성
**우선순위 기반 자동 일정 산출 알고리즘**으로 의존성·인원 풀·영업일 제약을 동시에 만족하는 WBS를 산출합니다.

```
priority = phase × 10 + criticality × 8 + risk × 15 + fan_out × 1 + bottleneck × 5
```

### 👥 인력 계획 생성
온톨로지 기반 **3축 가중 평균 매칭** (스킬 적합도 50% + 가용성 30% + 시너지 20%)으로 최적 인력을 추천하며, 각 결과에 **자연어 매칭 근거**가 함께 제공됩니다.

### 🔔 (운영 단계) 변경 감지 & AI 제언
GitLab·Figma 등 외부 도구의 변경 이벤트를 자동 수집해 **태스크 진척률·이슈·블로커**를 자동 갱신하고, 병목·의존성 지연·인력 과부하 위험을 PM에게 선제적으로 알려줍니다.

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| **언어 / 프레임워크** | Python 3.11+, FastAPI (async), Pydantic v2 |
| **데이터 저장** | Apache Jena Fuseki (RDF/SPARQL), MariaDB, SQLAlchemy (async) |
| **LLM** | OpenAI Chat Completions (GPT-4 / GPT-4o-mini), JSON Mode |
| **외부 통합** | GitLab API, Google Slides API |
| **인프라** | Docker, Docker Compose |
| **의존성 관리** | uv |
| **문서 처리** | PyMuPDF, python-docx, pyhwp |

---

## 기술적 도전

### 1. Ontology 설계 — 4-Layer 추상화

데이터를 단순 테이블이 아닌 **관계 기반 지식 그래프**로 표현해, 인력 매칭·의존성 추적·영향도 분석을 그래프 쿼리 한 줄로 처리할 수 있도록 설계했습니다.

```
Layer 4 ─ Service      │ Alert · Snapshot · Report · Recommendation
Layer 3 ─ SemanticUnit │ Progress · Issue · Competency · Collaboration
Layer 2 ─ WorkEvent    │ Git · Design · Document · Message Events
Layer 1 ─ Core Entity  │ Project · Person · Task · Skill · Requirement
```

**정의 → 기록 → 해석 → 실행** 의 4단계 추상화 덕분에, 새 외부 도구나 기능이 추가돼도 기존 구조를 깨지 않고 흩어진 데이터를 단일 지식 그래프로 통합할 수 있습니다.

### 2. GraphRAG — 한국 SI 컨텍스트 내재화

글로벌 AI 도구는 보편적인 애자일·스크럼 방법론에 맞춰져 있어 **국내 IT/SI 환경의 비즈니스 로직을 반영하지 못합니다.** TraceWorks는 단순 LLM 호출이 아니라:

- RFP 분석 시점에 추출한 **역할별 필요 스킬·M/M 산정 기준·요구사항 패턴**을 온톨로지에 적재
- 이후 인력 추천이나 일정 산출 시 **이 지식 그래프가 RAG의 가이드라인** 역할
- LLM 호출 없이 그래프 쿼리만으로 결정적·고속 매칭

결과적으로 한국형 SI 프로젝트 컨텍스트에 최적화된 추천·산출이 가능합니다.

### 3. Hallucination 제어 — "LLM은 콘텐츠, 코드는 구조"

초기에는 LLM에 ID 부여·중복 제거·일정 산정까지 맡겼더니, RFP 재분석 시 **`REQ-001` 같은 ID가 청크 간 충돌**하거나 동일 요구사항이 다른 ID로 두 번 추출되는 등 비결정적 동작이 반복됐습니다.

이를 해결한 원칙:

- **LLM의 책임**: 텍스트 추출·분류만 (요구사항 내용, phase/criticality/risk 분류 등)
- **코드의 책임**: ID 부여·중복 제거·정렬·일정 산정·신뢰도 측정

LLM 출력에는 `tempId`, `parentTempId` 같은 **임시 식별자**만 두고, 코드가 정규화 단계에서 최종 `REQ-001-001` 같은 ID를 결정적으로 부여합니다.

**결과**: 동일 RFP 재분석 시 ID 충돌 0건, AI가 흔들려도 시스템 구조적 일관성은 유지.

---

## 향후 계획

### 📌 단기 (MVP 보완)

- **수동 입력 기능** — 시스템 외부에서 발생한 이슈를 PM이 직접 등록할 수 있는 인터페이스
- **인력 승인 절차** — 선택된 인력에게 참여 요청 알림 발송 → 수락 후 정식 배정
- **다양한 문서 지원** — 요구사항 정의서, 기능 명세서 등 RFP 외 문서 분석 지원

### 🚀 중기 (정식 버전)

- **자체 호스팅 LLM 옵션** — 폐쇄망 환경의 엔터프라이즈를 위한 sLM(Llama 등) 전환 지원
- **데이터 마이그레이션 도구** — Jira·Notion·MS Project 등 기존 PM 도구의 데이터를 온톨로지로 변환
- **성과 분석 리포트** — 종료된 프로젝트의 누적 데이터로 차기 프로젝트 인력 추천 정확도 향상
- **GitHub Webhook 통합** — GitLab 외 GitHub도 지원

### 🌟 장기 (확장 비전)

- **다국어 RFP 지원** — 영문·일문 RFP까지 분석 범위 확대
- **다양한 사업 도메인 대응** — 소프트웨어 외 건설·연구·마케팅 등 프로젝트 일반화
- **조직 단위 학습** — 회사별 프로젝트 데이터가 누적될수록 그 조직에 특화된 추천 정확도 향상

---

## 🚀 실행 방법

### 사전 준비

- Docker / Docker Compose
- Python 3.11+ (로컬 개발 시)
- [uv](https://github.com/astral-sh/uv)
- OpenAI API Key

### 1. 환경 변수 설정

```bash
cp backend/.env.example backend/.env
# backend/.env 파일을 열어 OPENAI_API_KEY, DATABASE_URL 등을 채웁니다
```

### 2. Docker Compose로 실행

```bash
docker compose up -d
```

| 서비스 | 포트 |
|--------|------|
| Backend API | `8005` |
| Fuseki | `3030` |
| MariaDB | `3306` |

### 3. 접속

- API 문서 (Swagger UI): http://localhost:8005/docs
- Fuseki 콘솔: http://localhost:3030

### 4. 로컬 개발 모드 (Docker 없이)

```bash
cd backend
uv venv --python 3.11
uv sync
uv run uvicorn app.main:app --reload --port 8005
```

---

## 📚 더 알아보기

- [상세 설계 회고 (포트폴리오)](docs/resume-portfolio.md)
- [RFP 분석 화면 가이드](docs/api-guide/rfp-analyze-chunked-ui-guide.md)
- [API 가이드 모음](docs/api-guide/)
- [데모 이미지](demo/)
