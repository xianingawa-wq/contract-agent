__all__ = ["Base", "KnowledgeChunkModel", "KnowledgeChunkRepository"]


def __getattr__(name: str):
    if name in {"Base", "KnowledgeChunkModel"}:
        from contract_agent.knowledge.models import Base, KnowledgeChunkModel

        return {"Base": Base, "KnowledgeChunkModel": KnowledgeChunkModel}[name]
    if name == "KnowledgeChunkRepository":
        from contract_agent.knowledge.repository import KnowledgeChunkRepository

        return KnowledgeChunkRepository
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
