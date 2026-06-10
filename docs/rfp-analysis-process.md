# RFP 분석 프로세스 — 시나리오 및 신뢰도 측정 기준

> 청킹 기반 RFP 분석 파이프라인의 전체 흐름과 각 단계에서 LLM·코드가 담당하는 역할,
> 그리고 분석 결과의 품질을 정량적으로 평가하는 신뢰도 점수 계산 방식을 정리합니다.

---

## 1. 전체 시나리오 개요

RFP 파일을 업로드해서 프로젝트와 WBS가 자동 생성되기까지의 흐름:

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. 업로드        POST /rfp/upload                                   │
│       파일 → 텍스트 추출 (PDF/DOCX/HWP/TXT)                          │
│       status: extracted                                              │
├─────────────────────────────────────────────────────────────────────┤
│  2. 청킹 분석    POST /rfp/{rfp_id}/analyze-chunked                  │
│       Step 1: 요구사항 번호(FUN-01 등) 헤딩 기준 청킹                │
│       Step 2: 청크별 프로젝트 정보 추출 → 병합                       │
│       Step 3: 청크별 요구사항 추출 → tempId 기반 reqId 부여          │
│       Step 4: 요구사항별 WBS task 스켈레톤 생성 → LLM 내용 채움      │
│       status: analyzed (+ confidence_score)                          │
├─────────────────────────────────────────────────────────────────────┤
│  3. 검토·수정   PATCH /rfp/{rfp_id}/analysis                         │
│       사용자가 프로젝트/요구사항/WBS 직접 편집 (부분 수정 가능)      │
│       status: reviewed                                               │
├─────────────────────────────────────────────────────────────────────┤
│  4. 확정         POST /rfp/{rfp_id}/confirm                          │
│       Fuseki에 Project + Requirement + Task 트리플 적재              │
│       Google Slides 생성 + GitLab 저장소 생성                        │
│       status: confirmed                                              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 핵심 설계 원칙

### "LLM은 내용, 코드는 구조"

청킹 파이프라인은 **각자의 강점을 분리**해서 사용합니다:

| 책임 | LLM | 코드 |
|------|-----|------|
| 텍스트 분할 | ❌ | ✅ 요구사항 번호 기반 |
| 식별자(reqId/wbsCode) 부여 | ❌ | ✅ 순차 부여 |
| 요구사항 그룹화 (Large/Mid) | ❌ | ✅ tempId 기반 |
| 중복 제거 (dedup) | ❌ | ✅ tempId 기준 |
| Mid → WBS task 분해 | ❌ | ✅ assigneeType별 |
| 의존성(개발자→기획자) | ❌ | ✅ 자동 추가 |
| 요구사항 내용 추출 | ✅ | ❌ |
| 자연어 해석·요약 | ✅ | ❌ |
| 도메인 맥락 이해 | ✅ | ❌ |

이렇게 분리하면 청크 간 reqId 충돌, 일관성 없는 번호 매기기, LLM hallucination 같은 문제가 구조적으로 차단됩니다.

---

## 3. 단계별 상세

### Step 0. 업로드 — `POST /rfp/upload`

- 파일 텍스트 추출 (PDF/DOCX/HWP/TXT 지원, 최대 20MB)
- Fuseki에 `rfp_id`, `file_name`, `extracted_text`, `page_count`, `status="extracted"` 저장
- 응답에 `elapsed_seconds` 포함

---

### Step 1. 청킹 — 요구사항 번호 헤딩 기준

**함수**: `_split_by_requirement(text, max_chars=8000)` ([rfp_service.py](../backend/app/core/services/rfp_service.py))

#### 인식 prefix
```python
_REQ_PREFIXES = (
    "FUN", "PER", "INT", "DAR", "TER", "SER", "QUR",
    "COR", "PMR", "PSR", "ECR", "CNR", "NFR", "UIR", "REQ",
)
```

