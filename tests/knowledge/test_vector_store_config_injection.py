import sys
import types
import unittest
from unittest.mock import patch

from contract_agent.config import ModelEndpointConfig, ModelRole, ModelRuntimeConfig, Settings
from contract_agent.knowledge.rag import vector_store


class FakeMilvus:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @classmethod
    def from_texts(cls, **kwargs):
        instance = cls()
        instance.from_texts_kwargs = kwargs
        return instance


def _runtime_model_config() -> ModelRuntimeConfig:
    chat = ModelEndpointConfig(
        role=ModelRole.CHAT,
        provider="openai_compatible",
        base_url="https://chat.example.test/v1",
        api_key="chat-key",
        model="chat-model",
    )
    embedding = ModelEndpointConfig(
        role=ModelRole.EMBEDDING,
        provider="openai_compatible",
        base_url="https://embedding.example.test/v1",
        api_key="embedding-key",
        model="embedding-model",
    )
    rerank = ModelEndpointConfig(
        role=ModelRole.RERANK,
        provider="qwen",
        base_url="https://rerank.example.test/v1",
        api_key="rerank-key",
        model="rerank-model",
    )
    return ModelRuntimeConfig(chat=chat, embedding=embedding, rerank=rerank)


class VectorStoreConfigInjectionTests(unittest.TestCase):
    def test_milvus_build_uses_injected_model_and_runtime_config(self):
        runtime_settings = Settings(
            vector_backend="milvus",
            milvus_uri="http://milvus.example.test:19530",
            milvus_collection_name="contracts_test",
        )
        model_config = _runtime_model_config()
        vectorstores_module = types.ModuleType("langchain_community.vectorstores")
        vectorstores_module.Milvus = FakeMilvus

        with (
            patch.dict(sys.modules, {"langchain_community.vectorstores": vectorstores_module}),
            patch.object(
                vector_store, "get_embeddings", return_value="embeddings"
            ) as get_embeddings,
        ):
            store = vector_store.build_vector_store(
                [],
                runtime_settings=runtime_settings,
                model_config=model_config,
            )

        get_embeddings.assert_called_once_with(
            model_config=model_config, runtime_settings=runtime_settings
        )
        self.assertIsInstance(store, FakeMilvus)
        self.assertEqual(store.kwargs["embedding_function"], "embeddings")
        self.assertEqual(
            store.kwargs["connection_args"], {"uri": "http://milvus.example.test:19530"}
        )
        self.assertEqual(store.kwargs["collection_name"], "contracts_test")


if __name__ == "__main__":
    unittest.main()
