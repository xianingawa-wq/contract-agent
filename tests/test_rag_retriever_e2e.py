import unittest
import json
import tempfile
from pathlib import Path

from langchain_core.documents import Document

from contract_agent.knowledge.rag.config import RetrievalConfig
from contract_agent.knowledge.rag.retriever import ContractKnowledgeRetriever
from contract_agent.logger.audit import AuditLogger


class FakeVectorStore:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.calls: list[tuple[str, int]] = []

    def similarity_search(self, query: str, k: int = 3) -> list[Document]:
        self.calls.append((query, k))
        return self.documents[:k]


class FakeReranker:
    def __init__(self) -> None:
        self.calls = []
        self.last_profile = {"request_seconds": 0.01, "network_seconds": 0.002}

    def rerank(self, query: str, documents: list[Document], top_k: int) -> list[Document]:
        self.calls.append((query, len(documents), top_k))
        return list(reversed(documents[:top_k]))


class RagRetrieverE2ETests(unittest.TestCase):
    def test_dense_retrieval_then_rerank_returns_ranked_documents_and_meta(self):
        docs = [
            Document(page_content="付款 验收 后 支付", metadata={"article_label": "A"}),
            Document(page_content="违约 责任 赔偿", metadata={"article_label": "B"}),
            Document(page_content="争议 解决 管辖", metadata={"article_label": "C"}),
        ]
        vector_store = FakeVectorStore(docs)
        reranker = FakeReranker()
        retriever = ContractKnowledgeRetriever(
            vector_store,
            reranker=reranker,
            retrieval_config=RetrievalConfig(
                enable_rerank=True,
                enable_hybrid=False,
                fetch_k=3,
                final_k=2,
                dense_pool_k=3,
            ),
        )

        ranked = retriever.retrieve_documents_with_rerank("付款风险")

        self.assertEqual([doc.metadata["article_label"] for doc in ranked], ["B", "A"])
        self.assertEqual(vector_store.calls, [("付款风险", 3)])
        self.assertEqual(reranker.calls, [("付款风险", 3, 2)])
        self.assertEqual(retriever.last_rerank_meta["success"], True)
        self.assertEqual(retriever.last_rerank_meta["candidate_pool_size"], 3)

    def test_retrieval_writes_trace_spans_when_logger_is_injected(self):
        docs = [
            Document(page_content="付款 验收 后 支付", metadata={"article_label": "A"}),
            Document(page_content="违约 责任 赔偿", metadata={"article_label": "B"}),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(Path(tmp) / "trace.jsonl")
            retriever = ContractKnowledgeRetriever(
                FakeVectorStore(docs),
                reranker=FakeReranker(),
                retrieval_config=RetrievalConfig(
                    enable_rerank=True,
                    enable_hybrid=False,
                    fetch_k=2,
                    final_k=1,
                    dense_pool_k=2,
                ),
                audit_logger=logger,
            )
            with logger.trace("test.rag"):
                retriever.retrieve_documents_with_rerank("付款风险")

            records = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()]

        span_names = {record.get("span_name") for record in records if record["event"] == "span.completed"}
        self.assertIn("rag.retrieve", span_names)
        self.assertIn("rag.rerank", span_names)
        self.assertEqual(len({record.get("trace_id") for record in records}), 1)
        self.assertIn("[Knowledge][RAG]", {record.get("prefix") for record in records})


if __name__ == "__main__":
    unittest.main()
