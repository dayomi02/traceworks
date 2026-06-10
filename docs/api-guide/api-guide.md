# Traceworks MVP — 화면별 API 사용 가이드

> RFP 파일 업로드부터 인력 추천 확정까지, 5단계 위자드 플로우 기준으로 각 화면에서 호출해야 하는 API를 설명합니다.

---

## 전체 플로우 개요

```
[1] 프로젝트 개요  →  [2] 요구사항 분석  →  [3] WBS 일정 분석  →  [4] 인력 추천  →  [5] 등록 완료
```

각 단계는 하나의 `rfp_id`(또는 `project_id`)를 공유하며, 이전 단계의 결과가 다음 단계로 전달됩니다.

---

## 화면 1 — 프로젝트 개요

### 개요

사용자가 RFP 파일(PDF / DOCX / HWP)을 업로드하면 텍스트를 추출하고, AI가 프로젝트 개요를 자동 분석합니다. 분석 결과를 확인·수정한 뒤 다음 단계로 넘어갑니다.

### 1단계: RFP 파일 업로드

**파일 선택 후 업로드 버튼 클릭 시 호출**

```
POST /rfp/upload
Content-Type: multipart/form-data
```

**Request**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `file` | `UploadFile` | ✅ | PDF / DOCX / HWP, 최대 20MB |

**Response**

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "file_name": "자재료 통합 관리 시스템 구축 제안서.pdf",
  "extracted_text": "본 사업은...(추출된 전문)",
  "page_count": 42,
  "status": "extracted"
}
```

> `rfp_id`를 로컬 상태에 저장해 이후 모든 API 호출에 사용합니다.

**에러 처리**

| HTTP | 원인 | 처리 |
|------|------|------|
| 400 | 빈 파일 | "파일이 비어 있습니다" 안내 |
| 413 | 20MB 초과 | "파일 크기 초과" 안내 |
| 415 | 지원하지 않는 형식 | "PDF, DOCX, HWP만 지원합니다" 안내 |

---

### 2단계: AI 분석 실행

**업로드 완료 직후 자동 호출 (또는 "AI 분석 시작" 버튼 클릭 시)**

```
POST /rfp/{rfp_id}/analyze
```

**Request**

| 파라미터 | 위치 | 설명 |
|---------|------|------|
| `rfp_id` | Path | 업로드에서 받은 ID |

**Response**

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "analyzed",
  "project": {
    "project_name": "자재료 통합 관리 시스템 구축",
    "project_domain": "공공/시스템 구축",
    "client_name": "한국자재관리원",
    "contract_type": "일반경쟁입찰",
    "business_type": "공공/시스템 구축",
    "tech_stack": ["Java", "Spring Boot", "Oracle"],
    "difficulty_level": "상",
    "estimated_duration": "8개월",
    "budget": "1,200,000,000",
    "start_date": "2025-01-01",
    "end_date": "2025-08-31",
    "description": "업무 프로세스 통합 및 자동화 관련 시스템 구축"
  },
  "requirements": [...],
  "wbs": [...],
  "required_roles": [
    { "role": "PM", "count": 1, "skills": ["프로젝트 관리"] },
    { "role": "개발자", "count": 4, "skills": ["Java", "Spring Boot"] }
  ],
  "confidence_score": 0.88,
  "analysis_metadata": {
    "total_requirements": 20,
    "total_wbs_tasks": 47,
    "wbs_tasks_by_role": { "PM": 5, "개발자": 25, "QA": 8 },
    "total_estimated_days": 120,
    "total_planned_hours": 960,
    "confidence_score": 0.88,
    "low_confidence_items": [],
    "assumptions": []
  }
}
```

**화면 표시 매핑**

| UI 항목 | 응답 필드 |
|---------|-----------|
| 프로젝트명 | `project.project_name` |
| 발주사명 | `project.client_name` |
| 프로젝트 금액 | `project.budget` |
| 계약 방식 | `project.contract_type` |
| 사업 유형 | `project.business_type` |
| 프로젝트 기간 | `project.start_date` ~ `project.end_date` |
| AI 분석 요약 카드 (예산/기간/WBS/인력) | `project.budget`, `project.estimated_duration`, `analysis_metadata.total_wbs_tasks`, `required_roles[].count` 합계 |
| AI 분석 신뢰도 게이지 | `analysis_metadata.confidence_score` |
| 분석 완료 파일명 | `file_name` |

---

### 3단계: 분석 결과 수정 후 저장

**사용자가 프로젝트 정보 및 주관사·협력사 정보를 입력하고 "저장 및 다음" 클릭 시 호출**

