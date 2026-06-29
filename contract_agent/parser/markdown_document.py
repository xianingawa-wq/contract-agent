from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MarkdownDocument(BaseModel):
    markdown_content: str
    file_name: str
    file_type: str
    source_path: str
    backend_name: str
    html_content: str = ""
    warnings: list[str] = Field(default_factory=list)
    conversion_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("conversion_metadata")
    @classmethod
    def _conversion_metadata_must_be_json_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        _ensure_json_safe(value)
        return value


def _ensure_json_safe(value: Any) -> None:
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parser metadata fields must be JSON-compatible")
        return
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
