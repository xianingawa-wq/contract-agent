from __future__ import annotations

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.convertor.builtin_markdown_converter import (
    load_bytes,
    load_path,
    load_text,
)
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.parser_backend_contract import ParserBackendSupport
from contract_agent.parser.parser_source import ParserSource


class BuiltinParserImpl:
    name = "builtin"
    supported_suffixes = {".txt", ".docx", ".pdf"}

    def supports(self, source: ParserSource, config: ParserConfig) -> ParserBackendSupport:
        if source.kind == "text":
            return ParserBackendSupport(supported=True, confidence=1.0, reason="builtin text input")
        normalized_file_type = (source.file_type or "").strip().lower().lstrip(".")
        suffix = f".{normalized_file_type}" if normalized_file_type else ""
        if suffix in self.supported_suffixes and suffix in config.allowed_suffixes:
            return ParserBackendSupport(
                supported=True, confidence=0.95, reason="builtin suffix match"
            )
        return ParserBackendSupport(
            supported=False, reason=f"unsupported suffix: {suffix or 'unknown'}"
        )

    def convert(self, source: ParserSource, config: ParserConfig) -> MarkdownDocument:
        if source.kind == "text":
            loaded = load_text(source.text or "", source_name=source.file_name)
        elif source.kind == "bytes":
            loaded = load_bytes(
                source.file_name,
                source.content or b"",
                source_path=source.source_path,
            )
        else:
            _, loaded = load_path(source.local_path or source.source_path)

        return MarkdownDocument(
            markdown_content=loaded.markdown_content,
            file_name=source.file_name,
            file_type=loaded.file_type,
            source_path=loaded.source_path,
            backend_name=self.name,
            html_content=loaded.html_content,
            conversion_metadata={"parser_backend": self.name, "source_kind": source.kind},
        )

    parse = convert
