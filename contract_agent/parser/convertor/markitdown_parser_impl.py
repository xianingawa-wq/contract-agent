from __future__ import annotations

import importlib
import importlib.util

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.convertor.local_file_source import local_parser_source
from contract_agent.parser.exception import DocumentLoadError
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.parser_backend_contract import ParserBackendSupport
from contract_agent.parser.parser_source import ParserSource


class MarkitdownParserImpl:
    name = "markitdown"

    def supports(self, source: ParserSource, config: ParserConfig) -> ParserBackendSupport:
        if not config.markitdown_enabled:
            return ParserBackendSupport(supported=False, reason="markitdown backend disabled")
        if importlib.util.find_spec("markitdown") is None:
            return ParserBackendSupport(
                supported=False, reason="markitdown package is not installed"
            )
        return ParserBackendSupport(supported=True, confidence=0.85, reason="markitdown available")

    def convert(self, source: ParserSource, config: ParserConfig) -> MarkdownDocument:
        try:
            module = importlib.import_module("markitdown")
        except Exception as exc:
            raise DocumentLoadError(f"MarkItDown backend 依赖不可用：{exc}") from exc

        markitdown_cls = getattr(module, "MarkItDown", None)
        if markitdown_cls is None:
            raise DocumentLoadError("MarkItDown backend 未找到 MarkItDown 入口。")

        try:
            with local_parser_source(source) as input_path:
                result = markitdown_cls().convert(input_path)
        except DocumentLoadError:
            raise
        except Exception as exc:
            raise DocumentLoadError(f"MarkItDown backend 转换失败：{exc}") from exc

        markdown = _markdown_from_result(result)
        return MarkdownDocument(
            markdown_content=markdown,
            file_name=source.file_name,
            file_type=source.file_type,
            source_path=source.source_path,
            backend_name=self.name,
            conversion_metadata={"parser_backend": self.name, "source_kind": source.kind},
        )

    parse = convert


def _markdown_from_result(result: object) -> str:
    markdown = getattr(result, "text_content", None)
    if markdown is None:
        markdown = getattr(result, "markdown", None)
    if markdown is None:
        markdown = str(result)
    text = str(markdown)
    if not text.strip():
        raise DocumentLoadError("MarkItDown backend 未返回可解析内容。")
    return text
