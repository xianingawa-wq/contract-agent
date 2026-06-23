from __future__ import annotations

from langchain_core.embeddings import Embeddings

from contract_agent.provider.impl.dashscope.embeddings import DashScopeEmbeddings
from contract_agent.provider.impl.openai.provider import OpenAIProvider


class DashScopeProvider(OpenAIProvider):
    """Provider for DashScope/Qwen OpenAI-compatible endpoints."""

    def embeddings(self) -> Embeddings:
        return DashScopeEmbeddings(self.config)
