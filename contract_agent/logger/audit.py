from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contract_agent.runtime.config import PROJECT_ROOT


DEFAULT_AUDIT_LOG_PATH = PROJECT_ROOT / ".run" / "audit.jsonl"


@dataclass
class AuditLogger:
    path: Path = DEFAULT_AUDIT_LOG_PATH
    scope: str = "audit"
    _extra: dict[str, Any] = field(default_factory=dict)

    def emit(self, event: str, **payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scope": self.scope,
            "event": event,
        }
        if self._extra:
            record.update(self._extra)
        record.update(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def get_audit_logger(path: Path | None = None) -> AuditLogger:
    return AuditLogger(path or DEFAULT_AUDIT_LOG_PATH)
