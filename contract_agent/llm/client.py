from __future__ import annotations

from typing import TYPE_CHECKING

from contract_agent.llm.providers import LLMProvider, get_provider

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_openai import ChatOpenAI


def get_chat_model() -> "ChatOpenAI":
    return get_provider().chat_model()


def get_embeddings() -> "Embeddings":
    return get_provider().embeddings()


def get_llm_provider() -> LLMProvider:
    return get_provider()
