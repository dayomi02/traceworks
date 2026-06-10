# 백엔드 API 사용 가이드

> GitLab 코드 색인, Google Slides 연동, 실시간 알림(SSE), 코드 검색을 제공하는 백엔드 API.
> 알림 본문은 `content_json`(NotificationContent) 구조로 풍부하게 표현되며, 프론트에서 카드 UI·뱃지·상세 패널 등에 직접 매핑할 수 있도록 설계되어 있습니다.

---

## 전체 API 목록

```
[알림 생성/전달]
POST   /api/notifications              ← 알림 이벤트 생성 (DB 저장만, 전달 X)
POST   /api/notifications/send         ← 기존 이벤트를 특정 유저들에게 전달 + 이메일 + SSE push

[알림 조회]
GET    /api/notifications              ← 알림 목록 조회
GET    /api/notifications/unread-count ← 미읽음 개수 조회
GET    /api/notifications/{id}         ← 알림 단건 상세 조회
GET    /api/notifications/stream       ← SSE 실시간 스트림

[읽음 처리]
PUT    /api/notifications/{id}/read    ← 단건 읽음 처리
PUT    /api/notifications/read-all     ← 전체 읽음 처리

[웹훅]
POST   /webhook/gitlab                 ← GitLab Push/Merge Request 웹훅 수신
POST   /webhook/slides                 ← Google Slides 전체 변경 웹훅 수신
POST   /webhook/slides/page            ← (DEPRECATED) 단일 슬라이드 페이지 변경 웹훅

[코드 검색]
GET    /api/search/code                ← BM25 키워드 검색
GET    /api/search/code/hybrid         ← BM25 + 벡터 하이브리드 검색
```

---

## 1. NotificationContent 스키마 (프론트 표시 가이드)

알림의 풍부한 본문 데이터(`content_json`)는 `NotificationContent` 객체로 직렬화되어 응답에 포함됩니다.
**모든 필드가 Optional**이며, 알림 유형에 따라 일부만 채워집니다. 프론트는 필드 존재 여부로 조건부 렌더링을 해야 합니다.

### 1-1. NotificationContent (최상위 컨테이너)

| 필드 | 타입 | 설명 | 프론트 표시 위치 |
|------|------|------|----------------|
| `common` | `CommonItem` | 알림 공통 정보 (업무·테스크·담당자·알림 타입) | 카드 헤더 / 상세 상단 |
| `status_change` | `StatusChangeItem` | 상태 변경 정보 | 상태 변경 알림 본문 |
| `affected_wbs_tasks` | `list[WbsTaskChange]` | 영향받은 WBS 테스크 변경 목록 | 일정 영향 섹션(여러 줄 리스트) |
| `dev_task_items` | `list[DevTaskItem]` | 개발자가 수행해야 할 작업·이슈 목록 | 개발 작업 섹션(타입별 색상 뱃지) |
| `approval_result` | `ApprovalResultItem` | 승인/반려 결과 | 승인 결과 알림 본문 |

---

### 1-2. CommonItem — 알림 공통 정보

알림의 출처(어떤 업무·테스크·담당자)와 분류(노티 타입)를 담는 헤더 정보. **거의 모든 알림에 포함됩니다.**

| 필드 | 타입 | 설명 | 프론트 표시 예시 |
|------|------|------|----------------|
| `req_id` | string | 업무 ID | 내부 링크 라우팅용 (예: `/requests/REQ-001`) |
| `req_name` | string | 업무 명 | 카드 부제목 (예: `"결제 모듈 개편"`) |
| `task_id` | string | 테스크 ID | 내부 링크 라우팅용 |
| `task_name` | string | 테스크 명 | 카드 본문 라벨 |
| `assignee_user_name` | string | 담당자 이름 | 카드 우측 아바타 옆 (예: `"홍길동"`) |
| `assignee_user_role` | string | 담당자 역할 | 담당자 이름 아래 부가 정보 |
| `created_at` | string | 알림 생성 시각 (ISO 8601) | "3분 전" 등 상대시간 표시 |
| `noti_type` | string (enum) | 알림 타입 — **응답에서는 한글 라벨로 직렬화됨** | 카드 좌측 컬러 뱃지 |

**`noti_type` 매핑 (DB enum → 응답 라벨)**

| 코드값 (입력 시) | 응답 라벨 (프론트 수신) | 의미 / 뱃지 색상 가이드 |
|---------------|-------------------|-------------------|
| `PM_APPROVAL_REQUEST` | `PM 승인 요청` | 노랑 — "결재 대기" |
| `PM_APPROVED` | `PM 승인` | 초록 — "승인 완료" |
| `PM_REJECTED` | `PM 반려` | 빨강 — "반려됨" |

