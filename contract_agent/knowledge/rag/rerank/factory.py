from __future__ import annotations

from collections.abc import Callable

from contract_agent.knowledge.rag.rerank.impl.qwen import QwenReranker
from contract_agent.knowledge.rag.rerank.interface import Reranker
from contract_agent.knowledge.rag.rerank.service import RerankerService
from contract_agent.model_config.impl.env_source import EnvironmentModelConfigSource
from contract_agent.model_config.interface import ModelConfigSource, ModelEndpointConfig


RerankerBuilder = Callable[[ModelEndpointConfig], Reranker]


class RerankerFactory:
    def __init__(self) -> None:
        self._builders: dict[str, RerankerBuilder] = {}
        self.register("qwen", _create_qwen_reranker)
        self.register("dashscope", _create_qwen_reranker)
        self.register("openai_compatible", _create_qwen_reranker)

    def register(self, provider_name: str, builder: RerankerBuilder) -> None:
        self._builders[provider_name.strip().lower()] = builder

    def create(self, endpoint: ModelEndpointConfig) -> Reranker:
        provider_name = endpoint.provider.strip().lower()
        try:
            builder = self._builders[provider_name]
        except KeyError as exc:
            raise ValueError(f"Unsupported rerank provider: {endpoint.provider}") from exc
        return builder(endpoint)


def _create_qwen_reranker(endpoint: ModelEndpointConfig) -> QwenReranker:
    return QwenReranker(
        model=endpoint.model,
        api_key=endpoint.api_key,
        base_url=endpoint.base_url,
    )


def create_reranker_service(config_source: ModelConfigSource | None = None) -> RerankerService:
    return RerankerService(config_source or EnvironmentModelConfigSource(), RerankerFactory())
