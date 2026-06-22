from __future__ import annotations

from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole
from contract_agent.runtime.config import settings


class EnvironmentChatConfigSource:
    def load(self) -> ModelEndpointConfig:
        return ModelEndpointConfig(
            role=ModelRole.CHAT,
            provider=settings.chat_provider,
            base_url=settings.chat_base_url or "",
            api_key=settings.chat_api_key or "",
            model=settings.chat_model,
        )
