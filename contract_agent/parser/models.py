from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DocumentMetadata(BaseModel):
    doc_id: str
    file_name: str
    file_type: str
    source_path: str
    title: str | None = None
    contract_type_hint: str | None = None
    party_a: str | None = None
    party_b: str | None = None
    signed_date: str | None = None
    page_count: int = 0


class DocumentSpan(BaseModel):
    span_id: str
    page_no: int | None = Field(default=None, ge=1)
    block_index: int = Field(ge=0)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    text: str

    def model_post_init(self, __context: Any) -> None:
        if self.end_offset < self.start_offset:
            raise ValueError("end_offset must not be smaller than start_offset")


class ClauseChunk(BaseModel):
    chunk_id: str
    chunk_level: str
    clause_no: str | None = None
    parent_clause_no: str | None = None
    section_title: str
    page_no: int | None = Field(default=None, ge=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    source_text: str
    prev_chunk_id: str | None = None
    next_chunk_id: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if self.end_offset < self.start_offset:
            raise ValueError("end_offset must not be smaller than start_offset")


class BlockLocation(BaseModel):
    page_no: int | None = Field(default=None, ge=1)
    block_index: int = Field(ge=0)
    start_offset: int | None = Field(default=None, ge=0)
    end_offset: int | None = Field(default=None, ge=0)
    span_ids: list[str] = Field(default_factory=list)
    bbox: dict[str, float] | None = None
    source_path: str | None = None

    def model_post_init(self, __context: Any) -> None:
        if (
            self.start_offset is not None
            and self.end_offset is not None
            and self.end_offset < self.start_offset
        ):
            raise ValueError("end_offset must not be smaller than start_offset")


class BlockConfidence(BaseModel):
    score: float = 1.0
    source: str = "builtin"
    reason: str | None = None
    detector_scores: dict[str, float] = Field(default_factory=dict)


class DocumentBlock(BaseModel):
    block_id: str
    block_type: str
    text: str = ""
    markdown: str | None = None
    html: str | None = None
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)
    level: int | None = None
    location: BlockLocation
    confidence: BlockConfidence = Field(default_factory=BlockConfidence)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        _ensure_json_safe(value)
        return value


class DocumentTable(BaseModel):
    table_id: str
    page_no: int | None = None
    span_ids: list[str] = Field(default_factory=list)
    caption: str | None = None
    rows: list[list[str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        _ensure_json_safe(value)
        return value


class DocumentFigure(BaseModel):
    figure_id: str
    page_no: int | None = None
    span_ids: list[str] = Field(default_factory=list)
    caption: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        _ensure_json_safe(value)
        return value


class DocumentDefinition(BaseModel):
    term: str
    definition: str
    span_id: str | None = None
    clause_no: str | None = None


class DocumentReference(BaseModel):
    source_span_id: str | None = None
    target: str
    reference_type: str | None = None
    raw_text: str | None = None


class DocumentSemanticGraph(BaseModel):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("nodes", "edges")
    @classmethod
    def _graph_items_must_be_json_safe(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _ensure_json_safe(value)
        return value

    @field_validator("metadata")
    @classmethod
    def _metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        _ensure_json_safe(value)
        return value


class ParsedDocument(BaseModel):
    schema_version: str = "2.0"
    metadata: DocumentMetadata
    raw_text: str
    spans: list[DocumentSpan] = Field(default_factory=list)
    blocks: list[DocumentBlock] = Field(default_factory=list)
    clause_chunks: list[ClauseChunk] = Field(default_factory=list)
    html_content: str = Field(
        default="", description="Rich HTML representation for formats that support it."
    )
    markdown_content: str = ""
    tables: list[DocumentTable] = Field(default_factory=list)
    figures: list[DocumentFigure] = Field(default_factory=list)
    definitions: list[DocumentDefinition] = Field(default_factory=list)
    references: list[DocumentReference] = Field(default_factory=list)
    semantic_graph: DocumentSemanticGraph | None = None
    conversion_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("conversion_metadata")
    @classmethod
    def _conversion_metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        _ensure_json_safe(value)
        return value


class ParseResponse(BaseModel):
    document: ParsedDocument


def _ensure_json_safe(value: Any) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parser metadata fields must be JSON-compatible")
        return
    if isinstance(value, (bytes, bytearray, memoryview, Path)):
        raise ValueError("parser metadata fields must be JSON-compatible")
    if isinstance(value, list):
        for item in value:
            _ensure_json_safe(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("parser metadata dictionary keys must be strings")
            _ensure_json_safe(item)
        return
    raise ValueError("parser metadata fields must be JSON-compatible")
