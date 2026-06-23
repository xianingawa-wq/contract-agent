from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from contract_agent.config.config_app import AppConfig, AppContext
from contract_agent.config.config_runtime import (
    PROJECT_ROOT,
    load_settings_from_env,
    settings_to_dict,
    update_settings,
)


DEFAULT_APP_CONFIG_PATH = PROJECT_ROOT / ".run" / "config.yaml"


def load_app_config(
    path: Path | str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> AppConfig:
    config = AppConfig()
    config_path = Path(path) if path is not None else DEFAULT_APP_CONFIG_PATH
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(raw, Mapping):
            config = AppConfig.model_validate(_deep_merge(config.model_dump(), dict(raw)))
    config = _apply_environment_overlay(config, environ if environ is not None else os.environ)
    config = _apply_profile_overlay(config)
    return config


def configure_runtime(
    config: AppConfig | None = None,
    *,
    config_path: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppContext:
    app_config = config or load_app_config(config_path, environ=environ)
    runtime_settings = app_config.to_settings()
    update_settings(settings_to_dict(runtime_settings))
    return AppContext(
        config=app_config,
        settings=runtime_settings,
        model_config=app_config.to_model_runtime_config(),
        retrieval_config=app_config.to_retrieval_config(),
        multiagent_config=app_config.to_multiagent_config(),
    )


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = base.copy()
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], dict(value))
        else:
            result[key] = value
    return result


