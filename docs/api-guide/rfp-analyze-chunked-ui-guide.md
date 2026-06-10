# [프론트 가이드] RFP 청킹 분석 화면 — `/rfp/{rfp_id}/analyze-chunked`

이 문서는 `POST /rfp/{rfp_id}/analyze-chunked` API를 사용해 **RFP 분석 결과를 화면에 보여주는 페이지**를 만들 때 참고할 수 있도록 작성한 가이드입니다. 특정 프레임워크를 가정하지 않으며 데이터 구조, 화면 패턴, 인터랙션 원칙만 설명합니다. 기존 구현은 무시하고 새로 작성하는 것을 전제로 합니다.

---

## 1. API 개요

| 항목 | 내용 |
|------|------|
| **메서드** | `POST` |
| **경로** | `/rfp/{rfp_id}/analyze-chunked` |
| **인증** | 불필요 (현재 정책) |
| **처리 시간** | 평균 30초 ~ 2분 (LLM 다중 호출). 길어질 수 있음 |
| **선행 조건** | `/rfp/upload`로 RFP 파일 업로드 완료 상태 (`extracted`) |
| **후속 단계** | `/rfp/{rfp_id}/patch` (검토 수정) → `/rfp/{rfp_id}/confirm` (프로젝트 생성) |

분석 단계 (서버 내부):
1. 요구사항 번호 기반 청킹 (예: `FUN-01`, `PER-02` 헤딩으로 분할)
2. 청크별 프로젝트 정보 추출
3. 청크별 요구사항 추출 (병렬)
4. 요구사항 배치별 WBS 생성

---

## 2. 요청 형식

### Body (선택)

