from __future__ import annotations

from pathlib import Path

from contract_agent.config.config_parser import ParserConfig
from contract_agent.logger.base import ComponentLogger
from contract_agent.parser.logger import get_parser_logger, parser_log_event
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.models import (
    BlockLocation,
    DocumentBlock,
    DocumentSpan,
    DocumentTable,
    ParsedDocument,
)
from contract_agent.parser.parsed.markdown_block_parser import block_type_and_text, normalize_text
from contract_agent.parser.parsed.markdown_cleaner import clean_markdown
from contract_agent.parser.parsed.markdown_chunker import ContractChunker
from contract_agent.parser.parsed.markdown_metadata_builder import build_metadata
from contract_agent.parser.parsed.markdown_table_parser import (
    collect_table_lines,
    is_table_start,
    parse_table_rows,
    table_text,
)
from contract_agent.parser.parsed.semantic_graph_builder import build_semantic_graph


class MarkdownParsedService:
    def __init__(
        self,
        parser_config: ParserConfig | None = None,
        chunker: ContractChunker | None = None,
        logger: ComponentLogger | None = None,
    ) -> None:
        self.parser_config = parser_config or ParserConfig()
        self.chunker = chunker or ContractChunker(self.parser_config)
        self.logger = logger or get_parser_logger()

    def parse(self, markdown_document: MarkdownDocument) -> ParsedDocument:
        cleaned_markdown = clean_markdown(
            markdown_document.markdown_content,
            conversion_metadata=markdown_document.conversion_metadata,
        )
        conversion_metadata = {
            **markdown_document.conversion_metadata,
            "markdown_cleaner_removed_lines": cleaned_markdown.removed_lines,
            "markdown_cleaner_merged_tables": cleaned_markdown.merged_tables,
        }
        markdown_document = markdown_document.model_copy(
            update={
                "markdown_content": cleaned_markdown.markdown_content,
                "conversion_metadata": conversion_metadata,
            }
        )
        raw_text, spans, blocks, tables = _parse_markdown_blocks(markdown_document)
        metadata = build_metadata(
            file_name=markdown_document.file_name,
            source_path=markdown_document.source_path,
            file_type=markdown_document.file_type or _file_type(markdown_document.file_name),
            raw_text=raw_text,
            spans=spans,
        )
        document = ParsedDocument(
            metadata=metadata,
            raw_text=raw_text,
            spans=spans,
            blocks=blocks,
            tables=tables,
            html_content=markdown_document.html_content,
            markdown_content=markdown_document.markdown_content,
            conversion_metadata=conversion_metadata,
        )
        document.clause_chunks = self.chunker.chunk(document)
        self.logger.handle(
            parser_log_event(
                "Chunk",
                "Markdown chunk 完成 blocks=%s chunks=%s",
                len(document.blocks),
                len(document.clause_chunks),
            )
        )
        document.semantic_graph = build_semantic_graph(document)
        return document


def document_from_markdown(
    markdown: str,
    *,
    file_name: str,
    source_path: str,
    backend_name: str,
    html_content: str = "",
) -> ParsedDocument:
    return MarkdownParsedService().parse(
        MarkdownDocument(
            markdown_content=markdown,
            file_name=file_name,
            file_type=_file_type(file_name),
            source_path=source_path,
            backend_name=backend_name,
            html_content=html_content,
            conversion_metadata={"parser_backend": backend_name},
        )
    )


def _parse_markdown_blocks(
    markdown_document: MarkdownDocument,
) -> tuple[str, list[DocumentSpan], list[DocumentBlock], list[DocumentTable]]:
    lines = markdown_document.markdown_content.splitlines()
    spans: list[DocumentSpan] = []
    blocks: list[DocumentBlock] = []
    tables: list[DocumentTable] = []
    raw_parts: list[str] = []
    cursor = 0
    block_index = 0
    index = 0
    page_no = 1

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        if is_table_start(lines, index):
            table_lines, next_index = collect_table_lines(lines, index)
            block_markdown = "\n".join(table_lines)
            rows = parse_table_rows(block_markdown)
            text = table_text(rows)
            span, cursor = _append_span(
                spans,
                raw_parts,
                text=text,
                page_no=page_no,
                block_index=block_index,
                cursor=cursor,
            )
            table_id = f"table-{len(tables) + 1}"
            block = DocumentBlock(
                block_id=span.span_id,
                block_type="table",
                text=text,
                markdown=block_markdown,
                location=BlockLocation(
                    page_no=span.page_no,
                    block_index=span.block_index,
                    start_offset=span.start_offset,
                    end_offset=span.end_offset,
                    span_ids=[span.span_id],
                    source_path=markdown_document.source_path,
                ),
                metadata={"table_id": table_id, "row_count": len(rows)},
            )
            blocks.append(block)
            tables.append(
                DocumentTable(
                    table_id=table_id,
                    page_no=page_no,
                    span_ids=[span.span_id],
                    rows=rows,
                    metadata={"markdown": block_markdown},
                )
            )
            block_index += 1
            index = next_index
            continue

        block_type, text, level = block_type_and_text(line)
        if not text:
            index += 1
            continue
        span, cursor = _append_span(
            spans,
            raw_parts,
            text=text,
            page_no=page_no,
            block_index=block_index,
            cursor=cursor,
        )
        blocks.append(
            DocumentBlock(
                block_id=span.span_id,
                block_type=block_type,
                text=text,
                markdown=line.strip(),
                level=level,
                location=BlockLocation(
                    page_no=span.page_no,
                    block_index=span.block_index,
                    start_offset=span.start_offset,
                    end_offset=span.end_offset,
                    span_ids=[span.span_id],
                    source_path=markdown_document.source_path,
                ),
            )
        )
        block_index += 1
        index += 1

    return "\n".join(raw_parts), spans, blocks, tables


def _append_span(
    spans: list[DocumentSpan],
    raw_parts: list[str],
    *,
    text: str,
    page_no: int | None,
    block_index: int,
    cursor: int,
) -> tuple[DocumentSpan, int]:
    normalized = normalize_text(text)
    start_offset = cursor
    end_offset = start_offset + len(normalized)
    span = DocumentSpan(
        span_id=f"p{page_no or 0}-b{block_index}",
        page_no=page_no,
        block_index=block_index,
        start_offset=start_offset,
        end_offset=end_offset,
        text=normalized,
    )
    spans.append(span)
    raw_parts.append(normalized)
    return span, end_offset + 1


def _file_type(file_name: str) -> str:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    return suffix or "md"
