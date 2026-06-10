# Traceworks MVP — 전체 흐름 테스트 가이드

> **BASE URL**: `http://localhost:8000`  
> **서버 실행**: `cd backend && uv run uvicorn app.main:app --reload --port 8000`  
> **Swagger UI**: `http://localhost:8000/docs`

---

## 테스트 인력 데이터 (Fuseki 적재 완료)

| person_id | 이름 | 역할 | 직급 | 가용성 |
|-----------|------|------|------|--------|
| `PM001` | 홍길동 | PM | 수석 | 0.85 |
| `PM002` | 김지훈 | PM | 책임 | 0.70 |
| `PL001` | 이수연 | 기획자 | 선임 | 0.90 |
| `PL002` | 박서준 | 기획자 | 주임 | 0.95 |
| `BE001` | 김철수 | 개발자 | 수석 | 0.75 |
| `BE002` | 최민준 | 개발자 | 선임 | 0.80 |
| `BE003` | 정다은 | 개발자 | 선임 | 0.95 |
| `FE001` | 최예린 | 개발자 | 선임 | 0.80 |
| `FE002` | 한승우 | 개발자 | 주임 | 1.00 |
| `DS001` | 강나현 | UIUX 디자이너 | 선임 | 0.83 |
| `QA001` | 윤서연 | QA | 선임 | 0.88 |
| `DBA001` | 오현석 | DBA | 수석 | 0.70 |

> 인력 재적재: `cd backend && uv run python scripts/seed_fuseki.py`

---

## STEP 1. 로그인

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "pm@traceworks.com",
    "password": "traceworks1!"
  }'
```

**Response**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "e5dda30d-...",
    "email": "pm@traceworks.com",
    "name": "홍길동",
    "role": "pm"
  }
}
```

> 이후 모든 요청에 `Authorization: Bearer {access_token}` 헤더 추가

**역할별 테스트 계정**

| 역할 | 이메일 | 비밀번호 |
|------|--------|---------|
| PM | `pm@traceworks.com` | `traceworks1!` |
| 기획자 | `planner@traceworks.com` | `traceworks1!` |
| 개발자 | `dev@traceworks.com` | `traceworks1!` |

---

## STEP 2. RFP 파일 업로드

```bash
curl -X POST http://localhost:8000/rfp/upload \
  -H "Authorization: Bearer {TOKEN}" \
  -F "file=@/path/to/rfp.pdf"
```

> PDF 파일이 없다면 아래 샘플 텍스트로 .txt 파일을 만들어 업로드해도 됩니다.  
> 실제 테스트용 RFP 텍스트 파일 → `docs/sample_rfp.txt` (아래 STEP 참고)

**Response**
```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "file_name": "자재료_통합관리시스템.pdf",
  "extracted_text": "...",
  "page_count": 12,
  "status": "extracted"
}
```

> **`rfp_id`를 저장해두세요.** 이후 모든 단계에서 사용합니다.  
> 예시: `export RFP_ID=RFP_A1B2C3D4E5`

---

## STEP 2-1. 샘플 RFP 텍스트 파일 만들기 (PDF 없을 때)

```bash
cat > /tmp/sample_rfp.txt << 'EOF'
제안요청서 (RFP)

사업명: 자재료 통합 관리 시스템 구축
발주기관: 한국자재관리원
사업예산: 1,200,000,000원
사업기간: 2025.01.01 ~ 2025.08.31
계약방식: 일반경쟁입찰
사업유형: 공공/시스템 구축

1. 사업 개요
자재료 업무 프로세스를 통합하고 자동화하여 업무 효율을 향상시키는 시스템을 구축한다.

2. 기능 요구사항
REQ-001: 사용자 로그인 기능 (이메일/PW, 소셜 로그인)
REQ-002: 관한 관리 기능 (역할 기반 접근 제어)
REQ-003: 관한 관리 기능 (관리자 조직 목록 관리)
REQ-004: 데이터 입력 및 보고 기능
REQ-005: 시스템 동시 접속 1,000명 이상 처리
REQ-006: 항목 입력/등록 및 이력 조회 기능
REQ-007: 재고 현황 실시간 대시보드
REQ-008: 발주 요청 및 승인 워크플로우
REQ-009: 공급업체 정보 관리 및 평가
REQ-010: 보고서 자동 생성 및 엑셀 내보내기

3. 기술 스택
- Backend: Java, Spring Boot
- Database: Oracle
- Frontend: React, TypeScript
- 서버: Linux, Tomcat

4. 투입 인력
- PM 1명, 기획자 1명, 백엔드 개발자 2명, 프론트엔드 개발자 1명, QA 1명

주관사: (주)케이고솔루션
협력사: (주)테크파트너, ABC시스템즈
EOF
```

