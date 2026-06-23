import unittest
from pathlib import Path

from contract_agent.parser import ContractParser, ParsedDocument, normalize_review_input
from contract_agent.knowledge.rag.rerank.impl.qwen_endpoint import build_qwen_rerank_endpoint
from contract_agent.knowledge.rag.rerank.impl.qwen_response_parser import parse_qwen_rerank_results
from contract_agent.knowledge.rag.rerank.impl.qwen_transport import QwenRerankTransport
from contract_agent.config import (
    EnvironmentChatConfigSource,
    EnvironmentEmbeddingConfigSource,
    EnvironmentRerankConfigSource,
    ModelRole,
)
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
        self.assertEqual(
            OpenAIEmbeddings.__module__, "contract_agent.provider.impl.openai.embeddings"
        )
        self.assertEqual(
            DashScopeProvider.__module__, "contract_agent.provider.impl.dashscope.provider"
        )

    def test_qwen_rerank_helpers_are_separate_from_transport_class(self):
        endpoint = build_qwen_rerank_endpoint("https://dashscope.aliyuncs.com/compatible-mode/v1")
        results = parse_qwen_rerank_results({"results": [{"index": 0, "relevance_score": 0.9}]})

        self.assertEqual(endpoint, "https://dashscope.aliyuncs.com/compatible-api/v1/reranks")
        self.assertEqual(results[0].index, 0)
        self.assertEqual(results[0].score, 0.9)
        self.assertEqual(
            QwenRerankTransport.__module__,
            "contract_agent.knowledge.rag.rerank.impl.qwen_transport",
        )

    def test_parser_package_is_canonical_public_parser_api(self):
        self.assertEqual(ContractParser.__module__, "contract_agent.parser.service")
        self.assertEqual(ParsedDocument.__module__, "contract_agent.parser.models")
        self.assertEqual(normalize_review_input.__module__, "contract_agent.parser.normalizer")

    def test_parser_package_does_not_depend_on_rpc_review_service_or_agents(self):
        root = Path(__file__).resolve().parents[2]
        parser_dir = root / "contract_agent" / "parser"
        forbidden = [
            "contract_agent.agent_rpc",
            "agent_pb2",
            "HasField",
            "contract_agent.services.review_service",
            "contract_agent.agents",
        ]

        offenders = []
        for path in parser_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in text:
                    offenders.append(f"{path.relative_to(root)}:{marker}")

        self.assertEqual(offenders, [])

    def test_parser_modules_do_not_import_optional_converter_dependencies_at_top_level(self):
        root = Path(__file__).resolve().parents[2]
        parser_dir = root / "contract_agent" / "parser"
        offenders = []
        for path in parser_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for forbidden in (
                "import docling",
                "from docling",
                "import markitdown",
                "from markitdown",
            ):
                if forbidden in text:
                    offenders.append(f"{path.relative_to(root)}:{forbidden}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
