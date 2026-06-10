# Traceworks MVP — 로그인 / WBS 관리 API 가이드

> 로그인, WBS 작업 조회·추가·상태 수정 기능의 화면별 API 사용 방법을 설명합니다.
> 인증이 필요한 API는 `Authorization: Bearer <token>` 헤더를 반드시 포함해야 합니다.

---

## 공통 정보

### Base URL
```
http://localhost:8000
```

### 인증 방식
```
Authorization: Bearer <access_token>
```
- 로그인 API(`POST /auth/login`)로 발급받은 토큰을 사용합니다.
- 토큰 유효시간: **8시간**

### WBS 상태 정의

| 상태 | 설명 |
|------|------|
| `미진행` | 작업 시작 전 상태 |
| `진행` | 담당자가 작업을 시작한 상태 |
| `완료` | 작업이 완료된 상태 |

---

## 화면 1 — 로그인

> 서비스 진입 시 이메일·비밀번호로 로그인합니다.
> 로그인 성공 시 발급된 토큰을 클라이언트에 저장해 이후 인증 API에 사용합니다.

### 로그인

```
POST /auth/login
Content-Type: application/json
```

**Request Body**
```json
{
  "email": "pm@traceworks.com",
  "password": "traceworks1!"
}
```

**Response 200**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user_id": "uuid-string",
  "name": "홍길동",
  "role": "pm"
}
```

**오류 응답**
| 상태 코드 | 사유 |
|-----------|------|
| 401 | 이메일 또는 비밀번호 불일치 |

---

### 내 정보 조회 (토큰 유효성 확인)

> 앱 초기 진입 시 저장된 토큰이 유효한지 확인하거나, 헤더에 사용자 정보를 표시할 때 호출합니다.

```
GET /auth/me
Authorization: Bearer <token>
```

**Response 200**
```json
{
  "user_id": "uuid-string",
  "email": "pm@traceworks.com",
  "name": "홍길동",
  "role": "pm",
  "is_active": true
}
```

**오류 응답**
| 상태 코드 | 사유 |
|-----------|------|
| 401 | 토큰 없음 또는 만료 |

---

### 예시 계정

| 역할 | 이름 | 이메일 | 비밀번호 |
|------|------|--------|---------|
| PM | 홍길동 | pm@traceworks.com | traceworks1! |
| 기획자 | 이수연 | planner@traceworks.com | traceworks1! |
| 개발자 | 김철수 | dev@traceworks.com | traceworks1! |

> 계정 초기 생성: `cd backend && uv run python scripts/seed_users.py`

---

## 화면 2 — WBS 목록 (프로젝트 상세)

> 프로젝트의 전체 WBS 작업 목록을 표시합니다. 각 행을 클릭하면 작업 상세 팝업이 열립니다.

### WBS 목록 조회

```
GET /projects/{project_id}/wbs
```

**Path Parameter**
| 파라미터 | 설명 |
|----------|------|
| `project_id` | 프로젝트 ID |

**Response 200**
```json
[
  {
    "task_id": "PROJ001-T001",
    "wbs_code": "1.1.1",
    "task_name": "세입·세출 예산 편성 화면 개발",
    "progress": 65,
    "status": "진행",
    "assignee": "김철수",
    "due_date": "2025-04-25",
    "planned_hours": 40.0,
    "actual_hours": null
  }
]
```

---

## 화면 3 — WBS 작업 상세 팝업

> WBS 목록에서 작업 행을 클릭했을 때 열리는 팝업입니다.
> 담당자, 진행률, 일정, 진행 히스토리, 이슈 사항을 표시합니다.

### WBS 작업 상세 조회

```
GET /tasks/{task_id}
```

**Path Parameter**
| 파라미터 | 설명 |
|----------|------|
| `task_id` | WBS 작업 ID |

**Response 200**
```json
{
  "task_id": "PROJ001-T001",
  "task_name": "세입·세출 예산 편성 화면 개발",
  "wbs_code": "1.1.1",
  "status": "진행",
  "progress": 65,
  "planned_hours": 40.0,
  "actual_hours": null,
  "planned_start": "2025-03-03",
  "planned_end": "2025-04-25",
  "due_date": "2025-04-25",
  "assignee": {
    "person_id": "uuid-string",
    "person_name": "김철수"
  },
  "source_files": [],
  "history": [
    {
      "history_id": "uuid-string",
      "old_status": null,
      "new_status": "미진행",
      "note": "작업 배정",
      "change_reason": null,
      "extra_work_date": null,
      "changed_by_name": "홍길동",
      "created_at": "2025-03-01T09:00:00"
    },
    {
      "history_id": "uuid-string",
      "old_status": "미진행",
      "new_status": "진행",
      "note": "화면 설계 검토 완료 후 개발 착수",
      "change_reason": null,
      "extra_work_date": null,
      "changed_by_name": "김철수",
      "created_at": "2025-03-07T10:00:00"
    }
  ],
  "issues": [
    {
      "issue_id": "uuid-string",
      "title": "IE11 호환성 문제",
      "description": "Flex 레이아웃 폴리필 적용으로 해결",
      "status": "resolved",
      "created_at": "2025-04-05T09:00:00",
      "resolved_at": "2025-04-10T15:00:00"
    }
  ]
}
```

**오류 응답**
| 상태 코드 | 사유 |
|-----------|------|
| 404 | 작업 ID를 찾을 수 없음 |

---

## 화면 4 — WBS 상태 변경 팝업 (수정사항)

> WBS 작업 상세 팝업에서 상태 변경 버튼을 클릭했을 때 표시되는 팝업입니다.
> **로그인 필수**, **본인이 담당하는 작업만 수정 가능**합니다.

### WBS 작업 상태 수정

```
PATCH /tasks/{task_id}/status
Authorization: Bearer <token>
Content-Type: application/json
```

**Path Parameter**
| 파라미터 | 설명 |
|----------|------|
| `task_id` | WBS 작업 ID |

**Request Body**
```json
{
  "status": "완료",
  "note": "PM·기획 최종 검수 통과. 완료 처리."
}
```

> ⚠️ **완료 상태에서 다른 상태로 변경하는 경우** `change_reason`과 `extra_work_date`가 **필수**입니다.

```json
{
  "status": "진행",
  "note": "재작업 필요",
  "change_reason": "성능 개선 추가 작업 필요",
  "extra_work_date": "2025-05-10"
}
```

**Request 필드**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `status` | string | ✅ | `미진행` / `진행` / `완료` |
| `note` | string | - | 진행 메모 |
| `change_reason` | string | 완료→변경 시 ✅ | 변경 사유 |
| `extra_work_date` | string (YYYY-MM-DD) | 완료→변경 시 ✅ | 추가 작업 일자 |

**Response 200**
```json
{
  "task_id": "PROJ001-T001",
  "old_status": "진행",
  "new_status": "완료"
}
```

**오류 응답**
| 상태 코드 | 사유 |
|-----------|------|
| 401 | 인증 토큰 없음 또는 만료 |
| 403 | 본인 담당 작업이 아님 |
| 404 | 작업 ID를 찾을 수 없음 |
| 422 | 완료→변경 시 change_reason 또는 extra_work_date 누락 |

---

## 화면 5 — WBS 작업 추가

> WBS 목록 화면에서 **+ 작업 추가** 버튼을 클릭했을 때 표시되는 폼입니다.
> **로그인 필수**, PM 또는 기획자 역할 권장.

### WBS 작업 추가

```
POST /projects/{project_id}/tasks
Authorization: Bearer <token>
Content-Type: application/json
```

**Path Parameter**
| 파라미터 | 설명 |
|----------|------|
| `project_id` | 프로젝트 ID |

**Request Body**
```json
{
  "wbs_code": "1.2.3",
  "task_name": "공급업체 연동 API 개발",
  "description": "GET /api/v1/suppliers 엔드포인트 구현",
  "assignee_id": "uuid-string",
  "planned_start": "2025-05-01",
  "planned_end": "2025-05-20",
  "planned_hours": 40.0
}
```

**Request 필드**
| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `wbs_code` | string | ✅ | WBS 코드 (예: `1.2.3`) |
| `task_name` | string | ✅ | 작업명 |
| `description` | string | - | 작업 설명 |
| `assignee_id` | string | - | 담당자 ID |
| `planned_start` | string (YYYY-MM-DD) | - | 시작 예정일 |
| `planned_end` | string (YYYY-MM-DD) | - | 종료 예정일 |
| `planned_hours` | number | - | 계획 공수 (시간) |

**Response 201**
```json
{
  "task_id": "PROJ001-T3A2B1C0",
  "wbs_code": "1.2.3",
  "status": "미진행"
}
```

**오류 응답**
| 상태 코드 | 사유 |
|-----------|------|
| 401 | 인증 토큰 없음 또는 만료 |
| 404 | 프로젝트 ID를 찾을 수 없음 |

---

## 전체 API 요약

| 화면 | 메서드 | 엔드포인트 | 인증 | 설명 |
|------|--------|------------|------|------|
| 로그인 | POST | `/auth/login` | ❌ | 로그인 → 토큰 발급 |
| 로그인 | GET | `/auth/me` | ✅ | 내 정보 조회 |
| WBS 목록 | GET | `/projects/{project_id}/wbs` | ❌ | WBS 목록 조회 |
| WBS 상세 팝업 | GET | `/tasks/{task_id}` | ❌ | 작업 상세 + 히스토리 + 이슈 |
| 상태 변경 팝업 | PATCH | `/tasks/{task_id}/status` | ✅ | 상태 수정 (본인 담당만) |
| WBS 작업 추가 | POST | `/projects/{project_id}/tasks` | ✅ | 작업 추가 (미진행 상태) |