```bash
curl -X POST http://localhost:8000/rfp/upload \
  -H "Authorization: Bearer {TOKEN}" \
  -F "file=@/tmp/sample_rfp.txt"
```

---

## STEP 3. AI 분석 실행

```bash
curl -X POST http://localhost:8000/rfp/${RFP_ID}/analyze \
  -H "Authorization: Bearer {TOKEN}"
```

> LLM 호출로 10~30초 소요됩니다.

**Response 주요 필드**
```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "analyzed",
  "project": {
    "project_name": "자재료 통합 관리 시스템 구축",
    "client_name": "한국자재관리원",
    "contract_type": "일반경쟁입찰",
    "business_type": "공공/시스템 구축",
    "budget": "1,200,000,000",
    "start_date": "2025-01-01",
    "end_date": "2025-08-31"
  },
  "requirements": [
    { "req_id": "REQ-001", "req_name": "사용자 로그인", "importance": "높음", "priority": "상" }
  ],
  "wbs": [
    { "wbs_code": "REQ-001.PM.1", "task_name": "로그인 요구사항 확정", "assignee_role": "PM" }
  ],
  "required_roles": [
    { "role": "PM", "count": 1 },
    { "role": "개발자", "count": 2 }
  ],
  "confidence_score": 0.88
}
```

---

## STEP 4. 프로젝트 개요 수정 + 주관사·협력사 저장

```bash
curl -X PATCH http://localhost:8000/rfp/${RFP_ID}/analysis \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "project": {
      "project_name": "자재료 통합 관리 시스템 구축",
      "client_name": "한국자재관리원",
      "budget": "1,200,000,000",
      "start_date": "2025-01-01",
      "end_date": "2025-08-31",
      "contract_type": "일반경쟁입찰",
      "business_type": "공공/시스템 구축"
    },
    "consortium": {
      "lead_company": "(주)케이고솔루션",
      "partner_companies": ["(주)테크파트너", "ABC시스템즈"]
    }
  }'
```

**Response**
```json
{ "rfp_id": "RFP_A1B2C3D4E5", "status": "reviewed" }
```

---

## STEP 5. 요구사항 수정

```bash
curl -X PATCH http://localhost:8000/rfp/${RFP_ID}/analysis \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "requirements": [
      {
        "req_id": "REQ-001",
        "req_category": "기능",
        "req_name": "사용자 로그인 기능",
        "req_description": "이메일/PW 및 소셜 로그인(카카오·네이버) 지원",
        "importance": "높음",
        "priority": "상"
      },
      {
        "req_id": "REQ-002",
        "req_category": "기능",
        "req_name": "권한 관리 기능",
        "req_description": "역할 기반 접근 제어 (Admin/User)",
        "importance": "높음",
        "priority": "상"
      }
    ]
  }'
```

---

## STEP 6. WBS AI 재생성 (선택)

```bash
curl -X POST http://localhost:8000/rfp/${RFP_ID}/regenerate-wbs \
  -H "Authorization: Bearer {TOKEN}"
```

**Response**
```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "reviewed",
  "wbs": [ ... ],
  "analysis_metadata": { "total_wbs_tasks": 52 }
}
```

---

## STEP 7. WBS 항목 수정