> **중요**: 알림 생성(POST)할 때는 코드값(`"PM_APPROVED"`)으로 전달하지만, GET 응답에서는 항상 한글 라벨(`"PM 승인"`)로 반환됩니다. 프론트는 응답 라벨을 그대로 화면에 표시하면 됩니다.

---

### 1-3. StatusChangeItem — 상태 변경 정보

테스크/업무의 상태가 바뀌었을 때 채워집니다. **상태 변경 알림에서만 사용.**

| 필드 | 타입 | 설명 | 프론트 표시 예시 |
|------|------|------|----------------|
| `prev_status` | string (enum) | 이전 상태 — 응답에서 한글 라벨 | "진행중 → 완료" 형태로 표시 |
| `new_status` | string (enum) | 변경 후 상태 — 응답에서 한글 라벨 | 위와 동일 |
| `change_reason` | string | 변경 사유 (자유 텍스트) | 본문 내 인용구(`> 사유`) |
| `slide_change_summary` | string | 슬라이드 변경 요약 (기획자가 슬라이드 저장 시 자동 생성된 요약) | "기획 변경 요약" 섹션 |
| `actual_completion_date` | string | 실제 완료일 (`new_status=COMPLETED`일 때만 의미 있음) | "완료일: 2026-05-14" |

**상태 enum 매핑**

| 코드값 | 응답 라벨 |
|--------|---------|
| `TODO` | `미진행` |
| `IN_PROGRESS` | `진행중` |
| `COMPLETED` | `완료` |

> **참고**: `prev_status` / `new_status`의 Literal은 현재 `IN_PROGRESS` / `COMPLETED`만 허용합니다(`TODO`는 라벨 매핑은 있으나 Literal에서는 제외). 신규 진입 알림은 별도 noti_type으로 관리하세요.

---

### 1-4. WbsTaskChange — WBS 테스크 변경 정보 (반복)

`affected_wbs_tasks` 배열의 각 항목. 한 알림이 여러 테스크의 일정에 영향을 줄 때 다중으로 들어옵니다.

| 필드 | 타입 | 설명 | 프론트 표시 예시 |
|------|------|------|----------------|
| `task_id` | string | 테스크 코드 (실제 의미는 코드 ID) | 행 좌측 칩 `[T-101]` |
| `task_name` | string | 테스크 명 | 행 제목 |
| `assignee` | string | 담당자 | 행 우측 담당자 칩 |
| `period_start` | string | 기간 시작일 (YYYY-MM-DD) | 일정 바 시작점 |
| `period_end` | string | 기간 종료일 (YYYY-MM-DD) | 일정 바 끝점 |
| `new_deadline` | string | 변경된 마감일 | "→ 2026-06-01" 화살표 표시 |
| `modified_days` | int | 일정 변동 일수 (음수=당김, 양수=밀림) | `+3일` / `-2일` 칩, 양수는 빨강 |
| `is_completed` | bool | 완료 여부 | 완료 체크 아이콘 |

> **렌더링 팁**: `modified_days > 0`이면 일정 지연이므로 강조색, `< 0`이면 단축이므로 중립색 권장. 리스트 정렬은 `|modified_days|` 내림차순이 사용성 좋음.

> **필드명 주의**: `task_id`의 description은 "테스크 명", `task_name`은 "테스크 코드"로 적혀 있으나, 실제로는 `task_id`=식별자, `task_name`=표시명으로 사용하는 것이 자연스럽습니다(서버측 description 라벨링 이슈).

---

### 1-5. DevTaskItem — 개발 작업 / 이슈 항목 (반복)

`dev_task_items` 배열의 각 항목. **GPT-4o-mini가 Git 코드 변경 내역과 슬라이드(기획 문서)를 분석해 자동 생성**합니다. 알림 생성 시 `common.req_id`가 있으면 자동 enrich됩니다.

| 필드 | 타입 | 설명 | 프론트 표시 예시 |
|------|------|------|----------------|
| `change_type` | string (enum) | 변경 타입 — **응답에서 한글 라벨로 직렬화** | 좌측 컬러 뱃지 |
| `title` | string | 작업명 또는 이슈명 (50자 이내) | 항목 제목 |
| `description` | string | 작업/위험 내용 설명 (1~2문장) | 항목 본문 |

**`change_type` 매핑 (응답 라벨)**

| 코드값 | 응답 라벨 | 의미 | 권장 뱃지 색상 |
|--------|---------|------|--------------|
| `NEW` | `신규` | 새로 개발해야 하는 작업 | 파랑 |
| `UPDATED` | `수정` | 기존 코드를 수정해야 하는 작업 | 주황 |
| `MAINTENANCE` | `유지` | 변경 없이 유지하는 항목 | 회색 |
| `ISSUE` | `이슈` | **위험·민감 사항** (보안 취약점, 데이터 손실 가능성, 하위 호환성 파괴, 성능 저하 등) | 빨강 — 경고 아이콘 동반 권장 |

