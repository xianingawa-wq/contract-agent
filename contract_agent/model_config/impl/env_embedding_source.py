from __future__ import annotations

from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole
from contract_agent.runtime.config import settings


class EnvironmentEmbeddingConfigSource:
    def load(self) -> ModelEndpointConfig:
        return ModelEndpointConfig(
            role=ModelRole.EMBEDDING,
            provider=settings.embedding_provider,
            base_url=settings.embedding_base_url or "",
            api_key=settings.embedding_api_key or "",
            model=settings.embedding_model,
        )
