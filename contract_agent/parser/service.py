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
