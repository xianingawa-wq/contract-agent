from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.models import DetectorResult, ParsedDocument


class DetectorContext(BaseModel):
    document: ParsedDocument
    config: ParserConfig
    registry: object

    class Config:
        arbitrary_types_allowed = True


class DocumentDetector(Protocol):
    name: str

    def detect(self, context: DetectorContext) -> list[DetectorResult]: ...
