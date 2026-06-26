from __future__ import annotations

import builtins
from pathlib import Path
from typing import Literal

from pydantic import BaseModel


class ParserSource(BaseModel):
    kind: Literal["text", "bytes", "path"]
    file_name: str
    text: str | None = None
    content: builtins.bytes | None = None
    local_path: Path | None = None
    source_path: str
    file_type: str

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
            source_path=str(resolved),
            file_type=_file_type(resolved.name),
        )


def _file_type(file_name: str, *, default: str | None = None) -> str:
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if suffix:
        return suffix
    if default is not None:
        return default
    return ""
