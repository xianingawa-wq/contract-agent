from __future__ import annotations

from pathlib import Path

from contract_agent.parser.converters.builtin import _document_from_loaded
from contract_agent.parser.loaders import LoadedDocumentContent, build_spans_from_blocks
from contract_agent.parser.models import ParsedDocument


def document_from_markdown(
    markdown: str,
    *,
    file_name: str,
    source_path: str,
    converter_name: str,
    html_content: str = "",
) -> ParsedDocument:
    raw_text, spans = build_spans_from_blocks(markdown.splitlines(), page_no=1)
    loaded = LoadedDocumentContent(
        raw_text=raw_text,
        spans=spans,
        html_content=html_content,
        file_type=_file_type(file_name),
        source_path=source_path,
    )
    document = _document_from_loaded(file_name, loaded)
    document.markdown_content = markdown.strip()
    document.conversion_metadata = {"converter": converter_name}
    return document


def _file_type(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    return suffix or "md"
