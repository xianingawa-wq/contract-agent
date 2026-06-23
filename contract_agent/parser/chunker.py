from __future__ import annotations

import re

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.detectors.base import DetectorContext
from contract_agent.parser.detectors.clause_header import ClauseHeaderDetector
from contract_agent.parser.detectors.registry import RuleRegistry
from contract_agent.parser.models import ClauseChunk, DetectorResult, DocumentSpan, ParsedDocument


class ContractChunker:
    def __init__(self, parser_config: ParserConfig | None = None) -> None:
        self.parser_config = parser_config or ParserConfig()

    def chunk(
        self,
        document: ParsedDocument,
        detector_results: list[DetectorResult] | None = None,
    ) -> list[ClauseChunk]:
        header_results = self._header_results(document, detector_results)
        headers_by_span = {
            span_id: result
            for result in header_results
            for span_id in result.span_ids
            if result.confidence >= self.parser_config.min_header_confidence
        }
        chunks: list[ClauseChunk] = []
        current: dict | None = None
        parent_clause_no: str | None = None
        parent_title: str | None = None

        for span in document.spans:
            header_result = headers_by_span.get(span.span_id)
            if header_result:
                if current:
                    chunks.append(self._to_chunk(current))
                level, clause_no, section_title = self._header_tuple(header_result)
                if level == "clause":
                    parent_clause_no = clause_no
                    parent_title = section_title
                    current = self._new_chunk(span, level, clause_no, None, section_title)
                else:
                    title = section_title if section_title else (parent_title or clause_no)
                    current = self._new_chunk(span, level, clause_no, parent_clause_no, title)
                continue

            if current is None:
                current = self._new_chunk(span, "preface", None, None, "前言")
            else:
                current["source_text"] += "\n" + span.text
                current["end_offset"] = span.end_offset

        if current:
            chunks.append(self._to_chunk(current))

        self._link_neighbors(chunks)
        return self._split_long_chunks(chunks)

    def _header_results(
        self,
        document: ParsedDocument,
        detector_results: list[DetectorResult] | None,
    ) -> list[DetectorResult]:
        if detector_results is not None:
            return [
                result
                for result in detector_results
                if result.detector_name == "clause_header" and result.result_type == "clause_header"
            ]
        registry = RuleRegistry.from_config(self.parser_config)
        context = DetectorContext(
            document=document,
            config=self.parser_config,
            registry=registry,
        )
        return ClauseHeaderDetector().detect(context)

    def _header_tuple(self, result: DetectorResult) -> tuple[str, str, str]:
        level = str(result.value.get("level") or "clause")
        clause_no = str(result.value.get("clause_no") or "")
        section_title = str(result.value.get("title") or clause_no)
        return level, clause_no, section_title

    def _new_chunk(
        self,
        span: DocumentSpan,
        level: str,
        clause_no: str | None,
        parent_clause_no: str | None,
        section_title: str,
    ) -> dict:
        return {
            "chunk_id": f"chunk-{span.span_id}",
            "chunk_level": level,
            "clause_no": clause_no,
            "parent_clause_no": parent_clause_no,
            "section_title": section_title,
            "page_no": span.page_no,
            "start_offset": span.start_offset,
            "end_offset": span.end_offset,
            "source_text": span.text,
            "prev_chunk_id": None,
            "next_chunk_id": None,
        }

    def _to_chunk(self, payload: dict) -> ClauseChunk:
        return ClauseChunk(**payload)

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
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        source_text=part,
                    )
                )

        self._link_neighbors(refined)
        return refined

    def _split_by_sentences(self, text: str, max_chars: int) -> list[str]:
        sentences = re.split(r"(?<=[。；;])", text)
        parts: list[str] = []
        current = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(current) + len(sentence) <= max_chars:
                current += sentence
            else:
                if current:
                    parts.append(current)
                current = sentence
        if current:
            parts.append(current)
        return parts or [text]
