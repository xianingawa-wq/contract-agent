import os
from pathlib import Path

from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _bool_env(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = "Contract Review Agent"
    default_contract_type: str = "采购合同"

    llm_provider: str = os.getenv("LLM_PROVIDER", "openai_compatible")
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("QWEN_API_KEY")
    llm_base_url: str | None = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("QWEN_BASE_URL")
        or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    llm_chat_model: str = os.getenv("LLM_CHAT_MODEL") or os.getenv("OPENAI_CHAT_MODEL") or os.getenv("QWEN_CHAT_MODEL", "qwen-max")
    llm_embedding_model: str = (
        os.getenv("LLM_EMBEDDING_MODEL")
        or os.getenv("OPENAI_EMBEDDING_MODEL")
        or os.getenv("QWEN_EMBEDDING_MODEL", "text-embedding-v4")
    )
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0"))
    llm_use_responses_api: bool = _bool_env("LLM_USE_RESPONSES_API", "true")

    # Backward-compatible aliases for extracted modules that still use Qwen names.
    qwen_api_key: str | None = llm_api_key
    qwen_base_url: str | None = llm_base_url
    langchain_model: str = llm_chat_model
    langchain_embedding_model: str = llm_embedding_model

    vector_backend: str = os.getenv("VECTOR_BACKEND", "milvus")
    knowledge_vector_store_dir: str = os.getenv(
        "KNOWLEDGE_VECTOR_STORE_DIR",
        str(PROJECT_ROOT / "knowledge" / "ingested" / "laws_faiss"),
    )
    milvus_uri: str = os.getenv("MILVUS_URI", "http://127.0.0.1:19530")
    milvus_collection_name: str = os.getenv("MILVUS_COLLECTION_NAME", "legal_knowledge_chunks")
    milvus_consistency_level: str = os.getenv("MILVUS_CONSISTENCY_LEVEL", "Session")
    retrieval_enable_rerank: bool = _bool_env("RETRIEVAL_ENABLE_RERANK", "true")
    rerank_model: str = os.getenv("RERANK_MODEL", "qwen3-rerank")
    rerank_endpoint: str | None = os.getenv("RERANK_ENDPOINT")
    retrieval_fetch_k: int = int(os.getenv("RETRIEVAL_FETCH_K", "12"))
    retrieval_final_k: int = int(os.getenv("RETRIEVAL_FINAL_K", "4"))
    retrieval_enable_hybrid: bool = _bool_env("RETRIEVAL_ENABLE_HYBRID", "true")
    retrieval_dense_pool_k: int = int(os.getenv("RETRIEVAL_DENSE_POOL_K", "36"))
    rerank_timeout_seconds: int = int(os.getenv("RERANK_TIMEOUT_SECONDS", "8"))
    rerank_max_retries: int = int(os.getenv("RERANK_MAX_RETRIES", "0"))
    react_max_steps: int = int(os.getenv("REACT_MAX_STEPS", "3"))
    postgres_dsn: str | None = os.getenv("POSTGRES_DSN", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/contract_agent")
    max_upload_size_bytes: int = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(5 * 1024 * 1024)))
    max_redraft_chunk_chars: int = int(os.getenv("MAX_REDRAFT_CHUNK_CHARS", "12000"))


settings = Settings()
