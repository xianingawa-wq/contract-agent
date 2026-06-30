from __future__ import annotations

from pathlib import Path

import yaml

from contract_agent.config.config_app import AppConfig
from contract_agent.config.config_model import (
    DEFAULT_MODEL_PROFILE_PATH,
    ModelConfigSource,
    ModelEndpointConfig,
    ModelProfileStore,
    ModelRole,
    ModelRuntimeConfig,
)
from contract_agent.config.config_runtime import Settings, settings_snapshot, update_settings


class ProfileLoadError(RuntimeError):
    """Raised when an existing CLI profile cannot be loaded safely."""


class EnvironmentChatConfigSource:
    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.runtime_settings = runtime_settings or settings_snapshot()

    def load(self) -> ModelEndpointConfig:
        runtime_settings = self.runtime_settings
        return ModelEndpointConfig(
            role=ModelRole.CHAT,
            provider=runtime_settings.chat_provider,
            base_url=runtime_settings.chat_base_url or "",
            api_key=runtime_settings.chat_api_key or "",
            model=runtime_settings.chat_model,
        )


class EnvironmentEmbeddingConfigSource:
    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.runtime_settings = runtime_settings or settings_snapshot()

    def load(self) -> ModelEndpointConfig:
        runtime_settings = self.runtime_settings
        return ModelEndpointConfig(
            role=ModelRole.EMBEDDING,
            provider=runtime_settings.embedding_provider,
            base_url=runtime_settings.embedding_base_url or "",
            api_key=runtime_settings.embedding_api_key or "",
            model=runtime_settings.embedding_model,
        )


class EnvironmentRerankConfigSource:
    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.runtime_settings = runtime_settings or settings_snapshot()

    def load(self) -> ModelEndpointConfig:
        runtime_settings = self.runtime_settings
        return ModelEndpointConfig(
            role=ModelRole.RERANK,
            provider=runtime_settings.rerank_provider,
            base_url=runtime_settings.rerank_base_url or runtime_settings.rerank_endpoint or "",
            api_key=runtime_settings.rerank_api_key or "",
            model=runtime_settings.rerank_model,
            endpoint=runtime_settings.rerank_endpoint,
        )


class EnvironmentModelConfigSource:
    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.runtime_settings = runtime_settings or settings_snapshot()

    def load(self) -> ModelRuntimeConfig:
        runtime_settings = self.runtime_settings
        return ModelRuntimeConfig(
            chat=EnvironmentChatConfigSource(runtime_settings).load(),
            embedding=EnvironmentEmbeddingConfigSource(runtime_settings).load(),
            rerank=EnvironmentRerankConfigSource(runtime_settings).load(),
        )


class AppModelConfigSource:
    def __init__(self, app_config: AppConfig) -> None:
        self.app_config = app_config

    def load(self) -> ModelRuntimeConfig:
        return self.app_config.to_model_runtime_config()


class StaticModelConfigSource:
    def __init__(self, model_config: ModelRuntimeConfig) -> None:
        self.model_config = model_config

    def load(self) -> ModelRuntimeConfig:
        return self.model_config


class YamlModelProfileCodec:
    def decode(self, raw: dict[str, object], fallback: ModelRuntimeConfig) -> ModelRuntimeConfig:
        if "models" in raw and isinstance(raw["models"], dict):
            raw = raw["models"]  # type: ignore[assignment]
        return ModelRuntimeConfig(
            chat=self._endpoint_from_yaml(raw.get(ModelRole.CHAT.value), fallback.chat),
            embedding=self._endpoint_from_yaml(
                raw.get(ModelRole.EMBEDDING.value), fallback.embedding
            ),
            rerank=self._endpoint_from_yaml(raw.get(ModelRole.RERANK.value), fallback.rerank),
        )

    def encode(self, config: ModelRuntimeConfig) -> dict[str, object]:
        return {
            ModelRole.CHAT.value: self._endpoint_to_yaml(config.chat),
            ModelRole.EMBEDDING.value: self._endpoint_to_yaml(config.embedding),
            ModelRole.RERANK.value: self._endpoint_to_yaml(config.rerank),
        }

    def _endpoint_from_yaml(
        self, raw: object, fallback: ModelEndpointConfig
    ) -> ModelEndpointConfig:
        if not isinstance(raw, dict):
            return fallback
        return ModelEndpointConfig(
            role=fallback.role,
            provider=str(raw.get("provider") or fallback.provider),
            base_url=str(raw.get("base_url") or fallback.base_url),
            api_key=str(raw.get("api_key") or fallback.api_key),
            model=str(raw.get("model") or fallback.model),
            endpoint=str(raw["endpoint"]) if raw.get("endpoint") else fallback.endpoint,
        )

    def _endpoint_to_yaml(self, endpoint: ModelEndpointConfig) -> dict[str, object]:
        data: dict[str, object] = {
            "provider": endpoint.provider,
            "base_url": endpoint.base_url,
            "api_key": endpoint.api_key,
            "model": endpoint.model,
        }
        if endpoint.endpoint:
            data["endpoint"] = endpoint.endpoint
        return data