#### 동작
- 정규식 `(?=(?:FUN|PER|...)-\d+)`로 lookahead split → 각 요구사항이 별도 청크가 됨
- **각 요구사항 = 1 청크** (병합 없음, 오버랩 없음)
- 동일 요구사항이 두 청크에 걸치는 일이 발생하지 않음
- 첫 요구사항 이전 텍스트(사업 개요·목차)는 별도 청크 → projectInfo 추출에 활용
- 단일 요구사항이 8000자 초과해도 자르지 않음 (정보 손실 방지)

**예시 결과**:
```
청크 1: "사업 개요 / 추진 배경 / 사업 내용 ..." (FUN 이전 텍스트)
청크 2: "FUN-01 공통 요구사항 ..."
청크 3: "FUN-02 경제·금융 이슈사항 도출 ..."
...
청크 77: "PMR-07 검수 및 검사 요건 ..."
```

---

### Step 2. 프로젝트 정보 추출

**프롬프트**: `CHUNK_PROJECT_EXTRACT_SYSTEM` ([prompts.py](../backend/app/core/interpreter/prompts.py))

#### 추출 필드 (12개)

| 필드 | 설명 |
|------|------|
| `projectName` | 프로젝트명 |
| `projectAmount` | 사업 금액 (원 단위 정수) |
| `clientName` | 발주사 |
| `projectTheme` | 프로젝트 주제 (1~2문장) |
| `description` | 추진 배경 + 주요 사업 내용 + 사업 특성·제약 (요구사항 추출 시 컨텍스트로 활용됨) |
| `startDate` / `endDate` | YYYY-MM-DD |
| `contractType` | 계약 방식 |
| `businessType` | 사업 유형 |
| `budget` | 예산 표현 문자열 (원문 그대로) |
| `leadCompany` | 주관사 |
| `partnerCompanies` | 협력사 목록 |

#### 동작
- 모든 청크에 대해 **병렬** LLM 호출
- 청크마다 일부 필드만 채워질 수 있음 → `_merge_project_info`로 통합
- 필드별로 **가장 먼저 채워진 non-empty 값** 우선
- `partnerCompanies`는 청크 간 합집합 (중복 제거)
- `start_date` / `end_date`는 API 요청 body로 입력 시 LLM 값을 덮어씀

---

### Step 3. 요구사항 추출 — tempId 기반 식별

**프롬프트**: `CHUNK_REQ_EXTRACT_SYSTEM`

#### LLM 출력 필드 (reqId 없음)

LLM은 **`reqId`를 절대 생성하지 않습니다**. 대신:

| 필드 | 역할 |
|------|------|
| `tempId` | RFP 원문 번호(`"FUN-01"`) 또는 Mid 식별자(`"FUN-01:화면"`) |
| `parentTempId` | Large는 자기 자신, Mid는 부모 Large의 tempId |
| `isLarge` | true = Large, false = Mid |

#### 요구사항 식별 패턴 (CRITICAL-0)

정형 표 형식 블록만 요구사항으로 인식:
```
요구사항 분류 | 기능
요구사항 고유번호 | FUN-02
요구사항 명칭 | 경제·금융 이슈사항 도출
요구사항상세설명 | 정의 | ...
              | 세부내용 | ...
```

요구사항이 아닌 일반 본문/배경/안내 텍스트는 무시.

#### Large + Mid 분해 규칙 (CRITICAL-2)

각 RFP 요구사항(FUN-XX 하나)은 다음 구조로 분해:

**Large 1개** + **Mid N개** (세부내용 기반 분해)

| 분해 기준 | 적용 예시 |
|---|---|
| 구현 대상이 다름 | 화면 / API / AI 모델 |
| 담당 역할이 다름 | 기획자 vs 개발자 vs PM |
| 독립 완결 단위 | 하나의 Mid = 하나의 완결 산출물 |
| 과도한 세분화 금지 | 같은 역할 연속 작업은 통합 |

#### 코드 후처리: `_assign_req_ids`

