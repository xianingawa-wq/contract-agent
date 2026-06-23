from __future__ import annotations

from pathlib import Path

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ConversionResult, DocumentConverter, ParseSource
from contract_agent.parser.converters.builtin import BuiltinConverter
from contract_agent.parser.converters.docling import DoclingConverter
from contract_agent.parser.converters.markitdown import MarkItDownConverter
from contract_agent.parser.exceptions import DocumentLoadError, ParserError, UnsupportedFileType


class ConverterRouter:
    def __init__(self, converters: list[DocumentConverter]) -> None:
        self._converters = {converter.name: converter for converter in converters}

    @classmethod
    def default(cls) -> "ConverterRouter":
        return cls([BuiltinConverter(), MarkItDownConverter(), DoclingConverter()])

    def convert(self, source: ParseSource, config: ParserConfig) -> ConversionResult:
        self._validate_source(source, config)
        warnings: list[str] = []
        last_error: Exception | None = None

        for converter_name in config.fallback_order:
            converter = self._converters.get(converter_name)
            if converter is None:
                message = f"converter {converter_name} is not registered"
                if config.strict_converter_availability:
                    raise DocumentLoadError(message)
                warnings.append(message)
                continue
            if not self._is_enabled_by_adapter_flag(converter_name, config):
                warnings.append(f"converter {converter_name} is disabled by adapter flag")
                continue
            if converter_name not in config.enabled_converters:
                warnings.append(f"converter {converter_name} is not enabled")
                continue

            support = converter.supports(source, config)
            if not support.supported:
                message = (
                    f"converter {converter_name} unavailable: {support.reason or 'unsupported'}"
                )
                if config.strict_converter_availability and converter_name != "builtin":
                    raise DocumentLoadError(message)
                warnings.append(message)
                continue

            try:
                result = converter.convert(source, config)
                result.warnings = [*warnings, *result.warnings]
                result.metadata = {**result.metadata, "fallback_warnings": list(warnings)}
                result.document.conversion_metadata.update(
                    {
                        "converter": result.converter_name,
                        "warnings": list(result.warnings),
                    }
                )
                return result
            except ParserError as exc:
                last_error = exc
            except Exception as exc:  # pragma: no cover - defensive converter boundary
                last_error = DocumentLoadError(f"converter {converter_name} failed: {exc}")

            if not config.allow_converter_fallback:
                if isinstance(last_error, ParserError):
                    raise last_error
                raise DocumentLoadError(str(last_error))
            warnings.append(f"converter {converter_name} failed: {last_error}")

        if isinstance(last_error, ParserError):
            raise last_error
        if last_error is not None:
            raise DocumentLoadError(str(last_error))
        raise DocumentLoadError("没有可用的 parser converter。")

    def _validate_source(self, source: ParseSource, config: ParserConfig) -> None:
        suffix = f".{source.file_type}" if source.file_type else ""
        if source.kind == "text":
            text_size = len((source.text or "").encode("utf-8"))
            if config.max_input_bytes is not None and text_size > config.max_input_bytes:
                raise DocumentLoadError("文本大小超过 parser.max_input_bytes 限制。")
            return

        if source.kind != "text":
            if not suffix:
                raise DocumentLoadError("缺少文件名或文件后缀，无法判断文件类型。")
            if suffix.lower() not in config.allowed_suffixes:
                raise UnsupportedFileType(f"不支持的文件类型：{suffix or '未知'}")

        if source.kind == "path":
            if not config.allow_path_input:
                raise DocumentLoadError("当前 parser 配置禁止本地 path 输入。")
            path = Path(source.local_path or source.source_path).expanduser().resolve()
            if config.trusted_path_roots:
                roots = [Path(root).expanduser().resolve() for root in config.trusted_path_roots]
                if not any(path == root or root in path.parents for root in roots):
                    raise DocumentLoadError("文件路径不在 parser.trusted_path_roots 允许范围内。")
            if config.max_input_bytes is not None and path.exists():
                if path.stat().st_size > config.max_input_bytes:
                    raise DocumentLoadError("文件大小超过 parser.max_input_bytes 限制。")

        if source.kind == "bytes":
            content_size = len(source.content or b"")
            if config.max_input_bytes is not None and content_size > config.max_input_bytes:
                raise DocumentLoadError("文件大小超过 parser.max_input_bytes 限制。")

    def _is_enabled_by_adapter_flag(self, converter_name: str, config: ParserConfig) -> bool:
        if converter_name == "markitdown":
            return config.markitdown_enabled
        if converter_name == "docling":
            return config.docling_enabled
        return True
