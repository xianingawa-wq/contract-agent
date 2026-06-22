from __future__ import annotations

from collections.abc import Callable

from contract_agent.model_config.impl.env_source import EnvironmentModelConfigSource
from contract_agent.model_config.interface import ModelConfigSource
from contract_agent.provider.interface import LLMConfig, LLMProvider
from contract_agent.provider.service import ModelProviderService


ProviderBuilder = Callable[[LLMConfig], LLMProvider]


class ModelProviderFactory:
    def __init__(self) -> None:
        self._builders: dict[str, ProviderBuilder] = {}
        from contract_agent.provider.impl.dashscope.provider import DashScopeProvider
        from contract_agent.provider.impl.openai.provider import OpenAIProvider

        self.register("openai", OpenAIProvider)
        self.register("openai_compatible", OpenAIProvider)
        self.register("qwen", DashScopeProvider)
        self.register("dashscope", DashScopeProvider)

    def register(self, provider_name: str, builder: ProviderBuilder) -> None:
        self._builders[provider_name.strip().lower()] = builder

    def create(self, config: LLMConfig) -> LLMProvider:
        provider_name = config.provider.strip().lower()
        try:
            builder = self._builders[provider_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported model provider: {config.provider}") from exc
        return builder(config)


def create_model_provider_service(config_source: ModelConfigSource | None = None) -> ModelProviderService:
    return ModelProviderService(config_source or EnvironmentModelConfigSource(), ModelProviderFactory())
