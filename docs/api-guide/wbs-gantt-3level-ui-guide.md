# [프론트 가이드] WBS 간트 — 요구사항 대분류 > 중분류 > Task 3단계 트리

이 문서는 기존 평탄한 `ganttRows` 기반 간트 테이블을 **대분류(Large) > 중분류(Mid) > WBS Task** 3단계 계층 구조로 다시 그리기 위한 참고 가이드입니다. 특정 프레임워크에 종속되지 않게 데이터 구성 방법과 UI 패턴만 설명합니다. 기존 구현은 무시하고 새로 작성하는 것을 전제로 합니다.

---

## 1. 데이터 소스 — 2개의 API를 합친다

WBS API 한 개로는 대분류/중분류 이름을 알 수 없습니다 (Task의 `req_id`는 보통 Mid이고, Large의 이름은 별도로 가져와야 함). 다음 두 API를 **함께 호출**합니다.

| API | 용도 |
|-----|------|
| `GET /projects/{project_id}` | 요구사항 트리 (`requirements[]` = 대분류 + `children[]` Mid). 이름, 우선순위 등 메타데이터의 출처 |
| `GET /projects/{project_id}/wbs` | WBS Task 목록 (각 task의 `req_id`, `req_name`, 일정, 상태, 진행률 등) |

병렬로 호출 후 클라이언트에서 조립.

```js
const [project, wbs] = await Promise.all([
  fetch(`/projects/${id}`).then(r => r.json()),
  fetch(`/projects/${id}/wbs`).then(r => r.json()),
]);
```

---

## 2. 데이터 모델 — 무엇을 합치는가

**입력**
- `project.requirements` = `[ { req_id: "REQ-001", req_name, children: [ { req_id: "REQ-001-001", req_name, ... } ] } ]`
- `wbs` = `[ { task_id, task_name, wbs_code, req_id, req_name, status, progress, planned_start, planned_end, assignee, ... } ]`

**조립 키**
- Task의 `req_id`가 **Mid이면 (`REQ-XXX-YYY`)** 해당 Mid 노드 아래에 붙는다.
- Task의 `req_id`가 **Large이면 (`REQ-XXX`)** — Mid를 거치지 않고 Large 직속 Task가 됨. 별도 가상 그룹("기타" 또는 Large 직속)에 묶는다.
- Task의 `req_id`가 **null 또는 트리에 없는 ID이면** "미연결" 그룹으로 별도 묶음.

**출력 형태 (렌더링 직전 트리)**

```ts
type GanttTree = LargeGroup[];

interface LargeGroup {
  req_id: string;           // "REQ-001"
  req_name: string;
  mids: MidGroup[];
  direct_tasks: WbsTask[];  // Large 직속 task (보통 비어있음)
}

interface MidGroup {
  req_id: string;           // "REQ-001-001"
  req_name: string;
  tasks: WbsTask[];
}

// 최상단에 별도로 둠
interface UnlinkedGroup {
  tasks: WbsTask[];         // req_id 없거나 트리에 매칭 안 된 task
}
```

---

## 3. 트리 조립 알고리즘 (참고 의사코드)

```js
function buildGanttTree(requirements, wbsTasks) {
  // 1. 트리 인덱스 구축
  const largeById = new Map();      // req_id → LargeGroup
  const midToLarge = new Map();     // mid req_id → parent large req_id

  for (const lg of requirements) {
    largeById.set(lg.req_id, {
      req_id: lg.req_id,
      req_name: lg.req_name,
      mids: lg.children.map(m => ({
        req_id: m.req_id,
        req_name: m.req_name,
        tasks: [],
      })),
      direct_tasks: [],
    });
    for (const m of lg.children) midToLarge.set(m.req_id, lg.req_id);
  }

  const unlinked = [];

  // 2. Task를 Mid/Large/미연결로 분배
  for (const t of wbsTasks) {
    if (!t.req_id) { unlinked.push(t); continue; }

    const tokens = t.req_id.split('-');
    if (tokens.length >= 3) {
      // Mid 매칭
      const largeId = midToLarge.get(t.req_id);
      if (!largeId) { unlinked.push(t); continue; }
      const large = largeById.get(largeId);
      const mid = large.mids.find(m => m.req_id === t.req_id);
      mid.tasks.push(t);
    } else {
      // Large 직속
      const large = largeById.get(t.req_id);
      if (!large) { unlinked.push(t); continue; }
      large.direct_tasks.push(t);
    }
  }

  // 3. 정렬 — wbs_code 기준이 자연스러움
  const byWbsCode = (a, b) => a.wbs_code.localeCompare(b.wbs_code, undefined, { numeric: true });
  for (const lg of largeById.values()) {
    for (const m of lg.mids) m.tasks.sort(byWbsCode);
    lg.direct_tasks.sort(byWbsCode);
  }

  return {
    largeGroups: Array.from(largeById.values()),
    unlinked,
  };
}
```

