# RFP 분석 결과 수정 API 가이드

## `PATCH /rfp/{rfp_id}/analysis`

AI가 분석한 RFP 결과(프로젝트 개요, 요구사항, WBS, 필요 역할, 컨소시엄 정보)를 사용자가 직접 수정합니다.  
수정 완료 후 RFP 상태는 자동으로 `reviewed`로 전환됩니다.

---

## 요청

### Path Parameter

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `rfp_id` | string | ✅ | RFP ID (예: `RFP-2026-001`) |

### 인증
불필요

### Request Body

**모든 필드는 선택(Optional)이며, 변경할 필드만 포함해서 보내면 됩니다.**

| 필드 | 타입 | 설명 |
|------|------|------|
| `project` | `ProjectInfo` | 프로젝트 개요 정보 |
| `requirements` | `Requirement[]` | 요구사항 목록 (⚠️ 배열 전체 교체) |
| `wbs` | `WbsItem[]` | WBS 태스크 목록 (⚠️ 배열 전체 교체) |
| `required_roles` | `RequiredRole[]` | 필요 인력 역할 목록 (⚠️ 배열 전체 교체) |
| `consortium` | `ConsortiumInfo` | 컨소시엄 정보 |

#### ⚠️ 배열 필드 교체 규칙

`requirements`, `wbs`, `required_roles`는 **배열 전체가 교체**됩니다.  
한 항목만 수정하더라도 **전체 배열을 전송**해야 하며, 누락된 항목은 삭제됩니다.

#### tech_stack 보호 규칙

`project.tech_stack`을 **빈 배열 `[]`로 전송하면 기존 값이 유지**됩니다 (실수로 덮어쓰기 방지).
기존 값을 정말 지우려면 명시적으로 다른 값을 전송하거나 해당 필드를 보내지 마세요.

#### 상태 제약

- `confirmed` 상태의 RFP는 수정할 수 없습니다 (`409 Conflict`).

---

## 요청 예시

### 예시 1 — 프로젝트 개요만 수정

```json
PATCH /rfp/RFP-2026-001/analysis
Content-Type: application/json

{
  "project": {
    "project_name": "공공 의료 데이터 플랫폼 구축",
    "project_domain": "공공",
    "client_name": "보건복지부",
    "tech_stack": ["FastAPI", "React", "PostgreSQL"],
    "difficulty_level": "HIGH",
    "start_date": "2026-06-01",
    "end_date": "2026-12-31",
    "description": "공공 의료 데이터 기반 감염병 예측 플랫폼"
  }
}
```

### 예시 2 — 요구사항 전체 교체

```json
{
  "requirements": [
    {
      "req_id": "REQ-001",
      "req_name": "사용자 인증",
      "req_description": "이메일/비밀번호 및 소셜 로그인",
      "req_category": "기능",
      "importance": "필수",
      "priority": "상",
      "deliverables": ["로그인 화면설계서", "인증 API 명세서"],
      "related_req_ids": [],
      "source_text": "사용자는 이메일 및 소셜 로그인을 통해 시스템에 접근할 수 있어야 한다.",
      "inferred_from_context": false
    }
  ]
}
```

### 예시 3 — WBS 일부 수정 (전체 배열 전송 필수)

```json
{
  "wbs": [
    {
      "wbs_code": "REQ-001.BE.1",
      "req_id": "REQ-001",
      "task_name": "로그인 API 구현",
      "assignee_role": "백엔드",
      "estimated_days": 5,
      "planned_hours": 40,
      "planned_start": "2026-06-10",
      "planned_end": "2026-06-14",
      "deliverables": ["API 명세서", "구현 코드"],
      "depends_on": []
    }
  ]
}
```

### 예시 4 — 컨소시엄 정보 수정

```json
{
  "consortium": {
    "lead_company": "주관사ABC",
    "partner_companies": ["파트너1", "파트너2"]
  }
}
```

---

## 응답

### 성공 `200 OK`

```json
{
  "rfp_id": "RFP-2026-001",
  "status": "reviewed"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `rfp_id` | string | RFP ID |
| `status` | string | 변경 후 상태. 항상 `reviewed` |

### 에러

| 상태 코드 | 원인 |
|----------|------|
| `404 Not Found` | 존재하지 않는 `rfp_id` |
| `409 Conflict` | `confirmed` 상태의 RFP 수정 시도 |
| `422 Unprocessable Entity` | 필드 타입/형식 오류 |

```json
// 404 예시
{ "detail": "RFP를 찾을 수 없습니다: RFP-9999" }

