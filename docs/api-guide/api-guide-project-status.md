# 프로젝트 상태 관리 API 가이드

프로젝트 상태(`projectStatus`)는 `PLANNING` / `ACTIVE` / `COMPLETED` 3가지로 관리되며, 시작일과 현재 날짜를 기반으로 자동 파생됩니다. `COMPLETED` 전환은 명시적인 완료 처리 API 호출이 필요합니다.

---

## 상태 정의

| 상태 | 의미 | 결정 규칙 |
|------|------|----------|
| `PLANNING` | 시작 전 (계획 단계) | 시작일이 오늘보다 미래 |
| `ACTIVE` | 진행 중 | 시작일이 오늘 또는 과거 (종료일 경과 여부 무관) |
| `COMPLETED` | 완료 | `POST /projects/{project_id}/complete` 호출로 명시적 전환됨 |

⚠️ **종료일이 지나도 자동으로 `COMPLETED`가 되지 않습니다.** 반드시 완료 처리 API를 호출해야 합니다.

---

## `POST /projects/{project_id}/complete` — 프로젝트 완료 처리

프로젝트를 `COMPLETED` 상태로 전환합니다.

### 요청

#### Path Parameter

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `project_id` | string | ✅ | 프로젝트 ID (예: `PRJ-001`) |

#### 인증
**필요** — `Authorization: Bearer <token>` 헤더 포함

#### Body
없음

#### 예시
```http
POST /projects/PRJ-001/complete
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 응답

#### 성공 `200 OK`

응답 본문은 `GET /projects/{project_id}`와 동일한 `ProjectDetail` 형식이며 `project_status`가 `"COMPLETED"`로 반환됩니다.

```json
{
  "project_id": "PRJ-001",
  "project_name": "공공 의료 데이터 플랫폼 구축",
  "project_status": "COMPLETED",
  "start_date": "2026-05-01",
  "end_date": "2026-10-31",
  "...": "기타 필드는 GET /projects/{project_id} 응답과 동일"
}
```

#### 에러

| 상태 코드 | 설명 |
|----------|------|
| `401 Unauthorized` | 토큰 누락 또는 만료 |
| `403 Forbidden` | 호출 사용자가 해당 프로젝트의 PM이 아님 |
| `404 Not Found` | 존재하지 않는 `project_id` |
| `503 Service Unavailable` | 온톨로지 저장소 연결 불가 |

```json
// 403 예시
{
  "detail": "프로젝트 완료 처리는 해당 프로젝트의 PM만 가능합니다."
}

// 404 예시
{
  "detail": "프로젝트를 찾을 수 없습니다: PRJ-999"
}
```

### 동작 특성

- **PM 권한 필요** — 해당 프로젝트에 `pm:role "PM"`으로 `participatesIn`된 인력만 호출 가능합니다. 사용자의 `name`이 Fuseki Person의 `personName`과 일치해야 합니다.
- **멱등성** — 이미 `COMPLETED` 상태인 프로젝트에 PM이 재호출하면 `200 OK`로 정상 응답합니다.
- **재오픈 미지원** — 한 번 완료된 프로젝트를 다시 `ACTIVE`로 되돌리는 API는 제공되지 않습니다.

---

## `GET /projects?status={status}` — 상태 필터 목록 조회

기존 프로젝트 목록 API에 `status` 쿼리 파라미터가 추가되었습니다.

### 요청

#### Query Parameter

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `status` | string | - | 상태 필터. `PLANNING` \| `ACTIVE` \| `COMPLETED` 중 하나. 생략 시 전체 반환 |

#### 인증
불필요

#### 예시
```http
GET /projects?status=ACTIVE
GET /projects?status=PLANNING
GET /projects?status=COMPLETED
GET /projects                    # 전체
```

### 응답

#### 성공 `200 OK`

```json
[
  {
    "project_id": "PRJ-001",
    "project_name": "공공 의료 데이터 플랫폼 구축",
    "domain": "공공",
    "status": "ACTIVE",
    "start_date": "2026-05-01",
    "end_date": "2026-10-31",
    "overall_progress": 42.5
  },
  {
    "project_id": "PRJ-002",
    "project_name": "차세대 ERP 시스템",
    "domain": "금융",
    "status": "PLANNING",
    "start_date": "2026-07-01",
    "end_date": "2027-03-31",
    "overall_progress": 0.0
  }
]
```

#### 에러

| 상태 코드 | 설명 |
|----------|------|
| `422 Unprocessable Entity` | `status` 값이 허용되지 않은 문자열 |

```json
// 422 예시 (status=INVALID 호출 시)
{
  "detail": [
    {
      "type": "literal_error",
      "loc": ["query", "status"],
      "msg": "Input should be 'PLANNING', 'ACTIVE' or 'COMPLETED'"
    }
  ]
}
```

### 응답 필드

| 필드 | 타입 | Nullable | 설명 |
|------|------|----------|------|
| `project_id` | string | - | 프로젝트 고유 ID |
| `project_name` | string | - | 프로젝트명 |
| `domain` | string | ✅ | 사업 분야 |
| `status` | string | - | **파생된** 현재 상태. `PLANNING` \| `ACTIVE` \| `COMPLETED` |
| `start_date` | string (YYYY-MM-DD) | ✅ | 프로젝트 시작일 |
| `end_date` | string (YYYY-MM-DD) | ✅ | 프로젝트 종료일 |
| `overall_progress` | number | - | 전체 공정률 (0.0~100.0) |

---

## 프론트엔드 사용 시 주의사항

### 1. 상태 표시 색상 가이드 (제안)

| 상태 | 권장 색상 | 라벨 |
|------|----------|------|
| `PLANNING` | 회색/파랑 | "시작 전" 또는 "예정" |
| `ACTIVE` | 초록 | "진행 중" |
| `COMPLETED` | 짙은 회색 | "완료" |

### 2. 완료 처리 버튼 UX

- 완료 처리는 **돌이킬 수 없으므로** 클릭 전 확인 다이얼로그를 권장합니다.
- 이미 `COMPLETED`인 프로젝트에는 버튼을 비활성화하거나 숨김 처리.

```javascript
// 예시
const handleComplete = async (projectId) => {
  if (!confirm('프로젝트를 완료 처리하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) return;
  await fetch(`/projects/${projectId}/complete`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` },
  });
};
```

### 3. 종료일 경과 표시

종료일이 지났지만 `ACTIVE`인 프로젝트는 시각적으로 강조하면 UX에 도움이 됩니다 (예: 빨간 뱃지 "기한 초과"). 단, 상태값 자체는 변하지 않으니 프론트엔드에서 별도로 계산하세요.

```javascript
const isOverdue = project.status === 'ACTIVE' &&
                  project.end_date &&
                  new Date(project.end_date) < new Date();
```

### 4. 필터 UI 예시

```jsx
<select onChange={e => setStatusFilter(e.target.value)}>
  <option value="">전체</option>
  <option value="PLANNING">시작 전</option>
  <option value="ACTIVE">진행 중</option>
  <option value="COMPLETED">완료</option>
</select>
```

---

## 관련 API

- [`GET /projects/{project_id}`](api-guide-project-detail.md) — 프로젝트 상세 (응답의 `project_status`도 동일하게 파생됨)
- `GET /projects/{project_id}/wbs` — WBS 태스크 목록
- `GET /dashboard/projects` — 내 프로젝트 목록 (상태 파생 동일하게 적용)
