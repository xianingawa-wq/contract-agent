from __future__ import annotations

from pathlib import Path

from contract_agent.config.config_parser import ParserConfig
from contract_agent.logger.base import ComponentLogger
from contract_agent.parser.logger import get_parser_logger, parser_log_event
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.models import DocumentSemanticGraph, ParsedDocument
from contract_agent.parser.parsed.markdown_chunker import ContractChunker
from contract_agent.parser.parsed.markdown_parsed_service import MarkdownParsedService
from contract_agent.parser.parsed.semantic_graph_builder import build_semantic_graph
from contract_agent.parser.parser_backend_router import ParserBackendRouter
from contract_agent.parser.parser_source import ParserSource


class ContractParser:
    def __init__(
        self,
        parser_config: ParserConfig | None = None,
        backend_router: ParserBackendRouter | None = None,
        markdown_parser: MarkdownParsedService | None = None,
        chunker: ContractChunker | None = None,
        logger: ComponentLogger | None = None,
    ) -> None:
        self.parser_config = parser_config or ParserConfig.from_runtime_snapshot()
        self.backend_router = backend_router or ParserBackendRouter.default()
        self.chunker = chunker or ContractChunker(self.parser_config)
        self.markdown_parser = markdown_parser or MarkdownParsedService(
            self.parser_config,
            chunker=self.chunker,
        )
        self.logger = logger or get_parser_logger()

    def convert_text(self, text: str, source_name: str = "inline.txt") -> MarkdownDocument:
        return self.convert_to_markdown(ParserSource.from_text(text, file_name=source_name))

    def convert_bytes(
        self,
        file_name: str,
        content: bytes,
        source_path: str | None = None,
    ) -> MarkdownDocument:
        return self.convert_to_markdown(
            ParserSource.from_bytes(file_name, content, source_path=source_path)
        )

    def convert_path(self, file_path: str | Path) -> MarkdownDocument:
        return self.convert_to_markdown(ParserSource.from_path(file_path))

    def convert_to_markdown(self, source: str | Path | ParserSource) -> MarkdownDocument:
        parser_source = (
            source if isinstance(source, ParserSource) else ParserSource.from_path(source)
        )
        self.logger.handle(
            parser_log_event(
                "Service",
                "开始 Markdown 转换 source=%s kind=%s file_type=%s",
                parser_source.source_path,
                parser_source.kind,
                parser_source.file_type or "unknown",
            )
        )
        markdown_document = self.backend_router.convert(parser_source, self.parser_config)
        self.logger.handle(
            parser_log_event(
                "Service",
                "Markdown 转换完成 backend=%s chars=%s",
                markdown_document.backend_name,
                len(markdown_document.markdown_content),
            )
        )
        return markdown_document

    def parse_markdown(self, markdown_document: MarkdownDocument) -> ParsedDocument:
        self.logger.handle(
            parser_log_event(
                "Service",
                "开始 Markdown 解析 backend=%s chars=%s",
                markdown_document.backend_name,
                len(markdown_document.markdown_content),
            )
        )
        document = self.markdown_parser.parse(markdown_document)
        self.logger.handle(
            parser_log_event(
                "Service",
                "Markdown 解析完成 backend=%s blocks=%s chunks=%s",
                markdown_document.backend_name,
                len(document.blocks),
                len(document.clause_chunks),
            )
        )
        self.logger.handle(
            parser_log_event(
                "Output",
                "ParsedDocument 输出 backend=%s blocks=%s chunks=%s tables=%s",
                markdown_document.backend_name,
                len(document.blocks),
                len(document.clause_chunks),
                len(document.tables),
            )
        )
        return document

    def parse_text(self, text: str, source_name: str = "inline.txt") -> ParsedDocument:
        return self.parse_markdown(self.convert_text(text, source_name=source_name))

    def parse_bytes(
        self,
        file_name: str,
        content: bytes,
        source_path: str | None = None,
    ) -> ParsedDocument:
        return self.parse_markdown(self.convert_bytes(file_name, content, source_path=source_path))

    def parse_path(self, file_path: str | Path) -> ParsedDocument:
        return self.parse_markdown(self.convert_path(file_path))

    def parse(self, file_path: str | Path) -> ParsedDocument:
        return self.parse_path(file_path)

    def _parse_source(self, source: ParserSource) -> ParsedDocument:
        return self.parse_markdown(self.convert_to_markdown(source))

    def _build_semantic_graph(self, document: ParsedDocument) -> DocumentSemanticGraph:
        return build_semantic_graph(document)