```
PATCH /rfp/{rfp_id}/analysis
Content-Type: application/json
```

**Request Body** — 변경한 필드만 포함, 나머지는 생략

```json
{
  "project": {
    "project_name": "수정된 프로젝트명",
    "client_name": "수정된 발주사",
    "budget": "1,500,000,000",
    "start_date": "2025-02-01",
    "end_date": "2025-09-30",
    "contract_type": "수의계약",
    "business_type": "민간/SaaS"
  },
  "consortium": {
    "lead_company": "(주)케이고솔루션",
    "partner_companies": ["협력사A", "협력사B"]
  }
}
```

**consortium 필드 설명**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `consortium.lead_company` | string | - | 주관사명 |
| `consortium.partner_companies` | string[] | - | 협력사명 목록 (화면상 협력사 1, 협력사 2, ...) |

> - `consortium`은 AI 분석 결과에 포함되지 않습니다. 사용자가 직접 입력한 값만 저장됩니다.
> - 협력사가 없으면 `partner_companies`를 빈 배열 `[]`로 전송하거나 `consortium` 자체를 생략할 수 있습니다.
> - 수정 없이 다음 단계로 이동하는 경우 이 API 호출을 건너뛸 수 있습니다.

**Response**

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "reviewed"
}
```

---

### 화면 재진입 시 기존 데이터 복원

**브라우저 새로고침 또는 이전 단계에서 돌아올 때**

```
GET /rfp/{rfp_id}
```

**Response** — `RfpDetail` (화면 1~3 전체 데이터 포함)

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "file_name": "자재료 통합 관리 시스템 구축 제안서.pdf",
  "status": "reviewed",
  "page_count": 42,
  "created_at": "2025-01-15T09:30:00Z",
  "project": { ... },
  "requirements": [...],
  "wbs": [...],
  "required_roles": [...],
  "consortium": {
    "lead_company": "(주)케이고솔루션",
    "partner_companies": ["협력사A", "협력사B"]
  },
  "confidence_score": 0.88,
  "analysis_metadata": { ... },
  "confirmed_project_id": null
}
```

---

## 화면 2 — 요구사항 분석

### 개요

AI가 추출한 요구사항 목록을 표시합니다. 사용자는 각 요구사항의 중요도·우선도를 수정하거나, 요구사항을 추가·삭제할 수 있습니다.

### 요구사항 목록 표시

**화면 진입 시 — 화면 1에서 분석 결과를 받았다면 재호출 불필요, 상태 공유**

이미 받은 `analyze` 또는 `GET /rfp/{rfp_id}` 응답의 `requirements` 배열을 사용합니다.

**요구사항 항목 구조**

```json
{
  "req_id": "REQ-001",
  "req_category": "기능",
  "req_name": "사용자 로그인 기능",
  "req_description": "사용자 ID/PW 및 소셜 로그인(카카오·네이버) 지원",
  "importance": "높음",
  "priority": "상",
  "deliverables": ["로그인 화면", "인증 API"],
  "related_req_ids": [],
  "source_text": "원문 발췌...",
  "inferred_from_context": false
}
```

**화면 표시 매핑**

| UI 항목 | 응답 필드 |
|---------|-----------|
| 요구사항 ID | `req_id` |
| 요구사항 내용 | `req_description` |
| 유형 배지 (기능/비기능) | `req_category` |
| 중요도 배지 (높음/중간/낮음) | `importance` |
| 우선도 배지 (상/중/하) | `priority` |
| 비고 | `deliverables` 목록 |
| 전체 건수 | `analysis_metadata.total_requirements` |

---

### 요구사항 수정 / 추가 / 삭제

**"수정" 버튼 클릭 후 변경 저장, 또는 "요구사항 추가" 후 저장 시**

```
PATCH /rfp/{rfp_id}/analysis
Content-Type: application/json
```

> 개별 항목 수정이 불가하므로, 현재 전체 `requirements` 배열에 변경 사항을 반영한 뒤 전체를 전송합니다.

**수정 예시 (우선도·중요도 변경)**

```json
{
  "requirements": [
    {
      "req_id": "REQ-001",
      "req_category": "기능",
      "req_name": "사용자 로그인 기능",
      "req_description": "사용자 ID/PW 및 소셜 로그인 지원",
      "importance": "높음",
      "priority": "상"
    },
    {
      "req_id": "REQ-002",
      "req_category": "기능",
      "req_name": "관한 관리 기능",
      "req_description": "관리자 역할 기반 접근 제어",
      "importance": "중간",
      "priority": "중"
    }
  ]
}
```

