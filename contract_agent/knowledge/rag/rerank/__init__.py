__all__ = ["Reranker", "RerankResult"]


def __getattr__(name: str):
    if name in {"Reranker", "RerankResult"}:
        from contract_agent.knowledge.rag.rerank.interface import Reranker, RerankResult

        return {"Reranker": Reranker, "RerankResult": RerankResult}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
