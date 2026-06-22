from __future__ import annotations

from dataclasses import dataclass

from contract_agent.model_config.interface import ModelConfigSource, ModelEndpointConfig, ModelProfileStore, ModelRuntimeConfig
from contract_agent.runtime.config import settings


class ModelConfigResolver:
    def __init__(self, environment_source: ModelConfigSource, profile_store: ModelProfileStore) -> None:
        self.environment_source = environment_source
        self.profile_store = profile_store

    def resolve(self) -> ModelRuntimeConfig:
        if self.profile_store.exists():
            return self.profile_store.load()
        return self.environment_source.load()


class ModelProfileService:
    def __init__(self, resolver: ModelConfigResolver, profile_store: ModelProfileStore) -> None:
        self.resolver = resolver
        self.profile_store = profile_store

    def has_profile(self) -> bool:
        return self.profile_store.exists()

    def load(self) -> ModelRuntimeConfig:
        return self.resolver.resolve()

    def save(self, config: ModelRuntimeConfig) -> None:
        self.profile_store.save(config)

    def apply_to_settings(self, config: ModelRuntimeConfig) -> None:
        apply_model_runtime_config(config)

    def public_summary(self) -> str:
        config = self.load()
        return "\n".join(
            [
                *_endpoint_summary_lines("chat", config.chat),
                *_endpoint_summary_lines("embedding", config.embedding),
                *_endpoint_summary_lines("rerank", config.rerank),
            ]
        )


def apply_model_runtime_config(config: ModelRuntimeConfig) -> None:
    settings.chat_provider = config.chat.provider
    settings.chat_base_url = config.chat.base_url
    settings.chat_api_key = config.chat.api_key or None
    settings.chat_model = config.chat.model
    settings.embedding_provider = config.embedding.provider
    settings.embedding_base_url = config.embedding.base_url
    settings.embedding_api_key = config.embedding.api_key or None
    settings.embedding_model = config.embedding.model
    settings.rerank_provider = config.rerank.provider
    settings.rerank_base_url = config.rerank.base_url
    settings.rerank_api_key = config.rerank.api_key or None
    settings.rerank_model = config.rerank.model
    settings.rerank_endpoint = rerank_endpoint_from_base_url(config.rerank.base_url)

    settings.llm_provider = config.chat.provider
    settings.llm_base_url = config.chat.base_url
    settings.llm_api_key = config.chat.api_key or None
    settings.llm_chat_model = config.chat.model
    settings.llm_embedding_model = config.embedding.model
    settings.qwen_api_key = config.chat.api_key or None
    settings.qwen_base_url = config.chat.base_url
    settings.langchain_model = config.chat.model
    settings.langchain_embedding_model = config.embedding.model


def rerank_endpoint_from_base_url(base_url: str) -> str | None:
    base = base_url.strip().rstrip("/")
    if not base:
        return None
    if base.endswith("/reranks"):
        return base
    if "/compatible-mode/" in base:
        return base.replace("/compatible-mode/", "/compatible-api/") + "/reranks"
    return f"{base}/reranks"


def _endpoint_summary_lines(prefix: str, endpoint: ModelEndpointConfig) -> list[str]:
    return [
        f"{prefix}.provider={endpoint.provider}",
        f"{prefix}.base_url={endpoint.base_url}",
        f"{prefix}.model={endpoint.model}",
        f"{prefix}.api_key_configured={endpoint.api_key_configured}",
    ]
