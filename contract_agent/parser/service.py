from __future__ import annotations

from pathlib import Path

from contract_agent.config.config_parser import ParserConfig
from contract_agent.logger.base import ComponentLogger
from contract_agent.parser.chunker import ContractChunker
from contract_agent.parser.converters.base import ConversionResult, ParseSource
from contract_agent.parser.converters.router import ConverterRouter
from contract_agent.parser.detectors.registry import DetectorRegistry
from contract_agent.parser.log import get_parser_logger, parser_log_event
from contract_agent.parser.models import (
    DocumentDefinition,
    DocumentReference,
    DocumentSemanticGraph,
    ParsedDocument,
)
from contract_agent.parser.serializers import to_markdown, to_plain_text


class ContractParser:
    def __init__(
        self,
        parser_config: ParserConfig | None = None,
        converter_router: ConverterRouter | None = None,
        detector_registry: DetectorRegistry | None = None,
        chunker: ContractChunker | None = None,
        logger: ComponentLogger | None = None,
    ) -> None:
        self.parser_config = parser_config or ParserConfig.from_runtime_snapshot()
        self.converter_router = converter_router or ConverterRouter.default()
        self.detector_registry = detector_registry or DetectorRegistry.default(self.parser_config)
        self.chunker = chunker or ContractChunker(self.parser_config)
        self.logger = logger or get_parser_logger()

    def parse_text(self, text: str, source_name: str = "inline.txt") -> ParsedDocument:
        return self._parse_source(ParseSource.from_text(text, file_name=source_name))

    def parse_bytes(
        self,
        file_name: str,
        content: bytes,
        source_path: str | None = None,
    ) -> ParsedDocument:
        return self._parse_source(
            ParseSource.from_bytes(file_name, content, source_path=source_path)
        )

    def parse_path(self, file_path: str | Path) -> ParsedDocument:
        return self._parse_source(ParseSource.from_path(file_path))

    def parse(self, file_path: str | Path) -> ParsedDocument:
        return self.parse_path(file_path)

    def _parse_source(self, source: ParseSource) -> ParsedDocument:
        self.logger.handle(
            parser_log_event(
                "Convert",
                "开始转换 source=%s kind=%s file_type=%s",
                source.source_path,
                source.kind,
                source.file_type or "unknown",
            )
        )
        try:
            conversion = self.converter_router.convert(source, self.parser_config)
        except Exception as exc:
            self.logger.handle(
                parser_log_event(
                    "Convert",
                    "转换失败 source=%s error=%s",
                    source.source_path,
                    exc,
                )
            )
            raise
        self.logger.handle(
            parser_log_event(
                "Convert",
                "转换完成 converter=%s warnings=%s blocks=%s spans=%s",
                conversion.converter_name,
                len(conversion.warnings),
                len(conversion.document.blocks),
                len(conversion.document.spans),
            )
        )
        document = conversion.document
        self.logger.handle(
            parser_log_event(
                "Detector",
                "开始检测 detectors=%s min_confidence=%.2f",
                ",".join(self.parser_config.enabled_detectors),
                self.parser_config.min_detector_confidence,
            )
        )
        try:
            document.detector_results = self.detector_registry.detect(document, self.parser_config)
        except Exception as exc:
            self.logger.handle(
                parser_log_event(
                    "Detector",
                    "检测失败 error=%s",
                    exc,
                )
            )
            raise
        self.logger.handle(
            parser_log_event(
                "Detector",
                "检测完成 detectors=%s results=%s",
                ",".join(self.parser_config.enabled_detectors),
                len(document.detector_results),
            )
        )
        self._project_detector_results(document)
        document.clause_chunks = self.chunker.chunk(document, document.detector_results)
        document.raw_text = to_plain_text(document)
        document.markdown_content = to_markdown(document)
        document.semantic_graph = self._build_semantic_graph(document)
        document.conversion_metadata = self._conversion_metadata(conversion)
        return document

    def _project_detector_results(self, document: ParsedDocument) -> None:
        definitions: list[DocumentDefinition] = []
        references: list[DocumentReference] = []
        blocks_by_id = {block.block_id: block for block in document.blocks}
        for result in document.detector_results:
            if result.result_type == "metadata.title":
                document.metadata.title = result.value.get("title")
                for block_id in result.block_ids:
                    if block_id in blocks_by_id:
                        blocks_by_id[block_id].block_type = "title"
            elif result.result_type == "metadata.contract_type_hint":
                document.metadata.contract_type_hint = result.value.get("contract_type_hint")
            elif result.result_type == "metadata.party":
                role = result.value.get("role")
                party = result.value.get("party")
                if role == "甲方":
                    document.metadata.party_a = party
                elif role == "乙方":
                    document.metadata.party_b = party
            elif result.result_type == "metadata.signed_date":
                document.metadata.signed_date = result.value.get("signed_date")
            elif result.result_type == "clause_header":
                for block_id in result.block_ids:
                    block = blocks_by_id.get(block_id)
                    if block is None:
                        continue
                    block.block_type = "clause_header"
                    block.level = result.value.get("level_num")
                    block.metadata.update(
                        {
                            "clause_no": result.value.get("clause_no"),
                            "section_title": result.value.get("title"),
                        }
                    )
                    block.confidence.detector_scores[result.detector_name] = result.confidence
            elif result.result_type == "definition":
                definitions.append(
                    DocumentDefinition(
                        term=str(result.value.get("term") or ""),
                        definition=str(result.value.get("definition") or ""),
                        span_id=result.span_ids[0] if result.span_ids else None,
                    )
                )
            elif result.result_type == "reference":
                references.append(
                    DocumentReference(
                        source_span_id=result.span_ids[0] if result.span_ids else None,
                        target=str(result.value.get("target") or ""),
                        reference_type=result.value.get("reference_type"),
                        raw_text=result.value.get("raw_text"),
                    )
                )
        document.definitions = [definition for definition in definitions if definition.term]
        document.references = [reference for reference in references if reference.target]

    def _conversion_metadata(self, conversion: ConversionResult) -> dict[str, object]:
        return {
            "converter": conversion.converter_name,
            "warnings": list(conversion.warnings),
            **conversion.metadata,
        }

    def _build_semantic_graph(self, document: ParsedDocument) -> DocumentSemanticGraph:
        nodes: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        doc_node_id = f"doc:{document.metadata.doc_id}"
        nodes.append(
            {
                "id": doc_node_id,
                "type": "document",
                "label": document.metadata.title or document.metadata.file_name,
                "metadata": {
                    "file_name": document.metadata.file_name,
                    "file_type": document.metadata.file_type,
                    "source_path": document.metadata.source_path,
                },
            }
        )

        block_nodes_by_id: dict[str, str] = {}
        block_nodes_by_span_id: dict[str, str] = {}
        ordered_blocks = _blocks_ordered_by_offset(document)
        block_cursor = 0
        for block in document.blocks:
            node_id = f"block:{block.block_id}"
            block_nodes_by_id[block.block_id] = node_id
            for span_id in block.location.span_ids:
                block_nodes_by_span_id[span_id] = node_id
            nodes.append(
                {
                    "id": node_id,
                    "type": "block",
                    "label": _preview(block.text),
                    "metadata": {
                        "block_id": block.block_id,
                        "block_type": block.block_type,
                        "page_no": block.location.page_no,
                        "clause_no": block.metadata.get("clause_no"),
                    },
                }
            )
            edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})

        for table in document.tables:
            node_id = f"table:{table.table_id}"
            nodes.append(
                {
                    "id": node_id,
                    "type": "table",
                    "label": table.caption or table.table_id,
                    "metadata": {
                        "table_id": table.table_id,
                        "page_no": table.page_no,
                        "row_count": len(table.rows),
                    },
                }
            )
            edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
            for span_id in table.span_ids:
                block_node_id = block_nodes_by_span_id.get(span_id)
                if block_node_id:
                    edges.append(
                        {"source": node_id, "target": block_node_id, "type": "derived_from"}
                    )

        previous_chunk_node_id: str | None = None
        for chunk in document.clause_chunks:
            node_id = f"chunk:{chunk.chunk_id}"
            nodes.append(
                {
                    "id": node_id,
                    "type": "chunk",
                    "label": chunk.section_title,
                    "metadata": {
                        "chunk_id": chunk.chunk_id,
                        "chunk_level": chunk.chunk_level,
                        "clause_no": chunk.clause_no,
                        "page_no": chunk.page_no,
                    },
                }
            )
            edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
            if previous_chunk_node_id:
                edges.append({"source": previous_chunk_node_id, "target": node_id, "type": "next"})
            previous_chunk_node_id = node_id
            block, block_cursor = _next_block_for_chunk(
                ordered_blocks,
                block_cursor,
                chunk.start_offset,
                chunk.end_offset,
            )
            if block is not None:
                block_node_id = block_nodes_by_id.get(block.block_id)
                if block_node_id:
                    edges.append(
                        {"source": node_id, "target": block_node_id, "type": "derived_from"}
                    )

        for definition in document.definitions:
            node_id = f"definition:{definition.term}"
            nodes.append(
                {
                    "id": node_id,
                    "type": "definition",
                    "label": definition.term,
                    "metadata": definition.model_dump(mode="json"),
                }
            )
            edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
            if definition.span_id and definition.span_id in block_nodes_by_span_id:
                edges.append(
                    {
                        "source": node_id,
                        "target": block_nodes_by_span_id[definition.span_id],
                        "type": "defined_in",
                    }
                )

        for index, reference in enumerate(document.references):
            node_id = f"reference:{index}"
            nodes.append(
                {
                    "id": node_id,
                    "type": "reference",
                    "label": reference.target,
                    "metadata": reference.model_dump(mode="json"),
                }
            )
            edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
            if reference.source_span_id and reference.source_span_id in block_nodes_by_span_id:
                edges.append(
                    {
                        "source": block_nodes_by_span_id[reference.source_span_id],
                        "target": node_id,
                        "type": "references",
                    }
                )

        return DocumentSemanticGraph(
            nodes=nodes,
            edges=edges,
            metadata={"node_count": len(nodes), "edge_count": len(edges)},
        )


def _blocks_ordered_by_offset(document: ParsedDocument) -> list:
    return sorted(
        [
            block
            for block in document.blocks
            if block.location.start_offset is not None and block.location.end_offset is not None
        ],
        key=lambda block: (block.location.start_offset, block.location.end_offset),
    )


def _next_block_for_chunk(
    ordered_blocks: list,
    cursor: int,
    start_offset: int,
    end_offset: int,
) -> tuple[object | None, int]:
    while (
        cursor < len(ordered_blocks)
        and ordered_blocks[cursor].location.end_offset is not None
        and ordered_blocks[cursor].location.end_offset < start_offset
    ):
        cursor += 1
    if cursor >= len(ordered_blocks):
        return None, cursor
    block = ordered_blocks[cursor]
    if block.location.start_offset is not None and block.location.start_offset <= end_offset:
        return block, cursor
    return None, cursor


def _preview(text: str, limit: int = 120) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= limit else stripped[:limit] + "..."
