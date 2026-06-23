from __future__ import annotations

import importlib.util

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ConversionResult, ConverterSupport, ParseSource
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
            __import__("markitdown")
        except Exception as exc:
            raise DocumentLoadError(f"MarkItDown adapter 依赖不可用：{exc}") from exc
        raise DocumentLoadError("MarkItDown adapter 壳已启用，但第一阶段尚未接入真实转换。")