// 409 예시
{ "detail": "confirmed 상태의 RFP는 수정할 수 없습니다" }
```

---

## 스키마 상세

### `ProjectInfo`

| 필드 | 타입 | 설명 |
|------|------|------|
| `project_name` | string | 프로젝트명 (필수) |
| `project_domain` | string \| null | 사업 분야 |
| `client_name` | string \| null | 발주처 |
| `contract_type` | string \| null | 계약 형태 |
| `business_type` | string \| null | 사업 유형 |
| `tech_stack` | string[] | 기술 스택. `[]` 전송 시 기존 값 유지 |
| `difficulty_level` | string \| null | `LOW` \| `MEDIUM` \| `HIGH` \| `CRITICAL` |
| `estimated_duration` | string \| null | 예상 기간 (예: `6개월`) |
| `budget` | string \| null | 예산 |
| `start_date` | string \| null | YYYY-MM-DD |
| `end_date` | string \| null | YYYY-MM-DD |
| `description` | string \| null | 프로젝트 설명 |

### `Requirement`

| 필드 | 타입 | 설명 |
|------|------|------|
| `req_id` | string | 요구사항 ID (필수, 예: `REQ-001`) |
| `req_category` | string \| null | 카테고리 (`기능`, `비기능`, `보안` 등) |
| `req_name` | string \| null | 요구사항명 |
| `req_description` | string \| null | 상세 설명 |
| `importance` | string \| null | `필수` \| `중요` \| `선택` |
| `priority` | string \| null | `상` \| `중` \| `하` |
| `deliverables` | string[] | 산출물 목록 |
| `related_req_ids` | string[] | 연관 요구사항 ID 목록 |
| `source_text` | string \| null | RFP 원문 인용 |
| `inferred_from_context` | bool | LLM 추론 여부 (기본 `false`) |

### `WbsItem`

| 필드 | 타입 | 설명 |
|------|------|------|
| `wbs_code` | string | WBS 코드 (필수, 예: `REQ-001.BE.1`) |
| `req_id` | string \| null | 연결된 요구사항 ID |
| `task_name` | string | 태스크명 (필수) |
| `assignee_role` | string \| null | 담당 역할 (`PM`, `기획자`, `디자이너`, `프론트엔드`, `백엔드`, `DBA`, `QA`, `인프라`) |
| `task_description` | string \| null | 태스크 설명 |
| `required_skills` | string[] | 필요 스킬 목록 |
| `estimated_days` | float \| null | 예상 작업일 |
| `planned_hours` | float \| null | 계획 공수 (시간) |
| `planned_start` | string \| null | YYYY-MM-DD |
| `planned_end` | string \| null | YYYY-MM-DD |
| `deliverables` | string[] | 산출물 목록 |
| `depends_on` | string[] | 선행 태스크의 `wbs_code` 목록 |
| `evidence` | `WbsEvidence` \| null | 생성 근거 정보 |

### `WbsEvidence`

| 필드 | 타입 | 설명 |
|------|------|------|
| `source_req_id` | string \| null | 근거 요구사항 ID |
| `source_text` | string \| null | 근거 원문 |
| `reasoning_step` | string \| null | 생성 근거 추론 단계 |

### `RequiredRole`

| 필드 | 타입 | 설명 |
|------|------|------|
| `role` | string | 역할명 (필수) |
| `count` | int | 필요 인원 수 (기본 1) |
| `skills` | string[] | 필요 스킬 목록 |

### `ConsortiumInfo`

| 필드 | 타입 | 설명 |
|------|------|------|
| `lead_company` | string \| null | 주관사명 |
| `partner_companies` | string[] | 참여 파트너사 목록 |

---

## 사용 흐름

```
1. POST /rfp/upload            → 파일 업로드 (status: extracted)
2. POST /rfp/{id}/analyze      → AI 분석 (status: analyzed)
3. PATCH /rfp/{id}/analysis    → 사용자 검토·수정 (status: reviewed)  ← 이 API
4. POST /rfp/{id}/confirm      → 확정 및 프로젝트 생성 (status: confirmed)
```

### 부분 수정 패턴 권장

- 프론트엔드에서는 `GET /rfp/{rfp_id}`로 현재 분석 결과를 가져온 뒤,
- 사용자가 수정한 섹션만 PATCH로 전송하는 패턴을 권장합니다.
- 단, `requirements`/`wbs`/`required_roles`는 부분 항목만 수정해도 **전체 배열을 전송**해야 합니다.

### 재분석과의 차이

- WBS만 다시 생성하고 싶다면 `POST /rfp/{id}/regenerate-wbs`를 사용하세요.
- 이 API는 사용자가 직접 편집한 결과를 저장하는 용도이며, AI를 호출하지 않습니다.