class YamlModelProfileStore:
    def __init__(
        self,
        path: Path,
        *,
        fallback_source: ModelConfigSource | None = None,
    ) -> None:
        self.path = path
        self.codec = YamlModelProfileCodec()
        self.fallback_source = fallback_source or EnvironmentModelConfigSource()

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> ModelRuntimeConfig:
        fallback = self.fallback_source.load()
        if not self.path.exists():
            return fallback
        try:
            raw = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ProfileLoadError(f"CLI profile 配置文件不可读取：{self.path}：{exc}") from exc
        except yaml.YAMLError as exc:
            raise ProfileLoadError(f"CLI profile 配置文件 YAML 无效：{self.path}：{exc}") from exc
        if not isinstance(raw, dict):
            raise ProfileLoadError(f"CLI profile 配置文件必须是 YAML mapping：{self.path}")
        return self.codec.decode(raw, fallback)

    def save(self, config: ModelRuntimeConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(self.codec.encode(config), sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )


class ModelConfigResolver:
    def __init__(
        self, environment_source: ModelConfigSource, profile_store: ModelProfileStore
    ) -> None:
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


def create_model_config_resolver(
    profile_path: Path | None = None,
    app_config: AppConfig | None = None,
) -> ModelConfigResolver:
    source: ModelConfigSource = (
        AppModelConfigSource(app_config)
        if app_config is not None
        else EnvironmentModelConfigSource()
    )
    store = YamlModelProfileStore(
        profile_path or DEFAULT_MODEL_PROFILE_PATH, fallback_source=source
    )
    return ModelConfigResolver(source, store)


def create_model_profile_service(
    profile_path: Path | None = None,
    app_config: AppConfig | None = None,
) -> ModelProfileService:
    source: ModelConfigSource = (
        AppModelConfigSource(app_config)
        if app_config is not None
        else EnvironmentModelConfigSource()
    )
    store = YamlModelProfileStore(
        profile_path or DEFAULT_MODEL_PROFILE_PATH, fallback_source=source
    )
    resolver = ModelConfigResolver(source, store)
    return ModelProfileService(resolver, store)


def apply_model_runtime_config(config: ModelRuntimeConfig) -> None:
    update_settings(
        {
            "chat_provider": config.chat.provider,
            "chat_base_url": config.chat.base_url,
            "chat_api_key": config.chat.api_key or None,
            "chat_model": config.chat.model,
            "embedding_provider": config.embedding.provider,
            "embedding_base_url": config.embedding.base_url,
            "embedding_api_key": config.embedding.api_key or None,
            "embedding_model": config.embedding.model,
            "rerank_provider": config.rerank.provider,
            "rerank_base_url": config.rerank.base_url,
            "rerank_api_key": config.rerank.api_key or None,
            "rerank_model": config.rerank.model,
            "rerank_endpoint": config.rerank.endpoint
            or rerank_endpoint_from_base_url(config.rerank.base_url),
            "llm_provider": config.chat.provider,
            "llm_base_url": config.chat.base_url,
            "llm_api_key": config.chat.api_key or None,
            "llm_chat_model": config.chat.model,
            "llm_embedding_model": config.embedding.model,
            "qwen_api_key": config.chat.api_key or None,
            "qwen_base_url": config.chat.base_url,
            "langchain_model": config.chat.model,
            "langchain_embedding_model": config.embedding.model,
        }
    )


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
