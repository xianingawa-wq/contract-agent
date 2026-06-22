from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import select

from contract_agent.knowledge.models import KnowledgeChunkModel
from contract_agent.runtime.config import Settings, settings_snapshot
from contract_agent.runtime.database import session_scope
from contract_agent.runtime.schema import ensure_runtime_schema
from contract_agent.schemas.knowledge import KnowledgeChunk


class KnowledgeChunkRepository:
    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.settings = runtime_settings or settings_snapshot()
        if not self.settings.postgres_dsn:
            raise RuntimeError("POSTGRES_DSN 未配置，无法持久化知识块元数据。")
        ensure_runtime_schema(self.settings)

    def upsert_chunks(self, chunks: list[KnowledgeChunk], *, version: str) -> int:
        if not chunks:
            return 0

        inserted = 0
        with session_scope(self.settings) as session:
            for chunk in chunks:
                row = session.scalar(
                    select(KnowledgeChunkModel).where(KnowledgeChunkModel.chunk_id == chunk.chunk_id)
                )
                if row is None:
                    row = KnowledgeChunkModel(chunk_id=chunk.chunk_id)
                    session.add(row)
                    inserted += 1

                row.doc_id = chunk.doc_name
                row.source_path = chunk.source_path
                row.version = version
                row.content_hash = hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
                row.ingested_at = datetime.now(timezone.utc)
        return inserted
