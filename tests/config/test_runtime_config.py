import unittest

from contract_agent.config import ModelEndpointConfig, ModelRole, ModelRuntimeConfig
from contract_agent.config import apply_model_runtime_config
from contract_agent.config import (
    Settings,
    load_settings_from_env,
    settings,
    settings_snapshot,
    temporary_settings,
)


class RuntimeConfigTests(unittest.TestCase):
    def test_load_settings_from_env_keeps_defaults_instance_scoped(self):
        first = load_settings_from_env({"CHAT_MODEL": "chat-a", "LLM_API_KEY": "key-a"})
        second = load_settings_from_env({"CHAT_MODEL": "chat-b", "LLM_API_KEY": "key-b"})

        self.assertIsInstance(first, Settings)
        self.assertEqual(first.chat_model, "chat-a")
        self.assertEqual(first.chat_api_key, "key-a")
        self.assertEqual(second.chat_model, "chat-b")
        self.assertEqual(second.chat_api_key, "key-b")

    def test_settings_snapshot_is_detached_from_global_mutations(self):
        with temporary_settings(chat_model="snapshot-model"):
            snapshot = settings_snapshot()
            settings.chat_model = "mutated-model"

            self.assertEqual(snapshot.chat_model, "snapshot-model")
            self.assertEqual(settings.chat_model, "mutated-model")

    def test_apply_model_runtime_config_updates_related_aliases_together(self):
        config = ModelRuntimeConfig(
            chat=ModelEndpointConfig(
                role=ModelRole.CHAT,
                provider="openai",
                base_url="https://chat.example.test/v1",
                api_key="chat-key",
                model="chat-model",
            ),
            embedding=ModelEndpointConfig(
                role=ModelRole.EMBEDDING,
                provider="openai_compatible",
                base_url="https://embedding.example.test/v1",
                api_key="embedding-key",
                model="embedding-model",
            ),
            rerank=ModelEndpointConfig(
                role=ModelRole.RERANK,
                provider="qwen",
                base_url="https://rerank.example.test/v1",
                api_key="rerank-key",
                model="rerank-model",
            ),
        )

        with temporary_settings():
            apply_model_runtime_config(config)
            snapshot = settings_snapshot()

            self.assertEqual(snapshot.chat_model, "chat-model")
            self.assertEqual(snapshot.llm_chat_model, "chat-model")
            self.assertEqual(snapshot.embedding_model, "embedding-model")
            self.assertEqual(snapshot.llm_embedding_model, "embedding-model")
            self.assertEqual(snapshot.qwen_api_key, "chat-key")
            self.assertEqual(snapshot.langchain_embedding_model, "embedding-model")
            self.assertEqual(snapshot.rerank_model, "rerank-model")


if __name__ == "__main__":
    unittest.main()