**요구사항 추가 예시** — 새 항목을 배열 끝에 포함

```json
{
  "requirements": [
    ... (기존 항목 전체),
    {
      "req_id": "REQ-011",
      "req_category": "기능",
      "req_name": "신규 요구사항명",
      "req_description": "사용자가 직접 추가한 요구사항",
      "importance": "중간",
      "priority": "중"
    }
  ]
}
```

**요구사항 삭제** — 해당 항목을 배열에서 제외한 뒤 전체 전송

**Response**

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "reviewed"
}
```

---

### "AI WBS 생성하기" 버튼 — 다음 화면으로 이동

현재 화면에서 별도 API 호출은 없습니다. 수정 완료 후 화면 3으로 이동 시 WBS 분석 API를 호출합니다.

---

## 화면 3 — WBS 일정 분석

### 개요

AI가 요구사항을 기반으로 생성한 WBS를 간트 차트 형태로 표시합니다. 항목별 담당자·일정을 수정할 수 있으며, AI 재생성도 가능합니다.

### WBS 목록 표시

**화면 진입 시 — 이미 받은 `analyze` 응답의 `wbs` 배열 사용**

재진입 시에는 `GET /rfp/{rfp_id}` 응답의 `wbs` 배열을 사용합니다.

**WBS 항목 구조**

```json
{
  "wbs_code": "REQ-001.PM.1",
  "req_id": "REQ-001",
  "task_name": "프로젝트 계획 수립",
  "assignee_role": "PM",
  "task_description": "전체 일정, 자원 계획, 리스크 정의",
  "required_skills": ["프로젝트 관리", "일정 관리"],
  "estimated_days": 10,
  "planned_hours": 80,
  "deliverables": ["프로젝트 계획서", "WBS 일정표"],
  "depends_on": [],
  "evidence": {
    "source_req_id": "REQ-001",
    "source_text": "프로젝트 착수 시 계획 수립 필요",
    "reasoning_step": "PM이 전체 프로젝트 기간을 관리하기 위한 선행 작업"
  }
}
```

**화면 표시 매핑 (간트 차트)**

| UI 항목 | 응답 필드 |
|---------|-----------|
| 업무명 | `task_name` |
| 담당자 | `assignee_role` |
| 간트 바 위치 | `depends_on` 기반 선후 관계 계산 |
| 간트 바 길이 | `estimated_days` |
| 상태 | `planned_hours` 기반 또는 별도 상태 관리 |
| WBS 계층 구조 | `wbs_code` 앞 숫자(REQ-001, REQ-002...) 기준 그룹핑 |
| 전체 항목 수 | `analysis_metadata.total_wbs_tasks` |

---

### WBS AI 재생성

**"AI 재생성" 버튼 클릭 시 호출**

```
POST /rfp/{rfp_id}/regenerate-wbs
```

**Request**

| 파라미터 | 위치 | 설명 |
|---------|------|------|
| `rfp_id` | Path | 현재 RFP ID |

**Response**

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "analyzed",
  "wbs": [
    {
      "wbs_code": "REQ-001.PM.1",
      "task_name": "재생성된 WBS 항목",
      ...
    }
  ],
  "analysis_metadata": {
    "total_wbs_tasks": 52,
    ...
  }
}
```

> 재생성 결과로 화면의 WBS 목록을 전체 교체합니다. 기존에 수정한 내용은 사라지므로, 재생성 전 사용자에게 확인 다이얼로그를 표시하세요.

---

### WBS 항목 수정

**항목 클릭 후 인라인 편집, "저장" 클릭 시 호출**

```
PATCH /rfp/{rfp_id}/analysis
Content-Type: application/json
```

> 전체 `wbs` 배열을 교체합니다. 수정된 항목을 반영한 전체 배열을 전송하세요.

**Request Body**

```json
{
  "wbs": [
    {
      "wbs_code": "REQ-001.PM.1",
      "task_name": "프로젝트 계획 수립",
      "assignee_role": "PM",
      "estimated_days": 15,
      "planned_hours": 120,
      "depends_on": []
    },
    ...
  ]
}
```

