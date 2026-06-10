# 대시보드 API 가이드

> **대상**: 프론트엔드 개발자  
> **기준일**: 2025-05-09  
> **Base URL**: `http://localhost:8000`

---

## 공통 사항

### 인증
모든 대시보드 API는 JWT 인증이 필요합니다. 로그인 후 발급된 `access_token`을 모든 요청 헤더에 포함하세요.

```
Authorization: Bearer <access_token>
```

### 테스트 계정

| 이름 | 이메일 | 비밀번호 | 역할 | Fuseki Person 이름 |
|------|--------|----------|------|-------------------|
| 홍길동 | `pm@traceworks.com` | `traceworks1!` | PM | 홍길동 |
| 이수연 | `planner@traceworks.com` | `traceworks1!` | 기획자 | 이수연 |
| 김철수 | `dev@traceworks.com` | `traceworks1!` | 개발자 | 김철수 |

> **중요**: "내 프로젝트"와 "TO DO LIST"는 **로그인한 사용자의 이름**으로 Fuseki에서 담당자를 매칭합니다.  
> Fuseki에 등록된 Person의 `personName`이 위 이름과 일치해야 데이터가 조회됩니다.

### 로그인 방법

```http
POST /auth/login
Content-Type: application/x-www-form-urlencoded

username=pm@traceworks.com&password=traceworks1!
```

응답:
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## API 목록

### 1. 대시보드 요약

> 상단 요약 카드 영역 — 전체 업무 현황 수치 + 내 프로젝트 수 + 팀원 수

```http
GET /dashboard/summary
Authorization: Bearer <token>
```

**Response**
```json
{
  "task_summary": {
    "total": 47,
    "completed": 12,
    "in_progress": 18,
    "delayed": 3,
    "not_started": 14
  },
  "my_project_count": 2,
  "team_member_count": 10
}
```

| 필드 | 설명 |
|------|------|
| `task_summary.total` | 전체 업무 수 |
| `task_summary.completed` | 완료 업무 수 |
| `task_summary.in_progress` | 진행 중 업무 수 |
| `task_summary.delayed` | 지연 업무 수 |
| `task_summary.not_started` | 미진행 업무 수 |
| `my_project_count` | 내가 담당한 태스크가 있는 프로젝트 수 |
| `team_member_count` | 전체 팀원 수 |

---

### 2. 내 프로젝트 목록

> 사이드바 또는 프로젝트 목록 패널 — 로그인 사용자가 담당자인 프로젝트만 표시

```http
GET /dashboard/projects
Authorization: Bearer <token>
```

**Response**
```json
{
  "projects": [
    {
      "project_id": "PROJ-001",
      "project_name": "자재료 통합 관리 시스템 구축",
      "domain": "공공/시스템 구축",
      "status": "active",
      "progress": 42.5,
      "my_task_count": 7
    }
  ],
  "total": 1
}
```

| 필드 | 설명 |
|------|------|
| `project_id` | 프로젝트 ID |
| `project_name` | 프로젝트명 |
| `domain` | 사업 도메인 |
| `status` | 프로젝트 상태 (`active` 등) |
| `progress` | 평균 진행률 (%) |
| `my_task_count` | 내가 담당한 태스크 수 |

---

### 3. 내 TO DO LIST

> TO DO LIST 패널 — 로그인 사용자에게 배정된 미완료 WBS 태스크

```http
GET /dashboard/todos
Authorization: Bearer <token>
```

**Response**
```json
{
  "todos": [
    {
      "task_id": "PROJ-001-1.1",
      "task_name": "요구사항 분석",
      "wbs_code": "1.1",
      "project_id": "PROJ-001",
      "project_name": "자재료 통합 관리 시스템 구축",
      "status": "진행",
      "progress": 60.0,
      "due_date": "2025-03-31",
      "planned_hours": 40.0
    }
  ],
  "total": 5
}
```

| 필드 | 설명 |
|------|------|
| `task_id` | 태스크 ID |
| `task_name` | 태스크명 |
| `wbs_code` | WBS 코드 (예: `1.1`) |
| `project_id` | 소속 프로젝트 ID |
| `project_name` | 소속 프로젝트명 |
| `status` | 태스크 상태 (`미진행` / `진행` / `완료`) |
| `progress` | 진행률 (%) |
| `due_date` | 마감일 (없으면 `null`) |
| `planned_hours` | 계획 공수 (없으면 `null`) |

> 완료(`완료`) 상태인 태스크는 제외됩니다.

---

### 4. 역할별 공정률

> 공정률 바 차트 — 역할(PM/기획자/개발자 등)별 태스크 완료율

```http
GET /dashboard/progress
Authorization: Bearer <token>
```

**Response**
```json
{
  "roles": [
    {
      "role": "PM",
      "total_tasks": 5,
      "completed": 3,
      "in_progress": 1,
      "completion_rate": 0.6
    },
    {
      "role": "개발자",
      "total_tasks": 20,
      "completed": 8,
      "in_progress": 7,
      "completion_rate": 0.4
    }
  ],
  "overall_progress": 0.45
}
```

