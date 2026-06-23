from __future__ import annotations

from contract_agent.model_config.impl.env_chat_source import EnvironmentChatConfigSource
from contract_agent.model_config.impl.env_embedding_source import EnvironmentEmbeddingConfigSource
from contract_agent.model_config.impl.env_rerank_source import EnvironmentRerankConfigSource
from contract_agent.model_config.interface import ModelRuntimeConfig
from contract_agent.runtime.config import Settings, settings_snapshot


class EnvironmentModelConfigSource:
    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.runtime_settings = runtime_settings

    def load(self) -> ModelRuntimeConfig:
        runtime_settings = self.runtime_settings or settings_snapshot()
        return ModelRuntimeConfig(
            chat=EnvironmentChatConfigSource(runtime_settings).load(),
            embedding=EnvironmentEmbeddingConfigSource(runtime_settings).load(),
            rerank=EnvironmentRerankConfigSource(runtime_settings).load(),
        )
