from __future__ import annotations

from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole
from contract_agent.runtime.config import settings


class EnvironmentRerankConfigSource:
    def load(self) -> ModelEndpointConfig:
        return ModelEndpointConfig(
            role=ModelRole.RERANK,
            provider=settings.rerank_provider,
            base_url=settings.rerank_base_url or settings.rerank_endpoint or "",
            api_key=settings.rerank_api_key or "",
            model=settings.rerank_model,
        )
