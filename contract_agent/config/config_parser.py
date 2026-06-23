from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


DEFAULT_ENABLED_CONVERTERS = ["builtin"]
DEFAULT_ALLOWED_SUFFIXES = [".txt", ".docx", ".pdf"]
DEFAULT_ENABLED_DETECTORS = ["metadata", "clause_header", "definition", "reference"]


class ParserConfig(BaseModel):
    default_converter: str = "builtin"
    enabled_converters: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy())
    fallback_order: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy())
    allow_converter_fallback: bool = True
    strict_converter_availability: bool = False

    allowed_suffixes: list[str] = Field(default_factory=lambda: DEFAULT_ALLOWED_SUFFIXES.copy())
    allow_path_input: bool = True
    allow_url_input: bool = False
    trusted_path_roots: list[str] = Field(default_factory=list)
    max_input_bytes: int | None = None
    preserve_raw_text: bool = True

    detector_profile: str = "builtin_zh_contract_v1"
    enabled_detectors: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_DETECTORS.copy())
    detector_rules_path: str | None = None
    min_detector_confidence: float = 0.60
    store_detector_reasons: bool = True

    chunk_max_chars: int = 1200
    chunk_target_chars: int = 500
    min_header_confidence: float = 0.65

    markitdown_enabled: bool = False
    docling_enabled: bool = False
    docling_enable_ocr: bool = False
    docling_enable_remote_services: bool = False

    @model_validator(mode="after")
    def _validate_converter_settings(self) -> "ParserConfig":
        self.enabled_converters = _dedupe_non_empty(self.enabled_converters)
        self.fallback_order = _dedupe_non_empty(self.fallback_order)
        self.enabled_detectors = _dedupe_non_empty(self.enabled_detectors)
        self.allowed_suffixes = [_normalize_suffix(suffix) for suffix in self.allowed_suffixes]
        self.trusted_path_roots = [root for root in self.trusted_path_roots if root]
        if self.detector_rules_path == "":
            self.detector_rules_path = None
        if self.default_converter not in self.enabled_converters:
            raise ValueError("parser.default_converter must be present in enabled_converters")
        if self.chunk_max_chars <= 0 or self.chunk_target_chars <= 0:
            raise ValueError("parser chunk sizes must be positive")
        if self.max_input_bytes is not None and self.max_input_bytes <= 0:
            raise ValueError("parser.max_input_bytes must be positive when set")
        if not 0 <= self.min_detector_confidence <= 1:
            raise ValueError("parser.min_detector_confidence must be between 0 and 1")
        if not 0 <= self.min_header_confidence <= 1:
            raise ValueError("parser.min_header_confidence must be between 0 and 1")
        return self

    @classmethod
    def from_settings(cls, settings: Any) -> "ParserConfig":
        max_input_bytes = _effective_max_input_bytes(
            parser_limit=getattr(settings, "parser_max_input_bytes", None),
            upload_limit=getattr(settings, "max_upload_size_bytes", None),
        )
        return cls(
            default_converter=settings.parser_default_converter,
            enabled_converters=list(settings.parser_enabled_converters),
            fallback_order=list(settings.parser_fallback_order),
            allow_converter_fallback=settings.parser_allow_converter_fallback,
            strict_converter_availability=settings.parser_strict_converter_availability,
            allowed_suffixes=list(settings.parser_allowed_suffixes),
            allow_path_input=settings.parser_allow_path_input,
            allow_url_input=settings.parser_allow_url_input,
            trusted_path_roots=list(settings.parser_trusted_path_roots),
            max_input_bytes=max_input_bytes,
            preserve_raw_text=settings.parser_preserve_raw_text,
            detector_profile=settings.parser_detector_profile,
            enabled_detectors=list(settings.parser_enabled_detectors),
            detector_rules_path=settings.parser_detector_rules_path,
            min_detector_confidence=settings.parser_min_detector_confidence,
            store_detector_reasons=settings.parser_store_detector_reasons,
            chunk_max_chars=settings.parser_chunk_max_chars,
            chunk_target_chars=settings.parser_chunk_target_chars,
            min_header_confidence=settings.parser_min_header_confidence,
            markitdown_enabled=settings.parser_markitdown_enabled,
            docling_enabled=settings.parser_docling_enabled,
            docling_enable_ocr=settings.parser_docling_enable_ocr,
            docling_enable_remote_services=settings.parser_docling_enable_remote_services,
        )

    @classmethod
    def from_runtime_snapshot(cls) -> "ParserConfig":
        from contract_agent.config.config_runtime import settings_snapshot

        return cls.from_settings(settings_snapshot())


def derive_effective_max_input_bytes(
    *,
    parser_limit: int | None,
    upload_limit: int | None,
) -> int | None:
    return _effective_max_input_bytes(parser_limit=parser_limit, upload_limit=upload_limit)


def _effective_max_input_bytes(
    *,
    parser_limit: int | None,
    upload_limit: int | None,
) -> int | None:
    if parser_limit is None:
        return upload_limit
    if upload_limit is None:
        return parser_limit
    return min(parser_limit, upload_limit)


def _dedupe_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _normalize_suffix(value: str) -> str:
    suffix = str(value).strip().lower()
    if not suffix:
        return suffix
    return suffix if suffix.startswith(".") else f".{suffix}"