```
LLM 출력 (tempId/parentTempId/isLarge)
   ↓
정규화 (snake_case, tempId 형식 통일: "FUN 02" / "FUN02" → "FUN-002")
   ↓
tempId 기준 dedup (더 풍부한 reqDescription+reqDetail 채택)
   ↓
Large/Mid 분리 (부모 없는 Mid는 Large로 승격)
   ↓
Large reqId 순차 부여: REQ-001, REQ-002, ...
   ↓
Mid reqId 부여: REQ-{parent_seq}-{mid_seq} (REQ-001-001, REQ-001-002, ...)
   ↓
related_req_ids 변환 (tempId → reqId 매핑 가능한 것만)
   ↓
내부 필드(temp_id/parent_temp_id/is_large) 제거
```

---

### Step 4. WBS 생성 — 코드가 분해, LLM은 내용

**프롬프트**: `CHUNK_WBS_GEN_SYSTEM`

#### 핵심 원칙

```
1 Mid req × assigneeType 수 = WBS task 수
```

**예시**:
- `REQ-001-001` (`assigneeType = ["기획", "개발-화면", "개발-비화면"]`)
  → 3개 WBS task 생성:
  - WBS-001 (기획자, devType=기획)
  - WBS-002 (개발자, devType=개발-화면)
  - WBS-003 (개발자, devType=개발-비화면)

#### assigneeType → assigneeRole 매핑 (코드 상수)

```python
ASSIGNEE_TYPE_TO_ROLE = {
    "PM": "PM",
    "기획": "기획자",
    "개발-화면": "개발자",
    "개발-비화면": "개발자",
}
```

"전체"는 4개 역할(PM + 기획 + 개발-화면 + 개발-비화면)로 분해.

#### 처리 흐름

```
Mid 요구사항만 필터 (req_id에 '-'가 2개 이상)
   ↓
_expand_to_wbs_skeletons (assigneeType당 1 skeleton)
   ↓
tempTaskId 부여 (T001, T002, ...)
   ↓
배치별 LLM 호출 (12개씩)
   LLM 입력: { tempTaskId, sourceReqId, assigneeRole, devType, _reqName, _reqDescription, _reqDetail }
   LLM 출력: { tempTaskId(echo), taskName, taskDescription, estimatedDays, plannedHours, plannedStart, plannedEnd, deliverables, dependsOn(tempTaskId 참조), evidence }
   ↓
코드 후처리:
   - wbsCode 부여 (WBS-001, WBS-002, ...)
   - skeleton + LLM 응답 병합
   - dependsOn 해소 (tempTaskId → wbsCode)
   - 자동 dep 보강 (같은 sourceReqId의 개발자 → 기획자)
   - 디버그용 임시 키 제거
```

LLM은 wbsCode·assigneeRole·task 분해를 결정하지 않음 (코드가 모두 담당).

---

## 4. 신뢰도 점수 (`confidence_score`)

### 4.1. 점수 산출 함수

**위치**: [`_calc_confidence`](../backend/app/core/services/rfp_service.py)

3개 항목을 각각 0~1로 계산한 뒤 **가중 평균**:

```
overall = project_score × 0.2 + req_score × 0.3 + wbs_score × 0.5
```

**가중치 근거**:
- **WBS (50%)** — 최종 산출물이라 사용자 가치가 가장 큼
- **요구사항 (30%)** — 분석의 핵심 콘텐츠
- **프로젝트 (20%)** — 메타 정보, 영향 상대적으로 작음

---

### 4.2. ① 프로젝트 추출 품질 (`project_extraction`)

#### 계산 공식

```
[필수] project_name + description 모두 있으면 baseline = 0.5
       하나라도 없으면 0점 (RFP 인식 자체가 실패한 신호)

[보조] 10개 보조 필드마다 각 +0.05 (최대 +0.5)
```

#### 보조 필드 (10개)
- `project_amount`, `client_name`, `project_theme`
- `start_date`, `end_date`, `budget`
- `contract_type`, `business_type`
- `lead_company`, `partner_companies`

#### 점수 해석

