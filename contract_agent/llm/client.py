from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI

from contract_agent.llm.providers import LLMProvider, get_provider


def get_chat_model() -> ChatOpenAI:
    return get_provider().chat_model()


def get_embeddings() -> Embeddings:
    return get_provider().embeddings()


def get_llm_provider() -> LLMProvider:
    return get_provider()
