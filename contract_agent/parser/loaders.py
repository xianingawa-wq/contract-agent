from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from contract_agent.parser.exceptions import DocumentLoadError, DocumentParseError
from contract_agent.parser.models import DocumentSpan


@dataclass(frozen=True)
class LoadedDocumentContent:
    raw_text: str
    spans: list[DocumentSpan]
    html_content: str
    file_type: str
    source_path: str


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_spans_from_blocks(
    blocks: list[str],
    page_no: int | None,
) -> tuple[str, list[DocumentSpan]]:
    spans: list[DocumentSpan] = []
    raw_parts: list[str] = []
    cursor = 0

    for block_index, block in enumerate(blocks):
        normalized = normalize_text(block)
        if not normalized:
            continue

        start_offset = cursor
        end_offset = start_offset + len(normalized)
        span_id = f"p{page_no or 0}-b{block_index}"
        spans.append(
            DocumentSpan(
                span_id=span_id,
                page_no=page_no,
                block_index=block_index,
                start_offset=start_offset,
                end_offset=end_offset,
                text=normalized,
            )
        )
        raw_parts.append(normalized)
        cursor = end_offset + 1

    return "\n".join(raw_parts), spans


def load_text(text: str, source_name: str = "inline.txt") -> LoadedDocumentContent:
    raw_text, spans = build_spans_from_blocks(text.splitlines(), page_no=1)
    _ensure_parseable(raw_text, spans)
    return LoadedDocumentContent(
        raw_text=raw_text,
        spans=spans,
        html_content="",
        file_type="txt",
        source_path=source_name,
    )


def load_bytes(
    file_name: str,
    content: bytes,
    source_path: str | None = None,
) -> LoadedDocumentContent:
    suffix = Path(file_name).suffix.lower()
    if not content:
        raise DocumentLoadError("文件内容为空，无法解析。")

    if suffix == ".txt":
        raw_text, spans = _parse_txt_bytes(content)
        html_content = ""
    elif suffix == ".docx":
        raw_text, spans = _parse_docx_bytes(content)
        html_content = _docx_to_html(content)
    elif suffix == ".pdf":
        raw_text, spans = _parse_pdf_bytes(content)
        html_content = ""
    else:
        raise DocumentLoadError(f"不支持的文件类型：{suffix or '未知'}")

    _ensure_parseable(raw_text, spans)
    return LoadedDocumentContent(
        raw_text=raw_text,
        spans=spans,
        html_content=html_content,
        file_type=suffix.lstrip("."),
        source_path=source_path or file_name,
    )


def load_path(file_path: str | Path) -> tuple[str, LoadedDocumentContent]:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise DocumentLoadError(f"文件不存在：{path}")
    return path.name, load_bytes(path.name, path.read_bytes(), source_path=str(path))


def _parse_txt_bytes(content: bytes) -> tuple[str, list[DocumentSpan]]:
    encodings = ("utf-8-sig", "utf-8", "gb18030")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            text = content.decode(encoding)
            return build_spans_from_blocks(text.splitlines(), page_no=1)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise DocumentLoadError("无法使用 utf-8、utf-8-sig 或 gb18030 解码文本文件。") from last_error


def _parse_docx_bytes(content: bytes) -> tuple[str, list[DocumentSpan]]:
    try:
        from docx import Document
    except Exception as exc:  # pragma: no cover - depends on optional runtime installation
        raise DocumentLoadError(f"读取 docx 依赖不可用：{exc}") from exc

    try:
        doc = Document(BytesIO(content))
    except Exception as exc:
        raise DocumentLoadError(f"读取 docx 文件失败：{exc}") from exc

    blocks = [paragraph.text.strip() for paragraph in doc.paragraphs if paragraph.text.strip()]
    return build_spans_from_blocks(blocks, page_no=1)


def _parse_pdf_bytes(content: bytes) -> tuple[str, list[DocumentSpan]]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on optional runtime installation
        raise DocumentLoadError(f"读取 pdf 依赖不可用：{exc}") from exc

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise DocumentLoadError(f"读取 pdf 文件失败：{exc}") from exc

    all_spans: list[DocumentSpan] = []
    raw_parts: list[str] = []
    global_offset = 0

    for page_no, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue

        blocks = [line.strip() for line in text.splitlines() if line.strip()]
        page_text, page_spans = build_spans_from_blocks(blocks, page_no=page_no)
        for span in page_spans:
            span.start_offset += global_offset
            span.end_offset += global_offset
            all_spans.append(span)
        raw_parts.append(page_text)
        global_offset += len(page_text) + 2

    return "\n\n".join(raw_parts), all_spans


def _docx_to_html(content: bytes) -> str:
    try:
        from mammoth import convert_to_html as mammoth_to_html
    except Exception:
        return ""

    try:
        result = mammoth_to_html(BytesIO(content))
    except Exception as exc:
        raise DocumentLoadError(f"生成 docx HTML 失败：{exc}") from exc
    return result.value.strip() if result.value else ""


def _ensure_parseable(raw_text: str, spans: list[DocumentSpan]) -> None:
    if not raw_text.strip() or not spans:
        raise DocumentParseError("文件正文为空，无法形成有效解析结果。")