> **자동 생성 동작**: `POST /api/notifications` 호출 시 `content.common.req_id`가 채워져 있고 `content.dev_task_items`가 비어 있으면, 서버가 백그라운드로 OpenSearch(코드 인덱스) + 슬라이드 스냅샷을 조회하여 2~6개 항목을 자동 생성합니다. 직접 채워서 보내면 자동 생성은 건너뜁니다.

> **ISSUE 항목 강조**: 프론트는 `change_type === "이슈"`인 항목을 리스트 상단으로 sticky 정렬하거나 경고 아이콘(⚠️)을 함께 표시해 사용자가 놓치지 않도록 하세요.

---

### 1-6. ApprovalResultItem — 승인/반려 결과

`noti_type`이 `PM_APPROVED` 또는 `PM_REJECTED`일 때 채워집니다.

| 필드 | 타입 | 설명 | 프론트 표시 예시 |
|------|------|------|----------------|
| `is_approved` | bool | 승인 여부 (`true`=승인, `false`=반려) | 큰 상태 아이콘 (✅/❌) |
| `approved_at` | string | 승인/반려 시각 (ISO 8601) | "2026-05-14 13:30 처리됨" |
| `rejection_reason` | string | 반려 사유 (`is_approved=false`일 때만) | 빨간 박스 인용구 |

---

### NotificationContent 통합 예시 (실제 GET 응답)

```json
{
  "common": {
    "req_id": "REQ-001",
    "req_name": "결제 모듈 개편",
    "task_id": "TASK-021",
    "task_name": "PG 연동 리팩터링",
    "assignee_user_name": "홍길동",
    "assignee_user_role": "developer",
    "created_at": "2026-05-14T13:30:00",
    "noti_type": "PM 승인"
  },
  "status_change": {
    "prev_status": "진행중",
    "new_status": "완료",
    "change_reason": "PG사 응답 형식 변경 적용 완료",
    "slide_change_summary": null,
    "actual_completion_date": "2026-05-14"
  },
  "affected_wbs_tasks": [
    {
      "task_id": "TASK-022",
      "task_name": "결제 실패 처리 UI",
      "assignee": "김프론트",
      "period_start": "2026-05-15",
      "period_end": "2026-05-20",
      "new_deadline": "2026-05-22",
      "modified_days": 2,
      "is_completed": false
    }
  ],
  "dev_task_items": [
    {
      "change_type": "이슈",
      "title": "결제 응답에 카드번호 일부 노출",
      "description": "PG 응답 로깅 시 마스킹 없이 raw 데이터가 기록됨. 즉시 마스킹 처리 필요."
    },
    {
      "change_type": "신규",
      "title": "재시도 큐 구현",
      "description": "결제 실패 시 지수 백오프로 재시도하는 큐를 별도로 구성해야 함."
    },
    {
      "change_type": "수정",
      "title": "PG 클라이언트 응답 파서 변경",
      "description": "신규 응답 포맷(JSON) 기준으로 파서를 수정함."
    }
  ],
  "approval_result": {
    "is_approved": true,
    "approved_at": "2026-05-14T13:30:00",
    "rejection_reason": null
  }
}
```

---

## 2. 알림 생성 / 전달

### POST /api/notifications

알림 이벤트(`NotificationEvent`)를 DB에 저장만 합니다. **사용자에게 전달(이메일·SSE)은 하지 않습니다.** 별도로 `/send`를 호출해야 합니다.
알람내용은은 발송전에 미리 생성해두고, 발송 시점에 `UserNotification`과 이메일 콘텐츠로 변환하는 방식입니다.

```
POST /api/notifications
Content-Type: application/json
X-Internal-Token: {내부 토큰값}
```

**Request Body**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `title` | string | ✅ | - | 알림 제목 (1~200자) |
| `message` | string | ✅ | - | 알림 본문 (1~2000자) |
| `content` | NotificationContent | - | `null` | 알림 상세 본문 (위 스키마 참고) |
| `project_id` | string | - | `null` | 프로젝트 식별자 |

```json
{
  "title": "결제 모듈 개편 — PM 승인 완료",
  "message": "PG 연동 리팩터링 테스크가 승인되었습니다.",
  "project_id": "PRJ-PAY",
  "content": {
    "common": {
      "req_id": "REQ-001",
      "req_name": "결제 모듈 개편",
      "task_id": "TASK-021",
      "task_name": "PG 연동 리팩터링",
      "assignee_user_name": "홍길동",
      "assignee_user_role": "developer",
      "noti_type": "PM_APPROVED"
    },
    "approval_result": {
      "is_approved": true,
      "approved_at": "2026-05-14T13:30:00"
    }
  }
}
```

