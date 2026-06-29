from __future__ import annotations

import hashlib

from contract_agent.parser.models import DocumentMetadata, DocumentSpan


def build_metadata(
    *,
    file_name: str,
    source_path: str,
    file_type: str,
    raw_text: str,
    spans: list[DocumentSpan],
) -> DocumentMetadata:
    return DocumentMetadata(
        doc_id=_doc_id(source_path, raw_text),
        file_name=file_name,
        file_type=file_type,
        source_path=source_path,
        title=_extract_title(raw_text, file_name),
        page_count=max(1, max((span.page_no or 0) for span in spans)) if spans else 1,
    )


def _extract_title(raw_text: str, fallback: str) -> str:
    for line in raw_text.splitlines():
        clean = line.strip()
        if clean:
            return clean[:100]
    return fallback


def _doc_id(source: str, raw_text: str) -> str:
    digest = hashlib.md5(f"{source}\0{raw_text}".encode("utf-8")).hexdigest()[:12]
    return f"doc_{digest}"
