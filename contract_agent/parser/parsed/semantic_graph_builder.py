from __future__ import annotations

from contract_agent.parser.models import DocumentSemanticGraph, ParsedDocument


def build_semantic_graph(document: ParsedDocument) -> DocumentSemanticGraph:
    nodes: list[dict[str, object]] = []
    edges: list[dict[str, object]] = []
    doc_node_id = f"doc:{document.metadata.doc_id}"
    nodes.append(
        {
            "id": doc_node_id,
            "type": "document",
            "label": document.metadata.title or document.metadata.file_name,
            "metadata": {
                "file_name": document.metadata.file_name,
                "file_type": document.metadata.file_type,
                "source_path": document.metadata.source_path,
            },
        }
    )

    block_nodes_by_id: dict[str, str] = {}
    block_nodes_by_span_id: dict[str, str] = {}
    ordered_blocks = _blocks_ordered_by_offset(document)
    block_cursor = 0
    for block in document.blocks:
        node_id = f"block:{block.block_id}"
        block_nodes_by_id[block.block_id] = node_id
        for span_id in block.location.span_ids:
            block_nodes_by_span_id[span_id] = node_id
        nodes.append(
            {
                "id": node_id,
                "type": "block",
                "label": _preview(block.text),
                "metadata": {
                    "block_id": block.block_id,
                    "block_type": block.block_type,
                    "page_no": block.location.page_no,
                    "clause_no": block.metadata.get("clause_no"),
                },
            }
        )
        edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})

    for table in document.tables:
        node_id = f"table:{table.table_id}"
        nodes.append(
            {
                "id": node_id,
                "type": "table",
                "label": table.caption or table.table_id,
                "metadata": {
                    "table_id": table.table_id,
                    "page_no": table.page_no,
                    "row_count": len(table.rows),
                },
            }
        )
        edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
        for span_id in table.span_ids:
            block_node_id = block_nodes_by_span_id.get(span_id)
            if block_node_id:
                edges.append({"source": node_id, "target": block_node_id, "type": "derived_from"})

    previous_chunk_node_id: str | None = None
    for chunk in document.clause_chunks:
        node_id = f"chunk:{chunk.chunk_id}"
        nodes.append(
            {
                "id": node_id,
                "type": "chunk",
                "label": chunk.section_title,
                "metadata": {
                    "chunk_id": chunk.chunk_id,
                    "chunk_level": chunk.chunk_level,
                    "clause_no": chunk.clause_no,
                    "page_no": chunk.page_no,
                },
            }
        )
        edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
        if previous_chunk_node_id:
            edges.append({"source": previous_chunk_node_id, "target": node_id, "type": "next"})
        previous_chunk_node_id = node_id
        block, block_cursor = _next_block_for_chunk(
            ordered_blocks,
            block_cursor,
            chunk.start_offset,
            chunk.end_offset,
        )
        if block is not None:
            block_node_id = block_nodes_by_id.get(block.block_id)
            if block_node_id:
                edges.append({"source": node_id, "target": block_node_id, "type": "derived_from"})

    for index, definition in enumerate(document.definitions):
        node_id = f"definition:{index}:{definition.term}"
        nodes.append(
            {
                "id": node_id,
                "type": "definition",
                "label": definition.term,
                "metadata": definition.model_dump(mode="json"),
            }
        )
        edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
        if definition.span_id and definition.span_id in block_nodes_by_span_id:
            edges.append(
                {
                    "source": node_id,
                    "target": block_nodes_by_span_id[definition.span_id],
                    "type": "defined_in",
                }
            )

    for index, reference in enumerate(document.references):
        node_id = f"reference:{index}"
        nodes.append(
            {
                "id": node_id,
                "type": "reference",
                "label": reference.target,
                "metadata": reference.model_dump(mode="json"),
            }
        )
        edges.append({"source": doc_node_id, "target": node_id, "type": "contains"})
        if reference.source_span_id and reference.source_span_id in block_nodes_by_span_id:
            edges.append(
                {
                    "source": block_nodes_by_span_id[reference.source_span_id],
                    "target": node_id,
                    "type": "references",
                }
            )

    return DocumentSemanticGraph(
        nodes=nodes,
        edges=edges,
        metadata={"node_count": len(nodes), "edge_count": len(edges)},
    )


def _blocks_ordered_by_offset(document: ParsedDocument) -> list:
    return sorted(
        [
            block
            for block in document.blocks
            if block.location.start_offset is not None and block.location.end_offset is not None
        ],
        key=lambda block: (block.location.start_offset, block.location.end_offset),
    )


def _next_block_for_chunk(
    ordered_blocks: list,
    cursor: int,
    start_offset: int,
    end_offset: int,
) -> tuple[object | None, int]:
    while (
        cursor < len(ordered_blocks)
        and ordered_blocks[cursor].location.end_offset is not None
        and ordered_blocks[cursor].location.end_offset < start_offset
    ):
        cursor += 1
    if cursor >= len(ordered_blocks):
        return None, cursor
    block = ordered_blocks[cursor]
    if block.location.start_offset is not None and block.location.start_offset <= end_offset:
        return block, cursor
    return None, cursor


def _preview(text: str, limit: int = 120) -> str:
    stripped = text.strip()
    return stripped if len(stripped) <= limit else stripped[:limit] + "..."
