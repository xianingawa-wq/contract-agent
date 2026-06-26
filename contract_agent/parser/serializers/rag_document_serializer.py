from __future__ import annotations

from typing import Any

from contract_agent.parser.models import ParsedDocument


def to_rag_documents(document: ParsedDocument) -> list[dict[str, Any]]:
    if document.clause_chunks:
        return [
            {
                "page_content": chunk.source_text,
                "metadata": {
                    "doc_id": document.metadata.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "chunk_level": chunk.chunk_level,
                    "clause_no": chunk.clause_no,
                    "section_title": chunk.section_title,
                    "page_no": chunk.page_no,
                    "source_path": document.metadata.source_path,
                },
            }
            for chunk in document.clause_chunks
            if chunk.source_text.strip()
        ]

    if document.blocks:
        return [
            {
                "page_content": block.text,
                "metadata": {
                    "doc_id": document.metadata.doc_id,
                    "block_id": block.block_id,
                    "clause_no": block.metadata.get("clause_no"),
                    "page_no": block.location.page_no,
                    "source_path": document.metadata.source_path,
                },
            }
            for block in document.blocks
            if block.text.strip()
        ]

    return [
        {
            "page_content": chunk.source_text,
            "metadata": {
                "doc_id": document.metadata.doc_id,
                "block_id": None,
                "clause_no": chunk.clause_no,
                "page_no": chunk.page_no,
                "source_path": document.metadata.source_path,
            },
        }
        for chunk in document.clause_chunks
    ]
