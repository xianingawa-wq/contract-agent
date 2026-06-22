import unittest

from contract_agent.provider.factory import ModelProviderFactory
from contract_agent.provider.impl.dashscope.provider import DashScopeProvider
from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings
from contract_agent.provider.impl.openai.provider import OpenAIProvider
from contract_agent.provider.impl.openai_compatible import OpenAICompatibleEmbeddings, OpenAICompatibleProvider
from contract_agent.provider.interface import LLMConfig
from contract_agent.provider.providers import (
    _with_strict_objects,
    get_chat_provider,
    get_embedding_provider,
)
from contract_agent.runtime.config import settings


class LLMProviderTests(unittest.TestCase):
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
        original = settings.model_dump()
        try:
            settings.chat_provider = "openai_compatible"
            settings.chat_api_key = "chat-key"
            settings.chat_base_url = "https://chat.example.test/v1"
            settings.chat_model = "chat-model"
            settings.embedding_provider = "openai_compatible"
            settings.embedding_api_key = "embedding-key"
            settings.embedding_base_url = "https://embedding.example.test/v1"
            settings.embedding_model = "embedding-model"

            chat_provider = get_chat_provider()
            embedding_provider = get_embedding_provider()

            self.assertEqual(chat_provider.config.api_key, "chat-key")
            self.assertEqual(chat_provider.config.base_url, "https://chat.example.test/v1")
            self.assertEqual(chat_provider.config.chat_model, "chat-model")
            self.assertEqual(embedding_provider.config.api_key, "embedding-key")
            self.assertEqual(embedding_provider.config.base_url, "https://embedding.example.test/v1")
            self.assertEqual(embedding_provider.config.embedding_model, "embedding-model")
        finally:
            for key, value in original.items():
                setattr(settings, key, value)

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
