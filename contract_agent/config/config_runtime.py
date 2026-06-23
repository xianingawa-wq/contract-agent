from pathlib import Path
from collections.abc import Mapping
from contextlib import contextmanager
from threading import RLock
from typing import Iterator

from pydantic import BaseModel, Field

from contract_agent.config.config_parser import (
    DEFAULT_ALLOWED_SUFFIXES,
    DEFAULT_ENABLED_CONVERTERS,
    DEFAULT_ENABLED_DETECTORS,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
_settings_lock = RLock()


def settings_to_dict(value: BaseModel) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


def _env(environ: Mapping[str, str], name: str, default: str | None = None) -> str | None:
    value = environ.get(name)
    if value is None:
        return default
    return value


def _first_env(environ: Mapping[str, str], *names: str, default: str | None = None) -> str | None:
    for name in names:
        value = environ.get(name)
        if value:
            return value
    return default


def _bool_value(value: str | None, default: str) -> bool:
    return (value or default).strip().lower() in {"1", "true", "yes", "on"}


def _int_value(value: str | None, default: str) -> int:
    return int(value or default)


def _float_value(value: str | None, default: str) -> float:
    return float(value or default)


def _csv_list_value(value: str | None, default: list[str]) -> list[str]:
    if value is None or value.strip() == "":
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _optional_int_value(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


class Settings(BaseModel):
    app_name: str = "Contract Review Agent"
    default_contract_type: str = "采购合同"

    llm_provider: str = "openai_compatible"
    llm_api_key: str | None = None
    llm_base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_chat_model: str = "qwen-max"
    llm_embedding_model: str = "text-embedding-v4"
    llm_temperature: float = 0
    llm_use_responses_api: bool = True
    embedding_batch_size: int = 10

    chat_provider: str = "openai_compatible"
    chat_api_key: str | None = None
    chat_base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_model: str = "qwen-max"

    embedding_provider: str = "openai_compatible"
    embedding_api_key: str | None = None
    embedding_base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"

    # Backward-compatible aliases for extracted modules that still use Qwen names.
    qwen_api_key: str | None = None
    qwen_base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    langchain_model: str = "qwen-max"
    langchain_embedding_model: str = "text-embedding-v4"

    vector_backend: str = "milvus"
    knowledge_vector_store_dir: str = str(PROJECT_ROOT / "knowledge" / "ingested" / "laws_faiss")
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_collection_name: str = "legal_knowledge_chunks"
    milvus_consistency_level: str = "Session"
    retrieval_enable_rerank: bool = True
    rerank_provider: str = "qwen"
    rerank_api_key: str | None = None
    rerank_base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    rerank_model: str = "qwen3-rerank"
    rerank_endpoint: str | None = None
    retrieval_fetch_k: int = 12
    retrieval_final_k: int = 4
    retrieval_enable_hybrid: bool = True
    retrieval_dense_pool_k: int = 36
    rerank_timeout_seconds: int = 8
    rerank_max_retries: int = 0
    react_max_steps: int = 3
    postgres_dsn: str | None = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/contract_agent"
    )
    max_upload_size_bytes: int = 5 * 1024 * 1024
    max_redraft_chunk_chars: int = 12000
    stream_max_seconds: float = 24.0
    stream_max_chars: int = 900

    parser_default_converter: str = "builtin"
    parser_enabled_converters: list[str] = Field(
        default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy()
    )
    parser_fallback_order: list[str] = Field(
        default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy()
    )
    parser_allow_converter_fallback: bool = True
    parser_strict_converter_availability: bool = False
    parser_allowed_suffixes: list[str] = Field(
        default_factory=lambda: DEFAULT_ALLOWED_SUFFIXES.copy()
    )
    parser_allow_path_input: bool = True
    parser_allow_url_input: bool = False
    parser_trusted_path_roots: list[str] = Field(default_factory=list)
    parser_max_input_bytes: int | None = None
    parser_preserve_raw_text: bool = True
    parser_detector_profile: str = "builtin_zh_contract_v1"
    parser_enabled_detectors: list[str] = Field(
        default_factory=lambda: DEFAULT_ENABLED_DETECTORS.copy()
    )
    parser_detector_rules_path: str | None = None
    parser_min_detector_confidence: float = 0.60
    parser_store_detector_reasons: bool = True
    parser_chunk_max_chars: int = 1200
    parser_chunk_target_chars: int = 500
    parser_min_header_confidence: float = 0.65
    parser_markitdown_enabled: bool = False
    parser_docling_enabled: bool = False
    parser_docling_enable_ocr: bool = False
    parser_docling_enable_remote_services: bool = False


def load_settings_from_env(environ: Mapping[str, str] | None = None) -> Settings:
    import os

    env = environ or os.environ

    llm_provider = _env(env, "LLM_PROVIDER", "openai_compatible") or "openai_compatible"
    llm_api_key = _first_env(env, "LLM_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY")
    llm_base_url = _first_env(
        env,
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "QWEN_BASE_URL",
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    llm_chat_model = (
        _first_env(
            env, "LLM_CHAT_MODEL", "OPENAI_CHAT_MODEL", "QWEN_CHAT_MODEL", default="qwen-max"
        )
        or "qwen-max"
    )
    llm_embedding_model = (
        _first_env(
            env,
            "LLM_EMBEDDING_MODEL",
            "OPENAI_EMBEDDING_MODEL",
            "QWEN_EMBEDDING_MODEL",
            default="text-embedding-v4",
        )
        or "text-embedding-v4"
    )

    chat_provider = _env(env, "CHAT_PROVIDER") or llm_provider
    chat_api_key = _env(env, "CHAT_API_KEY") or llm_api_key
    chat_base_url = _env(env, "CHAT_BASE_URL") or llm_base_url
    chat_model = _env(env, "CHAT_MODEL") or llm_chat_model

    embedding_provider = _env(env, "EMBEDDING_PROVIDER") or llm_provider
    embedding_api_key = _env(env, "EMBEDDING_API_KEY") or llm_api_key
    embedding_base_url = _env(env, "EMBEDDING_BASE_URL") or llm_base_url
    embedding_model = _env(env, "EMBEDDING_MODEL") or llm_embedding_model

    rerank_api_key = _env(env, "RERANK_API_KEY") or chat_api_key
    rerank_base_url = _env(env, "RERANK_BASE_URL") or chat_base_url

    return Settings(
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_chat_model=llm_chat_model,
        llm_embedding_model=llm_embedding_model,
        llm_temperature=_float_value(_env(env, "LLM_TEMPERATURE"), "0"),
        llm_use_responses_api=_bool_value(_env(env, "LLM_USE_RESPONSES_API"), "true"),
        embedding_batch_size=_int_value(_env(env, "EMBEDDING_BATCH_SIZE"), "10"),
        chat_provider=chat_provider,
        chat_api_key=chat_api_key,
        chat_base_url=chat_base_url,
        chat_model=chat_model,
        embedding_provider=embedding_provider,
        embedding_api_key=embedding_api_key,
        embedding_base_url=embedding_base_url,
        embedding_model=embedding_model,
        qwen_api_key=chat_api_key,
        qwen_base_url=chat_base_url,
        langchain_model=chat_model,
        langchain_embedding_model=embedding_model,
        vector_backend=_env(env, "VECTOR_BACKEND", "milvus") or "milvus",
        knowledge_vector_store_dir=_env(
            env,
            "KNOWLEDGE_VECTOR_STORE_DIR",
            str(PROJECT_ROOT / "knowledge" / "ingested" / "laws_faiss"),
        )
        or str(PROJECT_ROOT / "knowledge" / "ingested" / "laws_faiss"),
        milvus_uri=_env(env, "MILVUS_URI", "http://127.0.0.1:19530") or "http://127.0.0.1:19530",
        milvus_collection_name=_env(env, "MILVUS_COLLECTION_NAME", "legal_knowledge_chunks")
        or "legal_knowledge_chunks",
        milvus_consistency_level=_env(env, "MILVUS_CONSISTENCY_LEVEL", "Session") or "Session",
        retrieval_enable_rerank=_bool_value(_env(env, "RETRIEVAL_ENABLE_RERANK"), "true"),
        rerank_provider=_env(env, "RERANK_PROVIDER", "qwen") or "qwen",
        rerank_api_key=rerank_api_key,
        rerank_base_url=rerank_base_url,
        rerank_model=_env(env, "RERANK_MODEL", "qwen3-rerank") or "qwen3-rerank",
        rerank_endpoint=_env(env, "RERANK_ENDPOINT"),
        retrieval_fetch_k=_int_value(_env(env, "RETRIEVAL_FETCH_K"), "12"),
        retrieval_final_k=_int_value(_env(env, "RETRIEVAL_FINAL_K"), "4"),
        retrieval_enable_hybrid=_bool_value(_env(env, "RETRIEVAL_ENABLE_HYBRID"), "true"),
        retrieval_dense_pool_k=_int_value(_env(env, "RETRIEVAL_DENSE_POOL_K"), "36"),
        rerank_timeout_seconds=_int_value(_env(env, "RERANK_TIMEOUT_SECONDS"), "8"),
        rerank_max_retries=_int_value(_env(env, "RERANK_MAX_RETRIES"), "0"),
        react_max_steps=_int_value(_env(env, "REACT_MAX_STEPS"), "3"),
        postgres_dsn=_env(
            env,
            "POSTGRES_DSN",
            "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/contract_agent",
        ),
        max_upload_size_bytes=_int_value(_env(env, "MAX_UPLOAD_SIZE_BYTES"), str(5 * 1024 * 1024)),
        max_redraft_chunk_chars=_int_value(_env(env, "MAX_REDRAFT_CHUNK_CHARS"), "12000"),
        stream_max_seconds=_float_value(_env(env, "STREAM_MAX_SECONDS"), "24.0"),
        stream_max_chars=_int_value(_env(env, "STREAM_MAX_CHARS"), "900"),
        parser_default_converter=_env(env, "PARSER_DEFAULT_CONVERTER", "builtin") or "builtin",
        parser_enabled_converters=_csv_list_value(
            _env(env, "PARSER_ENABLED_CONVERTERS"), DEFAULT_ENABLED_CONVERTERS
        ),
        parser_fallback_order=_csv_list_value(
            _env(env, "PARSER_FALLBACK_ORDER"), DEFAULT_ENABLED_CONVERTERS
        ),
        parser_allow_converter_fallback=_bool_value(
            _env(env, "PARSER_ALLOW_CONVERTER_FALLBACK"), "true"
        ),
        parser_strict_converter_availability=_bool_value(
            _env(env, "PARSER_STRICT_CONVERTER_AVAILABILITY"), "false"
        ),
        parser_allowed_suffixes=_csv_list_value(
            _env(env, "PARSER_ALLOWED_SUFFIXES"), DEFAULT_ALLOWED_SUFFIXES
        ),
        parser_allow_path_input=_bool_value(_env(env, "PARSER_ALLOW_PATH_INPUT"), "true"),
        parser_allow_url_input=_bool_value(_env(env, "PARSER_ALLOW_URL_INPUT"), "false"),
        parser_trusted_path_roots=_csv_list_value(_env(env, "PARSER_TRUSTED_PATH_ROOTS"), []),
        parser_max_input_bytes=_optional_int_value(_env(env, "PARSER_MAX_INPUT_BYTES")),
        parser_preserve_raw_text=_bool_value(_env(env, "PARSER_PRESERVE_RAW_TEXT"), "true"),
        parser_detector_profile=_env(env, "PARSER_DETECTOR_PROFILE", "builtin_zh_contract_v1")
        or "builtin_zh_contract_v1",
        parser_enabled_detectors=_csv_list_value(
            _env(env, "PARSER_ENABLED_DETECTORS"), DEFAULT_ENABLED_DETECTORS
        ),
        parser_detector_rules_path=_env(env, "PARSER_DETECTOR_RULES_PATH"),
        parser_min_detector_confidence=_float_value(
            _env(env, "PARSER_MIN_DETECTOR_CONFIDENCE"), "0.60"
        ),
        parser_store_detector_reasons=_bool_value(
            _env(env, "PARSER_STORE_DETECTOR_REASONS"), "true"
        ),
        parser_chunk_max_chars=_int_value(_env(env, "PARSER_CHUNK_MAX_CHARS"), "1200"),
        parser_chunk_target_chars=_int_value(_env(env, "PARSER_CHUNK_TARGET_CHARS"), "500"),
        parser_min_header_confidence=_float_value(
            _env(env, "PARSER_MIN_HEADER_CONFIDENCE"), "0.65"
        ),
        parser_markitdown_enabled=_bool_value(_env(env, "PARSER_MARKITDOWN_ENABLED"), "false"),
        parser_docling_enabled=_bool_value(_env(env, "PARSER_DOCLING_ENABLED"), "false"),
        parser_docling_enable_ocr=_bool_value(_env(env, "PARSER_DOCLING_ENABLE_OCR"), "false"),
        parser_docling_enable_remote_services=_bool_value(
            _env(env, "PARSER_DOCLING_ENABLE_REMOTE_SERVICES"), "false"
        ),
    )


if not hasattr(Settings, "model_dump"):

    def _settings_model_dump(self: Settings, *args, **kwargs) -> dict[str, object]:
        return self.dict(*args, **kwargs)

    Settings.model_dump = _settings_model_dump  # type: ignore[attr-defined]


if not hasattr(Settings, "model_validate"):

    @classmethod
    def _settings_model_validate(cls, value: object) -> Settings:
        if isinstance(value, cls):
            return cls(**value.model_dump())
        if isinstance(value, Mapping):
            return cls(**value)
        raise TypeError(f"Cannot validate Settings from {type(value)!r}")

    Settings.model_validate = _settings_model_validate  # type: ignore[attr-defined]


settings = load_settings_from_env()


def refresh_settings_from_env(environ: Mapping[str, str] | None = None) -> Settings:
    next_settings = load_settings_from_env(environ)
    update_settings(settings_to_dict(next_settings))
    return settings


def settings_snapshot() -> Settings:
    with _settings_lock:
        return Settings(**settings_to_dict(settings))


def update_settings(values: Mapping[str, object]) -> None:
    with _settings_lock:
        for key, value in values.items():
            setattr(settings, key, value)


@contextmanager
def temporary_settings(**overrides: object) -> Iterator[Settings]:
    original = settings_snapshot()
    try:
        update_settings({**settings_to_dict(original), **overrides})
        yield settings
    finally:
        update_settings(settings_to_dict(original))