> **자동 enrich**: `content.common.req_id`가 있고 `content.dev_task_items`가 비어 있으면 서버가 자동으로 `dev_task_items`를 채워서 저장합니다(GPT-4o-mini 분석, 최대 30초).

> **enum 입력값**: `noti_type`, `change_type`, `prev_status`, `new_status`는 **코드값으로 입력**해야 합니다 (예: `"PM_APPROVED"`, `"NEW"`). 응답에서는 한글 라벨로 반환됩니다.

**Response — 정상 (201)**

```json
{
  "id": 42,
  "title": "결제 모듈 개편 — PM 승인 완료",
  "message": "PG 연동 리팩터링 테스크가 승인되었습니다.",
  "project_id": "PRJ-PAY",
  "created_at": "2026-05-14T13:30:00",
  "content_json": { "common": { "...": "..." }, "...": "..." }
}
```

| HTTP | 원인 |
|------|------|
| 201 | 정상 생성 |
| 401 | `X-Internal-Token` 누락/불일치 |
| 422 | 필수 필드 누락 또는 타입 불일치 |

---

### POST /api/notifications/send

이미 생성된 `NotificationEvent`를 특정 사용자들에게 전달합니다. **이메일 발송 + SSE push + `UserNotification` 레코드 생성**을 모두 수행합니다.

PM 승인/반려 시점에 `approval_result`를 함께 전달하면, **알림의 `content_json.approval_result`를 해당 값으로 덮어쓴 뒤** 사용자에게 전달합니다. 값이 없으면 기존 알림 내용 그대로 전달됩니다.

```
POST /api/notifications/send
Content-Type: application/json
```

**Request Body**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `notification_event_id` | int | ✅ | 전달할 NotificationEvent의 ID |
| `user_ids` | string[] | ✅ | 수신자 user_id 목록 |
| `approval_result` | ApprovalResultItem | - | 승인/반려 결과. 값이 있으면 알림 content의 `approval_result`를 업데이트 후 전달 |

**`approval_result` 필드** (ApprovalResultItem — 모두 Optional)

| 필드 | 타입 | 설명 |
|------|------|------|
| `is_approved` | bool | 승인 여부 (`true`=승인, `false`=반려) |
| `approved_at` | string | 승인/반려 시각 (ISO 8601) |
| `rejection_reason` | string | 반려 사유 (`is_approved=false`일 때만 의미 있음) |

**예시 1 — 일반 전달 (승인/반려 정보 없음)**

```json
{
  "notification_event_id": 42,
  "user_ids": ["user-001", "user-002"]
}
```

**예시 2 — PM 승인 결과와 함께 전달**

```json
{
  "notification_event_id": 42,
  "user_ids": ["user-001", "user-002"],
  "approval_result": {
    "is_approved": true,
    "approved_at": "2026-05-14T13:30:00"
  }
}
```

**예시 3 — PM 반려 결과와 함께 전달**

```json
{
  "notification_event_id": 42,
  "user_ids": ["user-001"],
  "approval_result": {
    "is_approved": false,
    "approved_at": "2026-05-14T13:30:00",
    "rejection_reason": "PG사 응답 포맷 검토 후 재요청 필요"
  }
}
```

**Response — 정상 (200)**

```json
{
  "sent_to": ["hong@example.com", "kim@example.com"]
}
```

> **동작 상세**: `approval_result`가 전달되면 서버는 기존 `content_json`의 다른 필드(`common`, `status_change`, `dev_task_items` 등)는 그대로 유지하면서 `approval_result` 키만 추가·갱신한 뒤 DB에 저장합니다. 이후 `GET /api/notifications/{id}` 등 조회 응답에도 갱신된 `approval_result`가 포함됩니다.

| HTTP | 원인 |
|------|------|
| 200 | 정상 전달 (또는 대상 0명 — `0` 반환) |
| 422 | 필수 파라미터 누락 |

---

## 3. 알림 조회

### GET /api/notifications

특정 사용자의 알림 목록을 시간 역순으로 조회합니다.

```
GET /api/notifications?user_id={uid}&is_read={bool}&limit={n}&offset={n}
```

**Query Parameters**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `user_id` | string | ✅ | - | 수신자 user_id |
| `is_read` | bool | - | (전체) | 읽음 필터 (`true`/`false`) |
| `limit` | int | - | 50 | 최대 200 |
| `offset` | int | - | 0 | 페이지네이션 |

**Response — 정상 (200)**

```json
[
  {
    "id": 42,
    "title": "결제 모듈 개편 — PM 승인 완료",
    "message": "PG 연동 리팩터링 테스크가 승인되었습니다.",
    "project_id": "PRJ-PAY",
    "is_read": false,
    "read_at": null,
    "created_at": "2026-05-14T13:30:00",
    "content_json": { "common": { "...": "..." } }
  }
]
```

