import unittest

from contract_agent.memory import cold_store, hot_store, manager, models, warm_store


class MemoryPersistenceTests(unittest.TestCase):
    def test_memory_model_is_canonical(self):
        self.assertEqual(models.AgentOutputRecord.__tablename__, "agent_outputs")

    def test_memory_stores_are_canonical(self):
        self.assertTrue(hasattr(hot_store, "HotLayer"))
        self.assertTrue(hasattr(warm_store, "WarmLayer"))
        self.assertTrue(hasattr(cold_store, "ColdLayer"))
        self.assertTrue(hasattr(manager, "MemoryManager"))


if __name__ == "__main__":
    unittest.main()
