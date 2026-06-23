from sqlalchemy import text

from contract_agent.knowledge.models import Base as KnowledgeBase
from contract_agent.memory.models import Base as MemoryBase
from contract_agent.config import Settings
from contract_agent.runtime.database import get_engine


def ensure_runtime_schema(runtime_settings: Settings | None = None, *, dsn: str | None = None) -> None:
    engine = get_engine(runtime_settings, dsn=dsn)
    KnowledgeBase.metadata.create_all(bind=engine)
    MemoryBase.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_doc_version "
                "ON knowledge_chunks (doc_id, version)"
            )
        )