| 필드 | 설명 |
|------|------|
| `id` | NotificationEvent ID (읽음 처리 시 사용) |
| `is_read` | 해당 사용자의 읽음 여부 |
| `read_at` | 읽음 처리 시각 (null이면 미읽음) |
| `content_json` | NotificationContent (위 스키마) — 응답에서는 한글 라벨로 직렬화됨 |

| HTTP | 원인 |
|------|------|
| 200 | 정상 (빈 배열 가능) |
| 422 | `user_id` 누락 |

---

### GET /api/notifications/unread-count

특정 사용자의 미읽음 알림 개수를 반환합니다. 헤더 뱃지에 사용.
새로고침이나 새로운 화면으로 이동시 사용합니다.


```
GET /api/notifications/unread-count?user_id={uid}
```

**Response**

```json
{ "user_id": "user-001", "unread_count": 3 }
```

| HTTP | 원인 |
|------|------|
| 200 | 정상 |
| 422 | `user_id` 누락 |

---

### GET /api/notifications/{id}

NotificationEvent ID 기준 단건 상세 조회. (사용자별 읽음 상태는 포함되지 않습니다 — 목록 응답이나 SSE로 조회하세요.)

```
GET /api/notifications/42
```

**Response — 정상 (200)**

```json
{
  "id": 42,
  "title": "결제 모듈 개편 — PM 승인 완료",
  "message": "...",
  "project_id": "PRJ-PAY",
  "created_at": "2026-05-14T13:30:00",
  "content_json": { "...": "..." }
}
```

| HTTP | 원인 |
|------|------|
| 200 | 정상 |
| 404 | 알림 이벤트 없음 |

---

### GET /api/notifications/stream

SSE(Server-Sent Events) 실시간 스트림. 헤더 종 모양 아이콘의 실시간 미읽음 카운트·신규 알림 푸시에 사용.
알림내용과 함께 현재까지 미읽음 개수를 함께 보내므로, 프론트는 이 스트림만 구독해도 뱃지와 알림 목록을 실시간으로 유지할 수 있습니다.

```
GET /api/notifications/stream?user_id={uid}
Accept: text/event-stream
```

**Query Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `user_id` | string | ✅ | 구독할 사용자 user_id |

**스트림 이벤트 종류**

| `event:` | `data:` 형태 | 발생 시점                            |
|----------|------------|----------------------------------|
| `unread_count` | `{"count": 3}` | 연결 직후 1회 + 신규 알림 도착 시            |
| `notification` | NotificationListResponse + `unread_count` | 연결 직후 미읽을 알림 수, 신규 알림 도착 시 알림 내용 |
| (keepalive) | `: ping\n\n` (주석 라인) | 15초마다                            |

**예시 — 신규 알림 푸시 이벤트**

```
id: 1052
event: notification
data: {"id":42,"event_id":42,"title":"결제 모듈 개편 — PM 승인 완료","message":"...","project_id":"PRJ-PAY","is_read":false,"read_at":null,"created_at":"2026-05-14T13:30:00","content_json":{...},"unread_count":4}
```

> **프론트 구현 팁**
> - `EventSource` 사용 권장. `addEventListener("notification", ...)`, `addEventListener("unread_count", ...)` 분기.
> - 새 `notification` 이벤트마다 페이로드의 `unread_count`를 그대로 뱃지에 반영하면 별도 GET 호출 불필요.
> - 연결 끊김 시 `EventSource`는 자동 재연결합니다 — 별도 재시도 로직 불필요.

| HTTP | 원인 |
|------|------|
| 200 | 정상 (스트림 유지) |
| 422 | `user_id` 누락 |

---

## 4. 읽음 처리

### PUT /api/notifications/{id}/read

특정 알림을 읽음 처리합니다.

```
PUT /api/notifications/42/read?user_id={uid}
```

**Query Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `user_id` | string | ✅ | 읽음 처리할 사용자 user_id |

**Response**

```json
true
```

| HTTP | 원인 |
|------|------|
| 200 | 정상 처리 |
| 404 | 해당 사용자에게 전달된 알림 없음 |

---

### PUT /api/notifications/read-all

특정 사용자의 모든 미읽음 알림을 일괄 읽음 처리합니다.

```
PUT /api/notifications/read-all?user_id={uid}
```

**Response**

```json
{ "updated": 5 }
```

| 필드 | 설명 |
|------|------|
| `updated` | 읽음으로 변경된 알림 개수 |

| HTTP | 원인 |
|------|------|
| 200 | 정상 (변경 0건 가능) |
| 422 | `user_id` 누락 |

---

## 5. 웹훅 (Webhooks)

