from __future__ import annotations

from pathlib import Path

from contract_agent.config.config_parser import ParserConfig
from contract_agent.logger.base import ComponentLogger
from contract_agent.parser.convertor.builtin_parser_impl import BuiltinParserImpl
from contract_agent.parser.convertor.docling_parser_impl import DoclingParserImpl
from contract_agent.parser.convertor.markitdown_parser_impl import MarkitdownParserImpl
from contract_agent.parser.exception import DocumentLoadError, ParserError, UnsupportedFileType
from contract_agent.parser.logger import (
    get_parser_logger,
    parser_log_event,
    safe_log_text,
    safe_source_label,
)
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.parser_backend_contract import ParserBackend
from contract_agent.parser.parser_source import ParserSource


class ParserBackendRouter:
    def __init__(
        self, backends: list[ParserBackend], logger: ComponentLogger | None = None
    ) -> None:
        self._backends = {backend.name: backend for backend in backends}
        self.logger = logger or get_parser_logger()

    @classmethod
    def default(cls) -> "ParserBackendRouter":
        return cls([BuiltinParserImpl(), MarkitdownParserImpl(), DoclingParserImpl()])

    def convert(self, source: ParserSource, config: ParserConfig) -> MarkdownDocument:
        source = self._validate_source(source, config)
        warnings: list[str] = []
        last_error: Exception | None = None
        self.logger.handle(
            parser_log_event(
                "Router",
                "开始路由 source=%s order=%s enabled=%s",
                safe_source_label(source.source_path),
                ",".join(config.fallback_order),
                ",".join(config.enabled_converters),
            )
        )

        for backend_name in config.fallback_order:
            is_default_backend = backend_name == config.default_converter
            backend = self._backends.get(backend_name)
            if backend is None:
                message = f"parser backend {backend_name} is not registered"
                if is_default_backend or config.strict_converter_availability:
                    raise DocumentLoadError(message)
                if not config.allow_converter_fallback:
                    raise DocumentLoadError(message)
                warnings.append(message)
                self._log_skip(backend_name, message)
                continue

            if not self._is_enabled_by_backend_flag(backend_name, config):
                message = f"parser backend {backend_name} is disabled by feature flag"
                if is_default_backend or not config.allow_converter_fallback:
                    raise DocumentLoadError(message)
                warnings.append(message)
                self._log_skip(backend_name, message)
                continue

            if backend_name not in config.enabled_converters:
                message = f"parser backend {backend_name} is not enabled"
                if is_default_backend or not config.allow_converter_fallback:
                    raise DocumentLoadError(message)
                warnings.append(message)
                self._log_skip(backend_name, message)
                continue

            support = backend.supports(source, config)
            if not support.supported:
                message = (
                    f"parser backend {backend_name} unavailable: {support.reason or 'unsupported'}"
                )
                if is_default_backend:
                    raise DocumentLoadError(message)
                if config.strict_converter_availability and backend_name != "builtin":
                    raise DocumentLoadError(message)
                if not config.allow_converter_fallback:
                    raise DocumentLoadError(message)
                warnings.append(message)
                self._log_skip(backend_name, message)
                continue

            try:
                self.logger.handle(
                    parser_log_event(
                        "Router",
                        "调用 backend=%s source=%s",
                        backend_name,
                        safe_source_label(source.source_path),
                    )
                )
                result = backend.convert(source, config)
                result.warnings = [*warnings, *result.warnings]
                result.conversion_metadata = {
                    **result.conversion_metadata,
                    "parser_backend": result.backend_name,
                    "warnings": list(result.warnings),
                    "fallback_warnings": list(warnings),
                }
                self.logger.handle(
                    parser_log_event(
                        "Router",
                        "路由完成 backend=%s warnings=%s",
                        result.backend_name,
                        len(result.warnings),
                    )
                )
                return result
            except ParserError as exc:
                last_error = exc
            except Exception as exc:  # pragma: no cover - defensive backend boundary
                last_error = DocumentLoadError(f"parser backend {backend_name} failed: {exc}")

            if is_default_backend:
                if isinstance(last_error, ParserError):
                    raise last_error
                raise DocumentLoadError(str(last_error))
            if not config.allow_converter_fallback:
                if isinstance(last_error, ParserError):
                    raise last_error
                raise DocumentLoadError(str(last_error))
            warnings.append(f"parser backend {backend_name} failed: {last_error}")
            self._log_skip(backend_name, str(last_error))

        if isinstance(last_error, ParserError):
            raise last_error
        if last_error is not None:
            raise DocumentLoadError(str(last_error))
        raise DocumentLoadError("没有可用的 parser backend。")

    parse = convert

    def _validate_source(self, source: ParserSource, config: ParserConfig) -> ParserSource:
        if source.kind == "text":
            text_size = len((source.text or "").encode("utf-8"))
            if config.max_input_bytes is not None and text_size > config.max_input_bytes:
                raise DocumentLoadError("文本大小超过 parser.max_input_bytes 限制。")
            return source

        if source.kind == "path":
            if not config.allow_path_input:
                raise DocumentLoadError("当前 parser 配置禁止本地 path 输入。")
            path = Path(source.local_path or source.source_path).expanduser().resolve()
            if config.trusted_path_roots:
                roots = [Path(root).expanduser().resolve() for root in config.trusted_path_roots]
                if not any(path == root or root in path.parents for root in roots):
                    raise DocumentLoadError("文件路径不在 parser.trusted_path_roots 允许范围内。")
            if not path.exists():
                raise DocumentLoadError("文件路径不存在，无法解析。")
            if not path.is_file():
                raise DocumentLoadError("文件路径不是普通文件，无法解析。")
            try:
                path.open("rb").close()
            except OSError as exc:
                raise DocumentLoadError(f"文件不可读取，无法解析: {exc}") from exc
            if config.max_input_bytes is not None:
                if path.stat().st_size > config.max_input_bytes:
                    raise DocumentLoadError("文件大小超过 parser.max_input_bytes 限制。")
            source = ParserSource.from_path(path)
            suffix = f".{source.file_type}" if source.file_type else ""
            if not suffix:
                raise DocumentLoadError("缺少文件名或文件后缀，无法判断文件类型。")
            if suffix.lower() not in config.allowed_suffixes:
                raise UnsupportedFileType(f"不支持的文件类型：{suffix or '未知'}")
            return source

        suffix = f".{source.file_type}" if source.file_type else ""
        if not suffix:
            raise DocumentLoadError("缺少文件名或文件后缀，无法判断文件类型。")
        if suffix.lower() not in config.allowed_suffixes:
            raise UnsupportedFileType(f"不支持的文件类型：{suffix or '未知'}")

        if source.kind == "bytes":
            content_size = len(source.content or b"")
            if config.max_input_bytes is not None and content_size > config.max_input_bytes:
                raise DocumentLoadError("文件大小超过 parser.max_input_bytes 限制。")
        return source

    def _is_enabled_by_backend_flag(self, backend_name: str, config: ParserConfig) -> bool:
        if backend_name == "markitdown":
            return config.markitdown_enabled
        if backend_name == "docling":
            return config.docling_enabled
        return True

    def _log_skip(self, backend_name: str, reason: str) -> None:
        self.logger.handle(
            parser_log_event(
                "Router",
                "跳过 backend=%s reason=%s",
                backend_name,
                safe_log_text(reason),
            )
        )
