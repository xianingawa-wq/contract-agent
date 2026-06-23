from __future__ import annotations

from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole
from contract_agent.config import Settings, settings


class EnvironmentEmbeddingConfigSource:
    def __init__(self, runtime_settings: Settings = settings) -> None:
        self.settings = runtime_settings

    def load(self) -> ModelEndpointConfig:
        return ModelEndpointConfig(
            role=ModelRole.EMBEDDING,
            provider=self.settings.embedding_provider,
            base_url=self.settings.embedding_base_url or "",
            api_key=self.settings.embedding_api_key or "",
            model=self.settings.embedding_model,
        )
