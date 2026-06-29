import importlib
from pathlib import Path
import re
import unittest


class RemovedLegacyPathTests(unittest.TestCase):
    def test_legacy_packages_and_modules_are_removed(self):
        removed_paths = [
            "contract_agent.cli",
            "contract_agent.main",
            "contract_agent.models",
            "contract_agent.rules",
            "contract_agent.report",
            "contract_agent.service",
            "contract_agent.core",
            "contract_agent.data",
            "contract_agent.db",
            "contract_agent.scripts",
            "contract_agent.llm",
            "contract_agent.llm_provider",
            "contract_agent.multi_agent",
            "contract_agent.multi_agent.memory",
            "contract_agent.rag",
            "contract_agent.provider.impl.openai_compatible_embeddings",
            "contract_agent.provider.impl.openai_compatible_provider",
            "contract_agent.provider.impl.openai_message_codec",
            "contract_agent.orchestration.gateway",
            "contract_agent.orchestration.config",
            "contract_agent.knowledge.rag.config",
            "contract_agent.runtime.config",
            "contract_agent.model_config",
            "contract_agent.model_config.interface",
            "contract_agent.model_config.factory",
            "contract_agent.model_config.service",
            "contract_agent.services.parser",
            "contract_agent.services.chunker",
            "contract_agent.schemas.document",
        ]

        for path in removed_paths:
            with self.subTest(path=path):
                with self.assertRaises(ModuleNotFoundError) as exc:
                    importlib.import_module(path)
                missing_name = exc.exception.name or ""
                self.assertTrue(path == missing_name or path.startswith(f"{missing_name}."))

    def test_service_and_schema_packages_do_not_export_legacy_parser_symbols(self):
        import contract_agent.schemas as schemas
        import contract_agent.services as services

        for package, names in {
            services: ["ContractParser", "ContractChunker"],
            schemas: ["ParsedDocument", "DocumentMetadata", "DocumentSpan", "ClauseChunk"],
        }.items():
            for name in names:
                with self.subTest(package=package.__name__, name=name):
                    self.assertNotIn(name, package.__all__)
                    self.assertFalse(hasattr(package, name))

    def test_runtime_environment_reads_stay_inside_config_package(self):
        root = Path(__file__).resolve().parents[1]
        env_call_pattern = re.compile(r"os\.(?:getenv|environ)")
        offenders: list[str] = []

        for path in (root / "contract_agent").rglob("*.py"):
            relative = path.relative_to(root)
            if relative.parts[:2] == ("contract_agent", "config"):
                continue
            text = path.read_text(encoding="utf-8")
            if env_call_pattern.search(text):
                offenders.append(str(relative))

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
