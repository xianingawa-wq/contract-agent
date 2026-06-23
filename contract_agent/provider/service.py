from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from contract_agent.model_config.interface import ModelConfigSource
from contract_agent.provider.interface import LLMConfig, LLMProvider
from contract_agent.runtime.config import Settings, settings_snapshot


@dataclass(frozen=True)
class ProviderRuntimeOptions:
    temperature: float
    use_responses_api: bool

    @classmethod
    def from_settings(cls, runtime_settings: Settings) -> "ProviderRuntimeOptions":
        return cls(
            temperature=runtime_settings.llm_temperature,
            use_responses_api=runtime_settings.llm_use_responses_api,
        )


class ProviderFactory(Protocol):
    def create(self, config: LLMConfig) -> LLMProvider:
        ...


class ModelProviderService:
    def __init__(
        self,
        config_source: ModelConfigSource,
        provider_factory: ProviderFactory,
        runtime_options: ProviderRuntimeOptions | None = None,
    ) -> None:
        self.config_source = config_source
        self.provider_factory = provider_factory
        self.runtime_options = runtime_options

    def create_chat_provider(self) -> LLMProvider:
        model_config = self.config_source.load()
        runtime_options = self.runtime_options or ProviderRuntimeOptions.from_settings(settings_snapshot())
        return self.provider_factory.create(
            LLMConfig(
                provider=model_config.chat.provider,
                api_key=model_config.chat.api_key,
                base_url=model_config.chat.base_url,
                chat_model=model_config.chat.model,
                embedding_model=model_config.embedding.model,
                temperature=runtime_options.temperature,
                use_responses_api=runtime_options.use_responses_api,
            )
        )

    def create_embedding_provider(self) -> LLMProvider:
        model_config = self.config_source.load()
        runtime_options = self.runtime_options or ProviderRuntimeOptions.from_settings(settings_snapshot())
        return self.provider_factory.create(
            LLMConfig(
                provider=model_config.embedding.provider,
                api_key=model_config.embedding.api_key,
                base_url=model_config.embedding.base_url,
                chat_model=model_config.chat.model,
                embedding_model=model_config.embedding.model,
                temperature=runtime_options.temperature,
                use_responses_api=runtime_options.use_responses_api,
            )
        )
