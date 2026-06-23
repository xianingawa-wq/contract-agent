from __future__ import annotations

from typing import Any

from contract_agent.parser.models import ParsedDocument


def to_plain_text(document: ParsedDocument) -> str:
    if not document.blocks:
        return document.raw_text
    parts = [block.text.strip() for block in document.blocks if block.text.strip()]
    return "\n".join(parts)


def to_markdown(document: ParsedDocument) -> str:
    if document.markdown_content:
        return document.markdown_content
    if not document.blocks:
        return document.raw_text

    lines: list[str] = []
    for block in document.blocks:
        text = block.markdown or block.text.strip()
        if not text:
            continue
        if block.block_type == "title":
            lines.append(f"# {text}")
        elif block.block_type == "clause_header":
            level = min(max(block.level or 2, 2), 6)
            lines.append(f"{'#' * level} {text}")
        elif block.block_type == "list_item":
            lines.append(f"- {text}")
        elif block.block_type == "table":
            lines.append(block.markdown or text)
        else:
            lines.append(text)
    return "\n\n".join(lines)


def to_llm_context(document: ParsedDocument, *, max_chars: int | None = None) -> str:
    lines = [
        f"文档: {document.metadata.title or document.metadata.file_name}",
        f"类型: {document.metadata.contract_type_hint or '未知'}",
    ]
    if document.metadata.party_a:
        lines.append(f"甲方: {document.metadata.party_a}")
    if document.metadata.party_b:
        lines.append(f"乙方: {document.metadata.party_b}")

    for block in document.blocks:
        page_no = block.location.page_no if block.location.page_no is not None else "?"
        lines.append(
            "[block_id={block_id} page={page_no} confidence={confidence:.2f}] {text}".format(
                block_id=block.block_id,
                page_no=page_no,
                confidence=block.confidence.score,
                text=block.text,
            )
        )

    if not document.blocks and document.raw_text:
        lines.append(document.raw_text)

    if max_chars is None:
        return "\n".join(lines)

    selected: list[str] = []
    length = 0
    for line in lines:
        next_length = length + len(line) + (1 if selected else 0)
        if selected and next_length > max_chars:
            break
        selected.append(line)
        length = next_length
    return "\n".join(selected)


def to_rag_documents(document: ParsedDocument) -> list[dict[str, Any]]:
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


def to_evidence_json(document: ParsedDocument) -> dict[str, Any]:
    return _json_safe(
        {
            "metadata": document.metadata.model_dump(mode="json"),
            "blocks": [block.model_dump(mode="json") for block in document.blocks],
            "chunks": [chunk.model_dump(mode="json") for chunk in document.clause_chunks],
            "detector_results": [
                result.model_dump(mode="json") for result in document.detector_results
            ],
            "conversion_metadata": document.conversion_metadata,
        }
    )


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return "<bytes>"
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return str(value)