| 점수 | 의미 |
|------|------|
| 1.0 | 모든 12개 필드 추출 성공 |
| 0.5~0.9 | 필수 OK + 보조 일부 누락 (정상적인 RFP 다수가 여기) |
| 0.0 | project_name 또는 description 누락 — 분석 실패 의심 |

---

### 4.3. ② 요구사항 추출 품질 (`requirements_classification`)

> 이름은 레거시이지만 의미는 "요구사항 추출 품질"

#### 계산 공식

각 요구사항마다 3개 신호 중 채워진 비율 → 평균:

```python
per_req_score = (
    1 if req_description 있음 else 0 +
    1 if source_text 있음 else 0 +
    1 if assignee_type 비어있지 않음 else 0
) / 3

req_score = 평균(per_req_score)
```

#### 신호의 의미
- `req_description` — LLM이 요구사항 본문을 이해해서 요약했는지
- `source_text` — RFP 원문 grounding 여부 (hallucination 방지)
- `assignee_type` — Mid 분해 시 필수 (없으면 WBS 생성 불가)

#### 점수 해석

| 점수 | 의미 |
|------|------|
| 1.0 | 모든 요구사항이 완전 추출됨 |
| 0.7~0.9 | 일반적 |
| 0.5 미만 | 청크 해석 실패 빈번 — 청크 사이즈 조정 또는 재실행 권장 |

---

### 4.4. ③ WBS 채움 품질 (`wbs_accuracy`)

#### 계산 공식

LLM이 다음 3개를 모두 채운 WBS의 비율:
- `task_name` (단, fallback 패턴 `[devType] reqName` 제외)
- `task_description`
- `estimated_days`

```python
wbs_score = (LLM 완전 채움 WBS 수) / (전체 WBS 수)
```

#### fallback 감지 로직

코드가 LLM 응답 누락 시 자동으로 `"[개발-화면] 화면명"` 같은 형태로 채워주는데, 이 패턴(`[`로 시작하고 `] `를 포함)을 감지해서 "LLM이 응답 안 한 것"으로 카운트.

#### 점수 해석

| 점수 | 의미 |
|------|------|
| 1.0 | 모든 task를 LLM이 충실히 채움 |
| 0.5~0.9 | 일부 누락 — 사용 가능 |
| 0.0~0.5 | LLM 응답 다수 누락 — **재실행 강력 권장** |

---

### 4.5. 응답 구조

```json
{
  "confidence_score": 0.78,
  "analysis_metadata": {
    "confidence_score": 0.78,
    "confidence_breakdown": {
      "project_extraction": 0.85,
      "requirements_classification": 0.92,
      "wbs_accuracy": 0.70
    },
    "total_requirements": 24,
    "total_wbs_tasks": 54,
    "wbs_tasks_by_role": {"기획자": 18, "개발자": 28, "PM": 8},
    "total_estimated_days": 145.5,
    "total_planned_hours": 1164.0
  }
}
```

---

## 5. 점수별 가이드

### 종합 점수 활용 기준

| 종합 점수 | 사용자 액션 권장 |
|----------|----------------|
| **0.85 이상** | 그대로 검토 후 확정 진행 가능 |
| **0.65 ~ 0.85** | 일부 필드 수동 보완 후 확정 |
| **0.50 ~ 0.65** | breakdown 확인하여 약한 항목 집중 검토 또는 재실행 |
| **0.50 미만** | **재실행 강력 권장** — 청크 사이즈/프롬프트 조정 또는 RFP 텍스트 품질 확인 |

### breakdown 진단표

| 낮은 항목 | 가능한 원인 | 대응 |
|-----------|------------|------|
| `project_extraction` 낮음 | RFP 앞부분 사업 개요가 부실함 | `start_date`/`end_date`를 API에 직접 전달, 또는 다른 RFP 사용 |
| `requirements_classification` 낮음 | 요구사항 표 형식이 정형적이지 않음 | 프롬프트의 식별 마커 확장, 또는 수동 후처리 |
| `wbs_accuracy` 낮음 | LLM 응답이 batch마다 누락 | OpenAI rate limit 점검, max_tokens 증대, 모델 변경 검토 |