**Response**

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "reviewed"
}
```

---

### 프로젝트 확정 (저장 및 다음)

**WBS 확인 완료 후 "저장 및 다음" 버튼 클릭 시 호출**

```
POST /rfp/{rfp_id}/confirm
```

**Request**

| 파라미터 | 위치 | 설명 |
|---------|------|------|
| `rfp_id` | Path | 현재 RFP ID |

**Response**

```json
{
  "project_id": "PRJ_A1B2C3D4E5",
  "tasks_created": 47,
  "triples_inserted": 312,
  "fuseki_graph_uri": "https://ontology.example.org/instances#project_prj_a1b2c3d4e5",
  "next_step": "인력 추천 API를 실행하세요: POST /projects/PRJ_A1B2C3D4E5/recommend-staff"
}
```

> `project_id`를 로컬 상태에 저장합니다. 이후 화면 4에서 `/projects/{project_id}/...` API에 사용합니다.

**상태 전이**

```
extracted → analyzed → reviewed → confirmed
                           ↑ PATCH 가능
```

`confirmed` 이후에는 PATCH, analyze, regenerate-wbs 호출 시 409 Conflict가 반환됩니다.

---

## 화면 4 — 인력 추천

### 개요

역할별 필요 인원을 입력하면 AI가 적합한 인력을 추천합니다. 추천 목록에서 인력을 선택해 프로젝트에 배정합니다.

### 1단계: AI 인력 추천 (최초 진입)

**화면 진입 시 자동 호출**

```
POST /projects/{project_id}/recommend-staff
Content-Type: application/json
```

**Request Body** (생략 가능 — 기본값 사용)

```json
{
  "persist": false,
  "top_k": 10
}
```

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `persist` | bool | `false` | `true`이면 Fuseki에 추천 결과 저장 |
| `top_k` | int | null(전체) | 반환할 최대 추천 인원 수 (1~20) |

**Response**

```json
[
  {
    "rank": 1,
    "person_id": "P001",
    "person_name": "김기재",
    "role": "PM",
    "grade": "수석",
    "similarity_score": 0.95,
    "availability_score": 0.88,
    "matched_skills": [
      { "skill": "프로젝트 관리", "proficiency": 0.9 },
      { "skill": "리스크 관리", "proficiency": 0.85 }
    ],
    "reason": "프로젝트 관리(0.90)·리스크 관리(0.85) 역량 보유. 가용성 0.88."
  }
]
```

**화면 표시 매핑 (추천 목록 카드)**

| UI 항목 | 응답 필드 |
|---------|-----------|
| 이름 | `person_name` |
| 역할 | `role` |
| 직급 | `grade` |
| AI 추천 점수 (%) | `similarity_score × 100` |
| 가용성 점수 (%) | `availability_score × 100` |
| 매칭 스킬 | `matched_skills[].skill` |
| 추천 이유 | `reason` |

---

### 2단계: 역할별 인원수 입력 후 재추천

**좌측 패널 "역할별 필요 인원" 수정 후 "AI 인력 추천 재조회" 버튼 클릭 시**

```
POST /projects/{project_id}/recommend-staff/refresh
Content-Type: application/json
```

**Request Body**

```json
{
  "role_headcounts": [
    { "role": "PM", "count": 1 },
    { "role": "기획자", "count": 2 },
    { "role": "개발자", "count": 4 },
    { "role": "UIUX 디자이너", "count": 1 },
    { "role": "QA", "count": 2 }
  ],
  "top_k": 5,
  "persist": false
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `role_headcounts` | array | ✅ | 역할명과 필요 인원수 목록 |
| `role_headcounts[].role` | string | ✅ | 역할명 (DB에 저장된 `role` 값과 일치해야 함) |
| `role_headcounts[].count` | int | ✅ | 필요 인원 수 (1 이상) |
| `top_k` | int | - | 역할별 최대 추천 인원 수 (기본: count × 3) |
| `persist` | bool | - | 결과를 Fuseki에 저장할지 여부 |

**Response**

```json
{
  "by_role": [
    {
      "role": "PM",
      "required_count": 1,
      "candidates": [
        {
          "rank": 1,
          "person_id": "P001",
          "person_name": "김기재",
          "role": "PM",
          "grade": "수석",
          "similarity_score": 0.95,
          "availability_score": 0.88,
          "matched_skills": [...],
          "reason": "..."
        }
      ]
    },
    {
      "role": "개발자",
      "required_count": 4,
      "candidates": [...]
    }
  ],
  "total_required": 10
}
```

**화면 표시 매핑**

| UI 항목 | 응답 필드 |
|---------|-----------|
| 역할 섹션 헤더 | `by_role[].role` |
| 필요 인원 수 | `by_role[].required_count` |
| 추천 인력 카드 목록 | `by_role[].candidates` |
| 총 필요 인원 | `total_required` |

---

### 3단계: 인력 상세 정보 조회

**추천 카드 클릭 시 사이드 패널에 상세 정보 표시**

```
GET /persons/{person_id}
```

**Response**

```json
{
  "person_id": "P001",
  "person_name": "김기재",
  "role": "PM",
  "rank": "수석",
  "skills": [
    { "name": "프로젝트 관리", "proficiency": 0.9 },
    { "name": "리스크 관리", "proficiency": 0.85 }
  ],
  "participates_in": [
    { "project_id": "PRJ_XXX", "project_name": "이전 프로젝트명" }
  ]
}
```

**화면 표시 매핑 (선택된 인력 상세 패널)**

| UI 항목 | 응답 필드 |
|---------|-----------|
| 이름 | `person_name` |
| 역할 / 직급 | `role` / `rank` |
| 보유 스킬 | `skills[].name` + `skills[].proficiency` |
| 참여 프로젝트 이력 | `participates_in[].project_name` |

---

### 4단계: 확정 인력 등록

**우측 "선택된 인력" 패널에서 "계획 계속 및 인력 등록" 버튼 클릭 시**

```
POST /projects/{project_id}/staff
Content-Type: application/json
```

**Request Body**

```json
{
  "assignments": [
    { "person_id": "P001", "role": "PM" },
    { "person_id": "P002", "role": "기획자" },
    { "person_id": "P003", "role": "개발자" },
    { "person_id": "P004", "role": "개발자" },
    { "person_id": "P005", "role": "UIUX 디자이너" }
  ]
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `assignments` | array | ✅ | 확정 인력 목록 |
| `assignments[].person_id` | string | ✅ | 인력 ID |
| `assignments[].role` | string | ✅ | 배정 역할 |

**Response**

```json
{
  "project_id": "PRJ_A1B2C3D4E5",
  "assigned_count": 5
}
```

> 등록 완료 후 화면 5(등록 완료)로 이동합니다.

---

## API 호출 순서 요약

```
[화면 1] POST /rfp/upload                        ← 파일 업로드
         POST /rfp/{rfp_id}/analyze              ← AI 분석 (자동)
         PATCH /rfp/{rfp_id}/analysis            ← 개요 수정 (선택)
         GET  /rfp/{rfp_id}                      ← 재진입 시 복원

[화면 2] (GET /rfp/{rfp_id} 결과의 requirements 사용)
         PATCH /rfp/{rfp_id}/analysis            ← 요구사항 수정/추가/삭제

[화면 3] (GET /rfp/{rfp_id} 결과의 wbs 사용)
         POST /rfp/{rfp_id}/regenerate-wbs       ← WBS AI 재생성 (선택)
         PATCH /rfp/{rfp_id}/analysis            ← WBS 항목 수정 (선택)
         POST /rfp/{rfp_id}/confirm              ← 프로젝트 확정 → project_id 획득

[화면 4] POST /projects/{project_id}/recommend-staff         ← 최초 추천
         POST /projects/{project_id}/recommend-staff/refresh ← 역할별 재추천 (선택)
         GET  /persons/{person_id}                           ← 인력 상세 (선택)
         POST /projects/{project_id}/staff                   ← 인력 확정 등록
```

---

## 공통 에러 코드

| HTTP | 코드 | 원인 | 대응 |
|------|------|------|------|
| 404 | `RfpNotFound` | 존재하지 않는 rfp_id | "분석 정보를 찾을 수 없습니다" |
| 409 | `RfpStateError` | 상태 전이 불가 (예: confirmed 후 analyze 재호출) | "이미 확정된 RFP입니다" |
| 404 | `ProjectNotFound` | 존재하지 않는 project_id | "프로젝트를 찾을 수 없습니다" |
| 415 | `UnsupportedRfpFormat` | 지원하지 않는 파일 형식 | "PDF, DOCX, HWP 파일만 업로드 가능합니다" |

---

## 공통 참고 사항

- **rfp_id 패턴**: `^[A-Za-z0-9_-]+$` — 영숫자, 언더스코어, 하이픈만 허용
- **status 흐름**: `extracted` → `analyzed` → `reviewed` → `confirmed`
  - `PATCH` 호출 시 `reviewed`로 자동 변경
  - `confirmed` 상태에서는 수정 불가
- **persist 플래그**: `recommend-staff` 및 `recommend-staff/refresh`에서 `persist: true`로 호출하면 추천 결과가 Fuseki 트리플스토어에 기록됩니다. 최종 확정 시에만 `true`로 설정하세요.
- **파일 크기 제한**: 업로드 최대 20MB