| 필드 | 설명 |
|------|------|
| `role` | 역할명 |
| `total_tasks` | 역할 전체 태스크 수 |
| `completed` | 완료 태스크 수 |
| `in_progress` | 진행 중 태스크 수 |
| `completion_rate` | 완료율 (0.0 ~ 1.0, % 변환 필요) |
| `overall_progress` | 전체 평균 완료율 |

---

### 5. 팀원 현황

> 팀원 현황 패널 — 팀원별 진행 중/완료 태스크 수와 가용성

```http
GET /dashboard/team
Authorization: Bearer <token>
```

**Response**
```json
{
  "members": [
    {
      "person_id": "P001",
      "person_name": "김지훈",
      "role": "PM",
      "grade": "수석",
      "active_task_count": 3,
      "completed_task_count": 5,
      "availability_score": 0.75
    }
  ],
  "total": 10
}
```

| 필드 | 설명 |
|------|------|
| `person_id` | Person ID |
| `person_name` | 이름 |
| `role` | 역할 |
| `grade` | 직급 (수석/선임/중급 등, 없으면 `null`) |
| `active_task_count` | 진행 중 + 미진행 태스크 수 |
| `completed_task_count` | 완료 태스크 수 |
| `availability_score` | 가용성 점수 (0.0 ~ 1.0, 없으면 `null`) |

---

### 6. WBS 전체 현황 (테이블)

> 프로젝트 진행 현황 테이블 — 전체 WBS 태스크 목록, 페이지네이션 지원

```http
GET /dashboard/wbs-overview?page=1&page_size=50
Authorization: Bearer <token>
```

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `page` | int | `1` | 페이지 번호 (1부터 시작) |
| `page_size` | int | `50` | 페이지당 항목 수 (최대 200) |

**Response**
```json
{
  "items": [
    {
      "project_id": "PROJ-001",
      "project_name": "자재료 통합 관리 시스템 구축",
      "task_id": "PROJ-001-1.1",
      "task_name": "요구사항 분석",
      "wbs_code": "1.1",
      "assignee_role": "기획자",
      "assignee_name": "이수진",
      "status": "진행",
      "progress": 60.0,
      "due_date": "2025-03-31",
      "planned_hours": 40.0
    }
  ],
  "total": 47,
  "page": 1,
  "page_size": 50
}
```

| 필드 | 설명 |
|------|------|
| `project_id` / `project_name` | 소속 프로젝트 |
| `task_id` | 태스크 ID |
| `task_name` | 태스크명 |
| `wbs_code` | WBS 코드 |
| `assignee_role` | 담당 역할 (없으면 `null`) |
| `assignee_name` | 담당자 이름 (없으면 `null`) |
| `status` | 상태 (`미진행` / `진행` / `완료`) |
| `progress` | 진행률 (%) |
| `due_date` | 마감일 (없으면 `null`) |
| `planned_hours` | 계획 공수 (없으면 `null`) |

---

### 7. 최근 알림 (상태 변경 히스토리)

> 알림/피드 영역 — 최근 WBS 상태 변경 이력

```http
GET /dashboard/alerts?limit=20
Authorization: Bearer <token>
```

**Query Parameters**

| 파라미터 | 타입 | 기본값 | 설명 |
|---------|------|--------|------|
| `limit` | int | `20` | 최대 반환 건수 (최대 100) |

**Response**
```json
{
  "alerts": [
    {
      "history_id": "uuid-...",
      "task_id": "PROJ-001-1.1",
      "task_name": "요구사항 분석",
      "project_name": null,
      "old_status": "미진행",
      "new_status": "진행",
      "changed_by_name": "홍길동",
      "note": "작업 착수합니다.",
      "created_at": "2025-05-09T10:30:00"
    }
  ],
  "total": 20
}
```

| 필드 | 설명 |
|------|------|
| `history_id` | 이력 고유 ID |
| `task_id` | 태스크 ID |
| `task_name` | 태스크명 (Fuseki 조회, 없으면 `null`) |
| `project_name` | 프로젝트명 (현재 `null` — 추후 추가 예정) |
| `old_status` | 변경 전 상태 |
| `new_status` | 변경 후 상태 |
| `changed_by_name` | 변경한 사용자 이름 |
| `note` | 메모 (없으면 `null`) |
| `created_at` | 변경 일시 (ISO 8601) |

---

## 태스크 상태값 정의

| 상태값 | 설명 |
|--------|------|
| `미진행` | 작업 시작 전 |
| `진행` | 작업 진행 중 |
| `완료` | 작업 완료 |

---

## Swagger UI

서버 실행 후 아래 URL에서 직접 API를 테스트할 수 있습니다.

```
http://localhost:8000/docs
```

`/auth/login` → 토큰 발급 → 우상단 **Authorize** 버튼 → `Bearer <token>` 입력 → 대시보드 API 테스트
