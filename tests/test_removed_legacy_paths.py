import importlib
import unittest


class RemovedLegacyPathTests(unittest.TestCase):
    def test_top_level_rag_package_is_removed(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("contract_agent.rag")


if __name__ == "__main__":
    unittest.main()