```bash
curl -X PATCH http://localhost:8000/rfp/${RFP_ID}/analysis \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "wbs": [
      {
        "wbs_code": "REQ-001.PM.1",
        "task_name": "로그인 요구사항 확정 및 일정 수립",
        "assignee_role": "PM",
        "estimated_days": 3,
        "planned_hours": 24
      }
    ]
  }'
```

---

## STEP 8. 프로젝트 확정 (RFP → 실제 프로젝트 생성)

```bash
curl -X POST http://localhost:8000/rfp/${RFP_ID}/confirm \
  -H "Authorization: Bearer {TOKEN}"
```

**Response**
```json
{
  "project_id": "PRJ_A1B2C3D4E5",
  "tasks_created": 47,
  "triples_inserted": 312,
  "fuseki_graph_uri": "https://ontology.example.org/instances#project_prj_a1b2c3d4e5",
  "next_step": "인력 추천 API를 실행하세요: POST /projects/PRJ_A1B2C3D4E5/recommend-staff"
}
```

> **`project_id`를 저장해두세요.**  
> 예시: `export PROJECT_ID=PRJ_A1B2C3D4E5`

---

## STEP 9. AI 인력 추천

```bash
curl -X POST http://localhost:8000/projects/${PROJECT_ID}/recommend-staff \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "persist": false,
    "top_k": 10
  }'
```

**Response 예시** (실제 Fuseki 인물 데이터 기반)
```json
[
  {
    "rank": 1,
    "person_id": "BE001",
    "person_name": "김철수",
    "role": "개발자",
    "grade": "수석",
    "similarity_score": 0.91,
    "availability_score": 0.75,
    "matched_skills": [
      { "skill": "Java", "proficiency": 0.95 },
      { "skill": "Spring Boot", "proficiency": 0.93 }
    ],
    "reason": "Java(0.95)·Spring Boot(0.93)·Oracle(0.88) 역량 보유. 가용성 0.75."
  },
  {
    "rank": 2,
    "person_id": "PM001",
    "person_name": "홍길동",
    "role": "PM",
    "grade": "수석",
    "similarity_score": 0.88,
    "availability_score": 0.85,
    "matched_skills": [
      { "skill": "프로젝트 관리", "proficiency": 0.95 }
    ],
    "reason": "프로젝트 관리(0.95)·리스크 관리(0.90) 역량 보유. 가용성 0.85."
  }
]
```

---

## STEP 9-1. 역할별 인원수 지정 재추천

```bash
curl -X POST http://localhost:8000/projects/${PROJECT_ID}/recommend-staff/refresh \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "role_headcounts": [
      { "role": "PM",           "count": 1 },
      { "role": "기획자",        "count": 1 },
      { "role": "개발자",        "count": 3 },
      { "role": "UIUX 디자이너", "count": 1 },
      { "role": "QA",           "count": 1 }
    ],
    "top_k": 5,
    "persist": false
  }'
```

**Response**
```json
{
  "by_role": [
    {
      "role": "PM",
      "required_count": 1,
      "candidates": [
        { "rank": 1, "person_id": "PM001", "person_name": "홍길동", "grade": "수석", "similarity_score": 0.88 },
        { "rank": 2, "person_id": "PM002", "person_name": "김지훈", "grade": "책임", "similarity_score": 0.82 }
      ]
    },
    {
      "role": "기획자",
      "required_count": 1,
      "candidates": [
        { "rank": 1, "person_id": "PL001", "person_name": "이수연", "grade": "선임", "similarity_score": 0.85 },
        { "rank": 2, "person_id": "PL002", "person_name": "박서준", "grade": "주임", "similarity_score": 0.78 }
      ]
    },
    {
      "role": "개발자",
      "required_count": 3,
      "candidates": [
        { "rank": 1, "person_id": "BE001", "person_name": "김철수",  "grade": "수석", "similarity_score": 0.91 },
        { "rank": 2, "person_id": "FE001", "person_name": "최예린",  "grade": "선임", "similarity_score": 0.88 },
        { "rank": 3, "person_id": "BE002", "person_name": "최민준",  "grade": "선임", "similarity_score": 0.85 },
        { "rank": 4, "person_id": "BE003", "person_name": "정다은",  "grade": "선임", "similarity_score": 0.82 },
        { "rank": 5, "person_id": "FE002", "person_name": "한승우",  "grade": "주임", "similarity_score": 0.75 }
      ]
    },
    {
      "role": "UIUX 디자이너",
      "required_count": 1,
      "candidates": [
        { "rank": 1, "person_id": "DS001", "person_name": "강나현", "grade": "선임", "similarity_score": 0.87 }
      ]
    },
    {
      "role": "QA",
      "required_count": 1,
      "candidates": [
        { "rank": 1, "person_id": "QA001", "person_name": "윤서연", "grade": "선임", "similarity_score": 0.84 }
      ]
    }
  ],
  "total_required": 7
}
```

