from __future__ import annotations

from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole
from contract_agent.runtime.config import Settings, settings


class EnvironmentRerankConfigSource:
    def __init__(self, runtime_settings: Settings = settings) -> None:
        self.settings = runtime_settings

    def load(self) -> ModelEndpointConfig:
        return ModelEndpointConfig(
            role=ModelRole.RERANK,
            provider=self.settings.rerank_provider,
            base_url=self.settings.rerank_base_url or self.settings.rerank_endpoint or "",
            api_key=self.settings.rerank_api_key or "",
            model=self.settings.rerank_model,
        )
