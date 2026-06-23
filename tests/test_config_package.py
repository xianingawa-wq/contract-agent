import unittest

from contract_agent.config import MultiAgentConfig, RetrievalConfig, Settings


class ConfigPackageTests(unittest.TestCase):
    def test_multi_agent_config_lives_in_config_package(self):
        config = MultiAgentConfig(agent_timeout_seconds=7, max_parallel_agents=2)

        self.assertEqual(config.agent_timeout_seconds, 7)
        self.assertEqual(config.max_parallel_agents, 2)

    def test_retrieval_config_lives_in_config_package_and_derives_from_settings(self):
        settings = Settings(
            retrieval_enable_rerank=False,
            retrieval_enable_hybrid=False,
            retrieval_fetch_k=20,
            retrieval_final_k=5,
            retrieval_dense_pool_k=40,
        )

        config = RetrievalConfig.from_settings(settings)

        self.assertFalse(config.enable_rerank)
        self.assertFalse(config.enable_hybrid)
        self.assertEqual(config.fetch_k, 20)
        self.assertEqual(config.final_k, 5)
        self.assertEqual(config.dense_pool_k, 40)


if __name__ == "__main__":
    unittest.main()
