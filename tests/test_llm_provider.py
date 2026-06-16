import unittest

from contract_agent.provider.providers import LLMConfig, OpenAICompatibleProvider, _with_strict_objects


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

    def test_openai_compatible_provider_keeps_base_url_configurable(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="https://example.test/v1",
            chat_model="test-chat",
            embedding_model="test-embedding",
        )

        provider = OpenAICompatibleProvider(config)

        self.assertEqual(provider.config.base_url, "https://example.test/v1")
        self.assertEqual(provider.config.chat_model, "test-chat")


if __name__ == "__main__":
    unittest.main()
