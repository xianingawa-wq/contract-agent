from __future__ import annotations

import importlib
import importlib.util

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ConversionResult, ConverterSupport, ParseSource
from contract_agent.parser.converters.markdown import document_from_markdown
from contract_agent.parser.converters.source import local_converter_source
from contract_agent.parser.exceptions import DocumentLoadError


class DoclingConverter:
    name = "docling"

    def supports(self, source: ParseSource, config: ParserConfig) -> ConverterSupport:
        if not config.docling_enabled:
            return ConverterSupport(supported=False, reason="docling adapter disabled")
        if config.docling_enable_remote_services:
            return ConverterSupport(
                supported=False,
                reason="docling remote services are disabled by parser safety policy",
            )
        if importlib.util.find_spec("docling") is None:
            return ConverterSupport(supported=False, reason="docling package is not installed")
        return ConverterSupport(supported=True, confidence=0.85, reason="docling available")

    def convert(self, source: ParseSource, config: ParserConfig) -> ConversionResult:
        try:
            module = importlib.import_module("docling.document_converter")
        except Exception as exc:
            raise DocumentLoadError(f"Docling adapter 依赖不可用：{exc}") from exc

        converter_cls = getattr(module, "DocumentConverter", None)
        if converter_cls is None:
            raise DocumentLoadError("Docling adapter 未找到 DocumentConverter 入口。")

        with local_converter_source(source) as input_path:
            result = converter_cls().convert(input_path)

        document_obj = getattr(result, "document", None)
        if document_obj is None:
            raise DocumentLoadError("Docling adapter 未返回 document。")
        export_to_markdown = getattr(document_obj, "export_to_markdown", None)
        if export_to_markdown is None:
            raise DocumentLoadError("Docling document 不支持 export_to_markdown。")

        markdown = str(export_to_markdown()).strip()
        if not markdown:
            raise DocumentLoadError("Docling adapter 未返回可解析内容。")
        html_content = _export_html(document_obj)
        document = document_from_markdown(
            markdown,
            file_name=source.file_name,
            source_path=source.source_path,
            converter_name=self.name,
            html_content=html_content,
        )
        return ConversionResult(
            document=document,
            converter_name=self.name,
            metadata={"converter": self.name, "source_kind": source.kind},
        )


def _export_html(document_obj: object) -> str:
    export_to_html = getattr(document_obj, "export_to_html", None)
    if export_to_html is None:
        return ""
    try:
        return str(export_to_html()).strip()
    except Exception:
        return ""
