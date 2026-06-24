from __future__ import annotations

import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from contract_agent.parser.exceptions import DocumentLoadError, DocumentParseError
from contract_agent.parser.models import DocumentSpan


@dataclass(frozen=True)
class LoadedTableContent:
    table_id: str
    page_no: int | None
    span_ids: list[str]
    rows: list[list[str]]
    markdown: str
    caption: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedDocumentContent:
    raw_text: str
    spans: list[DocumentSpan]
    html_content: str
    file_type: str
    source_path: str
    block_types: dict[str, str] = field(default_factory=dict)
    block_markdown: dict[str, str] = field(default_factory=dict)
    block_metadata: dict[str, dict[str, object]] = field(default_factory=dict)
    tables: list[LoadedTableContent] = field(default_factory=list)


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
        loaded = _parse_docx_bytes(content, source_path=source_path or file_name)
        _ensure_parseable(loaded.raw_text, loaded.spans)
        return loaded
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


def _parse_docx_bytes(content: bytes, *, source_path: str) -> LoadedDocumentContent:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except Exception as exc:  # pragma: no cover - depends on optional runtime installation
        raise DocumentLoadError(f"读取 docx 依赖不可用：{exc}") from exc

    try:
        doc = Document(BytesIO(content))
    except Exception as exc:
        raise DocumentLoadError(f"读取 docx 文件失败：{exc}") from exc

    spans: list[DocumentSpan] = []
    raw_parts: list[str] = []
    block_types: dict[str, str] = {}
    block_markdown: dict[str, str] = {}
    block_metadata: dict[str, dict[str, object]] = {}
    tables: list[LoadedTableContent] = []
    cursor = 0
    block_index = 0
    page_no = 1

    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, doc)
            text = normalize_text(paragraph.text)
            if not text:
                continue
            span, cursor = _append_span(
                spans,
                raw_parts,
                text=text,
                page_no=page_no,
                block_index=block_index,
                cursor=cursor,
            )
            block_types[span.span_id] = "paragraph"
            block_index += 1
        elif child.tag.endswith("}tbl"):
            table = Table(child, doc)
            rows = _table_rows(table)
            if not rows:
                continue
            text = _table_text(rows)
            markdown = _table_markdown(rows)
            span, cursor = _append_span(
                spans,
                raw_parts,
                text=text,
                page_no=page_no,
                block_index=block_index,
                cursor=cursor,
            )
            table_id = f"table-{len(tables) + 1}"
            block_types[span.span_id] = "table"
            block_markdown[span.span_id] = markdown
            block_metadata[span.span_id] = {"table_id": table_id, "row_count": len(rows)}
            tables.append(
                LoadedTableContent(
                    table_id=table_id,
                    page_no=page_no,
                    span_ids=[span.span_id],
                    rows=rows,
                    markdown=markdown,
                )
            )
            block_index += 1

    return LoadedDocumentContent(
        raw_text="\n".join(raw_parts),
        spans=spans,
        html_content=_docx_to_html(content),
        file_type="docx",
        source_path=source_path,
        block_types=block_types,
        block_markdown=block_markdown,
        block_metadata=block_metadata,
        tables=tables,
    )


def _append_span(
    spans: list[DocumentSpan],
    raw_parts: list[str],
    *,
    text: str,
    page_no: int | None,
    block_index: int,
    cursor: int,
) -> tuple[DocumentSpan, int]:
    start_offset = cursor
    end_offset = start_offset + len(text)
    span = DocumentSpan(
        span_id=f"p{page_no or 0}-b{block_index}",
        page_no=page_no,
        block_index=block_index,
        start_offset=start_offset,
        end_offset=end_offset,
        text=text,
    )
    spans.append(span)
    raw_parts.append(text)
    return span, end_offset + 1


def _table_rows(table: object) -> list[list[str]]:
    from docx.table import _Cell

    rows: list[list[str]] = []
    for row in table.rows:
        values: list[str] = []
        row_has_merge_placeholder = False
        for cell_xml in row._tr.tc_lst:
            if _is_vertical_merge_continuation(cell_xml):
                values.extend([""] * _grid_span(cell_xml))
                row_has_merge_placeholder = True
                continue
            cell = _Cell(cell_xml, table)
            values.append(_normalize_cell_text(cell.text))
            values.extend([""] * (_grid_span(cell_xml) - 1))
        if any(values) or row_has_merge_placeholder:
            rows.append(values)
    return rows


def _grid_span(cell_xml: object) -> int:
    cell_properties = getattr(cell_xml, "tcPr", None)
    grid_span = getattr(cell_properties, "gridSpan", None)
    value = getattr(grid_span, "val", None)
    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return 1


def _is_vertical_merge_continuation(cell_xml: object) -> bool:
    cell_properties = getattr(cell_xml, "tcPr", None)
    vertical_merge = getattr(cell_properties, "vMerge", None)
    if vertical_merge is None:
        return False
    return getattr(vertical_merge, "val", None) != "restart"


def _normalize_cell_text(text: str) -> str:
    return " | ".join(normalize_text(part) for part in text.splitlines() if normalize_text(part))


def _table_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(cell for cell in row if cell) for row in rows)


def _table_markdown(rows: list[list[str]]) -> str:
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    separator = ["---"] * width
    lines = [_markdown_row(normalized[0]), _markdown_row(separator)]
    lines.extend(_markdown_row(row) for row in normalized[1:])
    return "\n".join(lines)


def _markdown_row(row: list[str]) -> str:
    return "| " + " | ".join(_escape_markdown_cell(cell) for cell in row) + " |"


def _escape_markdown_cell(text: str) -> str:
    return text.replace("|", "\\|")


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
