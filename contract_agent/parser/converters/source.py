from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from contract_agent.parser.converters.base import ParseSource


@contextmanager
def local_converter_source(source: ParseSource) -> Iterator[str]:
    if source.kind == "path":
        yield str(Path(source.local_path or source.source_path).expanduser().resolve())
        return

    suffix = Path(source.file_name).suffix or ".txt"
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            temp_path = Path(temp.name)
            if source.kind == "bytes":
                temp.write(source.content or b"")
            else:
                temp.write((source.text or "").encode("utf-8"))
        yield str(temp_path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
