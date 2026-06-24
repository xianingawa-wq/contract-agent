from __future__ import annotations

import importlib
import importlib.util

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ConversionResult, ConverterSupport, ParseSource
from contract_agent.parser.converters.markdown import document_from_markdown
from contract_agent.parser.converters.source import local_converter_source
from contract_agent.parser.exceptions import DocumentLoadError


class MarkItDownConverter:
    name = "markitdown"

    def supports(self, source: ParseSource, config: ParserConfig) -> ConverterSupport:
        if not config.markitdown_enabled:
            return ConverterSupport(supported=False, reason="markitdown adapter disabled")
        if importlib.util.find_spec("markitdown") is None:
            return ConverterSupport(supported=False, reason="markitdown package is not installed")
        return ConverterSupport(supported=True, confidence=0.85, reason="markitdown available")

    def convert(self, source: ParseSource, config: ParserConfig) -> ConversionResult:
        try:
            module = importlib.import_module("markitdown")
        except Exception as exc:
            raise DocumentLoadError(f"MarkItDown adapter 依赖不可用：{exc}") from exc

        converter_cls = getattr(module, "MarkItDown", None)
        if converter_cls is None:
            raise DocumentLoadError("MarkItDown adapter 未找到 MarkItDown 入口。")

        with local_converter_source(source) as input_path:
            result = converter_cls().convert(input_path)

        markdown = _markdown_from_result(result)
        document = document_from_markdown(
            markdown,
            file_name=source.file_name,
            source_path=source.source_path,
            converter_name=self.name,
        )
        return ConversionResult(
            document=document,
            converter_name=self.name,
            metadata={"converter": self.name, "source_kind": source.kind},
        )


def _markdown_from_result(result: object) -> str:
    markdown = getattr(result, "text_content", None)
    if markdown is None:
        markdown = getattr(result, "markdown", None)
    if markdown is None:
        markdown = str(result)
    text = str(markdown).strip()
    if not text:
        raise DocumentLoadError("MarkItDown adapter 未返回可解析内容。")
    return text
