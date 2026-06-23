from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from contract_agent.parser.exceptions import ParserError, ReviewInputError
from contract_agent.parser.models import ParsedDocument
from contract_agent.parser.service import ContractParser


ReviewSourceKind = Literal["text", "bytes", "path", "grpc_file"]


class ParsedReviewInput(BaseModel):
    document: ParsedDocument
    contract_text: str
    source_kind: ReviewSourceKind
    contract_type: str | None = None
    our_side: str | None = None


def normalize_review_input(
    *,
    contract_text: str | None = None,
    file_name: str | None = None,
    content: bytes | None = None,
    file_path: str | Path | None = None,
    source_kind: ReviewSourceKind | None = None,
    contract_type: str | None = None,
    our_side: str | None = None,
    parser: ContractParser | None = None,
) -> ParsedReviewInput:
    parser = parser or ContractParser()
    source_count = sum(
        [
            bool(contract_text and contract_text.strip()),
            content is not None,
            file_path is not None,
        ]
    )
    if source_count != 1:
        raise ReviewInputError("review 输入必须且只能提供一种正文来源。")

    if contract_text is not None:
        if not contract_text.strip():
            raise ReviewInputError("合同文本为空，无法审查。")
        _ensure_source_kind(source_kind, "text")
        document = parser.parse_text(contract_text)
        resolved_kind: ReviewSourceKind = "text"
    elif content is not None:
        if not file_name:
            raise ReviewInputError("文件输入缺少 file_name。")
        if not content:
            raise ReviewInputError("文件内容为空，无法审查。")
        if source_kind not in (None, "bytes", "grpc_file"):
            raise ReviewInputError("source_kind 与文件 bytes 输入不匹配。")
        document = parser.parse_bytes(file_name, content)
        resolved_kind = source_kind or "bytes"
    else:
        if file_path is None:
            raise ReviewInputError("review 输入为空。")
        _ensure_source_kind(source_kind, "path")
        try:
            document = parser.parse_path(file_path)
        except ParserError as exc:
            raise ReviewInputError(str(exc)) from exc
        resolved_kind = "path"

    return ParsedReviewInput(
        document=document,
        contract_text=document.raw_text,
        source_kind=resolved_kind,
        contract_type=contract_type,
        our_side=our_side,
    )


def _ensure_source_kind(source_kind: ReviewSourceKind | None, expected: ReviewSourceKind) -> None:
    if source_kind is not None and source_kind != expected:
        raise ReviewInputError("source_kind 与输入来源不匹配。")
