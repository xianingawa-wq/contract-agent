from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.parser_source import ParserSource


class ParserBackendSupport(BaseModel):
    supported: bool
    confidence: float = 0
    reason: str | None = None
    can_fallback: bool = False


class ParserBackend(Protocol):
    name: str

    def supports(self, source: ParserSource, config: ParserConfig) -> ParserBackendSupport: ...

    def convert(self, source: ParserSource, config: ParserConfig) -> MarkdownDocument: ...
