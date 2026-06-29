from __future__ import annotations

import re
from dataclasses import dataclass

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.models import ClauseChunk, DocumentBlock, DocumentSpan, ParsedDocument


@dataclass(frozen=True)
class _ChunkSource:
    source_id: str
    chunk_level: str
    section_title: str
    page_no: int | None
    start_offset: int
    end_offset: int
    source_text: str


@dataclass(frozen=True)
class _TextPart:
    text: str
    start: int
    end: int


class ContractChunker:
    def __init__(self, parser_config: ParserConfig | None = None) -> None:
        self.parser_config = parser_config or ParserConfig()

    def chunk(self, document: ParsedDocument) -> list[ClauseChunk]:
        chunks = [self._to_chunk(source) for source in self._chunk_sources(document)]
        self._link_neighbors(chunks)
        return self._split_long_chunks(chunks)

    def _chunk_sources(self, document: ParsedDocument) -> list[_ChunkSource]:
        if document.blocks:
            return [
                self._source_from_block(block) for block in document.blocks if _block_text(block)
            ]
        return [self._source_from_span(span) for span in document.spans if span.text.strip()]

    def _source_from_block(self, block: DocumentBlock) -> _ChunkSource:
        text = _block_text(block)
        return _ChunkSource(
            source_id=block.block_id,
            chunk_level=block.block_type or "block",
            section_title=_section_title(block.block_type, text),
            page_no=block.location.page_no,
            start_offset=block.location.start_offset or 0,
            end_offset=block.location.end_offset or len(text),
            source_text=text,
        )

    def _source_from_span(self, span: DocumentSpan) -> _ChunkSource:
        text = span.text.strip()
        return _ChunkSource(
            source_id=span.span_id,
            chunk_level="span",
            section_title=_preview(text),
            page_no=span.page_no,
            start_offset=span.start_offset,
            end_offset=span.end_offset,
            source_text=text,
        )

    def _to_chunk(self, source: _ChunkSource) -> ClauseChunk:
        return ClauseChunk(
            chunk_id=f"chunk-{source.source_id}",
            chunk_level=source.chunk_level,
            section_title=source.section_title,
            page_no=source.page_no,
            start_offset=source.start_offset,
            end_offset=source.end_offset,
            source_text=source.source_text,
        )

    def _link_neighbors(self, chunks: list[ClauseChunk]) -> None:
        for index, chunk in enumerate(chunks):
            chunk.prev_chunk_id = chunks[index - 1].chunk_id if index > 0 else None
            chunk.next_chunk_id = chunks[index + 1].chunk_id if index + 1 < len(chunks) else None

    def _split_long_chunks(self, chunks: list[ClauseChunk]) -> list[ClauseChunk]:
        refined: list[ClauseChunk] = []
        for chunk in chunks:
            if len(chunk.source_text) <= self.parser_config.chunk_max_chars:
                refined.append(chunk)
                continue

            parts = self._split_by_sentences(
                chunk.source_text,
                max_chars=self.parser_config.chunk_target_chars,
            )
            for index, part in enumerate(parts, start=1):
                refined.append(
                    ClauseChunk(
                        chunk_id=f"{chunk.chunk_id}-part{index}",
                        chunk_level="sentence_group",
                        clause_no=chunk.clause_no,
                        parent_clause_no=chunk.parent_clause_no or chunk.clause_no,
                        section_title=chunk.section_title,
                        page_no=chunk.page_no,
                        start_offset=chunk.start_offset + part.start,
                        end_offset=chunk.start_offset + part.end,
                        source_text=part.text,
                    )
                )

        self._link_neighbors(refined)
        return refined

    def _split_by_sentences(self, text: str, max_chars: int) -> list[_TextPart]:
        sentence_matches = re.finditer(r".*?(?:[。；;.!?]|$)", text, flags=re.S)
        parts: list[_TextPart] = []
        current_text = ""
        current_start: int | None = None
        current_end = 0
        for match in sentence_matches:
            sentence = match.group(0)
            if not sentence or not sentence.strip():
                continue

            sentence_start = match.start()
            sentence_end = match.end()
            if len(sentence) > max_chars:
                if current_text and current_start is not None:
                    parts.append(_TextPart(current_text, current_start, current_end))
                    current_text = ""
                    current_start = None
                for part_start in range(sentence_start, sentence_end, max_chars):
                    part_end = min(part_start + max_chars, sentence_end)
                    parts.append(_TextPart(text[part_start:part_end], part_start, part_end))
                continue

            candidate = current_text + sentence
            if current_start is None or len(candidate) <= max_chars:
                if current_start is None:
                    current_start = sentence_start
                current_text = candidate
                current_end = sentence_end
                continue

            parts.append(_TextPart(current_text, current_start, current_end))
            current_start = sentence_start
            current_end = sentence_end
            current_text = sentence
        if current_text and current_start is not None:
            parts.append(_TextPart(current_text, current_start, current_end))
        return parts or [_TextPart(text, 0, len(text))]


def _block_text(block: DocumentBlock) -> str:
    return (block.markdown or block.text or "").strip()


def _section_title(block_type: str, text: str) -> str:
    if block_type == "table":
        return "table"
    return _preview(text)


def _preview(text: str, limit: int = 80) -> str:
    stripped = " ".join(text.split())
    return stripped if len(stripped) <= limit else stripped[:limit] + "..."
