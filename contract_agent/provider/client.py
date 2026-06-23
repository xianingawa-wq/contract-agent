from __future__ import annotations

from typing import TYPE_CHECKING

from contract_agent.provider.factory import create_model_provider_service
from contract_agent.provider.interface import LLMProvider

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_openai import ChatOpenAI


def get_chat_model() -> "ChatOpenAI":
    return create_model_provider_service().create_chat_provider().chat_model()


def get_embeddings() -> "Embeddings":
    return create_model_provider_service().create_embedding_provider().embeddings()


def get_llm_provider() -> LLMProvider:
    return create_model_provider_service().create_chat_provider()
