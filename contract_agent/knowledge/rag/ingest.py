from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from contract_agent.runtime.config import Settings, settings_snapshot
from contract_agent.knowledge.repository import KnowledgeChunkRepository
from contract_agent.knowledge.rag.knowledge_documents import build_knowledge_documents
from contract_agent.knowledge.rag.legal_chunker import LegalKnowledgeChunker
from contract_agent.knowledge.rag.vector_store import build_vector_store, save_vector_store
from contract_agent.schemas.knowledge import KnowledgeChunk


class KnowledgeIngestor:
    def __init__(self, runtime_settings: Settings | None = None) -> None:
        self.settings = runtime_settings or settings_snapshot()
        self.legal_chunker = LegalKnowledgeChunker()

    def ingest_laws(
        self,
        source_dir: str = "knowledge/laws",
        output_dir: str = "knowledge/ingested/laws_faiss",
        manifest_path: str = "knowledge/ingested/laws_chunks.jsonl",
    ) -> dict:
        law_dir = Path(source_dir)
        files = sorted([path for path in law_dir.iterdir() if path.is_file() and path.name != ".gitkeep"])
        if not files:
            raise FileNotFoundError(f"No law files found in {law_dir}")

        chunks: list[KnowledgeChunk] = []
        for file_path in files:
            suffix = file_path.suffix.lower()
            if suffix != ".txt":
                continue
            chunks.extend(self.legal_chunker.chunk_file(str(file_path)))

        if not chunks:
            raise ValueError("No legal chunks were generated. Check file format or directory contents.")

        self._write_manifest(chunks, manifest_path)
        documents = build_knowledge_documents(chunks)
        vector_store = build_vector_store(documents, runtime_settings=self.settings)
        save_vector_store(vector_store, output_dir, runtime_settings=self.settings)

        metadata_rows = self._persist_chunk_metadata(chunks)
        return {
            "file_count": len(files),
            "chunk_count": len(chunks),
            "metadata_rows": metadata_rows,
            "manifest_path": manifest_path,
            "vector_store_dir": output_dir,
            "vector_backend": self.settings.vector_backend,
        }

    def _write_manifest(self, chunks: list[KnowledgeChunk], manifest_path: str) -> None:
        path = Path(manifest_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")

    def _persist_chunk_metadata(self, chunks: list[KnowledgeChunk]) -> int:
        if not self.settings.postgres_dsn:
            return 0
        version = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        repository = KnowledgeChunkRepository(runtime_settings=self.settings)
        return repository.upsert_chunks(chunks, version=version)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest legal knowledge into a persistent vector store.")
    parser.add_argument("--source-dir", default="knowledge/laws")
    parser.add_argument("--output-dir", default="knowledge/ingested/laws_faiss")
    parser.add_argument("--manifest-path", default="knowledge/ingested/laws_chunks.jsonl")
    args = parser.parse_args()

    result = KnowledgeIngestor().ingest_laws(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        manifest_path=args.manifest_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