외부 시스템(GitLab, Google Apps Script)이 호출하는 진입점입니다. 모든 무거운 처리는 **응답을 먼저 반환한 뒤 백그라운드 태스크로 수행**되므로, 호출자는 200 응답을 받았더라도 색인·요약 결과는 비동기로 반영됨에 유의하세요.

### POST /webhook/gitlab

GitLab Push Hook 또는 Merge Request Hook을 수신합니다. 커밋 메시지에서 `req_id`를 추출하여 변경 파일 목록을 OpenSearch 코드 인덱스에 저장합니다.

```
POST /webhook/gitlab
Content-Type: application/json
X-Gitlab-Event: Push Hook        ← 또는 "Merge Request Hook"
X-Gitlab-Token: {웹훅 시크릿}     ← settings.gitlab_webhook_secret 설정 시 필수
```

**처리 흐름**

```
[1] X-Gitlab-Token 검증 (설정 시)
    ↓
[2] X-Gitlab-Event 분기
    ├─ Push Hook        → commits[0].message 에서 req_id 추출
    └─ Merge Request    → state=merged 인 경우만, title 에서 req_id 추출
    ↓
[3] req_id 없으면 즉시 종료 (status=ignored)
    ↓
[4] GitLab API로 변경 파일 목록 + repository_url 조회 (동기)
    ↓
[5] 200 응답 반환 (status=ok, files_indexed=N)
    ↓
[BG] 백그라운드 태스크
     ├─ asyncio.gather()로 파일 내용 병렬 조회
     ├─ GPT-4o-mini로 통합 요약 (summary, methodSummaries, keywords, changeType)
     └─ OpenSearch code-artifacts 인덱스에 KNN 벡터 + nested 문서로 색인
```

**Request Body** — GitLab 표준 페이로드 (FastAPI는 `request.json()`으로 그대로 받음)

| 이벤트 | 주요 필드 | 비고 |
|-------|----------|-----|
| `Push Hook` | `project.id`, `after`, `commits[].message`, `project.name` | 첫 커밋 메시지에서 req_id 추출 |
| `Merge Request Hook` | `object_attributes.state`, `object_attributes.merge_commit_sha`, `object_attributes.title`, `project.id` | `state == "merged"`인 경우만 처리 |

**Response — 정상 (200, 색인 시작)**

```json
{
  "status": "ok",
  "req_id": "REQ-001",
  "files_indexed": 7
}
```

**Response — 무시 (200, 조건 미충족)**

```json
{ "status": "ignored", "reason": "req_id not found in commit message" }
```

| `reason` 값 | 설명 |
|------------|------|
| `no commits` | Push Hook이지만 commits 배열이 비어있음 |
| `not merged` | Merge Request Hook이지만 `state != "merged"` |
| `unsupported event: ...` | Push/Merge Request 외 이벤트 |
| `req_id not found in commit message` | 정규식 `[A-Z]+-\d+` 매치 실패 |

| HTTP | 원인 |
|------|------|
| 200 | 정상 수신 (status=ok / status=ignored) |
| 401 | `X-Gitlab-Token` 불일치 (시크릿 설정 시) |

> **주의**: `files_indexed`는 *색인을 시작한 파일 수*이며 *완료된 파일 수*가 아닙니다. 실제 색인 결과는 OpenSearch 또는 `/api/search/code`로 확인하세요.

> **req_id 추출 규칙**: 커밋 메시지에서 정규식 `[A-Z]+-\d+` 첫 매치 (예: `[TASK-021] PG 클라이언트 리팩터링` → `TASK-021`). 매치 실패 시 색인 자체를 건너뜁니다.

---

### POST /webhook/slides

Google Apps Script에서 슬라이드 프레젠테이션 변경 시 호출합니다. 전체 페이지를 순회해 변경된 페이지를 자동 감지하여 처리합니다.

```
POST /webhook/slides
Content-Type: application/json
```

**처리 흐름**

```
[1] 현재 프레젠테이션 전체 스냅샷 저장 (snapshot_group_id 발급)
    ├─ 페이지별 text_content, element_snapshot, page_fingerprint 저장
    └─ MariaDB slide_snapshot 테이블
    ↓
[2] 이전 group_id vs 신규 group_id diff 계산
    └─ ADDED / MODIFIED / REMOVED 페이지 분류 (fingerprint 기반)
    ↓
[3] 변경 페이지별 병렬 처리
    ├─ 페이지 키워드로 OpenSearch 코드 검색 (BM25)
    ├─ GPT-4o-mini로 슬라이드 변경 요약 (15초 타임아웃)
    └─ 발표자 노트에 연관 파일 목록 + 요약 삽입
    ↓
[4] 전체 슬라이드 변경 통합 요약 생성
```