---

## STEP 10. 인력 확정 등록 + WBS 자동 배정

```bash
curl -X POST http://localhost:8000/projects/${PROJECT_ID}/staff \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [
      { "person_id": "PM001",  "role": "PM" },
      { "person_id": "PL001",  "role": "기획자" },
      { "person_id": "BE001",  "role": "개발자" },
      { "person_id": "FE001",  "role": "개발자" },
      { "person_id": "BE002",  "role": "개발자" },
      { "person_id": "DS001",  "role": "UIUX 디자이너" },
      { "person_id": "QA001",  "role": "QA" }
    ]
  }'
```

**Response**
```json
{
  "project_id": "PRJ_A1B2C3D4E5",
  "assigned_count": 7,
  "wbs_tasks_assigned": 42
}
```

> - `assigned_count`: 배정된 인원 수  
> - `wbs_tasks_assigned`: WBS 태스크 중 `assigneeRole`이 일치해 담당자가 채워진 수  
> - 배정된 WBS 태스크 초기 상태: `"미진행"`

---

## STEP 11. 프로젝트 상세 조회

```bash
curl http://localhost:8000/projects \
  -H "Authorization: Bearer {TOKEN}"

curl http://localhost:8000/projects/${PROJECT_ID}/wbs \
  -H "Authorization: Bearer {TOKEN}"
```

**WBS 목록 Response (담당자 배정 확인)**
```json
[
  {
    "task_id": "PRJ_A1B2C3D4E5-T001",
    "wbs_code": "REQ-001.PM.1",
    "task_name": "로그인 요구사항 확정",
    "status": "미진행",
    "progress": 0,
    "assignee": "홍길동",
    "planned_hours": 24
  }
]
```

---

## STEP 12. WBS 태스크 상세 조회

```bash
# task_id는 STEP 11에서 확인
curl http://localhost:8000/tasks/{task_id} \
  -H "Authorization: Bearer {TOKEN}"
```

**Response**
```json
{
  "task_id": "PRJ_A1B2C3D4E5-T001",
  "task_name": "로그인 요구사항 확정",
  "wbs_code": "REQ-001.PM.1",
  "status": "미진행",
  "progress": 0,
  "planned_hours": 24,
  "actual_hours": null,
  "due_date": null,
  "assignee": { "person_id": "PM001", "person_name": "홍길동" },
  "source_files": []
}
```

---

## STEP 13. WBS 태스크 상태 수정

### 미진행 → 진행

```bash
curl -X PATCH http://localhost:8000/tasks/{task_id}/status \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "new_status": "진행",
    "note": "요구사항 인터뷰 착수"
  }'
```

### 진행 → 완료

```bash
curl -X PATCH http://localhost:8000/tasks/{task_id}/status \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "new_status": "완료",
    "note": "요구사항 확정서 작성 완료"
  }'
```

### 완료 → 진행 (재오픈) — `change_reason`, `extra_work_date` 필수

```bash
curl -X PATCH http://localhost:8000/tasks/{task_id}/status \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "new_status": "진행",
    "note": "추가 요구사항 발생으로 재작업",
    "change_reason": "발주처 요청으로 소셜 로그인 범위 변경",
    "extra_work_date": "2025-03-15"
  }'
```

> `완료` → 다른 상태 변경 시 `change_reason`, `extra_work_date` 누락이면 **422 Unprocessable Entity** 반환

