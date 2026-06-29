from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from contract_agent.parser.exception import DocumentLoadError, DocumentParseError


MAX_DOCX_GRID_SPAN = 100


@dataclass(frozen=True)
class BuiltinMarkdownContent:
    markdown_content: str
    html_content: str
    file_type: str
    source_path: str


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def load_text(text: str, source_name: str = "inline.txt") -> BuiltinMarkdownContent:
    markdown = "\n".join(
        normalized for line in text.splitlines() if (normalized := normalize_text(line))
    )
    _ensure_parseable(markdown)
    return BuiltinMarkdownContent(
        markdown_content=markdown,
        html_content="",
        file_type="txt",
        source_path=source_name,
    )


def load_bytes(
    file_name: str,
    content: bytes,
    source_path: str | None = None,
) -> BuiltinMarkdownContent:
    suffix = Path(file_name).suffix.lower()
    if not content:
        raise DocumentLoadError("文件内容为空，无法解析。")

    if suffix == ".txt":
        markdown = _parse_txt_bytes(content)
        html_content = ""
    elif suffix == ".docx":
        markdown = _parse_docx_bytes(content)
        try:
            html_content = _docx_to_html(content)
        except Exception:
            html_content = ""
    elif suffix == ".pdf":
        markdown = _parse_pdf_bytes(content)
        html_content = ""
    else:
        raise DocumentLoadError(f"不支持的文件类型：{suffix or '未知'}")

    _ensure_parseable(markdown)
    return BuiltinMarkdownContent(
        markdown_content=markdown,
        html_content=html_content,
        file_type=suffix.lstrip("."),
        source_path=source_path or file_name,
    )


def load_path(file_path: str | Path) -> tuple[str, BuiltinMarkdownContent]:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise DocumentLoadError(f"文件不存在：{path}")
    return path.name, load_bytes(path.name, path.read_bytes(), source_path=str(path))


def _parse_txt_bytes(content: bytes) -> str:
    encodings = ("utf-8-sig", "utf-8", "gb18030")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            text = content.decode(encoding)
            return "\n".join(
                normalized for line in text.splitlines() if (normalized := normalize_text(line))
            )
        except UnicodeDecodeError as exc:
            last_error = exc
    raise DocumentLoadError("无法使用 utf-8、utf-8-sig 或 gb18030 解码文本文件。") from last_error


def _parse_docx_bytes(content: bytes) -> str:
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

    parts: list[str] = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, doc)
            text = normalize_text(paragraph.text)
            if text:
                parts.append(text)
        elif child.tag.endswith("}tbl"):
            table = Table(child, doc)
            rows = _table_rows(table)
            if rows:
                parts.append(_table_markdown(rows))

    return "\n\n".join(parts)


def _table_rows(table: object) -> list[list[str]]:
    from docx.table import _Cell

    rows: list[list[str]] = []
    for row in table.rows:
        values: list[str] = []
        row_has_merge_placeholder = False
        for cell_xml in row._tr.tc_lst:
            grid_span = _grid_span(cell_xml)
            if grid_span > MAX_DOCX_GRID_SPAN:
                raise DocumentParseError("DOCX 表格列数超过限制，无法解析。")
            if _is_vertical_merge_continuation(cell_xml):
                values.extend([""] * grid_span)
                row_has_merge_placeholder = True
                continue
            cell = _Cell(cell_xml, table)
            values.append(_normalize_cell_text(cell.text))
            values.extend([""] * (grid_span - 1))
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


