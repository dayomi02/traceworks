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
| `presentation_id` | string | - | `null` | Google Slides 프레젠테이션 ID. 자동 enrich 시 슬라이드 스냅샷 조회를 해당 프레젠테이션으로 한정합니다 |
| `gitlab_project_id` | int | - | `null` | GitLab 프로젝트 ID. 자동 enrich 시 OpenSearch 코드 아티팩트 조회를 해당 프로젝트로 한정합니다 |

```json
{
  "title": "결제 모듈 개편 — PM 승인 완료",
  "message": "PG 연동 리팩터링 테스크가 승인되었습니다.",
  "project_id": "PRJ-PAY",
  "presentation_id": "1mz4IGJcXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "gitlab_project_id": 123,
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

> **자동 enrich**: `content.common.req_id`가 있고 `content.dev_task_items`가 비어 있으면 서버가 자동으로 `dev_task_items`를 채워서 저장합니다(GPT-4o-mini 분석, 최대 30초). 이때 `presentation_id`·`gitlab_project_id`를 함께 보내면 해당 프레젠테이션과 GitLab 프로젝트로 조회 범위를 한정합니다(같은 `req_id`가 여러 프로젝트/프레젠테이션에 걸쳐 있을 때 유용).

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