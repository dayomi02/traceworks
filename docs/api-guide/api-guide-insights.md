# AI 제언 조회 API 가이드

## `GET /projects/{project_id}/insights`

프로젝트의 온톨로지 데이터를 분석하여 AI가 생성한 관리 제언 목록을 반환합니다.  
역할별 일정 병목, 미구현 요구사항, 의존성 연쇄 지연, 인력 과부하, 스킬 불일치를 자동 감지합니다.

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
GET /projects/PRJ-001/insights
```

---

## 응답

### 성공 `200 OK`

```json
{
  "project_id": "PRJ-001",
  "generated_at": "2026-05-21T09:00:00+00:00",
  "insights": [
    {
      "type": "role_bottleneck",
      "severity": "critical",
      "title": "디자이너 파트 일정 지연 위험",
      "message": "디자이너 파트의 평균 진행률이 12%로 잔여 작업량이 96시간입니다. 리소스 재배분 또는 일정 조정을 즉시 검토하세요.",
      "affected_entities": []
    },
    {
      "type": "unimplemented_requirement",
      "severity": "critical",
      "title": "구현되지 않은 요구사항 감지",
      "message": "APPROVED 상태인 요구사항 2건에 대응하는 WBS 태스크가 없습니다. 누락 여부를 확인하고 태스크를 추가하세요.",
      "affected_entities": ["REQ-001", "REQ-005"]
    },
    {
      "type": "dependency_chain_risk",
      "severity": "warning",
      "title": "'로그인 API 구현' 의존성 연쇄 지연 위험",
      "message": "미진행 상태인 '로그인 API 구현' 태스크로 인해 하위 태스크 3개가 연쇄 지연될 수 있습니다. 담당자 배정과 착수 일정을 확인하세요.",
      "affected_entities": ["TASK-002", "TASK-005", "TASK-008"]
    },
    {
      "type": "person_overload",
      "severity": "warning",
      "title": "김개발 인력 과부하",
      "message": "김개발 님이 현재 3개 프로젝트에서 진행 중인 태스크를 보유하고 있으며 총 72시간의 작업량이 집중되어 있습니다. 일정 충돌 위험이 높습니다.",
      "affected_entities": ["PERSON-DEV01"]
    },
    {
      "type": "skill_mismatch",
      "severity": "warning",
      "title": "인력-스킬 불일치 감지",
      "message": "진행 중인 태스크 2건에서 담당자가 요구 스킬을 보유하지 않은 것으로 확인됩니다. 리소스 교체 또는 사전 교육을 검토하세요.",
      "affected_entities": ["TASK-012", "TASK-015"]
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

### 최상위

| 필드 | 타입 | 설명 |
|------|------|------|
| `project_id` | string | 요청한 프로젝트 ID |
| `generated_at` | string (ISO 8601) | 제언 생성 시각 (UTC) |
| `insights` | array | 제언 목록. 감지된 항목이 없으면 빈 배열 `[]` |

### `insights[*]`

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | string | 제언 유형 식별자 (하단 유형 목록 참고) |
| `severity` | `"critical"` \| `"warning"` \| `"info"` | 심각도. `critical` → `warning` 순으로 정렬되어 반환 |
| `title` | string | 제언 제목 (UI 카드 헤더에 사용) |
| `message` | string | AI가 생성한 자연어 제언 본문 (1~2문장) |
| `affected_entities` | string[] | 관련 엔티티 ID 목록 (task_id, req_id, person_id 등). 없으면 `[]` |

---

## 제언 유형 (`type`) 목록

| type | 한국어 | severity 기준 | affected_entities |
|------|--------|--------------|-------------------|
| `role_bottleneck` | 역할별 일정 병목 | 평균 진행률 < 15% → `critical`<br>15~30% → `warning` | 없음 (빈 배열) |
| `unimplemented_requirement` | 구현 누락 요구사항 | HIGH/CRITICAL 우선순위 포함 → `critical`<br>그 외 → `warning` | `req_id` 목록 |
| `dependency_chain_risk` | 의존성 연쇄 지연 | 블록된 태스크 3개 이상 → `critical`<br>2개 → `warning` | 블록된 `task_id` 목록 |
| `person_overload` | 멀티 프로젝트 인력 과부하 | 진행 중 작업 60h 초과 또는 참여 프로젝트 3개 초과 → `critical`<br>그 외 → `warning` | `person_id` |
| `skill_mismatch` | 인력-스킬 불일치 | 항상 `warning` | 불일치 `task_id` 목록 |

---

## UI 구현 가이드

### severity 뱃지 색상

| severity | 색상 | 용도 |
|----------|------|------|
| `critical` | 빨강 `#EF4444` | 즉각 조치 필요 |
| `warning` | 노랑 `#F59E0B` | 주의 요망 |
| `info` | 파랑 `#3B82F6` | 참고 정보 |

### 렌더링 순서
응답 배열 자체가 `critical → warning → info` 순으로 정렬되어 있으므로 **순서 그대로** 렌더링합니다.

### 빈 상태 처리
`insights` 배열이 비어 있으면 "현재 감지된 위험 항목이 없습니다" 메시지를 표시합니다.

### `affected_entities` 활용 예시
- `unimplemented_requirement`: req_id 클릭 시 해당 요구사항 상세로 이동
- `dependency_chain_risk`: task_id 클릭 시 WBS 태스크 상세로 이동
- `person_overload`: person_id로 팀원 현황 조회 가능

### 폴링 권장 주기
제언 생성에 LLM 호출이 포함되어 **응답까지 3~10초**가 소요될 수 있습니다.  
페이지 진입 시 1회 호출 후 수동 새로고침 버튼을 제공하는 방식을 권장합니다.