---

## 6. 로그 추적

분석 중 발생하는 모든 단계를 로그로 추적 가능:

```bash
# 단계별 진행 상황
docker logs <backend> 2>&1 | grep "\[ANALYZE-CHUNKED\]"

# 추출된 요구사항 (LLM 출력 직후)
docker logs <backend> 2>&1 | grep "\[REQ-EXTRACT\]"

# reqId 부여 후 dedup 결과
docker logs <backend> 2>&1 | grep "\[REQ-ASSIGN\]"

# WBS 생성 (skeleton 생성 + LLM 응답)
docker logs <backend> 2>&1 | grep "\[WBS-GEN\]"

# 프로젝트 정보 추출
docker logs <backend> 2>&1 | grep "\[PROJECT-EXTRACT\]"
```

### 로그 예시

```
============================================================
[ANALYZE-CHUNKED] 시작 rfp_id=RFP_016280E753 text_len=45120
============================================================
[ANALYZE-CHUNKED] Step 1/4 청킹 완료: chunks=77 (요구사항 번호 헤딩 기반, max_chars=8000)
[ANALYZE-CHUNKED] Step 2/4 프로젝트 정보 추출 시작
[PROJECT-EXTRACT] chunk=1/77 filled_fields=8 keys=['projectName', 'projectAmount', ...]
[PROJECT-EXTRACT] 병합 완료: project_name=HF 인사이트 시스템 개발 theme=경제·금융 키워드 분석 ...
[ANALYZE-CHUNKED] Step 3/4 요구사항 추출 시작
[REQ-EXTRACT] chunk=2/77 count=4
[REQ-EXTRACT]   - FUN-01 | 공통 요구사항 | type=기능 assignee=['PM', '개발-비화면']
...
[REQ-EXTRACT] 전체 추출 합계: 280 (assign 전)
[REQ-ASSIGN] 총 280개 입력 → dedup 4개 → 최종 276개 (Large 76, Mid 200)
[ANALYZE-CHUNKED] Step 4/4 WBS 생성 시작
[WBS-GEN] Mid 요구사항 200개에서 스켈레톤 생성
[WBS-GEN] 총 task 스켈레톤 510개 (Mid 200개 분해)
[WBS-GEN] 배치 시작 batch=1/43 tasks=12
[WBS-GEN] 배치 완료 batch=1/43 filled=12
...
[WBS-GEN] 최종 WBS task 510개 생성 (wbsCode WBS-001 ~ WBS-510)
============================================================
[ANALYZE-CHUNKED] 완료 rfp_id=RFP_016280E753 reqs=276 wbs=510 confidence=0.82
[ANALYZE-CHUNKED] 합계 estimated_days=2104.5 planned_hours=16836.0 breakdown={'project_extraction': 0.95, 'requirements_classification': 0.91, 'wbs_accuracy': 0.75}
============================================================
```

---

## 7. 참고: API 명세

### `POST /rfp/upload`

| 필드 | 타입 | 설명 |
|------|------|------|
| file | multipart | RFP 파일 (PDF/DOCX/HWP/TXT) |

**응답**: `rfp_id`, `file_name`, `extracted_text`, `page_count`, `status`, `elapsed_seconds`

### `POST /rfp/{rfp_id}/analyze-chunked`

```json
{
  "start_date": "2026-06-01",    // 선택. LLM 추출값 덮어씀
  "end_date": "2026-12-31"       // 선택
}
```

**응답**: `RfpAnalyzeResponse` (project + requirements + wbs + required_roles + confidence_score + analysis_metadata + elapsed_seconds)

### `PATCH /rfp/{rfp_id}/analysis`

부분 수정. `project` / `requirements` / `wbs` / `required_roles` / `consortium` 중 변경할 필드만 전송.

### `POST /rfp/{rfp_id}/confirm`

Fuseki 적재 + Google Slides 생성 + GitLab 저장소 생성. `confirmed` 상태로 전환.
