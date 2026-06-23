import unittest

from contract_agent.knowledge.rag.rerank.impl.qwen_endpoint import build_qwen_rerank_endpoint
from contract_agent.knowledge.rag.rerank.impl.qwen_response_parser import parse_qwen_rerank_results
from contract_agent.knowledge.rag.rerank.impl.qwen_transport import QwenRerankTransport
from contract_agent.model_config.impl.env_chat_source import EnvironmentChatConfigSource
from contract_agent.model_config.impl.env_embedding_source import EnvironmentEmbeddingConfigSource
from contract_agent.model_config.impl.env_rerank_source import EnvironmentRerankConfigSource
from contract_agent.model_config.interface import ModelRole
from contract_agent.provider.impl.dashscope.provider import DashScopeProvider
from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings
from contract_agent.provider.impl.openai.provider import OpenAIProvider


class PackageBoundaryTests(unittest.TestCase):
    def test_environment_config_sources_are_split_by_model_role(self):
        self.assertEqual(EnvironmentChatConfigSource().load().role, ModelRole.CHAT)
        self.assertEqual(EnvironmentEmbeddingConfigSource().load().role, ModelRole.EMBEDDING)
        self.assertEqual(EnvironmentRerankConfigSource().load().role, ModelRole.RERANK)

    def test_provider_implementations_are_grouped_by_vendor_package(self):
        self.assertEqual(OpenAIProvider.__module__, "contract_agent.provider.impl.openai.provider")
        self.assertEqual(OpenAIEmbeddings.__module__, "contract_agent.provider.impl.openai.embeddings")
        self.assertEqual(DashScopeProvider.__module__, "contract_agent.provider.impl.dashscope.provider")

    def test_qwen_rerank_helpers_are_separate_from_transport_class(self):
        endpoint = build_qwen_rerank_endpoint("https://dashscope.aliyuncs.com/compatible-mode/v1")
        results = parse_qwen_rerank_results({"results": [{"index": 0, "relevance_score": 0.9}]})

        self.assertEqual(endpoint, "https://dashscope.aliyuncs.com/compatible-api/v1/reranks")
        self.assertEqual(results[0].index, 0)
        self.assertEqual(results[0].score, 0.9)
        self.assertEqual(QwenRerankTransport.__module__, "contract_agent.knowledge.rag.rerank.impl.qwen_transport")


if __name__ == "__main__":
    unittest.main()
