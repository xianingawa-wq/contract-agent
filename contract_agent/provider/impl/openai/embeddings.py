from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from openai import OpenAI

from contract_agent.provider.interface import LLMConfig


class OpenAIEmbeddings(Embeddings):
    def __init__(self, config: LLMConfig) -> None:
        kwargs: dict[str, Any] = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)
        self.model = config.embedding_model
        self.chunk_size = 10

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.chunk_size):
            batch = [text if isinstance(text, str) else str(text) for text in texts[start : start + self.chunk_size]]
            response = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding
