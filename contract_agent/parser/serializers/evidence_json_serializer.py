from __future__ import annotations

from typing import Any

from contract_agent.parser.models import ParsedDocument


def to_evidence_json(document: ParsedDocument) -> dict[str, Any]:
    return _json_safe(
        {
            "metadata": document.metadata.model_dump(mode="json"),
            "blocks": [block.model_dump(mode="json") for block in document.blocks],
            "chunks": [chunk.model_dump(mode="json") for chunk in document.clause_chunks],
            "tables": [table.model_dump(mode="json") for table in document.tables],
            "figures": [figure.model_dump(mode="json") for figure in document.figures],
            "definitions": [
                definition.model_dump(mode="json") for definition in document.definitions
            ],
            "references": [reference.model_dump(mode="json") for reference in document.references],
            "semantic_graph": (
                document.semantic_graph.model_dump(mode="json")
                if document.semantic_graph is not None
                else None
            ),
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