---

## 4. UI — 테이블 행 구성 패턴

기존 코드는 `category` 플래그로 1단계 그룹만 표현했습니다. 3단계에서는 **행 종류를 3가지**로 늘립니다.

| 행 종류 | 시각 표현 | 데이터 |
|--------|----------|--------|
| `large` | 진한 보라 배경, 굵은 텍스트 16px | `req_id` + `req_name` + (자식 task 총 개수) |
| `mid` | 옅은 보라/회색 배경, 굵은 텍스트 13px, 왼쪽 들여쓰기 16px | `req_id` + `req_name` + (자식 task 개수) |
| `task` | 일반 행, 왼쪽 들여쓰기 32px, 트리 연결선(└) | 기존 task 필드 (담당자, 상태, %, 간트 바) |

평탄화 → 렌더링 직전 단계에서 행 배열로 펼치는 함수:

```js
function flattenForTable(tree) {
  const rows = [];
  for (const lg of tree.largeGroups) {
    const taskCount = lg.direct_tasks.length + lg.mids.reduce((s, m) => s + m.tasks.length, 0);
    if (taskCount === 0) continue;  // Task가 0개인 Large는 숨김(선택)
    rows.push({ kind: 'large', req_id: lg.req_id, name: lg.req_name, count: taskCount });

    for (const m of lg.mids) {
      if (m.tasks.length === 0) continue;
      rows.push({ kind: 'mid', req_id: m.req_id, name: m.req_name, count: m.tasks.length });
      for (const t of m.tasks) rows.push({ kind: 'task', ...t });
    }
    for (const t of lg.direct_tasks) {
      rows.push({ kind: 'task', ...t });
    }
  }
  if (tree.unlinked.length > 0) {
    rows.push({ kind: 'large', req_id: '—', name: '요구사항 미연결', count: tree.unlinked.length });
    for (const t of tree.unlinked) rows.push({ kind: 'task', ...t });
  }
  return rows;
}
```

---

## 5. 렌더링 — 행 종류별 분기 (참고 JSX)

> 기존 코드의 `row.category` 분기를 **`row.kind`** 분기로 교체합니다. 컬럼 구조(업무명/담당자/상태/%/간트 바)는 유지하고, **`large`/`mid` 행에서는 colSpan으로 첫 컬럼을 합쳐 헤더처럼 표시**합니다.

```jsx
<tbody>
  {rows.map((row, ri) => {
    if (row.kind === 'large') {
      return (
        <tr key={ri} style={{ background: '#ede9fe' }}>
          <td colSpan={5} style={{ padding: '10px 12px', fontWeight: 800, color: '#5b21b6', fontSize: 13 }}>
            {row.req_id} · {row.name}
            <span style={{ marginLeft: 8, fontSize: 11, color: '#7c3aed' }}>{row.count}건</span>
          </td>
        </tr>
      );
    }
    if (row.kind === 'mid') {
      return (
        <tr key={ri} style={{ background: '#f5f3ff' }}>
          <td colSpan={5} style={{ padding: '7px 12px 7px 28px', fontWeight: 700, color: '#6d28d9', fontSize: 12 }}>
            └ {row.req_id} · {row.name}
            <span style={{ marginLeft: 8, fontSize: 11, color: '#8b5cf6' }}>{row.count}건</span>
          </td>
        </tr>
      );
    }
    // task 행 — 기존 td 그대로, 들여쓰기만 깊게
    return (
      <tr key={ri} style={{ cursor: 'pointer' }} onClick={() => row.task_id && setSelectedTaskId(row.task_id)}>
        <td style={{ ...s.td, paddingLeft: 48 }}>{row.task_name}</td>
        <td style={{ ...s.td, textAlign: 'center' }}>
          <Avatar text={row.assignee} color={row.assigneeColor} size="xs" style={{ margin: '0 auto' }} />
        </td>
        <td style={s.td}><Tag type={row.statusType} style={{ fontSize: 10 }}>{row.status}</Tag></td>
        <td style={{ ...s.td, fontWeight: 700, color: row.bar.color }}>{row.pct}%</td>
        <td style={{ ...s.td, background: '#f9fafb', padding: '0 8px', height: 36 }}>
          {/* 기존 간트 바 — 그대로 유지 */}
        </td>
      </tr>
    );
  })}
</tbody>
```

들여쓰기 가이드:
- Large 행: 좌측 패딩 12px
- Mid 행: 좌측 패딩 28px (Large 대비 +16)
- Task 행 업무명 셀: 좌측 패딩 48px (Mid 대비 +20)

---

## 6. 인터랙션 (선택)

