import unittest

from contract_agent.db import multi_agent_models as legacy_models
from contract_agent.memory import cold_store, hot_store, manager, models, warm_store
from contract_agent.multi_agent import memory as legacy_memory


class MemoryPersistenceTests(unittest.TestCase):
    def test_db_multi_agent_models_reexport_memory_models(self):
        self.assertIs(legacy_models.Base, models.Base)
        self.assertIs(legacy_models.AgentOutputRecord, models.AgentOutputRecord)

    def test_multi_agent_memory_reexports_memory_stores(self):
        self.assertIs(legacy_memory.HotLayer, hot_store.HotLayer)
        self.assertIs(legacy_memory.WarmLayer, warm_store.WarmLayer)
        self.assertIs(legacy_memory.ColdLayer, cold_store.ColdLayer)
        self.assertIs(legacy_memory.MemoryManager, manager.MemoryManager)


if __name__ == "__main__":
    unittest.main()
