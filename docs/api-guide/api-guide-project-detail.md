# 프로젝트 상세 조회 API 가이드

## `GET /projects/{project_id}`

특정 프로젝트의 전체 정보와 해당 프로젝트에 연결된 요구사항 목록을 반환합니다.

---

## 요청

### Path Parameter

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `project_id` | string | ✅ | 프로젝트 ID (예: `PRJ-001`) |

### 인증
불필요

### 예시
```
GET /projects/PRJ-001
```

---

## 응답

### 성공 `200 OK`

```json
{
  "project_id": "PRJ-001",
  "project_name": "공공 의료 데이터 플랫폼 구축",
  "project_domain": "공공",
  "tech_stack": ["FastAPI", "React", "PostgreSQL"],
  "difficulty_level": "HIGH",
  "project_status": "ACTIVE",
  "start_date": "2026-05-01",
  "end_date": "2026-10-31",
  "description": "공공 의료 데이터를 수집·분석하여 감염병 예측 모델을 제공하는 플랫폼 구축 사업",
  "google_slide_id": "1lAmfHQSYE1ZkaEnzK1CynBvl6-xrdp5Nwagr4zLsasE",
  "gitlab_project_id": "7",
  "gitlab_repo_url": "http://gitlab.example.com/root/prj-001",
  "requirements": [
    {
      "req_id": "REQ-001",
      "req_name": "사용자 인증",
      "req_description": "사용자 인증 기능 요구사항 묶음",
      "req_type": "기능",
      "user_type": ["사용자"],
      "req_priority": "HIGH",
      "req_status": "APPROVED",
      "children": [
        {
          "req_id": "REQ-001-001",
          "req_name": "이메일 로그인",
          "req_description": "이메일/비밀번호로 로그인",
          "req_type": "기능",
          "user_type": ["사용자"],
          "req_priority": "HIGH",
          "req_status": "APPROVED"
        },
        {
          "req_id": "REQ-001-002",
          "req_name": "비밀번호 재설정",
          "req_description": "이메일 인증을 통한 비밀번호 재설정",
          "req_type": "기능",
          "user_type": ["사용자"],
          "req_priority": "MEDIUM",
          "req_status": "APPROVED"
        }
      ]
    },
    {
      "req_id": "REQ-002",
      "req_name": "데이터 시각화 대시보드",
      "req_description": "수집된 의료 데이터를 차트 및 지도로 시각화하는 대시보드 제공",
      "req_type": "기능",
      "user_type": ["사용자", "관리자"],
      "req_priority": "MEDIUM",
      "req_status": "APPROVED",
      "children": []
    }
  ]
}
```

### 에러

| 상태 코드 | 설명 |
|----------|------|
| `404 Not Found` | 존재하지 않는 `project_id` |
| `503 Service Unavailable` | 온톨로지 저장소 연결 불가 |

```json
// 404 예시
{
  "detail": "프로젝트를 찾을 수 없습니다: PRJ-999"
}
```

---

## 응답 필드 상세

### 프로젝트 정보

| 필드 | 타입 | Nullable | 설명 |
|------|------|----------|------|
| `project_id` | string | - | 프로젝트 고유 ID |
| `project_name` | string | - | 프로젝트명 |
| `project_domain` | string | ✅ | 사업 분야 (예: `공공`, `금융`, `의료`) |
| `tech_stack` | string[] | - | 기술 스택 목록. 없으면 빈 배열 `[]` |
| `difficulty_level` | string | ✅ | 난이도. `LOW` \| `MEDIUM` \| `HIGH` \| `CRITICAL` |
| `project_status` | string | - | 프로젝트 상태. `PLANNING` \| `ACTIVE` \| `ON_HOLD` \| `COMPLETED` |
| `start_date` | string (YYYY-MM-DD) | ✅ | 프로젝트 시작일 |
| `end_date` | string (YYYY-MM-DD) | ✅ | 프로젝트 종료일 |
| `description` | string | ✅ | 프로젝트 상세 설명 |
| `google_slide_id` | string | ✅ | 연동된 Google Slides 프레젠테이션 ID |
| `gitlab_project_id` | string | ✅ | 연동된 GitLab 프로젝트 ID |
| `gitlab_repo_url` | string | ✅ | GitLab 저장소 URL |
| `requirements` | array | - | **대분류(Large) 요구사항 트리.** 각 항목이 `children`(중분류 Mid 배열)을 포함. 없으면 빈 배열 `[]` |

### 요구사항 계층 구조

- 응답의 `requirements`는 **대분류(Large)만** 루트로 들어있고, 각 Large 항목의 `children`에 **중분류(Mid)** 배열이 들어있는 2-depth 트리입니다.
- 대/중 판정은 `req_id`의 토큰 수로 결정됩니다.
  - **대분류(Large)**: `REQ-001`, `REQ-002` — 토큰 2개
  - **중분류(Mid)**: `REQ-001-001`, `REQ-001-002` — 토큰 3개. 부모 = 앞 두 토큰(`REQ-001`)
- 정렬: 대분류는 `req_id` 숫자 오름차순, 같은 Large 안의 중분류도 동일 기준 정렬됨.
- Mid가 없는 Large도 `children: []` (null 아님).

### `requirements[*]` (대분류)

| 필드 | 타입 | Nullable | 설명 |
|------|------|----------|------|
| `req_id` | string | - | 대분류 요구사항 ID (예: `REQ-001`) |
| `req_name` | string | ✅ | 요구사항명 |
| `req_description` | string | ✅ | 요구사항 상세 설명 |
| `req_type` | string | ✅ | 유형. `기능` \| `비기능` |
| `user_type` | string[] | - | 사용자 유형 (예: `["사용자", "관리자"]`). 없으면 `[]` |
| `req_priority` | string | ✅ | 우선순위. `CRITICAL` \| `HIGH` \| `MEDIUM` \| `LOW` |
| `req_status` | string | ✅ | 상태. `DRAFT` \| `APPROVED` \| `IMPLEMENTED` \| `VERIFIED` |
| `children` | array | - | 하위 중분류 요구사항 배열. 없으면 `[]` |

### `requirements[*].children[*]` (중분류)

대분류와 동일한 필드를 가지며 `children` 필드만 없습니다.

| 필드 | 타입 | Nullable | 설명 |
|------|------|----------|------|
| `req_id` | string | - | 중분류 요구사항 ID (예: `REQ-001-001`). 앞 두 토큰이 부모 대분류의 `req_id`와 일치 |
| `req_name` ~ `req_status` | - | - | 대분류와 동일 |

---

## 참고

- `google_slide_id`를 이용해 Google Slides 링크를 구성할 경우: `https://docs.google.com/presentation/d/{google_slide_id}`
- `requirements`는 RFP 분석 후 확정(`POST /rfp/{rfp_id}/confirm`) 시점에 생성됩니다. 수동 생성 프로젝트는 빈 배열일 수 있습니다.
- WBS 태스크 목록은 이 API가 아닌 `GET /projects/{project_id}/wbs`를 사용하세요.
