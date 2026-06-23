from __future__ import annotations

from dataclasses import dataclass

from contract_agent.config.config_runtime import Settings, settings_snapshot


@dataclass(frozen=True)
class RetrievalConfig:
    enable_rerank: bool
    enable_hybrid: bool
    fetch_k: int
    final_k: int
    dense_pool_k: int

    @classmethod
    def from_settings(cls, runtime_settings: Settings | None = None) -> "RetrievalConfig":
        source = runtime_settings or settings_snapshot()
        return cls(
            enable_rerank=source.retrieval_enable_rerank,
            enable_hybrid=source.retrieval_enable_hybrid,
            fetch_k=source.retrieval_fetch_k,
            final_k=source.retrieval_final_k,
            dense_pool_k=source.retrieval_dense_pool_k,
        )
