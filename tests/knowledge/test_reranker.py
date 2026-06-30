import unittest

from contract_agent.knowledge.rag.rerank.factory import RerankerFactory
from contract_agent.knowledge.rag.rerank.impl.qwen import QwenReranker
from contract_agent.config import ModelEndpointConfig, ModelRole, Settings


class RerankerConfigTests(unittest.TestCase):
    def test_reranker_uses_dedicated_rerank_api_key(self):
        runtime_settings = Settings(
            qwen_api_key="chat-key",
            rerank_api_key=None,
            rerank_endpoint="http://127.0.0.1:9/reranks",
        )

        reranker = QwenReranker(runtime_settings=runtime_settings)

        with self.assertRaisesRegex(RuntimeError, "RERANK_API_KEY"):
            reranker._request({"model": "rerank", "query": "q", "documents": ["d"], "top_n": 1})

    def test_reranker_builds_endpoint_from_dedicated_base_url(self):
        runtime_settings = Settings(
            rerank_base_url="https://rerank.example.test/v1",
            rerank_endpoint=None,
        )

        reranker = QwenReranker(runtime_settings=runtime_settings)

        self.assertEqual(reranker.endpoint, "https://rerank.example.test/v1/reranks")

    def test_reranker_keeps_full_rerank_endpoint_idempotent(self):
        runtime_settings = Settings(
            rerank_base_url="https://rerank.example.test/v1/reranks/",
            rerank_endpoint=None,
        )

        reranker = QwenReranker(runtime_settings=runtime_settings)

        self.assertEqual(reranker.endpoint, "https://rerank.example.test/v1/reranks")

    def test_reranker_normalizes_full_compatible_mode_rerank_endpoint(self):
        runtime_settings = Settings(
            rerank_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1/reranks/",
            rerank_endpoint=None,
        )

        reranker = QwenReranker(runtime_settings=runtime_settings)

        self.assertEqual(
            reranker.endpoint,
            "https://dashscope.aliyuncs.com/compatible-api/v1/reranks",
        )

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
