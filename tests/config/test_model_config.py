import tempfile
import unittest
from pathlib import Path

from contract_agent.config import (
    ModelEndpointConfig,
    ModelRole,
    ModelRuntimeConfig,
    ProfileLoadError,
    YamlModelProfileStore,
    create_model_config_resolver,
    create_model_profile_service,
)


class ModelConfigTests(unittest.TestCase):
    def test_yaml_profile_store_round_trips_runtime_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yaml"
            store = YamlModelProfileStore(path)
            config = ModelRuntimeConfig(
                chat=ModelEndpointConfig(
                    role=ModelRole.CHAT,
                    provider="openai_compatible",
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
                    provider="openai_compatible",
                    base_url="https://rerank.example.test/v1",
                    api_key="rerank-key",
                    model="rerank-model",
                ),
            )

            store.save(config)
            loaded = store.load()

        self.assertEqual(loaded, config)

    def test_profile_service_hides_api_keys_in_public_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yaml"
            path.write_text(
                """
chat:
  provider: openai_compatible
  base_url: https://chat.example.test/v1
  api_key: chat-secret
  model: chat-model
embedding:
  provider: openai_compatible
  base_url: https://embedding.example.test/v1
  api_key: embedding-secret
  model: embedding-model
rerank:
  provider: openai_compatible
  base_url: https://rerank.example.test/v1
  api_key: rerank-secret
  model: rerank-model
""",
                encoding="utf-8",
            )
            service = create_model_profile_service(path)

            summary = service.public_summary()

        self.assertIn("chat.model=chat-model", summary)
        self.assertIn("embedding.model=embedding-model", summary)
        self.assertIn("rerank.model=rerank-model", summary)
        self.assertIn("chat.api_key_configured=True", summary)
        self.assertNotIn("chat-secret", summary)
        self.assertNotIn("embedding-secret", summary)
        self.assertNotIn("rerank-secret", summary)

    def test_resolver_prefers_local_profile_over_environment_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yaml"
            path.write_text(
                """
chat:
  provider: openai_compatible
  base_url: https://profile-chat.example.test/v1
  api_key: profile-chat-key
  model: profile-chat-model
""",
                encoding="utf-8",
            )
            resolver = create_model_config_resolver(path)

            config = resolver.resolve()

        self.assertEqual(config.chat.base_url, "https://profile-chat.example.test/v1")
        self.assertEqual(config.chat.api_key, "profile-chat-key")
        self.assertEqual(config.chat.model, "profile-chat-model")
        self.assertEqual(config.embedding.role, ModelRole.EMBEDDING)
        self.assertEqual(config.rerank.role, ModelRole.RERANK)

    def test_corrupt_yaml_profile_raises_clear_error_instead_of_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yaml"
            path.write_text("chat:\n  model: broken\n    bad-indent: true\n", encoding="utf-8")
            store = YamlModelProfileStore(path)

            with self.assertRaises(ProfileLoadError) as captured:
                store.load()

        self.assertIn("CLI profile", str(captured.exception))
        self.assertIn("profile.yaml", str(captured.exception))

    def test_non_mapping_yaml_profile_raises_clear_error_instead_of_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yaml"
            path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
            store = YamlModelProfileStore(path)

            with self.assertRaises(ProfileLoadError):
                store.load()

    def test_profile_store_missing_after_exists_check_returns_fallback(self):
        fallback = ModelRuntimeConfig(
            chat=ModelEndpointConfig(
                role=ModelRole.CHAT,
                provider="openai_compatible",
                base_url="https://fallback-chat.example.test/v1",
                api_key="",
                model="fallback-chat",
            ),
            embedding=ModelEndpointConfig(
                role=ModelRole.EMBEDDING,
                provider="openai_compatible",
                base_url="https://fallback-embedding.example.test/v1",
                api_key="",
                model="fallback-embedding",
            ),
            rerank=ModelEndpointConfig(
                role=ModelRole.RERANK,
                provider="qwen",
                base_url="https://fallback-rerank.example.test/v1",
                api_key="",
                model="fallback-rerank",
            ),
        )

        class FallbackSource:
            def load(self) -> ModelRuntimeConfig:
                return fallback

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yaml"
            path.write_text("chat:\n  model: race\n", encoding="utf-8")
            store = YamlModelProfileStore(path, fallback_source=FallbackSource())
            path.unlink()

            loaded = store.load()

        self.assertEqual(loaded, fallback)


if __name__ == "__main__":
    unittest.main()
