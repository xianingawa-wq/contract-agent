from __future__ import annotations

from contract_agent.provider.factory import ModelProviderFactory, create_model_provider_service
from contract_agent.provider.impl.dashscope.embeddings import DashScopeEmbeddings
from contract_agent.provider.impl.dashscope.provider import DashScopeProvider
from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings
from contract_agent.provider.impl.openai.message_codec import (
    with_strict_objects as _with_strict_objects,
)
from contract_agent.provider.impl.openai.provider import OpenAIProvider
from contract_agent.provider.interface import LLMConfig, LLMProvider, ModelResponse, ToolCall

OpenAICompatibleEmbeddings = OpenAIEmbeddings
OpenAICompatibleProvider = OpenAIProvider


def get_provider() -> LLMProvider:
    return get_chat_provider()


def get_chat_provider() -> LLMProvider:
    return create_model_provider_service().create_chat_provider()


def get_embedding_provider() -> LLMProvider:
    return create_model_provider_service().create_embedding_provider()


__all__ = [
    "LLMConfig",
    "LLMProvider",
    "ModelProviderFactory",
    "ModelResponse",
    "DashScopeEmbeddings",
    "DashScopeProvider",
    "OpenAICompatibleEmbeddings",
    "OpenAICompatibleProvider",
    "OpenAIEmbeddings",
    "OpenAIProvider",
    "ToolCall",
    "_with_strict_objects",
    "get_chat_provider",
    "get_embedding_provider",
    "get_provider",
]
