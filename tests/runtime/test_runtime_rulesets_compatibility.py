import unittest

from contract_agent import config
from contract_agent.rulesets import built_in


class RuntimeRulesetsTests(unittest.TestCase):
    def test_config_package_exports_settings(self):
        self.assertTrue(config.PROJECT_ROOT.exists())
        self.assertIsInstance(config.settings, config.Settings)

    def test_builtin_rules_exports_rules(self):
        self.assertTrue(built_in.RULES)


if __name__ == "__main__":
    unittest.main()
