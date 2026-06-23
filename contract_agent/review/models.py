from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass(frozen=True)
class ReviewRequest:
    text: str
    contract_type: str | None = None
    our_side: str = "甲方"


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    title: str
    evidence: str
    reason: str
    suggestion: str
    clause: str | None = None
    domain: str | None = None


@dataclass
class ReviewReport:
    summary: str
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    llm_used: bool = False
