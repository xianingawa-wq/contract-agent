import unittest

from contract_agent.knowledge.rag.rerank.factory import RerankerFactory
from contract_agent.knowledge.rag.rerank.impl.qwen import QwenReranker
from contract_agent.model_config.interface import ModelEndpointConfig, ModelRole
from contract_agent.runtime.config import settings


class RerankerConfigTests(unittest.TestCase):
    def test_reranker_uses_dedicated_rerank_api_key(self):
        original = settings.model_dump()
        try:
            settings.qwen_api_key = "chat-key"
            settings.rerank_api_key = None
            settings.rerank_endpoint = "http://127.0.0.1:9/reranks"

            reranker = QwenReranker()

            with self.assertRaisesRegex(RuntimeError, "RERANK_API_KEY"):
                reranker._request({"model": "rerank", "query": "q", "documents": ["d"], "top_n": 1})
        finally:
            for key, value in original.items():
                setattr(settings, key, value)

    def test_reranker_builds_endpoint_from_dedicated_base_url(self):
        original = settings.model_dump()
        try:
            settings.rerank_base_url = "https://rerank.example.test/v1"
            settings.rerank_endpoint = None

            reranker = QwenReranker()

            self.assertEqual(reranker.endpoint, "https://rerank.example.test/v1/reranks")
        finally:
            for key, value in original.items():
                setattr(settings, key, value)

    def test_reranker_factory_creates_qwen_reranker_from_endpoint_config(self):
        endpoint = ModelEndpointConfig(
            role=ModelRole.RERANK,
            provider="qwen",
            base_url="https://rerank.example.test/v1",
            api_key="rerank-key",
            model="rerank-model",
        )

        reranker = RerankerFactory().create(endpoint)

        self.assertIsInstance(reranker, QwenReranker)
        self.assertEqual(reranker.model, "rerank-model")
        self.assertEqual(reranker.endpoint, "https://rerank.example.test/v1/reranks")


if __name__ == "__main__":
    unittest.main()
