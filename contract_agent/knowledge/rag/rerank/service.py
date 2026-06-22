from __future__ import annotations

from typing import Protocol

from contract_agent.knowledge.rag.rerank.interface import Reranker
from contract_agent.model_config.interface import ModelConfigSource, ModelEndpointConfig


class RerankerProviderFactory(Protocol):
    def create(self, endpoint: ModelEndpointConfig) -> Reranker:
        ...


class RerankerService:
    def __init__(self, config_source: ModelConfigSource, reranker_factory: RerankerProviderFactory) -> None:
        self.config_source = config_source
        self.reranker_factory = reranker_factory

    def create_reranker(self) -> Reranker:
        model_config = self.config_source.load()
        return self.reranker_factory.create(model_config.rerank)
