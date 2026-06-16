import unittest

from contract_agent.core import config as old_config
from contract_agent.data import rules as old_rules
from contract_agent.runtime import config as new_config
from contract_agent.rulesets import built_in as new_rules


class RuntimeRulesetsCompatibilityTests(unittest.TestCase):
    def test_core_config_reexports_runtime_config_objects(self):
        self.assertIs(old_config.PROJECT_ROOT, new_config.PROJECT_ROOT)
        self.assertIs(old_config.Settings, new_config.Settings)
        self.assertIs(old_config._bool_env, new_config._bool_env)
        self.assertIs(old_config.settings, new_config.settings)

    def test_data_rules_reexports_builtin_rules_object(self):
        self.assertIs(old_rules.RULES, new_rules.RULES)
        self.assertTrue(new_rules.RULES)


if __name__ == "__main__":
    unittest.main()
