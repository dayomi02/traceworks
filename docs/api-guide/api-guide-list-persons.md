# 인력 목록 조회 API 가이드

## `GET /persons`

Fuseki에 등록된 전체 인력 풀의 요약 정보를 반환합니다. 각 인력의 역할(role)과 보유 스킬(skills)을 함께 포함하며, 인력 추천 화면의 후보 풀 탐색·필터링에 사용됩니다.

---

## 요청

### Query Parameter
없음

### 인증
불필요

### 예시
```
GET /persons
```

---

## 응답

### 성공 `200 OK`

```json
[
  {
    "person_id": "PM001",
    "person_name": "홍길동",
    "role": "PM",
    "rank": null,
    "skills": [
      { "name": "프로젝트 관리", "proficiency": 0.95 },
      { "name": "리스크 관리",  "proficiency": 0.90 },
      { "name": "예산 관리",    "proficiency": 0.85 }
    ]
  },
  {
    "person_id": "PM002",
    "person_name": "김지훈",
    "role": "PM",
    "rank": null,
    "skills": [
      { "name": "프로젝트 관리", "proficiency": 0.88 },
      { "name": "예산 관리",     "proficiency": 0.85 }
    ]
  },
  {
    "person_id": "DEV015",
    "person_name": "박서연",
    "role": "개발자",
    "rank": null,
    "skills": [
      { "name": "React",      "proficiency": 0.90 },
      { "name": "TypeScript", "proficiency": 0.85 },
      { "name": "Node.js",    "proficiency": 0.80 }
    ]
  }
]
```

빈 목록일 경우 `[]`을 반환합니다.

### 에러

| 상태 코드 | 설명 |
|----------|------|
| `503 Service Unavailable` | 온톨로지 저장소(Fuseki) 연결 불가 |

---

## 응답 필드 상세

### 배열 요소 (`PersonSummary`)

| 필드 | 타입 | Nullable | 설명 |
|------|------|----------|------|
| `person_id` | string | - | 인력 고유 ID (예: `PM001`, `DEV015`) |
| `person_name` | string | - | 이름 |
| `role` | string | ✅ | 역할. 현재 시드 기준 `PM` / `기획자` / `개발자` 중 하나 |
| `rank` | string | ✅ | 직급. 현재 응답에서는 사용되지 않아 `null`이 들어감 (스키마 호환용) |
| `skills` | array | - | 보유 스킬 목록. 없으면 빈 배열 `[]` |

### `skills[*]` (`SkillRef`)

| 필드 | 타입 | Nullable | 설명 |
|------|------|----------|------|
| `name` | string | - | 스킬명 (예: `React`, `프로젝트 관리`) |
| `proficiency` | number | ✅ | 숙련도 (0.0 ~ 1.0). Fuseki의 `pm:proficiencyLevel` |

---

## 정렬

- 응답은 `person_id` 오름차순으로 정렬되어 반환됩니다 (SPARQL `ORDER BY ?personId`).
- 클라이언트에서 다른 기준으로 정렬해야 할 때만 추가 정렬을 적용하세요.

---

## 사용 예시

### 1. 역할별 그룹핑 (JS)
```js
const persons = await fetch('/persons').then(r => r.json());
const grouped = persons.reduce((acc, p) => {
  const key = p.role || '미지정';
  (acc[key] ??= []).push(p);
  return acc;
}, {});
// { PM: [...], 기획자: [...], 개발자: [...] }
```

### 2. 스킬 보유자 필터링
```js
const reactDevs = persons.filter(p =>
  p.skills.some(s => s.name === 'React' && (s.proficiency ?? 0) >= 0.8)
);
```

### 3. 인력 카드 렌더링 (의사 JSX)
```jsx
{persons.map(p => (
  <Card key={p.person_id}>
    <Avatar text={p.person_name} />
    <Title>{p.person_name}</Title>
    <Tag>{p.role ?? '미지정'}</Tag>
    <SkillChips skills={p.skills.slice(0, 3)} />
  </Card>
))}
```

---

## 참고

- **상세 조회**: 특정 인력의 참여 프로젝트 이력까지 보려면 `GET /persons/{person_id}` 사용.
- **가용성 조회**: 실시간 가용성(진행중 태스크 기반)이 필요하면 `GET /persons/availability` 사용.
- **인력 추천**: 프로젝트 기준 자동 추천은 `POST /projects/{project_id}/recommend-staff` 사용.
- 인력 등록 API(`POST /persons`)는 현재 미구현 상태입니다. 인력 데이터는 [backend/db/seeds/002_persons.ttl](../../backend/db/seeds/002_persons.ttl) 시드 스크립트로 적재합니다.
- 역할 값은 시드 기준 3종(`PM` / `기획자` / `개발자`)이지만 향후 추가 가능. 화면에서는 동적으로 키 수집을 권장합니다.
