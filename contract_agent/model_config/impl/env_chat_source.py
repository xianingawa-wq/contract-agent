from __future__ import annotations

from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole
from contract_agent.runtime.config import Settings, settings


class EnvironmentChatConfigSource:
    def __init__(self, runtime_settings: Settings = settings) -> None:
        self.settings = runtime_settings

    def load(self) -> ModelEndpointConfig:
        return ModelEndpointConfig(
            role=ModelRole.CHAT,
            provider=self.settings.chat_provider,
            base_url=self.settings.chat_base_url or "",
            api_key=self.settings.chat_api_key or "",
            model=self.settings.chat_model,
        )
