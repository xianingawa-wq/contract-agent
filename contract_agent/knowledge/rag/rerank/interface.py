from __future__ import annotations

from dataclasses import dataclass

from langchain_core.documents import Document


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


class Reranker:
    def rerank(self, query: str, documents: list[Document], top_k: int) -> list[Document]:
        raise NotImplementedError
