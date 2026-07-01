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
from contract_agent.parser.parsed.markdown_cleaner import clean_markdown
from contract_agent.parser.parsed.markdown_chunker import ContractChunker
from contract_agent.parser.parsed.markdown_logical_block_collector import collect_logical_blocks
from contract_agent.parser.parsed.markdown_metadata_builder import build_metadata
from contract_agent.parser.parsed.markdown_page_resolver import (
    MarkdownPageEvidence,
    page_numbers_for_cleaned_lines,
    resolve_page_evidence,
    table_page_no,
)
from contract_agent.parser.parsed.markdown_table_row_parser import split_pipe_row
from contract_agent.parser.parsed.markdown_table_parser import parse_table_rows, table_text
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
        original_lines = markdown_document.markdown_content.splitlines()
        page_evidence = resolve_page_evidence(
            original_lines,
            conversion_metadata=markdown_document.conversion_metadata,
        )
        cleaned_markdown = clean_markdown(
            markdown_document.markdown_content,
            conversion_metadata=markdown_document.conversion_metadata,
        )
        cleaned_line_page_numbers = page_numbers_for_cleaned_lines(
            original_lines,
            cleaned_markdown.markdown_content.splitlines(),
            page_evidence,
        )
        conversion_metadata = {
            **markdown_document.conversion_metadata,
            "markdown_cleaner_removed_lines": cleaned_markdown.removed_lines,
            "markdown_cleaner_merged_tables": cleaned_markdown.merged_tables,
            "markdown_cleaner_table_source_indexes": cleaned_markdown.table_source_indexes,
            "markdown_page_evidence": page_evidence.to_metadata(),
        }
        markdown_document = markdown_document.model_copy(
            update={
                "markdown_content": cleaned_markdown.markdown_content,
                "conversion_metadata": conversion_metadata,
            }
        )
        raw_text, spans, blocks, tables = _parse_markdown_blocks(
            markdown_document,
            line_page_numbers=cleaned_line_page_numbers,
            page_evidence=page_evidence,
        )
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
    *,
    line_page_numbers: list[int | None] | None = None,
    page_evidence: MarkdownPageEvidence | None = None,
) -> tuple[str, list[DocumentSpan], list[DocumentBlock], list[DocumentTable]]:
    lines = markdown_document.markdown_content.splitlines()
    spans: list[DocumentSpan] = []
    blocks: list[DocumentBlock] = []
    tables: list[DocumentTable] = []
    raw_parts: list[str] = []
    cursor = 0
    block_index = 0
    bounded_lines, bounded_line_page_numbers = _lines_with_page_boundaries(
        lines,
        line_page_numbers,
    )
    logical_blocks = collect_logical_blocks(bounded_lines)

    for logical_block in logical_blocks:
        if logical_block.block_type == "table":
            page_no = _line_page_no(bounded_line_page_numbers, logical_block.line_start)
            if page_no is None:
                source_index = _table_source_index(
                    markdown_document.conversion_metadata, len(tables)
                )
                if source_index is not None:
                    page_no = table_page_no(page_evidence, source_index)
            block_markdown = logical_block.markdown
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
            continue

        page_no = _line_page_no(bounded_line_page_numbers, logical_block.line_start)
        block_type = logical_block.block_type
        text = logical_block.text
        level = logical_block.level
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
        blocks.append(
            DocumentBlock(
                block_id=span.span_id,
                block_type=block_type,
                text=text,
                markdown=logical_block.markdown.strip(),
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

    return "\n".join(raw_parts), spans, blocks, tables


def _line_page_no(line_page_numbers: list[int | None] | None, index: int) -> int | None:
    if line_page_numbers is None or index >= len(line_page_numbers):
        return None
    return line_page_numbers[index]


def _table_source_index(conversion_metadata: dict[str, object], table_index: int) -> int | None:
    source_indexes = conversion_metadata.get("markdown_cleaner_table_source_indexes")
    if not isinstance(source_indexes, list):
        return table_index
    if table_index >= len(source_indexes):
        return table_index
    source_index = source_indexes[table_index]
    if isinstance(source_index, bool) or source_index is None:
        return None
    if isinstance(source_index, int) and source_index >= 0:
        return source_index
    return None


def _lines_with_page_boundaries(
    lines: list[str],
    line_page_numbers: list[int | None] | None,
) -> tuple[list[str], list[int | None] | None]:
    if not line_page_numbers:
        return lines, line_page_numbers
    bounded_lines: list[str] = []
    bounded_line_page_numbers: list[int | None] = []
    previous_page: int | None = None
    for index, line in enumerate(lines):
        page_no = _line_page_no(line_page_numbers, index)
        if (
            bounded_lines
            and page_no != previous_page
            and page_no is not None
            and previous_page is not None
            and bounded_lines[-1].strip()
            and not _looks_like_table_row_boundary(bounded_lines[-1], line)
        ):
            bounded_lines.append("")
            bounded_line_page_numbers.append(None)
        bounded_lines.append(line)
        bounded_line_page_numbers.append(page_no)
        previous_page = page_no
    return bounded_lines, bounded_line_page_numbers


def _looks_like_table_row_boundary(previous_line: str, line: str) -> bool:
    previous_cells = _pipe_row_cells(previous_line)
    current_cells = _pipe_row_cells(line)
    return bool(previous_cells and current_cells and len(previous_cells) == len(current_cells))


def _pipe_row_cells(line: str) -> list[str]:
    stripped = line.strip()
    if "|" not in stripped:
        return []
    cells = split_pipe_row(stripped)
    return cells if len(cells) >= 2 else []


def _append_span(
    spans: list[DocumentSpan],
    raw_parts: list[str],
    *,
    text: str,
    page_no: int | None,
    block_index: int,
    cursor: int,
) -> tuple[DocumentSpan, int]:
    normalized = text.strip()
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
