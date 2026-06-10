## 화면 1 — 프로젝트 개요

### 개요

사용자가 RFP 파일(PDF / DOCX / HWP)을 업로드하면 텍스트를 추출하고, AI가 프로젝트 개요를 자동 분석합니다. 분석 결과를 확인·수정한 뒤 다음 단계로 넘어갑니다.

### 3단계: 분석 결과 수정 후 저장

**사용자가 프로젝트 정보 및 주관사·협력사 정보를 입력하고 "저장 및 다음" 클릭 시 호출**

```
PATCH /rfp/{rfp_id}/analysis
Content-Type: application/json
```

**Request Body** — 변경한 필드만 포함, 나머지는 생략

```json
{
  "project": {
    "project_name": "수정된 프로젝트명",
    "client_name": "수정된 발주사",
    "budget": "1,500,000,000",
    "start_date": "2025-02-01",
    "end_date": "2025-09-30",
    "contract_type": "수의계약",
    "business_type": "민간/SaaS"
  },
  "consortium": {
    "lead_company": "(주)케이고솔루션",
    "partner_companies": ["협력사A", "협력사B"]
  }
}
```

**consortium 필드 설명**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `consortium.lead_company` | string | - | 주관사명 |
| `consortium.partner_companies` | string[] | - | 협력사명 목록 (화면상 협력사 1, 협력사 2, ...) |

> - `consortium`은 AI 분석 결과에 포함되지 않습니다. 사용자가 직접 입력한 값만 저장됩니다.
> - 협력사가 없으면 `partner_companies`를 빈 배열 `[]`로 전송하거나 `consortium` 자체를 생략할 수 있습니다.
> - 수정 없이 다음 단계로 이동하는 경우 이 API 호출을 건너뛸 수 있습니다.

**Response**

```json
{
  "rfp_id": "RFP_A1B2C3D4E5",
  "status": "reviewed"
}
```
