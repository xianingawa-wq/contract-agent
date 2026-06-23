from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from contract_agent.config.config_runtime import PROJECT_ROOT


DEFAULT_MODEL_PROFILE_PATH = PROJECT_ROOT / ".run" / "cli_profile.yaml"


class ModelRole(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"


@dataclass(frozen=True)
class ModelEndpointConfig:
    role: ModelRole
    provider: str
    base_url: str
    api_key: str
    model: str
    endpoint: str | None = None

    @property
    def api_key_configured(self) -> bool:
        return bool(self.api_key.strip())

    def with_role(self, role: ModelRole) -> "ModelEndpointConfig":
        return ModelEndpointConfig(
            role=role,
            provider=self.provider,
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            endpoint=self.endpoint,
        )


@dataclass(frozen=True)
class ModelRuntimeConfig:
    chat: ModelEndpointConfig
    embedding: ModelEndpointConfig
    rerank: ModelEndpointConfig

    def endpoint_for(self, role: ModelRole) -> ModelEndpointConfig:
        if role == ModelRole.CHAT:
            return self.chat
        if role == ModelRole.EMBEDDING:
            return self.embedding
        if role == ModelRole.RERANK:
            return self.rerank
        raise ValueError(f"Unsupported model role: {role}")


@dataclass(frozen=True)
class ModelProviderOption:
    key: str
    label: str
    provider: str
    base_url: str


DEFAULT_PROVIDER_OPTIONS = (
    ModelProviderOption("1", "OpenAI", "openai", "https://api.openai.com/v1"),
    ModelProviderOption(
        "2", "DashScope / Qwen", "qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ),
    ModelProviderOption("3", "Custom OpenAI-compatible URL", "openai_compatible", ""),
)


class ModelConfigSource(Protocol):
    def load(self) -> ModelRuntimeConfig: ...


class ModelProfileStore(Protocol):
    path: Path

    def exists(self) -> bool: ...

    def load(self) -> ModelRuntimeConfig: ...

    def save(self, config: ModelRuntimeConfig) -> None: ...
