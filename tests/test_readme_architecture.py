from pathlib import Path
import unittest


class ReadmeArchitectureTests(unittest.TestCase):
    def test_readme_documents_canonical_agent_packages(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        required_packages = [
            "contract_agent/provider/",
            "contract_agent/constants/",
            "contract_agent/agents/",
            "contract_agent/orchestration/",
            "contract_agent/logger/",
            "contract_agent/trace/",
        ]

        for package in required_packages:
            with self.subTest(package=package):
                self.assertIn(package, readme)

    def test_readme_does_not_document_removed_agent_layers(self):
        readme = Path("README.md").read_text(encoding="utf-8")
        removed_packages = [
            "contract_agent/llm/",
            "contract_agent/llm_provider/",
            "contract_agent/multi_agent/",
        ]

        for package in removed_packages:
            with self.subTest(package=package):
                self.assertNotIn(package, readme)


if __name__ == "__main__":
    unittest.main()