**Request Body** (`SlideUpdateRequest`)

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `git_lab_project_id` | int | ✅ | 연관 GitLab 프로젝트 ID |
| `presentation_id` | string | ✅ | Google Slides 프레젠테이션 ID |
| `req_id` | string | ✅ | 연관 업무 ID (스냅샷에 함께 저장) |

```json
{
  "git_lab_project_id": 42,
  "presentation_id": "1abcDEFghijKLMnopQRStuvWXYz0123456789",
  "req_id": "REQ-001"
}
```

**Response — 정상 (200)**

```json
{
  "status": "ok",
  "snapshot_group_id": "5e1f...",
  "changed_pages": 3,
  "summary": "결제 모듈 화면 흐름 3개 페이지가 변경됨..."
}
```

> **응답 필드**: 처리 결과는 `slides_sync_service.on_slide_page_updated()`가 반환하는 dict 그대로 전달됩니다. 실제 필드 구성은 변경 페이지 유무·LLM 응답에 따라 달라질 수 있으므로 호출자는 `status` 외 필드는 옵셔널로 처리하세요.

| HTTP | 원인 |
|------|------|
| 200 | 정상 처리 |
| 400 | `slides_sync_service` 처리 중 오류 (응답 `status=error`, `reason` 메시지 포함) |
| 422 | 필수 필드 누락 |

---

### POST /webhook/slides/page  `[DEPRECATED]`

