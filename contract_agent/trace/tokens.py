from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


TokenDirection = Literal["input", "output"]


class TokenUsageRecord(BaseModel):
    label: str
    direction: TokenDirection
    estimated_tokens: int
    text_length: int


class TraceSummary(BaseModel):
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_total_tokens: int = 0
    records: list[TokenUsageRecord] = Field(default_factory=list)


def estimate_tokens(text: object) -> int:
    content = "" if text is None else str(text)
    if not content:
        return 0
    return max(1, (len(content) + 3) // 4)


class TokenTrace:
    def __init__(self) -> None:
        self._records: list[TokenUsageRecord] = []

    def add_input(self, label: str, text: object) -> TokenUsageRecord:
        return self._add(label=label, direction="input", text=text)

    def add_output(self, label: str, text: object) -> TokenUsageRecord:
        return self._add(label=label, direction="output", text=text)

    def summary(self) -> TraceSummary:
        input_tokens = sum(
            record.estimated_tokens for record in self._records if record.direction == "input"
        )
        output_tokens = sum(
            record.estimated_tokens for record in self._records if record.direction == "output"
        )
        return TraceSummary(
            estimated_input_tokens=input_tokens,
            estimated_output_tokens=output_tokens,
            estimated_total_tokens=input_tokens + output_tokens,
            records=list(self._records),
        )

    def _add(self, *, label: str, direction: TokenDirection, text: object) -> TokenUsageRecord:
        content = "" if text is None else str(text)
        record = TokenUsageRecord(
            label=label,
            direction=direction,
            estimated_tokens=estimate_tokens(content),
            text_length=len(content),
        )
        self._records.append(record)
        return record
