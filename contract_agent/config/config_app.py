from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from contract_agent.config.config_parser import (
    DEFAULT_ALLOWED_SUFFIXES,
    DEFAULT_ENABLED_CONVERTERS,
    DEFAULT_ENABLED_DETECTORS,
    ParserConfig,
    derive_effective_max_input_bytes,
)
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
    backend: str = "faiss"
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


class ParserAdapterSection(BaseModel):
    enabled: bool = False


class DoclingAdapterSection(ParserAdapterSection):
    enabled: bool = True
    enable_ocr: bool = True
    ocr_lang: list[str] = Field(default_factory=lambda: ["chinese"])
    force_full_page_ocr: bool = True
    bitmap_area_threshold: float = 0.02
    text_score: float = 0.35
    do_table_structure: bool = True
    compact_tables: bool = True
    enable_remote_services: bool = False


class ParserDetectorsSection(BaseModel):
    enabled: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_DETECTORS.copy())
    profile: str = "builtin_zh_contract_v1"
    rules_path: str | None = None
    min_confidence: float = 0.60
    store_reasons: bool = True


class ParserChunkingSection(BaseModel):
    max_chars: int = 1200
    target_chars: int = 500
    min_header_confidence: float = 0.65


class ParserSection(BaseModel):
    default_converter: str = "docling"
    enabled_converters: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy())
    fallback_order: list[str] = Field(default_factory=lambda: DEFAULT_ENABLED_CONVERTERS.copy())
    allow_converter_fallback: bool = True
    strict_converter_availability: bool = False
    allowed_suffixes: list[str] = Field(default_factory=lambda: DEFAULT_ALLOWED_SUFFIXES.copy())
    allow_path_input: bool = False
    allow_url_input: bool = False
    trusted_path_roots: list[str] = Field(default_factory=list)
    max_input_bytes: int | None = None
    preserve_raw_text: bool = True
    detectors: ParserDetectorsSection = Field(default_factory=ParserDetectorsSection)
    chunking: ParserChunkingSection = Field(default_factory=ParserChunkingSection)
    markitdown: ParserAdapterSection = Field(default_factory=ParserAdapterSection)
    docling: DoclingAdapterSection = Field(default_factory=DoclingAdapterSection)


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
    parser: ParserSection = Field(default_factory=ParserSection)
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

    def to_parser_config(self) -> ParserConfig:
        parser_limit = derive_effective_max_input_bytes(
            parser_limit=self.parser.max_input_bytes,
            upload_limit=self.limits.max_upload_size_bytes,
        )
        return ParserConfig(
            default_converter=self.parser.default_converter,
            enabled_converters=list(self.parser.enabled_converters),
            fallback_order=list(self.parser.fallback_order),
            allow_converter_fallback=self.parser.allow_converter_fallback,
            strict_converter_availability=self.parser.strict_converter_availability,
            allowed_suffixes=list(self.parser.allowed_suffixes),
            allow_path_input=self.parser.allow_path_input,
            allow_url_input=self.parser.allow_url_input,
            trusted_path_roots=list(self.parser.trusted_path_roots),
            max_input_bytes=parser_limit,
            preserve_raw_text=self.parser.preserve_raw_text,
            detector_profile=self.parser.detectors.profile,
            enabled_detectors=list(self.parser.detectors.enabled),
            detector_rules_path=self.parser.detectors.rules_path,
            min_detector_confidence=self.parser.detectors.min_confidence,
            store_detector_reasons=self.parser.detectors.store_reasons,
            chunk_max_chars=self.parser.chunking.max_chars,
            chunk_target_chars=self.parser.chunking.target_chars,
            min_header_confidence=self.parser.chunking.min_header_confidence,
            markitdown_enabled=self.parser.markitdown.enabled,
            docling_enabled=self.parser.docling.enabled,
            docling_enable_ocr=self.parser.docling.enable_ocr,
            docling_ocr_lang=list(self.parser.docling.ocr_lang),
            docling_force_full_page_ocr=self.parser.docling.force_full_page_ocr,
            docling_bitmap_area_threshold=self.parser.docling.bitmap_area_threshold,
            docling_text_score=self.parser.docling.text_score,
            docling_do_table_structure=self.parser.docling.do_table_structure,
            docling_compact_tables=self.parser.docling.compact_tables,
            docling_enable_remote_services=self.parser.docling.enable_remote_services,
        )

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
            parser_default_converter=self.parser.default_converter,
            parser_enabled_converters=list(self.parser.enabled_converters),
            parser_fallback_order=list(self.parser.fallback_order),
            parser_allow_converter_fallback=self.parser.allow_converter_fallback,
            parser_strict_converter_availability=self.parser.strict_converter_availability,
            parser_allowed_suffixes=list(self.parser.allowed_suffixes),
            parser_allow_path_input=self.parser.allow_path_input,
            parser_allow_url_input=self.parser.allow_url_input,
            parser_trusted_path_roots=list(self.parser.trusted_path_roots),
            parser_max_input_bytes=self.parser.max_input_bytes,
            parser_preserve_raw_text=self.parser.preserve_raw_text,
            parser_detector_profile=self.parser.detectors.profile,
            parser_enabled_detectors=list(self.parser.detectors.enabled),
            parser_detector_rules_path=self.parser.detectors.rules_path,
            parser_min_detector_confidence=self.parser.detectors.min_confidence,
            parser_store_detector_reasons=self.parser.detectors.store_reasons,
            parser_chunk_max_chars=self.parser.chunking.max_chars,
            parser_chunk_target_chars=self.parser.chunking.target_chars,
            parser_min_header_confidence=self.parser.chunking.min_header_confidence,
            parser_markitdown_enabled=self.parser.markitdown.enabled,
            parser_docling_enabled=self.parser.docling.enabled,
            parser_docling_enable_ocr=self.parser.docling.enable_ocr,
            parser_docling_ocr_lang=list(self.parser.docling.ocr_lang),
            parser_docling_force_full_page_ocr=self.parser.docling.force_full_page_ocr,
            parser_docling_bitmap_area_threshold=self.parser.docling.bitmap_area_threshold,
            parser_docling_text_score=self.parser.docling.text_score,
            parser_docling_do_table_structure=self.parser.docling.do_table_structure,
            parser_docling_compact_tables=self.parser.docling.compact_tables,
            parser_docling_enable_remote_services=self.parser.docling.enable_remote_services,
        )


@dataclass(frozen=True)
class AppContext:
    config: AppConfig
    settings: Settings
    model_config: ModelRuntimeConfig
    retrieval_config: RetrievalConfig
    multiagent_config: MultiAgentConfig
    parser_config: ParserConfig