> **⚠️ DEPRECATED**: 이 엔드포인트는 더 이상 권장되지 않습니다. 대신 [POST /webhook/slides](#post-webhookslides)를 사용하세요. 단일 페이지만 처리하므로 페이지 추가·삭제 감지가 불가능하고, 스냅샷 일관성이 깨질 수 있습니다.

특정 슬라이드 페이지 하나에 대해서만 변경을 처리합니다.

```
POST /webhook/slides/page
Content-Type: application/json
```

**Request Body** (`SlidePageUpdateRequest`)

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `git_lab_project_id` | int | ✅ | 연관 GitLab 프로젝트 ID |
| `presentation_id` | string | ✅ | Google Slides 프레젠테이션 ID |
| `page_id` | string | ✅ | 처리할 슬라이드 페이지의 `pageObjectId` |
| `req_id` | string | ✅ | 연관 업무 ID |

```json
{
  "git_lab_project_id": 42,
  "presentation_id": "1abc...",
  "page_id": "p1",
  "req_id": "REQ-001"
}
```

**Response — 정상 (200)**: `POST /webhook/slides`와 동일하게 처리 결과 dict 반환 (`status`, 변경 정보 등).

| HTTP | 원인 |
|------|------|
| 200 | 정상 처리 |
| 400 | 처리 중 오류 (응답 `status=error`, `reason` 메시지 포함) |
| 422 | 필수 필드 누락 |

> **마이그레이션 안내**: 기존 Apps Script가 이 엔드포인트를 호출한다면, body에서 `page_id`를 제거하고 호출 경로를 `/webhook/slides`로 변경하면 됩니다. 서버가 전체 페이지를 스캔해 변경 페이지를 자동 감지하므로 동작은 더 정확해집니다.

---

## 6. 코드 검색 (Search)

OpenSearch에 색인된 `code-artifacts`(GitLab 커밋 단위로 GPT가 요약한 코드 아티팩트)를 검색합니다. 두 엔드포인트는 **요청 파라미터와 응답 스키마가 완전히 동일**하며, 차이는 검색 방식뿐입니다.

| 엔드포인트 | 검색 방식 | 특징 |
|-----------|---------|------|
| `GET /api/search/code` | BM25 키워드 | 빠르고 단순, 정확한 키워드 매치 |
| `GET /api/search/code/hybrid` | BM25 + 벡터(KNN) | 의미 검색 결합, 동의어·맥락에 강함 |

### GET /api/search/code

```
GET /api/search/code?q={검색어}&size={n}&git_lab_project_id={id}&req_id={req}
```

**Query Parameters** (`SearchRequest`)

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `q` | string | ✅ | - | 검색 쿼리 (키워드) |
| `git_lab_project_id` | int | - | (전체) | GitLab 프로젝트 ID 필터 |
| `req_id` | string | - | (전체) | 연관 업무 ID 필터 |
| `size` | int | - | 10 | 반환 결과 수 (1~50) |

**Response — 정상 (200)**

`list[CodeArtifactResponse]` 배열. 각 항목은 다음 필드를 가집니다 (응답은 camelCase alias로 직렬화됨).

| 필드 | 타입 | 설명 |
|------|------|------|
| `filePaths` | string[] | 변경된 파일 경로 목록 |
| `sourceType` | string | `FRONTEND` / `BACKEND` / `UNKNOWN` |
| `changeType` | string | `FEATURE` / `BUGFIX` / `REFACTOR` / `DOCS` 등 |
| `commitHash` | string | 커밋 SHA |
| `repositoryUrl` | string | 저장소 웹 URL |
| `projectName` | string | GitLab 프로젝트 이름 |
| `summary` | string | GPT-4o-mini가 생성한 코드 변경 요약 |
| `keywords` | string[] | 추출된 키워드 |
| `affectedModules` | string[] | 영향 모듈/패키지 |
| `dependencies` | string[] | 새로 추가·변경된 의존성 |

```json
[
  {
    "filePaths": ["src/payment/pg_client.py", "src/payment/retry_queue.py"],
    "sourceType": "BACKEND",
    "changeType": "REFACTOR",
    "commitHash": "a1b2c3d4...",
    "repositoryUrl": "https://gitlab.example.com/team/payment",
    "projectName": "payment-service",
    "summary": "PG 클라이언트 응답 파서를 JSON 기준으로 교체하고 재시도 큐 모듈을 분리.",
    "keywords": ["pg", "retry", "json"],
    "affectedModules": ["payment.pg", "payment.retry"],
    "dependencies": ["tenacity"]
  }
]
```

| HTTP | 원인 |
|------|------|
| 200 | 정상 (결과 없으면 빈 배열) |
| 422 | `q` 누락 또는 `size` 범위(1~50) 위반 |

---

### GET /api/search/code/hybrid

요청 파라미터·응답 스키마는 위 `GET /api/search/code`와 동일합니다. 검색 단계에서 BM25 점수와 임베딩 벡터 KNN 점수를 결합해 정렬합니다.

```
GET /api/search/code/hybrid?q={검색어}&size={n}
```

> **언제 어느 쪽을 쓸지**: 명확한 함수명·키워드를 찾을 때는 `code`, "결제 실패 처리"처럼 자연어 의도가 들어가는 검색에는 `code/hybrid`를 권장합니다.

---

## 공통 에러 코드

| HTTP | 원인 | 대응 |
|------|------|------|
| 400 | 슬라이드 처리 중 오류 (`POST /webhook/slides`, `POST /webhook/slides/page`) | 응답 `detail` 또는 `reason` 메시지 확인 |
| 401 | `X-Internal-Token` 누락 또는 불일치 (`POST /api/notifications`) | 헤더 값 확인 |
| 401 | `X-Gitlab-Token` 불일치 (`POST /webhook/gitlab`, 시크릿 설정 시) | GitLab 웹훅 설정의 Secret Token 확인 |
| 404 | 리소스 없음 | `detail` 메시지 확인 |
| 422 | 필수 파라미터 누락 또는 타입 불일치 | 유효성 오류 상세 확인 |
| 500 | 서버 내부 오류 | 서버 로그 확인 |

**422 응답 예시**

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["query", "user_id"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

---

## 공통 참고사항

- **Base URL**: `http://localhost:8000` (로컬 기준, 실제 배포에 따라 변경)
- **인증 헤더 종류**:
  - `X-Internal-Token` — `POST /api/notifications` (내부 서비스 간 호출 보호)
  - `X-Gitlab-Token` — `POST /webhook/gitlab` (`settings.gitlab_webhook_secret` 설정 시에만 검증)
  - `X-Gitlab-Event` — `POST /webhook/gitlab` (값: `Push Hook` | `Merge Request Hook` — 이외는 무시 응답)
  - 그 외 엔드포인트는 현 단계 MVP 기준 인증 없음
- **시간 형식**: 모든 `*_at` 필드는 ISO 8601(UTC). 프론트는 로컬타임존으로 변환해 표시 필요.
- **enum 직렬화 규칙**:
  - **요청(POST) 시**: 코드값(`"PM_APPROVED"`, `"NEW"`, `"COMPLETED"` 등)으로 입력
  - **응답(GET·SSE) 시**: 항상 한글 라벨(`"PM 승인"`, `"신규"`, `"완료"` 등)로 반환
  - 프론트가 응답에서 enum 코드값을 받지 않는다는 점 주의
  - 단, **검색 API의 `sourceType`·`changeType`은 enum 매핑 없이 원본 문자열(`BACKEND`, `REFACTOR` 등) 그대로 반환**됩니다.
- **DevTaskItem 자동 생성**: `content.common.req_id`가 있으면 서버가 GPT-4o-mini로 자동 enrich (최대 30초). 직접 채워서 보내면 자동 생성 건너뜀.
- **웹훅 비동기 처리**: 모든 웹훅은 200 응답을 먼저 반환하고 색인·요약은 백그라운드로 진행됩니다. 응답을 받았더라도 OpenSearch에 즉시 결과가 나타나지 않을 수 있음에 유의하세요.
