from __future__ import annotations

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ConversionResult, ConverterSupport, ParseSource
from contract_agent.parser.loaders import LoadedDocumentContent, load_bytes, load_path, load_text
from contract_agent.parser.metadata import build_metadata
from contract_agent.parser.models import (
    BlockLocation,
    DocumentBlock,
    ParsedDocument,
)


class BuiltinConverter:
    name = "builtin"

    def supports(self, source: ParseSource, config: ParserConfig) -> ConverterSupport:
        if source.kind == "text":
            return ConverterSupport(supported=True, confidence=1.0, reason="builtin text input")
        suffix = f".{source.file_type}" if source.file_type else ""
        if suffix in config.allowed_suffixes:
            return ConverterSupport(supported=True, confidence=0.95, reason="builtin suffix match")
        return ConverterSupport(
            supported=False, reason=f"unsupported suffix: {suffix or 'unknown'}"
        )

    def convert(self, source: ParseSource, config: ParserConfig) -> ConversionResult:
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

        document = _document_from_loaded(source.file_name, loaded)
        return ConversionResult(
            document=document,
            converter_name=self.name,
            metadata={"converter": self.name, "source_kind": source.kind},
        )


def _document_from_loaded(file_name: str, loaded: LoadedDocumentContent) -> ParsedDocument:
    metadata = build_metadata(
        file_name=file_name,
        source_path=loaded.source_path,
        file_type=loaded.file_type,
        raw_text=loaded.raw_text,
        spans=loaded.spans,
    )
    blocks = [
        DocumentBlock(
            block_id=span.span_id,
            block_type="paragraph",
            text=span.text,
            location=BlockLocation(
                page_no=span.page_no,
                block_index=span.block_index,
                start_offset=span.start_offset,
                end_offset=span.end_offset,
                span_ids=[span.span_id],
                source_path=loaded.source_path,
            ),
        )
        for span in loaded.spans
    ]
    return ParsedDocument(
        metadata=metadata,
        raw_text=loaded.raw_text,
        spans=loaded.spans,
        blocks=blocks,
        html_content=loaded.html_content,
        conversion_metadata={"converter": "builtin"},
    )
