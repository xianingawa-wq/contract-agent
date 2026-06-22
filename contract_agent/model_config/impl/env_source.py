from __future__ import annotations

from contract_agent.model_config.impl.env_chat_source import EnvironmentChatConfigSource
from contract_agent.model_config.impl.env_embedding_source import EnvironmentEmbeddingConfigSource
from contract_agent.model_config.impl.env_rerank_source import EnvironmentRerankConfigSource
from contract_agent.model_config.interface import ModelRuntimeConfig


class EnvironmentModelConfigSource:
    def load(self) -> ModelRuntimeConfig:
        return ModelRuntimeConfig(
            chat=EnvironmentChatConfigSource().load(),
            embedding=EnvironmentEmbeddingConfigSource().load(),
            rerank=EnvironmentRerankConfigSource().load(),
        )
