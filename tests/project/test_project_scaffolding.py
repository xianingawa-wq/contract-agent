from pathlib import Path
import tomllib
import unittest


class ProjectScaffoldingTests(unittest.TestCase):
    def test_requirements_matches_pyproject_runtime_dependencies(self):
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        pyproject_dependencies = set(pyproject["project"]["dependencies"])
        requirements = {
            line.strip()
            for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }

        self.assertTrue(pyproject_dependencies.issubset(requirements))

    def test_protobuf_runtime_matches_generated_grpc_code(self):
        generated = Path("contract_agent/agent_rpc/agent_pb2.py").read_text(encoding="utf-8")
        version_line = next(
            line
            for line in generated.splitlines()
            if line.startswith("# Protobuf Python Version: ")
        )
        expected = f"protobuf=={version_line.removeprefix('# Protobuf Python Version: ')}"
        pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        requirements = {
            line.strip()
            for line in Path("requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }

        self.assertIn(expected, pyproject["project"]["dependencies"])
        self.assertIn(expected, requirements)

    def test_env_example_documents_required_runtime_keys(self):
        env_example = Path(".env.example")
        self.assertTrue(env_example.exists())
        content = env_example.read_text(encoding="utf-8")
        required_keys = [
            "LLM_API_KEY",
            "CHAT_API_KEY",
            "EMBEDDING_API_KEY",
            "RERANK_API_KEY",
            "POSTGRES_DSN",
            "MILVUS_URI",
            "KNOWLEDGE_VECTOR_STORE_DIR",
            "AGENT_GRPC_PORT",
        ]

        for key in required_keys:
            with self.subTest(key=key):
                self.assertIn(f"{key}=", content)

    def test_canonical_provider_package_exports_public_interfaces(self):
        from contract_agent.config import LLMConfig
        from contract_agent.provider import (
            LLMProvider,
            ModelProviderFactory,
            ModelProviderService,
            create_model_provider_service,
        )

        self.assertIsNotNone(LLMConfig)
        self.assertIsNotNone(LLMProvider)
        self.assertIsNotNone(ModelProviderFactory)
        self.assertIsNotNone(ModelProviderService)
        self.assertIsNotNone(create_model_provider_service)

    def test_canonical_service_agent_and_schema_packages_export_public_interfaces(self):
        import contract_agent.agents as agents
        import contract_agent.parser as parser
        import contract_agent.schemas as schemas
        import contract_agent.services as services

        for package, names in {
            services: [
                "ChatService",
                "ReviewService",
                "GatewayRouter",
                "RuleEngine",
            ],
            agents: ["ContractEditor", "LLMReviewer", "parser_agent", "risk_checker_agent"],
            schemas: [
                "ReviewRequest",
                "ReviewResponse",
                "ChatRequest",
                "KnowledgeChunk",
            ],
            parser: [
                "ContractParser",
                "ParsedDocument",
                "ParsedReviewInput",
                "normalize_review_input",
            ],
        }.items():
            for name in names:
                with self.subTest(package=package.__name__, name=name):
                    self.assertIn(name, package.__all__)
                    self.assertIsNotNone(getattr(package, name))

    def test_runtime_errors_do_not_use_legacy_qwen_api_key_as_primary_message(self):
        for path in Path("contract_agent").rglob("*.py"):
            with self.subTest(path=str(path)):
                self.assertNotIn(
                    "QWEN_API_KEY 未配置",
                    path.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
