from __future__ import annotations

import logging
from typing import Any

from contract_agent.config import Settings, settings_snapshot

logger = logging.getLogger(__name__)


class ColdLayer:
    """Milvus-backed cold layer: historical data for semantic retrieval."""

    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.settings = runtime_settings or settings_snapshot()

    def is_available(self) -> bool:
        try:
            from contract_agent.knowledge.rag.vector_store import is_knowledge_base_ready
            return is_knowledge_base_ready(self.settings.knowledge_vector_store_dir, runtime_settings=self.settings)
        except Exception:
            return False

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        if not self.is_available():
            return []
        try:
            from contract_agent.knowledge.rag.vector_store import load_vector_store
            from contract_agent.knowledge.rag.retriever import ContractKnowledgeRetriever
            store = load_vector_store(self.settings.knowledge_vector_store_dir, runtime_settings=self.settings)
            retriever = ContractKnowledgeRetriever(store)
            docs = retriever.retrieve_documents(query=query, k=top_k)
            return [
                {
                    "content": doc.page_content[:300],
                    "source": doc.metadata.get("title", "未知"),
                    "score": doc.metadata.get("score", 0),
                }
                for doc in docs
            ]
        except Exception as exc:
            logger.warning("Cold layer search failed: %s", exc)
            return []
