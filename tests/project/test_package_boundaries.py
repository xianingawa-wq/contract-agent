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
        self.assertEqual(
            ContractParser.__module__,
            "contract_agent.parser.contract_parser_service",
        )
        self.assertEqual(ParsedDocument.__module__, "contract_agent.parser.models")
        self.assertEqual(
            normalize_review_input.__module__,
            "contract_agent.parser.review_input_normalizer",
        )

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

    def test_parser_modules_do_not_import_optional_backend_dependencies_at_top_level(self):
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

    def test_parser_legacy_backend_and_converter_packages_are_removed(self):
        root = Path(__file__).resolve().parents[2]
        parser_dir = root / "contract_agent" / "parser"

        self.assertFalse((parser_dir / "backends").exists())
        self.assertFalse((parser_dir / "converters").exists())
        self.assertFalse((parser_dir / "detectors").exists())
        self.assertFalse((parser_dir / "impl").exists())
        self.assertFalse((parser_dir / "chunker.py").exists())
        self.assertFalse((parser_dir / "loaders.py").exists())
        self.assertFalse((parser_dir / "normalizer.py").exists())
        self.assertFalse((parser_dir / "service.py").exists())

    def test_parser_markdown_first_layers_have_explicit_file_names(self):
        root = Path(__file__).resolve().parents[2]
        parser_dir = root / "contract_agent" / "parser"

        expected_files = [
            parser_dir / "contract_parser_service.py",
            parser_dir / "parser_backend_router.py",
            parser_dir / "parser_backend_contract.py",
            parser_dir / "parser_source.py",
            parser_dir / "markdown_document.py",
            parser_dir / "convertor" / "builtin_parser_impl.py",
            parser_dir / "convertor" / "docling_parser_impl.py",
            parser_dir / "convertor" / "markitdown_parser_impl.py",
            parser_dir / "convertor" / "builtin_markdown_converter.py",
            parser_dir / "convertor" / "local_file_source.py",
            parser_dir / "parsed" / "markdown_parsed_service.py",
            parser_dir / "parsed" / "markdown_block_parser.py",
            parser_dir / "parsed" / "markdown_cleaner.py",
            parser_dir / "parsed" / "markdown_table_parser.py",
            parser_dir / "parsed" / "markdown_chunker.py",
            parser_dir / "parsed" / "markdown_metadata_builder.py",
            parser_dir / "parsed" / "semantic_graph_builder.py",
            parser_dir / "serializers" / "parsed_document_serializer.py",
            parser_dir / "serializers" / "rag_document_serializer.py",
            parser_dir / "serializers" / "evidence_json_serializer.py",
        ]

        missing = [str(path.relative_to(root)) for path in expected_files if not path.exists()]

        self.assertEqual(missing, [])

    def test_parser_service_and_chunker_do_not_depend_on_detector_layer(self):
        root = Path(__file__).resolve().parents[2]
        parser_dir = root / "contract_agent" / "parser"
        offenders = []
        for path in (
            parser_dir / "contract_parser_service.py",
            parser_dir / "parsed" / "markdown_chunker.py",
        ):
            text = path.read_text(encoding="utf-8")
            if "contract_agent.parser.detectors" in text:
                offenders.append(str(path.relative_to(root)))

        self.assertEqual(offenders, [])

    def test_convertor_layer_does_not_import_parsed_document_models(self):
        root = Path(__file__).resolve().parents[2]
        convertor_dir = root / "contract_agent" / "parser" / "convertor"
        forbidden = [
            "ParsedDocument",
            "DocumentSpan",
            "DocumentBlock",
            "DocumentTable",
            "ClauseChunk",
            "MarkdownParsedService",
        ]
        offenders = []

        for path in convertor_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in text:
                    offenders.append(f"{path.relative_to(root)}:{marker}")

        self.assertEqual(offenders, [])

    def test_serializers_do_not_parse_markdown(self):
        root = Path(__file__).resolve().parents[2]
        serializers_dir = root / "contract_agent" / "parser" / "serializers"
        forbidden = [
            "document_from_markdown",
            "MarkdownParsedService",
            "markdown_parsed_service",
            "parse_markdown",
        ]
        offenders = []

        for path in serializers_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for marker in forbidden:
                if marker in text:
                    offenders.append(f"{path.relative_to(root)}:{marker}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
