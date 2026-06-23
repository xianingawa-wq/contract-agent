import unittest

from contract_agent.provider.factory import ModelProviderFactory
from contract_agent.provider.impl.dashscope.provider import DashScopeProvider
from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings
from contract_agent.provider.impl.openai.provider import OpenAIProvider
from contract_agent.provider.impl.openai_compatible import (
    OpenAICompatibleEmbeddings,
    OpenAICompatibleProvider,
)
from contract_agent.provider.interface import LLMConfig
from contract_agent.config import ModelEndpointConfig, ModelRole, ModelRuntimeConfig, Settings
from contract_agent.provider import client as provider_client
from contract_agent.provider.service import ModelProviderService, ProviderRuntimeOptions
from contract_agent.provider.providers import (
    _with_strict_objects,
    get_chat_provider,
    get_embedding_provider,
)


class StaticModelConfigSource:
    def __init__(self, config: ModelRuntimeConfig) -> None:
        self.config = config

    def load(self) -> ModelRuntimeConfig:
        return self.config


class LLMProviderTests(unittest.TestCase):
    def test_provider_client_uses_explicit_model_config_and_runtime_settings(self):
        runtime_config = ModelRuntimeConfig(
            chat=ModelEndpointConfig(
                role=ModelRole.CHAT,
                provider="openai_compatible",
                api_key="chat-key",
                base_url="https://chat.example.test/v1",
                model="chat-model",
            ),
            embedding=ModelEndpointConfig(
                role=ModelRole.EMBEDDING,
                provider="openai_compatible",
                api_key="embedding-key",
                base_url="https://embedding.example.test/v1",
                model="embedding-model",
            ),
            rerank=ModelEndpointConfig(
                role=ModelRole.RERANK,
                provider="qwen",
                api_key="rerank-key",
                base_url="https://rerank.example.test/v1",
                model="rerank-model",
            ),
        )
        runtime_settings = Settings(llm_temperature=0.7, llm_use_responses_api=False)
        captured = {}

        class FakeProvider:
            def chat_model(self):
                return "chat-llm"

            def embeddings(self):
                return "embedding-client"

        class FakeService:
            def create_chat_provider(self):
                return FakeProvider()

            def create_embedding_provider(self):
                return FakeProvider()

        original = provider_client.create_model_provider_service
        try:

            def fake_create_model_provider_service(
                config_source=None, *, model_config=None, runtime_settings=None
            ):
                captured["model_config"] = model_config or config_source.load()
                captured["runtime_settings"] = runtime_settings
                return FakeService()

            provider_client.create_model_provider_service = fake_create_model_provider_service  # type: ignore[method-assign]

            chat = provider_client.get_chat_model(
                model_config=runtime_config, runtime_settings=runtime_settings
            )
            embeddings = provider_client.get_embeddings(
                model_config=runtime_config, runtime_settings=runtime_settings
            )
        finally:
            provider_client.create_model_provider_service = original  # type: ignore[method-assign]

        self.assertEqual(chat, "chat-llm")
        self.assertEqual(embeddings, "embedding-client")
        self.assertEqual(captured["model_config"], runtime_config)
        self.assertIs(captured["runtime_settings"], runtime_settings)

    def test_strict_schema_disallows_extra_object_properties(self):
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                }
            },
        }

        strict = _with_strict_objects(schema)

        self.assertFalse(strict["additionalProperties"])
        nested = strict["properties"]["items"]["items"]
        self.assertFalse(nested["additionalProperties"])

    def test_openai_provider_keeps_base_url_configurable(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="https://example.test/v1",
            chat_model="test-chat",
            embedding_model="test-embedding",
        )

        provider = OpenAIProvider(config)

        self.assertEqual(provider.config.base_url, "https://example.test/v1")
        self.assertEqual(provider.config.chat_model, "test-chat")

    def test_provider_factories_use_separate_chat_and_embedding_configs(self):
        runtime_config = ModelRuntimeConfig(
            chat=ModelEndpointConfig(
                role=ModelRole.CHAT,
                provider="openai_compatible",
                api_key="chat-key",
                base_url="https://chat.example.test/v1",
                model="chat-model",
            ),
            embedding=ModelEndpointConfig(
                role=ModelRole.EMBEDDING,
                provider="openai_compatible",
                api_key="embedding-key",
                base_url="https://embedding.example.test/v1",
                model="embedding-model",
            ),
            rerank=ModelEndpointConfig(
                role=ModelRole.RERANK,
                provider="qwen",
                api_key="rerank-key",
                base_url="https://rerank.example.test/v1",
                model="rerank-model",
            ),
        )
        service = ModelProviderService(
            StaticModelConfigSource(runtime_config),
            ModelProviderFactory(),
            ProviderRuntimeOptions(temperature=0.2, use_responses_api=False),
        )

        chat_provider = service.create_chat_provider()
        embedding_provider = service.create_embedding_provider()

        self.assertEqual(chat_provider.config.api_key, "chat-key")
        self.assertEqual(chat_provider.config.base_url, "https://chat.example.test/v1")
        self.assertEqual(chat_provider.config.chat_model, "chat-model")
        self.assertEqual(chat_provider.config.temperature, 0.2)
        self.assertFalse(chat_provider.config.use_responses_api)
        self.assertEqual(embedding_provider.config.api_key, "embedding-key")
        self.assertEqual(embedding_provider.config.base_url, "https://embedding.example.test/v1")
        self.assertEqual(embedding_provider.config.embedding_model, "embedding-model")

    def test_model_provider_factory_creates_openai_registered_provider(self):
        factory = ModelProviderFactory()
        config = LLMConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="https://example.test/v1",
            chat_model="chat-model",
            embedding_model="embedding-model",
        )

        provider = factory.create(config)

        self.assertIsInstance(provider, OpenAIProvider)

    def test_model_provider_factory_creates_dashscope_registered_provider(self):
        factory = ModelProviderFactory()
        config = LLMConfig(
            provider="dashscope",
            api_key="test-key",
            base_url="https://dashscope.example.test/v1",
            chat_model="chat-model",
            embedding_model="embedding-model",
        )

        provider = factory.create(config)

        self.assertIsInstance(provider, DashScopeProvider)

    def test_openai_compatible_provider_is_legacy_alias(self):
        self.assertIs(OpenAICompatibleProvider, OpenAIProvider)

    def test_openai_compatible_embeddings_is_legacy_alias(self):
        self.assertIs(OpenAICompatibleEmbeddings, OpenAIEmbeddings)


if __name__ == "__main__":
    unittest.main()
