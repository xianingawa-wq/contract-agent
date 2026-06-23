from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from contract_agent.config.config_model import ModelEndpointConfig, ModelRole, ModelRuntimeConfig
from contract_agent.config.config_multiagent import MultiAgentConfig
from contract_agent.config.config_retrieval import RetrievalConfig
from contract_agent.config.config_runtime import PROJECT_ROOT, Settings


class AppSection(BaseModel):
    name: str = "Contract Review Agent"
    default_contract_type: str = "采购合同"


class ModelEndpointSection(BaseModel):
    provider: str = "openai_compatible"
    base_url: str | None = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: str | None = None
    model: str
    endpoint: str | None = None

    def to_endpoint(self, role: ModelRole) -> ModelEndpointConfig:
        return ModelEndpointConfig(
            role=role,
            provider=self.provider,
            base_url=self.base_url or "",
            api_key=self.api_key or "",
            model=self.model,
            endpoint=self.endpoint,
        )


class ModelsSection(BaseModel):
    chat: ModelEndpointSection = Field(
        default_factory=lambda: ModelEndpointSection(model="qwen-max")
    )
    embedding: ModelEndpointSection = Field(
        default_factory=lambda: ModelEndpointSection(model="text-embedding-v4")
    )
    rerank: ModelEndpointSection = Field(
        default_factory=lambda: ModelEndpointSection(provider="qwen", model="qwen3-rerank")
    )


class ProviderSection(BaseModel):
    temperature: float = 0
    use_responses_api: bool = True
    embedding_batch_size: int = 10


class RetrievalSection(BaseModel):
    enable_rerank: bool = True
    enable_hybrid: bool = True
    fetch_k: int = 12
    final_k: int = 4
    dense_pool_k: int = 36
    rerank_timeout_seconds: int = 8
    rerank_max_retries: int = 0


class VectorStoreSection(BaseModel):
    backend: str = "milvus"
    knowledge_vector_store_dir: str = str(PROJECT_ROOT / "knowledge" / "ingested" / "laws_faiss")
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_collection_name: str = "legal_knowledge_chunks"
    milvus_consistency_level: str = "Session"
    milvus_retry_max: int = 3


class DatabaseSection(BaseModel):
    postgres_dsn: str | None = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/contract_agent"
    )


class GrpcSection(BaseModel):
    port: int = 50051
    max_workers: int = 16
    max_message_bytes: int = 10 * 1024 * 1024


class LimitsSection(BaseModel):
    react_max_steps: int = 3
    max_upload_size_bytes: int = 5 * 1024 * 1024
    max_redraft_chunk_chars: int = 12000
    stream_max_seconds: float = 24.0
    stream_max_chars: int = 900


class ProfileSection(BaseModel):
    path: str = str(PROJECT_ROOT / ".run" / "cli_profile.yaml")


class AppConfig(BaseModel):
    app: AppSection = Field(default_factory=AppSection)
    models: ModelsSection = Field(default_factory=ModelsSection)
    provider: ProviderSection = Field(default_factory=ProviderSection)
    retrieval: RetrievalSection = Field(default_factory=RetrievalSection)
    vector_store: VectorStoreSection = Field(default_factory=VectorStoreSection)
    database: DatabaseSection = Field(default_factory=DatabaseSection)
    multiagent: MultiAgentConfig = Field(default_factory=MultiAgentConfig)
    grpc: GrpcSection = Field(default_factory=GrpcSection)
    limits: LimitsSection = Field(default_factory=LimitsSection)
    profile: ProfileSection = Field(default_factory=ProfileSection)

    def to_model_runtime_config(self) -> ModelRuntimeConfig:
        return ModelRuntimeConfig(
            chat=self.models.chat.to_endpoint(ModelRole.CHAT),
            embedding=self.models.embedding.to_endpoint(ModelRole.EMBEDDING),
            rerank=self.models.rerank.to_endpoint(ModelRole.RERANK),
        )

    def to_retrieval_config(self) -> RetrievalConfig:
        return RetrievalConfig(
            enable_rerank=self.retrieval.enable_rerank,
            enable_hybrid=self.retrieval.enable_hybrid,
            fetch_k=self.retrieval.fetch_k,
            final_k=self.retrieval.final_k,
            dense_pool_k=self.retrieval.dense_pool_k,
        )

    def to_multiagent_config(self) -> MultiAgentConfig:
        values = self.multiagent.__dict__.copy()
        values["milvus_retry_max"] = self.vector_store.milvus_retry_max
        return MultiAgentConfig(**values)

    def to_settings(self) -> Settings:
        return Settings(
            app_name=self.app.name,
            default_contract_type=self.app.default_contract_type,
            llm_provider=self.models.chat.provider,
            llm_api_key=self.models.chat.api_key,
            llm_base_url=self.models.chat.base_url,
            llm_chat_model=self.models.chat.model,
            llm_embedding_model=self.models.embedding.model,
            llm_temperature=self.provider.temperature,
            llm_use_responses_api=self.provider.use_responses_api,
            embedding_batch_size=self.provider.embedding_batch_size,
            chat_provider=self.models.chat.provider,
            chat_api_key=self.models.chat.api_key,
            chat_base_url=self.models.chat.base_url,
            chat_model=self.models.chat.model,
            embedding_provider=self.models.embedding.provider,
            embedding_api_key=self.models.embedding.api_key,
            embedding_base_url=self.models.embedding.base_url,
            embedding_model=self.models.embedding.model,
            qwen_api_key=self.models.chat.api_key,
            qwen_base_url=self.models.chat.base_url,
            langchain_model=self.models.chat.model,
            langchain_embedding_model=self.models.embedding.model,
            vector_backend=self.vector_store.backend,
            knowledge_vector_store_dir=self.vector_store.knowledge_vector_store_dir,
            milvus_uri=self.vector_store.milvus_uri,
            milvus_collection_name=self.vector_store.milvus_collection_name,
            milvus_consistency_level=self.vector_store.milvus_consistency_level,
            retrieval_enable_rerank=self.retrieval.enable_rerank,
            rerank_provider=self.models.rerank.provider,
            rerank_api_key=self.models.rerank.api_key,
            rerank_base_url=self.models.rerank.base_url,
            rerank_model=self.models.rerank.model,
            rerank_endpoint=self.models.rerank.endpoint,
            retrieval_fetch_k=self.retrieval.fetch_k,
            retrieval_final_k=self.retrieval.final_k,
            retrieval_enable_hybrid=self.retrieval.enable_hybrid,
            retrieval_dense_pool_k=self.retrieval.dense_pool_k,
            rerank_timeout_seconds=self.retrieval.rerank_timeout_seconds,
            rerank_max_retries=self.retrieval.rerank_max_retries,
            react_max_steps=self.limits.react_max_steps,
            postgres_dsn=self.database.postgres_dsn,
            max_upload_size_bytes=self.limits.max_upload_size_bytes,
            max_redraft_chunk_chars=self.limits.max_redraft_chunk_chars,
            stream_max_seconds=self.limits.stream_max_seconds,
            stream_max_chars=self.limits.stream_max_chars,
        )


@dataclass(frozen=True)
class AppContext:
    config: AppConfig
    settings: Settings
    model_config: ModelRuntimeConfig
    retrieval_config: RetrievalConfig
    multiagent_config: MultiAgentConfig