def _parse_pdf_bytes(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - depends on optional runtime installation
        raise DocumentLoadError(f"读取 pdf 依赖不可用：{exc}") from exc

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise DocumentLoadError(f"读取 pdf 文件失败：{exc}") from exc

    page_parts: list[str] = []
    for page in reader.pages:
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        lines = [normalize_text(line) for line in text.splitlines() if normalize_text(line)]
        if lines:
            page_parts.append("\n".join(lines))

    return "\n\n".join(page_parts)


def _docx_to_html(content: bytes) -> str:
    try:
        from mammoth import convert_to_html as mammoth_to_html
    except Exception:
        return ""

    try:
        result = mammoth_to_html(BytesIO(content))
    except Exception:
        return ""
    return _sanitize_html(result.value.strip()) if result.value else ""


def _sanitize_html(html: str) -> str:
    sanitizer = _HtmlAllowlistSanitizer()
    sanitizer.feed(html)
    sanitizer.close()
    return sanitizer.output.strip()


_ALLOWED_HTML_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
}
_VOID_HTML_TAGS = {"br", "hr", "img"}
_DROP_HTML_CONTENT_TAGS = {"embed", "iframe", "math", "object", "script", "style", "svg"}
_GLOBAL_HTML_ATTRS = {"title"}
_ALLOWED_HTML_ATTRS = {
    "a": {"href", "title"},
    "img": {"alt", "src", "title"},
    "ol": {"start"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
_URL_HTML_ATTRS = {"href", "src"}
_ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


class _HtmlAllowlistSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._drop_depth = 0
        self._open_tags: list[str] = []

    @property
    def output(self) -> str:
        return "".join(self.parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if self._drop_depth:
            if tag_name in _DROP_HTML_CONTENT_TAGS:
                self._drop_depth += 1
            return
        if tag_name in _DROP_HTML_CONTENT_TAGS:
            self._drop_depth = 1
            return
        if tag_name not in _ALLOWED_HTML_TAGS:
            return
        rendered_attrs = self._render_attrs(tag_name, attrs)
        self.parts.append(f"<{tag_name}{rendered_attrs}>")
        if tag_name not in _VOID_HTML_TAGS:
            self._open_tags.append(tag_name)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_name = tag.lower()
        if tag_name in _DROP_HTML_CONTENT_TAGS or self._drop_depth:
            return
        if tag_name not in _ALLOWED_HTML_TAGS:
            return
        rendered_attrs = self._render_attrs(tag_name, attrs)
        if tag_name in _VOID_HTML_TAGS:
            self.parts.append(f"<{tag_name}{rendered_attrs}>")
            return
        self.parts.append(f"<{tag_name}{rendered_attrs}></{tag_name}>")

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.lower()
        if self._drop_depth:
            if tag_name in _DROP_HTML_CONTENT_TAGS:
                self._drop_depth -= 1
            return
        if tag_name in _ALLOWED_HTML_TAGS and self._open_tags and self._open_tags[-1] == tag_name:
            self.parts.append(f"</{tag_name}>")
            self._open_tags.pop()

    def handle_data(self, data: str) -> None:
        if not self._drop_depth:
            self.parts.append(escape(data, quote=False))

    def _render_attrs(self, tag_name: str, attrs: list[tuple[str, str | None]]) -> str:
        allowed = _GLOBAL_HTML_ATTRS | _ALLOWED_HTML_ATTRS.get(tag_name, set())
        rendered: list[str] = []
        for raw_name, raw_value in attrs:
            attr_name = raw_name.lower()
            if attr_name not in allowed or raw_value is None:
                continue
            if attr_name in _URL_HTML_ATTRS and not _is_safe_html_url(raw_value):
                continue
            rendered.append(f'{attr_name}="{escape(raw_value.strip(), quote=True)}"')
        return f" {' '.join(rendered)}" if rendered else ""


def _is_safe_html_url(value: str) -> bool:
    compact = re.sub(r"[\x00-\x20]+", "", value).strip()
    if compact.startswith("//"):
        return False
    scheme = urlsplit(compact).scheme.lower()
    return not scheme or scheme in _ALLOWED_URL_SCHEMES


def _ensure_parseable(markdown: str) -> None:
    if not markdown.strip():
        raise DocumentParseError("文件正文为空，无法形成有效解析结果。")
