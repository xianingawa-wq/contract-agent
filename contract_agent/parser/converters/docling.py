from __future__ import annotations

import importlib.util

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ConversionResult, ConverterSupport, ParseSource
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
            __import__("docling")
        except Exception as exc:
            raise DocumentLoadError(f"Docling adapter 依赖不可用：{exc}") from exc
        raise DocumentLoadError("Docling adapter 壳已启用，但第一阶段尚未接入真实转换。")
