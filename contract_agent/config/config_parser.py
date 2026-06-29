from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


DEFAULT_ENABLED_CONVERTERS = ["docling"]
DEFAULT_ALLOWED_SUFFIXES = [".txt", ".doc", ".docx", ".pdf"]
DEFAULT_ENABLED_DETECTORS = ["metadata", "clause_header", "definition", "reference"]


class ParserConfig(BaseModel):
    default_converter: str = "docling"
    enabled_converters: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy())
    fallback_order: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy())
    allow_converter_fallback: bool = True
    strict_converter_availability: bool = False

    allowed_suffixes: list[str] = Field(default_factory=lambda: DEFAULT_ALLOWED_SUFFIXES.copy())
    allow_path_input: bool = False
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
    docling_enabled: bool = True
    docling_enable_ocr: bool = True
    docling_ocr_lang: list[str] = Field(default_factory=lambda: ["chinese"])
    docling_force_full_page_ocr: bool = True
    docling_bitmap_area_threshold: float = 0.02
    docling_text_score: float = 0.35
    docling_do_table_structure: bool = True
    docling_compact_tables: bool = True
    docling_enable_remote_services: bool = False

    @model_validator(mode="after")
    def _validate_converter_settings(self) -> "ParserConfig":
        self.default_converter = str(self.default_converter).strip()
        self.enabled_converters = _dedupe_non_empty(self.enabled_converters)
        self.fallback_order = _dedupe_non_empty(self.fallback_order)
        self.enabled_detectors = _dedupe_non_empty(self.enabled_detectors)
        self.allowed_suffixes = _dedupe_non_empty(
            [_normalize_suffix(suffix) for suffix in self.allowed_suffixes]
        )
        self.docling_ocr_lang = _dedupe_non_empty(self.docling_ocr_lang)
        self.trusted_path_roots = [root for root in self.trusted_path_roots if root]
        if self.detector_rules_path == "":
            self.detector_rules_path = None
        if not self.default_converter:
            raise ValueError("parser.default_converter must be non-empty")
        if self.default_converter not in self.enabled_converters:
            raise ValueError("parser.default_converter must be present in enabled_converters")
        if not self.fallback_order:
            raise ValueError("parser.fallback_order must be non-empty")
        if not self.allowed_suffixes:
            raise ValueError("parser.allowed_suffixes must contain at least one valid suffix")
        if self.default_converter not in self.fallback_order:
            raise ValueError("parser.default_converter must be present in fallback_order")
        if self.fallback_order[0] != self.default_converter:
            raise ValueError("parser.fallback_order must start with parser.default_converter")
        missing_enabled = [
            converter
            for converter in self.fallback_order
            if converter not in self.enabled_converters
        ]
        if missing_enabled:
            raise ValueError(
                "parser.fallback_order converters must be present in enabled_converters: "
                + ", ".join(missing_enabled)
            )
        if "markitdown" in self.enabled_converters and not self.markitdown_enabled:
            raise ValueError(
                "parser.markitdown_enabled must be true when markitdown converter is enabled"
            )
        if "docling" in self.enabled_converters and not self.docling_enabled:
            raise ValueError(
                "parser.docling_enabled must be true when docling converter is enabled"
            )
        if self.chunk_max_chars <= 0 or self.chunk_target_chars <= 0:
            raise ValueError("parser chunk sizes must be positive")
        if self.chunk_target_chars > self.chunk_max_chars:
            raise ValueError(
                "parser.chunk_target_chars must be less than or equal to chunk_max_chars"
            )
        if self.max_input_bytes is not None and self.max_input_bytes <= 0:
            raise ValueError("parser.max_input_bytes must be positive when set")
        if not 0 <= self.min_detector_confidence <= 1:
            raise ValueError("parser.min_detector_confidence must be between 0 and 1")
        if not 0 <= self.min_header_confidence <= 1:
            raise ValueError("parser.min_header_confidence must be between 0 and 1")
        if self.allow_url_input:
            raise ValueError("parser.allow_url_input is reserved until URL input is implemented")
        if self.allow_path_input and not self.trusted_path_roots:
            raise ValueError(
                "parser.trusted_path_roots must be non-empty when path input is enabled"
            )
        if self.docling_enable_ocr and not self.docling_ocr_lang:
            raise ValueError("parser.docling_ocr_lang must be non-empty when OCR is enabled")
        if not 0 <= self.docling_bitmap_area_threshold <= 1:
            raise ValueError("parser.docling_bitmap_area_threshold must be between 0 and 1")
        if not 0 <= self.docling_text_score <= 1:
            raise ValueError("parser.docling_text_score must be between 0 and 1")
        if self.docling_enable_remote_services:
            raise ValueError(
                "parser.docling_enable_remote_services is reserved until remote Docling services are explicitly supported"
            )
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
            docling_ocr_lang=list(settings.parser_docling_ocr_lang),
            docling_force_full_page_ocr=settings.parser_docling_force_full_page_ocr,
            docling_bitmap_area_threshold=settings.parser_docling_bitmap_area_threshold,
            docling_text_score=settings.parser_docling_text_score,
            docling_do_table_structure=settings.parser_docling_do_table_structure,
            docling_compact_tables=settings.parser_docling_compact_tables,
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