```json
{
  "start_date": "2026-06-01",
  "end_date": "2026-12-31"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `start_date` | string (YYYY-MM-DD) | - | 프로젝트 시작일. 미입력 시 LLM 추출값 사용 |
| `end_date` | string (YYYY-MM-DD) | - | 프로젝트 종료일. 미입력 시 LLM 추출값 사용 |

> 📌 두 날짜를 모두 입력하면 WBS 일정 산출이 더 정확합니다. 사용자가 사전에 일정을 알고 있을 때 입력하도록 UI에서 권장하세요.

### 호출 예시

```js
const res = await fetch(`/rfp/${rfpId}/analyze-chunked`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ start_date, end_date }),  // 비워 보내려면 {}
});
const result = await res.json();
```

---

## 3. 응답 구조

응답은 `RfpAnalyzeResponse` 형식이며 5개의 주요 영역으로 구성됩니다.

```jsonc
{
  "rfp_id": "RFP-001",
  "status": "analyzed",
  "elapsed_seconds": 47.213,

  "project": { ... },                  // 프로젝트 개요
  "requirements": [ ... ],             // 요구사항 목록 (Large + Mid 혼재, req_id 명명으로 구분)
  "wbs": [ ... ],                      // WBS 태스크 목록
  "required_roles": [ ... ],           // 역할별 필요 인원
  "confidence_score": 0.78,            // 종합 신뢰도 (0.0~1.0)
  "analysis_metadata": {
    "total_requirements": 24,
    "total_wbs_tasks": 38,
    "wbs_tasks_by_role": { "PM": 4, "개발자": 28, "기획자": 6 },
    "total_estimated_days": 412.5,
    "total_planned_hours": 3300,
    "confidence_score": 0.78,
    "confidence_breakdown": {
      "project_extraction": 0.85,
      "requirements_classification": 0.72,
      "wbs_accuracy": 0.78
    },
    "low_confidence_items": [ ... ],
    "assumptions": [ "휴일 없음 가정", "..." ]
  }
}
```

### 3-1. `project` (프로젝트 개요)

| 필드 | 타입 | 설명 |
|------|------|------|
| `project_name` | string | 프로젝트명 |
| `project_amount` | number? | 프로젝트 금액 (원) |
| `client_name` | string? | 발주사 |
| `project_theme` | string? | 프로젝트 주제 |
| `project_domain` | string? | 사업 분야 (예: 공공, 금융) |
| `description` | string? | 상세 설명 |
| `start_date` / `end_date` | string? (YYYY-MM-DD) | 일정 |
| `contract_type` | string? | 계약 방식 |
| `business_type` | string? | 사업 유형 |
| `budget` | string? | 예산 표현 |
| `lead_company` | string? | 주관사 |
| `partner_companies` | string[] | 협력사 |

### 3-2. `requirements` (요구사항)

**평탄 배열**입니다. 대분류/중분류는 `req_id` 명명으로만 구분됩니다.
- `REQ-001` (토큰 2개) = 대분류
- `REQ-001-001` (토큰 3개) = 중분류 (부모 = `REQ-001`)

| 필드 | 타입 | 설명 |
|------|------|------|
| `req_id` | string | 요구사항 ID |
| `req_name` | string? | 요구사항명 |
| `req_description` | string? | 내용 |
| `req_detail` | string? | 세부 내용 |
| `requirement_type` | string? | `기능` / `비기능` |
| `req_category` | string? | (레거시) |
| `assignee_type` | string[] | `["기획", "개발-화면", "개발-비화면", "PM"]` 일부 |
| `user_type` | string[] | 사용자 유형 |
| `priority` | string? | `CRITICAL` / `HIGH` / `MEDIUM` / `LOW` |
| `importance` | string? | 중요도 |
| `deliverables` | string[] | 산출물 |
| `related_req_ids` | string[] | 관련 요구사항 ID |
| `source_text` | string? | LLM이 발췌한 원문 짧은 인용 (최대 200자) |
| `source_chunk_index` | number? | 출처 청크 번호 (0-based) |
| `source_chunk_text` | string? | 출처 청크 전체 원문 (UI 추적용) |
| `inferred_from_context` | boolean | 원문 명시 없이 LLM이 맥락으로 추론한 항목인지 |
| `notes` | string? | 비고 |

> 💡 화면에서 트리로 그릴 때는 `req_id`를 `-`로 split해 토큰 수가 3 이상이면 Mid로 분류하고, 앞 두 토큰을 부모 Large로 매칭합니다. 자세한 패턴은 [project-detail-requirements-ui-guide.md](project-detail-requirements-ui-guide.md) 참고.

### 3-3. `wbs` (WBS 태스크)

| 필드 | 타입 | 설명 |
|------|------|------|
| `wbs_code` | string | `1.1`, `1.2` 등 |
| `req_id` | string? | 연결된 요구사항 ID (보통 Mid) |
| `task_name` | string | 업무명 |
| `assignee_role` | string? | 담당 역할 |
| `task_description` | string? | 업무 설명 |
| `required_skills` | string[] | 필요 스킬 |
| `estimated_days` | number? | 예상 M/D |
| `planned_hours` | number? | 예상 시간 |
| `planned_start` / `planned_end` | string? (YYYY-MM-DD) | 코드가 산출한 일정 |
| `deliverables` | string[] | 산출물 |
| `depends_on` | string[] | 선행 `wbs_code` 목록 |
| `phase` | string? | `foundation` / `core` / `feature` / `closing` |
| `criticality` | string? | `blocker` / `core` / `normal` |
| `risk` | string? | `high` / `low` |
| `evidence` | object? | `{ source_req_id, source_text, reasoning_step }` |

### 3-4. `required_roles` (역할별 인원)

| 필드 | 타입 | 설명 |
|------|------|------|
| `role` | string | 역할명 (PM, 기획자, 개발자 등) |
| `count` | number | 필요 인원 |
| `skills` | string[] | 필요 스킬 |
| `mm` | number? | 총 M/M (22영업일 = 1 M/M) |
| `total_days` | number? | 총 M/D |
| `total_hours` | number? | 총 M/H |
| `task_count` | number? | 담당 WBS task 수 |
| `breakdown` | object? | 산정 근거 (project_biz_days / utilization_rate / effective_days / parallel_buffer / raw_count) |

### 3-5. `analysis_metadata` (분석 메타)

신뢰도, 통계, 가정사항을 담습니다.

| 필드 | 설명 |
|------|------|
| `total_requirements` | 총 요구사항 수 |
| `total_wbs_tasks` | 총 WBS 수 |
| `wbs_tasks_by_role` | 역할별 task 개수 맵 |
| `total_estimated_days` | 전체 M/D 합 |
| `total_planned_hours` | 전체 M/H 합 |
| `confidence_score` | 종합 신뢰도 (0~1) |
| `confidence_breakdown` | 3축 분해 — project/requirements/wbs 별 점수 |
| `low_confidence_items` | 점수가 낮아 검토 권장되는 항목들 |
| `assumptions` | 분석 시 적용한 가정사항 (문자열 배열) |

---

## 4. 화면 구성 권장

전체를 5개 섹션으로 나눠 한 페이지에 길게 스크롤하거나, 탭으로 분리합니다.

```
┌─ 헤더 ────────────────────────────────────────────────┐
│ RFP-001 분석 결과    소요 47.2초    신뢰도 78% [확정] │
└───────────────────────────────────────────────────────┘
│
├─ ① 프로젝트 개요 (project)
├─ ② 요구사항 (requirements, 대/중 트리)
├─ ③ WBS 태스크 (wbs, 요구사항-Task 3단계 또는 단순 리스트)
├─ ④ 필요 인력 (required_roles)
└─ ⑤ 분석 메타 (analysis_metadata)
```

### 4-1. 헤더 — 항상 보이는 상단 영역
- `rfp_id`, 파일명(별도 GET 필요), 분석 소요 시간(`elapsed_seconds`)
- 종합 신뢰도 뱃지 — 색상은 임계값에 따라:
  - 0.80~ : 초록 (양호)
  - 0.60~0.79 : 노랑 (검토 필요)
  - ~0.59 : 빨강 (재분석 권장)
- 우측에 액션 버튼: **재분석** / **수정 저장(patch)** / **확정(confirm)**

### 4-2. 프로젝트 개요 (`project`)
- 카드형 2열 그리드. 필드명-값 쌍.
- `start_date`, `end_date`는 입력 가능한 폼으로 노출하고 변경 시 별도 patch API 호출 (선택 사항).
- 빈 값 필드는 회색 placeholder "—" 또는 "(미상)" 처리.

### 4-3. 요구사항 (`requirements`)
- **대분류/중분류 트리** — 응답이 평탄 배열이므로 클라이언트에서 `req_id` 파싱으로 트리화.
- 트리화 규칙은 [project-detail-requirements-ui-guide.md](project-detail-requirements-ui-guide.md) 참고.
- 각 요구사항 행에서 **원문 인용(`source_text`)** 을 작은 회색 텍스트로 노출.
- 클릭 시 사이드패널 또는 모달에서 **출처 청크 전체(`source_chunk_text`)** 표시 — 사용자가 RFP 원문 어디서 추출됐는지 확인 가능.
- `inferred_from_context: true` 인 항목은 작은 ⚠️ 아이콘 + 툴팁("원문 명시 없이 추론된 항목")으로 표시.

### 4-4. WBS 태스크 (`wbs`)
- 3단계 트리 (요구사항 대분류 > 중분류 > Task)로 그리려면 [wbs-gantt-3level-ui-guide.md](wbs-gantt-3level-ui-guide.md) 참고.
- 또는 분석 결과 페이지에서는 단순 테이블로 충분 (확정 후 프로젝트 페이지에서 풀 트리 제공).
- 컬럼 권장: `wbs_code` / `task_name` / `assignee_role` / `estimated_days` / `planned_start ~ planned_end` / 의존 / `phase` 뱃지
- `risk: high`인 task는 행 좌측에 빨간 막대 또는 배경색 강조.
- `criticality: blocker`인 task는 별도 배지("막힘 위험").

### 4-5. 필요 인력 (`required_roles`)
- 카드 또는 표.
- `role` × `count` 큰 글씨로 강조 + `mm` (M/M) 표시.
- `breakdown` 확장 시 산정 공식 노출:
  ```
  영업일 130 × 가용률 0.8 = 유효일 104
  → 병렬 버퍼 1.2 적용 → raw_count = 1.5 → ⌈1.5⌉ = 2명
  ```
- `skills` 칩 나열.

### 4-6. 분석 메타 (`analysis_metadata`)
- **신뢰도 3축 그래프** — `confidence_breakdown`의 3개 값을 가로 막대 또는 레이더 차트로 시각화:
  - project_extraction (프로젝트 추출)
  - requirements_classification (요구사항 분류)
  - wbs_accuracy (WBS 정확도)
- **저신뢰도 항목** (`low_confidence_items`) — 클릭 시 해당 항목으로 스크롤/하이라이트.
- **가정사항** (`assumptions`) — 불릿 리스트.
- 총계 4종 — total_requirements / total_wbs_tasks / total_estimated_days / total_planned_hours 를 통계 카드로.

---

## 5. 로딩 / 진행 상태 UI

LLM 호출이 길어 사용자 체감 대기 시간이 큽니다. 다음 패턴 권장:

1. **버튼 비활성화 + 스피너** — 분석 중에는 재시도 클릭 방지.
2. **단계 진행 텍스트** (가짜 진행 표시여도 UX 개선):
   ```
   "RFP 청킹 중..."  →  "프로젝트 정보 추출 중..."
   →  "요구사항 추출 중..."  →  "WBS 생성 중..."
   ```
   서버가 단계 이벤트를 주지 않으므로 클라이언트에서 **타이머 기반으로 메시지를 순차 갱신**해도 무방.
3. **예상 시간 안내** — "보통 30초~2분 소요됩니다" 같은 가이드 문구.
4. **취소 기능** — `AbortController`로 fetch abort. 서버는 이미 시작된 작업을 중단하지 않으므로 클라이언트만 종료.

---

## 6. 에러 처리

| 상태 코드 | 의미 | UI 처리 |
|----------|------|--------|
| `404 Not Found` | 존재하지 않는 `rfp_id` | "RFP를 찾을 수 없습니다" 메시지 + 업로드 페이지로 이동 |
| `400 Bad Request` | `extracted_text` 없음 등 선행 조건 미충족 | "RFP 업로드를 먼저 완료해주세요" |
| `500 Internal Server Error` | LLM 호출 실패 / 파싱 실패 | "분석 중 오류가 발생했습니다. 재시도해주세요" + 재시도 버튼 |
| `503 Service Unavailable` | Fuseki/LLM 일시 불가 | "잠시 후 다시 시도해주세요" |
| `504 Gateway Timeout` | 분석 시간 초과 | "분석이 지연되고 있습니다. 잠시 후 다시 시도해주세요" |

부분 실패(예: WBS만 비어있음)는 200으로 떨어질 수 있으므로 응답을 받은 뒤 `total_wbs_tasks === 0` 같은 케이스도 안내합니다.

---

## 7. 후속 액션 — 수정/확정

| 액션 | API | 시점 |
|------|-----|------|
| 분석 결과 수정 | `POST /rfp/{rfp_id}/patch` | 사용자가 요구사항/WBS 등을 편집 후 저장 |
| WBS 재생성 | `POST /rfp/{rfp_id}/regenerate-wbs` | 요구사항만 수정한 뒤 WBS만 다시 만들고 싶을 때 |
| 프로젝트로 확정 | `POST /rfp/{rfp_id}/confirm` | Fuseki에 적재 + GitLab 저장소 + Google Slides 생성 |

확정 버튼은 신뢰도가 낮을 때 확인 다이얼로그를 띄우길 권장:
> "종합 신뢰도가 65%로 낮습니다. 일부 항목 검토 후 확정을 진행하시겠습니까?"

---

## 8. 자주 묻는 질문

**Q. `analysis_metadata`가 null로 올 수도 있나요?**
A. 정상 응답에서는 항상 들어옵니다. 하위 필드는 기본값이 채워져 있으므로 별도 null 체크는 최소화해도 됩니다.

**Q. 요구사항이 평탄 배열인데 트리로 어떻게?**
A. `req_id` split — 토큰 3개 이상 = Mid. 앞 두 토큰 join = 부모 Large. 자세한 패턴은 별도 가이드 참조.

**Q. `wbs_tasks_by_role`의 키는 어떤 값들인가요?**
A. 백엔드는 PM / 기획자 / 개발자 3개 역할을 기본 사용합니다 (`backend/db/seeds/002_persons.ttl` 기준). RFP에 따라 다른 역할명이 섞일 수 있으니 동적으로 key를 순회하세요.

**Q. `elapsed_seconds`는 항상 들어오나요?**
A. `/analyze-chunked` 응답에는 항상 들어옵니다. 다른 분석 엔드포인트(`/analyze`, `/analyze-staged`)는 들어오지 않을 수 있어 옵셔널 체크 권장.

**Q. 같은 RFP를 다시 분석하면 결과가 덮어쓰여지나요?**
A. 네. 백엔드가 새 `analysis_json`으로 교체합니다. 사용자 편집 내용은 사라지므로 재분석 전 경고 다이얼로그 권장.

**Q. `inferred_from_context: true`인 요구사항은 어떻게 처리해야 하나요?**
A. UI에 ⚠️ 표시 + 사용자에게 "원문에 명시되어 있지 않은 추론 항목"이라고 안내해 검토 후 확정하도록 유도합니다.

---

## 9. AI 코드 에이전트 작업 지시 프롬프트

이 문서를 참조해서 화면을 만들 때 그대로 복사해서 쓸 수 있는 프롬프트입니다.

> "RFP 분석 결과 화면을 새로 만들어줘. 데이터 소스는 `POST /rfp/{rfp_id}/analyze-chunked` 응답이다.
>
> 응답 구조와 각 영역의 의미·필드는 `docs/api-guide/rfp-analyze-chunked-ui-guide.md`를 따른다. 핵심:
> - 응답은 `project`, `requirements`, `wbs`, `required_roles`, `analysis_metadata` 5개 섹션과 `confidence_score`, `elapsed_seconds` 헤더 정보로 구성
> - `requirements`는 평탄 배열이지만 화면에서는 `req_id` 명명 규약으로 대/중 트리화
> - 각 요구사항의 `source_text`와 `source_chunk_text`로 출처 청크 추적 UI 제공
> - `inferred_from_context: true`는 ⚠️ 아이콘으로 강조
> - WBS는 단순 테이블로 충분 (3단계 트리는 확정 후 별도 화면)
> - `confidence_breakdown` 3축은 막대/레이더로 시각화
> - 상단 헤더에 재분석/수정저장/확정 액션 버튼 노출
>
> 추가 요구사항:
> - 분석 호출 중에는 단계 메시지를 타이머 기반으로 순차 갱신해서 사용자 대기감 완화
> - 응답 후 페이지에 진입했을 때 신뢰도 70% 미만이면 상단에 안내 배너 노출
> - 확정 버튼은 신뢰도 60% 미만이면 확인 다이얼로그 추가
>
> 기존 분석 결과 페이지 구현이 있더라도 무시하고 새로 작성. 응답의 모든 필드를 반드시 화면에 노출할 필요는 없고, 위 가이드의 4번 절에 정리된 권장 항목을 우선 노출하면 된다.

요구사항/WBS 영역의 트리 구조·들여쓰기·행 종류 분기 패턴은 project-detail-requirements-ui-guide.md 와 wbs-gantt-3level-ui-guide.md 를 동일하게 따른다. 단, 분석 결과는 ① requirements가 평탄 배열이므로 클라이언트에서 req_id 토큰 수로 트리화하고, ② WBS에는 task_id/status/progress/assignee가 없으므로 상태·진행률·담당자 컬럼은 숨기고 assignee_role·phase·risk 뱃지로 대체한다.
"

---

## 10. 관련 문서

- [api-guide-rfp-analysis-patch.md](api-guide-rfp-analysis-patch.md) — 분석 결과 수정 API
- [rfp-analysis-process.md](../rfp-analysis-process.md) — 분석 파이프라인 상세 (백엔드 관점)
- [project-detail-requirements-ui-guide.md](project-detail-requirements-ui-guide.md) — 요구사항 대/중 트리 렌더링 공통 가이드
- [wbs-gantt-3level-ui-guide.md](wbs-gantt-3level-ui-guide.md) — 요구사항 ▸ WBS 3단계 트리 가이드
- [rfp-viewer.html](../rfp-viewer.html) — 동작하는 참조 구현 (JSON 붙여넣어 시각화)
