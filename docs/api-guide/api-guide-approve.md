# POST /tasks/{task_id}/approve — PM 승인/반려 API

## 개요

태스크 상태 변경 요청에 대해 PM이 **승인** 또는 **반려**하는 API입니다.

작업자가 태스크 상태를 `완료`로 변경하거나, `완료` 상태에서 되돌리는 경우 즉시 반영되지 않고 PM 승인 대기 상태(`pending_approval`)가 됩니다. PM은 알림 목록에서 해당 요청을 확인하고 이 API를 호출해 처리합니다.

### PM 승인이 필요한 전환

| 이전 상태 | 변경 요청 상태 | 처리 방식 |
|---|---|---|
| 미진행 | **완료** | PM 승인 필요 |
| 진행 | **완료** | PM 승인 필요 |
| 완료 | 미진행 / 진행 등 | PM 승인 필요 |
| 미진행 | 진행 | **즉시 반영** (승인 불필요) |

---

## 엔드포인트

```
POST /tasks/{task_id}/approve
```

### Path Parameter

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `task_id` | string | ✅ | 태스크 ID (예: `TEST001-R1A2B3C4`) |

### Headers

| 헤더 | 값 | 필수 | 설명 |
|---|---|---|---|
| `Authorization` | `Bearer {access_token}` | ✅ | PM 로그인 후 발급된 JWT 토큰 |
| `Content-Type` | `application/json` | ✅ | |

---

## Request Body

```json
{
  "notification_event_id": 42,
  "is_approved": true,
  "rejection_reason": null
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `notification_event_id` | integer | ✅ | 알림 목록(`GET /api/notifications`) 응답의 `id` 값 |
| `is_approved` | boolean | ✅ | `true` = 승인 / `false` = 반려 |
| `rejection_reason` | string \| null | 반려 시 필수 | 반려 사유. `is_approved: false`일 때 입력 |

---

## Response

### 승인 성공 (`200 OK`)

```json
{
  "task_id": "TEST001-R1A2B3C4",
  "result": "approved",
  "new_task_id": null
}
```

### 승인 성공 — 완료 → 다른 상태 전환 (`200 OK`)

`완료` 상태에서 되돌리는 요청을 승인하면 추가 작업 태스크가 자동 생성됩니다.

```json
{
  "task_id": "TEST001-R1A2B3C4",
  "result": "approved",
  "new_task_id": "TEST001-RAA07A5ED"
}
```

### 반려 성공 (`200 OK`)

```json
{
  "task_id": "TEST001-R1A2B3C4",
  "result": "rejected",
  "new_task_id": null
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `task_id` | string | 처리된 태스크 ID |
| `result` | `"approved"` \| `"rejected"` | 처리 결과 |
| `new_task_id` | string \| null | `완료 → ?` 승인 시 생성된 추가 태스크 ID. 그 외 `null` |

---

## 오류 응답

### `404 Not Found` — 승인 대기 이력 없음

```json
{
  "detail": "task_id=TEST001-R1A2B3C4, notification_event_id=42 에 해당하는 승인 대기 이력이 없습니다."
}
```

이미 승인/반려된 건이거나, `notification_event_id`가 올바르지 않은 경우입니다.

### `401 Unauthorized` — 인증 토큰 없음 또는 만료

```json
{
  "detail": "Not authenticated"
}
```

---

## 프론트엔드 연동 흐름

### 1. PM 알림 목록 조회

`GET http://dweax.iptime.org:50009/api/notifications` 를 호출해 알림 목록을 받습니다.

`content_json` 안의 `noti_type`이 `"PM_APPROVAL_REQUEST"`인 항목이 승인 대기 건입니다.

```json
{
  "id": 42,
  "title": "'로그인 API 구현' 작업이 완료되었습니다.",
  "content_json": {
    "common": {
      "task_id": "TEST001-R1A2B3C4",
      "task_name": "로그인 API 구현",
      "req_id": "REQ-TEST001-1",
      "req_name": "사용자 인증 기능 개발",
      "assignee_user_name": "박개발",
      "assignee_user_role": "개발자",
      "noti_type": "PM_APPROVAL_REQUEST"
    },
    "status_change": {
      "prev_status": "IN_PROGRESS",
      "new_status": "COMPLETED",
      "change_reason": null
    }
  }
}
```

### 2. 승인 버튼 클릭

`content_json.common.task_id`와 알림의 `id`(`notification_event_id`)를 사용해 호출합니다.

```js
// 승인
await fetch(`/tasks/${task_id}/approve`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    notification_event_id: 42,
    is_approved: true,
    rejection_reason: null,
  }),
})
```

### 3. 반려 버튼 클릭

```js
// 반려
await fetch(`/tasks/${task_id}/approve`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    notification_event_id: 42,
    is_approved: false,
    rejection_reason: 'PG사 응답 포맷 검토 후 재요청 필요',
  }),
})
```

### 4. 처리 결과

- **승인**: 태스크 상태가 요청된 값으로 변경되며, 담당 작업자에게 승인 알림이 전송됩니다.
- **반려**: 태스크 상태는 변경되지 않으며, 담당 작업자에게 반려 사유와 함께 알림이 전송됩니다.
- `완료 → ?` 승인 시 응답의 `new_task_id`로 추가 생성된 태스크를 WBS 목록에서 확인할 수 있습니다.

---

## Base URL

```
http://dweax.iptime.org:50008
```

> 알림 목록 조회(`GET /api/notifications`)는 `http://dweax.iptime.org:50009` 서버를 사용합니다.
