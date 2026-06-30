import unittest
from types import SimpleNamespace

from contract_agent.provider.factory import ModelProviderFactory
from contract_agent.provider.impl.dashscope.provider import DashScopeProvider
from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings
from contract_agent.provider.impl.openai.provider import OpenAIProvider
from contract_agent.provider.impl.openai_compatible import (
    OpenAICompatibleEmbeddings,
    OpenAICompatibleProvider,
)
from contract_agent.config import LLMConfig
from contract_agent.config import ModelEndpointConfig, ModelRole, ModelRuntimeConfig, Settings
from contract_agent.provider import client as provider_client
from contract_agent.provider.service import ModelProviderService, ProviderRuntimeOptions
from contract_agent.provider.providers import _with_strict_objects


class StaticModelConfigSource:
    def __init__(self, config: ModelRuntimeConfig) -> None:
        self.config = config

    def load(self) -> ModelRuntimeConfig:
        return self.config


class FakeChatCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=None,
                            tool_calls=[
                                SimpleNamespace(
                                    id="call_lookup",
                                    function=SimpleNamespace(
                                        name="lookup_clause",
                                        arguments='{"clause": "付款"}',
                                    ),
                                )
                            ],
                        )
                    )
                ]
            )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="已完成", tool_calls=[]))]
        )


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(
                id="resp_1",
                output_text="",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        call_id="call_lookup",
                        name="lookup_clause",
                        arguments='{"clause": "付款"}',
                    )
                ],
            )
        return SimpleNamespace(id="resp_2", output_text="已完成", output=[])


class FailingResponses:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raise RuntimeError("responses unsupported")


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

    def test_chat_tool_loop_sends_chat_continuation_messages(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="https://example.test/v1",
            chat_model="chat-model",
            embedding_model="embedding-model",
            use_responses_api=False,
        )
        provider = OpenAIProvider(config)
        chat_completions = FakeChatCompletions()
        provider.client = SimpleNamespace(chat=SimpleNamespace(completions=chat_completions))
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "lookup_clause",
                    "parameters": {"type": "object"},
                },
            }
        ]

        response = provider.run_tool_loop(
            input="检查付款条款",
            instructions="你是合同审查助手。",
            tools=tools,
            handlers={"lookup_clause": lambda args: {"found": args["clause"]}},
        )

        self.assertEqual(response.text, "已完成")
        self.assertEqual(len(chat_completions.calls), 2)
        first_messages = chat_completions.calls[0]["messages"]
        self.assertEqual(
            first_messages,
            [
                {"role": "system", "content": "你是合同审查助手。"},
                {"role": "user", "content": "检查付款条款"},
            ],
        )
        second_messages = chat_completions.calls[1]["messages"]
        self.assertEqual(second_messages[0], first_messages[0])
        self.assertEqual(second_messages[1], first_messages[1])
        self.assertEqual(second_messages[2]["role"], "assistant")
        self.assertIsNone(second_messages[2]["content"])
        self.assertEqual(second_messages[2]["tool_calls"][0]["id"], "call_lookup")
        self.assertEqual(second_messages[2]["tool_calls"][0]["type"], "function")
        self.assertEqual(
            second_messages[2]["tool_calls"][0]["function"],
            {"name": "lookup_clause", "arguments": '{"clause": "付款"}'},
        )
        self.assertEqual(
            second_messages[3],
            {
                "role": "tool",
                "tool_call_id": "call_lookup",
                "content": '{"found": "付款"}',
            },
        )
        self.assertNotIn("previous_response_id", chat_completions.calls[1])
        self.assertNotIn("type", second_messages[3])

    def test_responses_tool_loop_keeps_responses_continuation_payloads(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="https://example.test/v1",
            chat_model="chat-model",
            embedding_model="embedding-model",
            use_responses_api=True,
        )
        provider = OpenAIProvider(config)
        responses = FakeResponses()
        provider.client = SimpleNamespace(responses=responses)
        tools = [{"type": "function", "name": "lookup_clause"}]

        response = provider.run_tool_loop(
            input="检查付款条款",
            tools=tools,
            handlers={"lookup_clause": lambda args: {"found": args["clause"]}},
        )

        self.assertEqual(response.text, "已完成")
        self.assertEqual(len(responses.calls), 2)
        self.assertEqual(
            responses.calls[1]["input"],
            [
                {
                    "type": "function_call_output",
                    "call_id": "call_lookup",
                    "output": '{"found": "付款"}',
                }
            ],
        )
        self.assertEqual(responses.calls[1]["previous_response_id"], "resp_1")

    def test_tool_loop_uses_chat_continuation_after_responses_fallback(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="https://example.test/v1",
            chat_model="chat-model",
            embedding_model="embedding-model",
            use_responses_api=True,
        )
        provider = OpenAIProvider(config)
        responses = FailingResponses()
        chat_completions = FakeChatCompletions()
        provider.client = SimpleNamespace(
            responses=responses,
            chat=SimpleNamespace(completions=chat_completions),
        )
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "lookup_clause",
                    "parameters": {"type": "object"},
                },
            }
        ]

        response = provider.run_tool_loop(
            input="检查付款条款",
            tools=tools,
            handlers={"lookup_clause": lambda args: {"found": args["clause"]}},
        )

        self.assertEqual(response.text, "已完成")
        self.assertEqual(len(responses.calls), 1)
        self.assertEqual(len(chat_completions.calls), 2)
        second_messages = chat_completions.calls[1]["messages"]
        self.assertEqual(second_messages[0], {"role": "user", "content": "检查付款条款"})
        self.assertEqual(second_messages[1]["role"], "assistant")
        self.assertIn("tool_calls", second_messages[1])
        self.assertEqual(
            second_messages[2],
            {
                "role": "tool",
                "tool_call_id": "call_lookup",
                "content": '{"found": "付款"}',
            },
        )
        self.assertNotIn("type", second_messages[2])


if __name__ == "__main__":
    unittest.main()
