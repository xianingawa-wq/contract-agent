import importlib.util
import unittest


class ArchitecturePackageTests(unittest.TestCase):
    def test_canonical_agent_runtime_packages_are_discoverable(self):
        canonical_paths = [
            "contract_agent.llm_provider.client",
            "contract_agent.llm_provider.providers",
            "contract_agent.constants.prompts",
            "contract_agent.constants.agent_prompts",
            "contract_agent.agents.reviewer",
            "contract_agent.agents.editor",
            "contract_agent.agents.workers",
            "contract_agent.orchestration.config",
            "contract_agent.orchestration.protocol",
            "contract_agent.orchestration.gateway",
            "contract_agent.orchestration.pipeline",
            "contract_agent.orchestration.supervisor",
        ]

        for path in canonical_paths:
            with self.subTest(path=path):
                self.assertIsNotNone(importlib.util.find_spec(path))


if __name__ == "__main__":
    unittest.main()
