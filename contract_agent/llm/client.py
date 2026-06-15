from openai import OpenAI
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI

from contract_agent.core.config import settings


class QwenCompatibleEmbeddings(Embeddings):
    def __init__(self) -> None:
        self.client = OpenAI(
            api_key=settings.qwen_api_key,
            base_url=settings.qwen_base_url,
        )
        self.model = settings.langchain_embedding_model
        self.chunk_size = 10

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.chunk_size):
            batch = [text if isinstance(text, str) else str(text) for text in texts[start : start + self.chunk_size]]
            response = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding


def get_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.qwen_api_key,
        base_url=settings.qwen_base_url,
        model=settings.langchain_model,
        temperature=0,
    )


def get_embeddings() -> Embeddings:
    return QwenCompatibleEmbeddings()
