from __future__ import annotations

from typing import TYPE_CHECKING

from contract_agent.config import ModelRuntimeConfig, Settings
from contract_agent.provider.factory import create_model_provider_service
from contract_agent.provider.interface import LLMProvider

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_openai import ChatOpenAI


def get_chat_model(
    model_config: ModelRuntimeConfig | None = None,
    runtime_settings: Settings | None = None,
) -> "ChatOpenAI":
    return (
        create_model_provider_service(
            model_config=model_config,
            runtime_settings=runtime_settings,
        )
        .create_chat_provider()
        .chat_model()
    )


def get_embeddings(
    model_config: ModelRuntimeConfig | None = None,
    runtime_settings: Settings | None = None,
) -> "Embeddings":
    return (
        create_model_provider_service(
            model_config=model_config,
            runtime_settings=runtime_settings,
        )
        .create_embedding_provider()
        .embeddings()
    )


def get_llm_provider(
    model_config: ModelRuntimeConfig | None = None,
    runtime_settings: Settings | None = None,
) -> LLMProvider:
    return create_model_provider_service(
        model_config=model_config,
        runtime_settings=runtime_settings,
    ).create_chat_provider()