---

## STEP 14. RFP 분석 결과 다시 조회 (재진입 시)

```bash
curl http://localhost:8000/rfp/${RFP_ID} \
  -H "Authorization: Bearer {TOKEN}"
```

---

## 전체 흐름 요약

```
[STEP 1]  POST /auth/login                              → TOKEN 발급
[STEP 2]  POST /rfp/upload                              → RFP_ID 획득
[STEP 3]  POST /rfp/{RFP_ID}/analyze                   → AI 분석 (10~30초)
[STEP 4]  PATCH /rfp/{RFP_ID}/analysis  (project)      → 개요 + 주관사 저장
[STEP 5]  PATCH /rfp/{RFP_ID}/analysis  (requirements) → 요구사항 수정
[STEP 6]  POST /rfp/{RFP_ID}/regenerate-wbs            → WBS 재생성 (선택)
[STEP 7]  PATCH /rfp/{RFP_ID}/analysis  (wbs)          → WBS 수정 (선택)
[STEP 8]  POST /rfp/{RFP_ID}/confirm                   → PROJECT_ID 획득
[STEP 9]  POST /projects/{PROJECT_ID}/recommend-staff  → 인력 추천
[STEP 9-1] POST /projects/{PROJECT_ID}/recommend-staff/refresh → 역할별 재추천
[STEP 10] POST /projects/{PROJECT_ID}/staff            → 인력 확정 + WBS 자동 배정
[STEP 11] GET  /projects/{PROJECT_ID}/wbs              → WBS 목록 + 담당자 확인
[STEP 12] GET  /tasks/{task_id}                        → 태스크 상세
[STEP 13] PATCH /tasks/{task_id}/status                → 상태 변경
[STEP 14] GET  /rfp/{RFP_ID}                           → 분석 전체 재조회
```

---

## 빠른 테스트 (curl 스크립트)

```bash
#!/bin/bash
BASE="http://localhost:8000"
TOKEN="여기에_발급받은_토큰_입력"

# 환경변수 설정
export RFP_ID=""
export PROJECT_ID=""

# 1. 업로드
RFP_ID=$(curl -s -X POST $BASE/rfp/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/sample_rfp.txt" | python3 -c "import sys,json; print(json.load(sys.stdin)['rfp_id'])")
echo "RFP_ID: $RFP_ID"

# 2. 분석
curl -s -X POST $BASE/rfp/$RFP_ID/analyze \
  -H "Authorization: Bearer $TOKEN" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('프로젝트명:', d['project']['project_name'])
print('요구사항:', len(d['requirements']), '건')
print('WBS:', len(d['wbs']), '항목')
print('신뢰도:', d['confidence_score'])
"

# 3. 확정
PROJECT_ID=$(curl -s -X POST $BASE/rfp/$RFP_ID/confirm \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['project_id'])")
echo "PROJECT_ID: $PROJECT_ID"

# 4. 인력 배정
curl -s -X POST $BASE/projects/$PROJECT_ID/staff \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "assignments": [
      {"person_id":"PM001","role":"PM"},
      {"person_id":"PL001","role":"기획자"},
      {"person_id":"BE001","role":"개발자"},
      {"person_id":"FE001","role":"개발자"},
      {"person_id":"DS001","role":"UIUX 디자이너"},
      {"person_id":"QA001","role":"QA"}
    ]
  }' | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('배정 인원:', d['assigned_count'], '명')
print('WBS 자동 배정:', d['wbs_tasks_assigned'], '건')
"
```

---

## 오류 코드 참고

| HTTP | 원인 | 대응 |
|------|------|------|
| 401 | 토큰 없음 / 만료 | 재로그인 후 토큰 갱신 |
| 403 | 권한 없음 (본인 태스크 아님) | 해당 담당자 계정으로 로그인 |
| 404 | rfp_id / project_id / task_id 없음 | ID 확인 |
| 409 | 상태 전이 불가 (confirmed 후 재분석 등) | 현재 status 확인 |
| 422 | 완료→변경 시 change_reason 누락 | change_reason, extra_work_date 추가 |