- **접기/펼치기**: Large 행 클릭 시 그 하위 Mid + Task 모두 토글. Mid 행 클릭 시 그 Task만 토글.
- **기본 상태**: 전부 펼쳐진 상태 (사용자가 한눈에 의존 관계 파악).
- **빈 그룹 숨김**: Task가 0인 Large/Mid는 행 자체를 생성하지 않음 (위 의사코드 4번 단계 참고).
- **"요구사항 미연결" 그룹**: 항상 맨 아래에. Task가 0이면 표시하지 않음.

---

## 7. 정렬 우선순위

1. Large: API 응답 순서를 그대로 사용 (백엔드가 `req_id` 숫자 기준 정렬해서 보냄).
2. Mid: 같음 — 백엔드 응답 순서 유지.
3. Task: `wbs_code` 자연 정렬 (`1.1`, `1.2`, `1.10` 순). `localeCompare(undefined, { numeric: true })` 사용.

직접 정렬할 일은 거의 없고, 정렬 기준 변경 옵션(우선순위·담당자별 등)이 필요할 때만 클라이언트에서 처리.

---

## 8. 자주 묻는 질문

**Q. Task의 `req_id`가 정확히 Large인 경우와 Mid인 경우를 어떻게 구분하나요?**
A. `'-' split` 토큰 수로 판단합니다. 토큰 3개 이상 → Mid, 2개 → Large. (백엔드 `_build_requirement_tree`와 동일 규약)

**Q. `req_id`가 없는 Task는 어떻게 처리하나요?**
A. "요구사항 미연결" 그룹으로 묶어 맨 아래에 표시합니다. WBS는 보통 RFP 분석 시 Mid 요구사항과 매핑되지만, 사용자가 수동으로 추가한 Task는 미연결 상태일 수 있습니다.

**Q. 모든 Mid가 다 Task를 가지나요?**
A. 아닙니다. Task가 0인 Mid는 행을 생성하지 않습니다 (위 평탄화 함수 참고). 요구사항 목록만 보고 싶으면 프로젝트 상세 화면을 이용합니다.

**Q. 같은 Mid 아래 Task가 여러 개일 때 의존성 표시는 어떻게?**
A. `depends_on` 필드는 `wbs_code` 배열입니다. 간트 바 위에 화살표를 그리거나, 행 호버 시 의존 task를 하이라이트하는 방식이 일반적. 본 가이드 범위 외.

**Q. 진행률 합계를 그룹 행에 표시할 수 있나요?**
A. 가능. Mid 행에 "5건 중 2건 완료" 또는 평균 진행률 % 뱃지를 추가해도 됩니다. 단, 그룹 행의 colSpan으로 첫 컬럼을 합치고 있어 우측 컬럼 공간이 없으니, 첫 컬럼 안에 우측 정렬로 배치하세요.

---

## 9. AI 코드 에이전트 작업 지시 프롬프트

이 문서를 참조해서 화면을 새로 작성시키고 싶을 때 그대로 복사해서 쓸 수 있는 프롬프트입니다.

> "WBS 간트 화면을 **요구사항 대분류 > 중분류 > Task** 3단계 트리 구조로 다시 그려줘.
>
> 데이터 소스:
> - `GET /projects/{project_id}` 응답의 `requirements` 배열 (Large + children Mid)
> - `GET /projects/{project_id}/wbs` 응답의 task 목록 (각 task의 `req_id`, `req_name`, `wbs_code`, `status`, `progress`, `planned_start`, `planned_end`, `assignee`, `depends_on`)
>
> 두 응답을 병렬로 받아 클라이언트에서 트리를 조립한다. 조립 규칙·UI 패턴·들여쓰기·행 종류 분기·미연결 처리·평탄화 함수는 모두 `docs/api-guide/wbs-gantt-3level-ui-guide.md`를 따른다.
>
> 요구사항:
> - 기존 `ganttRows.category` 기반 평탄 구조는 무시하고 완전히 새로 작성
> - 행 종류는 `large` / `mid` / `task` 3가지. colSpan으로 그룹 헤더 표현
> - 들여쓰기: Large 12px / Mid 28px / Task 업무명 셀 48px
> - 정렬은 백엔드 응답 순서 + Task만 `wbs_code` 자연 정렬
> - Task가 0인 Large/Mid는 행 생성 X
> - `req_id` 없거나 트리에 매칭 안 되는 Task는 '요구사항 미연결' 그룹으로 맨 아래
> - 기존 간트 바·Tag·Avatar·클릭→상세 인터랙션은 task 행에서 그대로 유지
>
> 컬럼 구조(업무명/담당자/상태/%/간트 바)는 유지하되, Large/Mid 그룹 행은 첫 컬럼에 모든 정보를 합쳐 표시한다."

---

## 10. 관련 문서

- 응답 형식: [api-guide-project-detail.md](api-guide-project-detail.md), `GET /projects/{project_id}/wbs` (API 문서 별도)
- 요구사항 트리 렌더링 (프로젝트 상세 화면용): [project-detail-requirements-ui-guide.md](project-detail-requirements-ui-guide.md)
