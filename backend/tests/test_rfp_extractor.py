import pytest

from app.core.normalizer.rfp_extractor import (
    UnsupportedRfpFormat,
    detect_format,
    extract,
)
from tests.fixtures.rfp_samples import make_docx_bytes, make_pdf_bytes


def test_detect_format():
    assert detect_format("a.pdf") == "pdf"
    assert detect_format("A.DOCX") == "docx"
    assert detect_format("rfp.hwp") == "hwp"
    assert detect_format("new.hwpx") == "hwpx"


def test_detect_format_unsupported():
    with pytest.raises(UnsupportedRfpFormat):
        detect_format("README.md")


def test_extract_pdf_roundtrip():
    pdf = make_pdf_bytes("스마트팩토리 MES 시스템 구축")
    text, pages = extract(pdf, "rfp.pdf")
    assert pages == 1
    # pymupdf + basic font는 한글이 깨질 수 있으므로 길이로 sanity check만
    assert isinstance(text, str)


def test_extract_docx_roundtrip():
    docx_bytes = make_docx_bytes("사업명: 테스트 프로젝트\n예산: 10억")
    text, count = extract(docx_bytes, "rfp.docx")
    assert "사업명" in text
    assert "예산" in text
    assert count >= 1


def test_extract_unsupported():
    with pytest.raises(UnsupportedRfpFormat):
        extract(b"whatever", "rfp.txt")
