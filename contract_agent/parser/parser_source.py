from __future__ import annotations

import builtins
import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, model_validator


class ParserSource(BaseModel):
    kind: Literal["text", "bytes", "path"]
    file_name: str
    text: str | None = None
    content: builtins.bytes | None = None
    local_path: Path | None = None
    source_path: str
    file_type: str

    @model_validator(mode="after")
    def _kind_must_match_payload(self) -> "ParserSource":
        if self.kind == "text":
            if self.text is None or self.content is not None or self.local_path is not None:
                raise ValueError("text parser source must provide only text payload")
        elif self.kind == "bytes":
            if self.content is None or self.text is not None or self.local_path is not None:
                raise ValueError("bytes parser source must provide only bytes payload")
        elif self.kind == "path":
            if self.local_path is None or self.text is not None or self.content is not None:
                raise ValueError("path parser source must provide only local_path payload")
        return self

    @classmethod
    def from_text(cls, text: str, *, file_name: str = "inline.txt") -> "ParserSource":
        return cls(
            kind="text",
            file_name=file_name,
            text=text,
            source_path=file_name,
            file_type=_file_type(file_name, default="txt"),
        )

    @classmethod
    def from_bytes(
        cls,
        file_name: str,
        content: builtins.bytes,
        *,
        source_path: str | None = None,
    ) -> "ParserSource":
        return cls(
            kind="bytes",
            file_name=file_name,
            content=content,
            source_path=source_path or file_name,
            file_type=_file_type(file_name),
        )

    @classmethod
    def from_path(cls, path: str | Path) -> "ParserSource":
        resolved = Path(path).expanduser().resolve()
        return cls(
            kind="path",
            file_name=resolved.name,
            local_path=resolved,
            source_path=_local_source_path(resolved),
            file_type=_file_type(resolved.name),
        )


def _file_type(file_name: str, *, default: str | None = None) -> str:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if suffix:
        return suffix
    if default is not None:
        return default
    return ""


def _local_source_path(path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    safe_name = "".join("_" if char in "\r\n\t" else char for char in path.name).strip()
    return f"local:{digest}:{safe_name or 'source'}"