def _apply_environment_overlay(config: AppConfig, environ: Mapping[str, str]) -> AppConfig:
    if not environ:
        return config
    settings = load_settings_from_env(environ)
    data = config.model_dump()

    _copy_if_present(
        environ,
        data,
        ("models", "chat", "provider"),
        settings.chat_provider,
        "CHAT_PROVIDER",
        "LLM_PROVIDER",
    )
    _copy_if_present(
        environ,
        data,
        ("models", "chat", "api_key"),
        settings.chat_api_key,
        "CHAT_API_KEY",
        "LLM_API_KEY",
        "OPENAI_API_KEY",
        "QWEN_API_KEY",
    )
    _copy_if_present(
        environ,
        data,
        ("models", "chat", "base_url"),
        settings.chat_base_url,
        "CHAT_BASE_URL",
        "LLM_BASE_URL",
        "OPENAI_BASE_URL",
        "QWEN_BASE_URL",
    )
    _copy_if_present(
        environ,
        data,
        ("models", "chat", "model"),
        settings.chat_model,
        "CHAT_MODEL",
        "LLM_CHAT_MODEL",
        "OPENAI_CHAT_MODEL",
        "QWEN_CHAT_MODEL",
    )
    _copy_if_present(
        environ,
        data,
        ("models", "embedding", "provider"),
        settings.embedding_provider,
        "EMBEDDING_PROVIDER",
    )
    _copy_if_present(
        environ,
        data,
        ("models", "embedding", "api_key"),
        settings.embedding_api_key,
        "EMBEDDING_API_KEY",
    )
    _copy_if_present(
        environ,
        data,
        ("models", "embedding", "base_url"),
        settings.embedding_base_url,
        "EMBEDDING_BASE_URL",
    )
    _copy_if_present(
        environ,
        data,
        ("models", "embedding", "model"),
        settings.embedding_model,
        "EMBEDDING_MODEL",
        "LLM_EMBEDDING_MODEL",
        "OPENAI_EMBEDDING_MODEL",
        "QWEN_EMBEDDING_MODEL",
    )
    _copy_if_present(
        environ, data, ("models", "rerank", "provider"), settings.rerank_provider, "RERANK_PROVIDER"
    )
    _copy_if_present(
        environ, data, ("models", "rerank", "api_key"), settings.rerank_api_key, "RERANK_API_KEY"
    )
    _copy_if_present(
        environ, data, ("models", "rerank", "base_url"), settings.rerank_base_url, "RERANK_BASE_URL"
    )
    _copy_if_present(
        environ, data, ("models", "rerank", "model"), settings.rerank_model, "RERANK_MODEL"
    )
    _copy_if_present(
        environ, data, ("models", "rerank", "endpoint"), settings.rerank_endpoint, "RERANK_ENDPOINT"
    )
    _copy_if_present(
        environ, data, ("provider", "temperature"), settings.llm_temperature, "LLM_TEMPERATURE"
    )
    _copy_if_present(
        environ,
        data,
        ("provider", "use_responses_api"),
        settings.llm_use_responses_api,
        "LLM_USE_RESPONSES_API",
    )
    _copy_if_present(
        environ,
        data,
        ("provider", "embedding_batch_size"),
        settings.embedding_batch_size,
        "EMBEDDING_BATCH_SIZE",
    )
    _copy_if_present(
        environ, data, ("vector_store", "backend"), settings.vector_backend, "VECTOR_BACKEND"
    )
    _copy_if_present(
        environ,
        data,
        ("vector_store", "knowledge_vector_store_dir"),
        settings.knowledge_vector_store_dir,
        "KNOWLEDGE_VECTOR_STORE_DIR",
    )
    _copy_if_present(
        environ, data, ("vector_store", "milvus_uri"), settings.milvus_uri, "MILVUS_URI"
    )
    _copy_if_present(
        environ,
        data,
        ("vector_store", "milvus_collection_name"),
        settings.milvus_collection_name,
        "MILVUS_COLLECTION_NAME",
    )
    _copy_if_present(
        environ,
        data,
        ("vector_store", "milvus_consistency_level"),
        settings.milvus_consistency_level,
        "MILVUS_CONSISTENCY_LEVEL",
    )
    _copy_if_present(
        environ,
        data,
        ("retrieval", "enable_rerank"),
        settings.retrieval_enable_rerank,
        "RETRIEVAL_ENABLE_RERANK",
    )
    _copy_if_present(
        environ, data, ("retrieval", "fetch_k"), settings.retrieval_fetch_k, "RETRIEVAL_FETCH_K"
    )
    _copy_if_present(
        environ, data, ("retrieval", "final_k"), settings.retrieval_final_k, "RETRIEVAL_FINAL_K"
    )
    _copy_if_present(
        environ,
        data,
        ("retrieval", "enable_hybrid"),
        settings.retrieval_enable_hybrid,
        "RETRIEVAL_ENABLE_HYBRID",
    )
    _copy_if_present(
        environ,
        data,
        ("retrieval", "dense_pool_k"),
        settings.retrieval_dense_pool_k,
        "RETRIEVAL_DENSE_POOL_K",
    )
    _copy_if_present(
        environ,
        data,
        ("retrieval", "rerank_timeout_seconds"),
        settings.rerank_timeout_seconds,
        "RERANK_TIMEOUT_SECONDS",
    )
    _copy_if_present(
        environ,
        data,
        ("retrieval", "rerank_max_retries"),
        settings.rerank_max_retries,
        "RERANK_MAX_RETRIES",
    )
    _copy_if_present(
        environ, data, ("database", "postgres_dsn"), settings.postgres_dsn, "POSTGRES_DSN"
    )
    _copy_if_present(
        environ, data, ("limits", "react_max_steps"), settings.react_max_steps, "REACT_MAX_STEPS"
    )
    _copy_if_present(
        environ,
        data,
        ("limits", "max_upload_size_bytes"),
        settings.max_upload_size_bytes,
        "MAX_UPLOAD_SIZE_BYTES",
    )
    _copy_if_present(
        environ,
        data,
        ("limits", "max_redraft_chunk_chars"),
        settings.max_redraft_chunk_chars,
        "MAX_REDRAFT_CHUNK_CHARS",
    )
    _copy_if_present(
        environ,
        data,
        ("limits", "stream_max_seconds"),
        settings.stream_max_seconds,
        "STREAM_MAX_SECONDS",
    )
    _copy_if_present(
        environ, data, ("limits", "stream_max_chars"), settings.stream_max_chars, "STREAM_MAX_CHARS"
    )
    _copy_if_present(
        environ, data, ("multiagent", "redis_url"), environ.get("REDIS_URL"), "REDIS_URL"
    )
    _copy_if_present(
        environ, data, ("grpc", "port"), _int(environ.get("AGENT_GRPC_PORT")), "AGENT_GRPC_PORT"
    )
    return AppConfig.model_validate(data)


def _apply_profile_overlay(config: AppConfig) -> AppConfig:
    path = Path(config.profile.path)
    if not path.exists():
        return config
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, Mapping):
        return config
    model_overlay = {key: raw[key] for key in ("chat", "embedding", "rerank") if key in raw}
    if not model_overlay and isinstance(raw.get("models"), Mapping):
        model_overlay = dict(raw["models"])
    if not model_overlay:
        return config
    data = config.model_dump()
    data["models"] = _deep_merge(data["models"], model_overlay)
    return AppConfig.model_validate(data)


def _copy_if_present(
    environ: Mapping[str, str],
    data: dict[str, Any],
    path: tuple[str, ...],
    value: object,
    *names: str,
) -> None:
    if not any(name in environ and environ[name] != "" for name in names):
        return
    target = data
    for key in path[:-1]:
        target = target.setdefault(key, {})
    target[path[-1]] = value


def _int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
