import io
import tempfile
from pathlib import Path, PurePath

import docx
import fitz  # PyMuPDF
from hwp5.hwp5html import HTMLTransform
from hwp5.hwp5txt import TextTransform
from hwp5.xmlmodel import Hwp5File
from lxml import etree


class UnsupportedRfpFormat(ValueError):
    pass


class RfpExtractionError(RuntimeError):
    pass


def detect_format(filename: str) -> str:
    ext = PurePath(filename).suffix.lower().lstrip(".")
    if ext in {"pdf", "docx", "hwp", "hwpx", "txt"}:
        return ext
    raise UnsupportedRfpFormat(f"지원하지 않는 파일 형식: .{ext}")


def extract(content: bytes, filename: str) -> tuple[str, int]:
    """RFP 파일 바이트에서 텍스트와 페이지/섹션 수를 추출.

    Returns (text, page_count).
    """
    fmt = detect_format(filename)
    if fmt == "pdf":
        return _extract_pdf(content)
    if fmt == "docx":
        return _extract_docx(content)
    if fmt in {"hwp", "hwpx"}:
        return _extract_hwp(content, filename)
    if fmt == "txt":
        return _extract_txt(content)
    raise UnsupportedRfpFormat(fmt)  # pragma: no cover


def _extract_txt(content: bytes) -> tuple[str, int]:
    text = content.decode("utf-8", errors="replace").strip()
    lines = [l for l in text.splitlines() if l.strip()]
    return text, max(1, len(lines) // 30)


def _extract_pdf(content: bytes) -> tuple[str, int]:
    try:
        with fitz.open(stream=content, filetype="pdf") as doc:
            pages = [page.get_text() for page in doc]
    except Exception as exc:  # pragma: no cover
        raise RfpExtractionError(f"PDF 추출 실패: {exc}") from exc
    return "\n".join(pages).strip(), len(pages)


def _extract_docx(content: bytes) -> tuple[str, int]:
    try:
        doc = docx.Document(io.BytesIO(content))
    except Exception as exc:  # pragma: no cover
        raise RfpExtractionError(f"DOCX 추출 실패: {exc}") from exc

    lines: list[str] = []
    # doc.element.body를 순서대로 순회해 단락과 표를 원문 순서로 처리
    from docx.oxml.ns import qn
    for child in doc.element.body:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "p":
            text = "".join(r.text or "" for r in child.iter(qn("w:t"))).strip()
            if text:
                lines.append(text)
        elif tag == "tbl":
            for row in child.iter(qn("w:tr")):
                cells = []
                for cell in row.iter(qn("w:tc")):
                    cell_text = " ".join(
                        "".join(r.text or "" for r in cell.iter(qn("w:t"))).split()
                    )
                    cells.append(cell_text)
                if any(cells):
                    lines.append(" | ".join(cells))

    return "\n".join(lines).strip(), max(1, len(lines))


def _extract_hwp(content: bytes, filename: str) -> tuple[str, int]:
    """HWP5 → XHTML(HTMLTransform) → 텍스트 추출. 표 셀 내용 포함.

    pyhwp의 Hwp5File은 파일 경로(str)만 받으므로 임시 파일에 써서 전달.
    HTMLTransform이 실패하면 TextTransform으로 폴백.
    """
    suffix = PurePath(filename).suffix.lower() or ".hwp"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        hwp = Hwp5File(str(tmp_path))
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise RfpExtractionError(f"HWP 열기 실패: {exc}") from exc

    try:
        text = _hwp_to_text_via_html(hwp)
    except Exception:
        # HTMLTransform 실패 시 TextTransform으로 폴백 (표는 <표>로 표시됨)
        try:
            out_buf = io.BytesIO()
            TextTransform().transform_hwp5_to_text(hwp, out_buf)
            text = out_buf.getvalue().decode("utf-8", errors="replace").strip()
        except Exception as exc:
            raise RfpExtractionError(f"HWP 텍스트 변환 실패: {exc}") from exc
    finally:
        close = getattr(hwp, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # pragma: no cover
                pass
        tmp_path.unlink(missing_ok=True)

    return text, 1


def _hwp_to_text_via_html(hwp) -> str:
    """HWP5File → XHTML 변환 후 표 셀을 포함한 텍스트 추출."""
    xhtml_buf = io.BytesIO()
    HTMLTransform().transform_hwp5_to_xhtml(hwp, xhtml_buf)
    xhtml_bytes = xhtml_buf.getvalue()
    return _xhtml_to_text(xhtml_bytes)


def _xhtml_to_text(xhtml_bytes: bytes) -> str:
    """XHTML 바이트에서 표 셀을 포함한 텍스트를 추출한다.

    - 표 행: 셀을 ' | '로 구분해 한 줄로 합침
    - 단락/제목: 그대로 한 줄
    - 표 내부 단락은 표 행 처리에서 이미 포함되므로 중복 처리하지 않음
    """
    try:
        root = etree.fromstring(xhtml_bytes)
    except etree.XMLSyntaxError:
        # HTML parser로 재시도
        root = etree.fromstring(xhtml_bytes, parser=etree.HTMLParser())

    def localname(elem) -> str:
        tag = elem.tag
        return tag.split("}")[-1] if isinstance(tag, str) and "}" in tag else (tag or "")

    lines: list[str] = []

    def _collect(elem, in_table: bool) -> None:
        ln = localname(elem)

        if ln == "table":
            # 각 행 → 셀 텍스트를 ' | '로 합침
            for row in elem.iter():
                if localname(row) == "tr":
                    cells = []
                    for cell in row:
                        if localname(cell) in ("td", "th"):
                            cell_text = " ".join("".join(cell.itertext()).split())
                            cells.append(cell_text)
                    if any(cells):
                        lines.append(" | ".join(cells))
            return  # 표 내부는 위에서 처리 완료

        if ln in ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6"):
            if not in_table:
                text = " ".join("".join(elem.itertext()).split())
                if text:
                    lines.append(text)
            return  # 자식은 재귀하지 않음 (itertext로 이미 처리)

        for child in elem:
            _collect(child, in_table)

    _collect(root, False)
    return "\n".join(lines).strip()
