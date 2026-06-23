import importlib
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
            "contract_agent.orchestration.config",
            "contract_agent.knowledge.rag.config",
            "contract_agent.runtime.config",
        ]

        for path in removed_paths:
            with self.subTest(path=path):
                with self.assertRaises(ModuleNotFoundError):
                    importlib.import_module(path)


if __name__ == "__main__":
    unittest.main()
