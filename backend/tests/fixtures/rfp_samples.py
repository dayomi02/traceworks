"""RFP 테스트용 파일 바이트를 즉시 생성."""
import io

import docx
import fitz  # PyMuPDF


SAMPLE_RFP_TEXT = """\
제안요청서

1. 사업명
   스마트팩토리 MES 시스템 구축

2. 사업 개요
   생산 공정을 실시간 모니터링하고 품질 정보를 추적하는 MES 시스템을
   신규 구축한다. 도메인은 제조/MES이며 기술 스택은 Java, Spring Boot,
   Oracle DB, React를 사용한다.

3. 예산 및 일정
   - 예산: 15억원
   - 기간: 12개월 (2025-06-01 ~ 2026-05-31)
   - 난이도: HIGH

4. 주요 요구사항
   4.1 생산계획 수립 기능
   4.2 실시간 설비 모니터링
   4.3 품질 검사 결과 추적
   4.4 재고 관리 및 자재 소요량 계산
"""


def make_pdf_bytes(text: str = SAMPLE_RFP_TEXT) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    # PyMuPDF는 한글 폰트 핸들링이 기본 설정에서 제한적이므로
    # insert_text로 삽입하되, 추출 테스트엔 영숫자만으로도 충분.
    page.insert_text((50, 50), text.encode("utf-8").decode("utf-8", errors="ignore"))
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def make_docx_bytes(text: str = SAMPLE_RFP_TEXT) -> bytes:
    doc = docx.Document()
    for line in text.splitlines():
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# LLM이 반환할 mock 분석 JSON
SAMPLE_ANALYSIS = {
    "project": {
        "project_name": "스마트팩토리 MES 시스템 구축",
        "project_domain": "제조 / MES",
        "tech_stack": ["Java", "Spring Boot", "Oracle DB", "React"],
        "difficulty_level": "HIGH",
        "estimated_duration": "12개월",
        "budget": "15억",
        "start_date": "2025-06-01",
        "end_date": "2026-05-31",
        "description": "생산관리시스템 신규 구축",
    },
    "wbs": [
        {
            "wbs_code": "1.0",
            "task_name": "요구사항 분석",
            "estimated_weeks": 4,
            "planned_hours": 320,
            "required_skills": ["BA", "도메인 분석"],
            "deliverable": "요구사항 정의서",
            "depends_on": [],
        },
        {
            "wbs_code": "1.1",
            "task_name": "현행 시스템 분석",
            "estimated_weeks": 2,
            "planned_hours": 160,
            "required_skills": ["BA"],
            "deliverable": "현행 시스템 분석서",
            "depends_on": [],
        },
        {
            "wbs_code": "2.0",
            "task_name": "시스템 설계",
            "estimated_weeks": 6,
            "planned_hours": 480,
            "required_skills": ["Spring Boot", "Oracle DB", "아키텍처 설계"],
            "deliverable": "설계서",
            "depends_on": ["1.0"],
        },
    ],
    "required_roles": [
        {"role": "PM", "count": 1, "skills": ["리더십", "제조 도메인"]},
        {"role": "백엔드 개발자", "count": 3, "skills": ["Spring Boot", "Oracle"]},
    ],
    "confidence_score": 0.91,
}
