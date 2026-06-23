from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from contract_agent.config import PROJECT_ROOT


DEFAULT_AUDIT_LOG_PATH = PROJECT_ROOT / ".run" / "audit.jsonl"
_trace_id_var: ContextVar[str | None] = ContextVar("contract_agent_trace_id", default=None)
_span_stack_var: ContextVar[tuple[str, ...]] = ContextVar("contract_agent_span_stack", default=())


@dataclass
class AuditLogger:
    path: Path = DEFAULT_AUDIT_LOG_PATH
    scope: str = "audit"
    prefix: str = "[Audit]"
    _extra: dict[str, Any] = field(default_factory=dict)

    def emit(self, event: str, **payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scope": self.scope,
            "prefix": self.prefix,
            "event": event,
        }
        record.update(self._current_context())
        if self._extra:
            record.update(self._extra)
        record.update(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")

    def with_prefix(self, prefix: str, *, scope: str | None = None, **extra: Any) -> "AuditLogger":
        merged_extra = dict(self._extra)
        merged_extra.update(extra)
        return AuditLogger(
            path=self.path,
            scope=scope or self.scope,
            prefix=prefix,
            _extra=merged_extra,
        )

    @contextmanager
    def trace(self, operation: str, *, trace_id: str | None = None, **payload: Any) -> Iterator[str]:
        active_trace_id = _trace_id_var.get() or trace_id or uuid.uuid4().hex
        trace_token = _trace_id_var.set(active_trace_id)
        stack_token = _span_stack_var.set(())
        started = time.perf_counter()
        self.emit("trace.started", operation=operation, **payload)
        try:
            yield active_trace_id
        except Exception as exc:
            self.emit(
                "trace.failed",
                operation=operation,
                duration_ms=self._elapsed_ms(started),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise
        else:
            self.emit("trace.completed", operation=operation, duration_ms=self._elapsed_ms(started))
        finally:
            _span_stack_var.reset(stack_token)
            _trace_id_var.reset(trace_token)

    @contextmanager
    def span(self, name: str, **payload: Any) -> Iterator[str]:
        stack = _span_stack_var.get()
        parent_span_id = stack[-1] if stack else None
        span_id = uuid.uuid4().hex
        token = _span_stack_var.set((*stack, span_id))
        started = time.perf_counter()
        self.emit(
            "span.started",
            span_name=name,
            span_id=span_id,
            parent_span_id=parent_span_id,
            **payload,
        )
        try:
            yield span_id
        except Exception as exc:
            self.emit(
                "span.failed",
                span_name=name,
                span_id=span_id,
                parent_span_id=parent_span_id,
                duration_ms=self._elapsed_ms(started),
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise
        else:
            self.emit(
                "span.completed",
                span_name=name,
                span_id=span_id,
                parent_span_id=parent_span_id,
                duration_ms=self._elapsed_ms(started),
            )
        finally:
            _span_stack_var.reset(token)

    def _current_context(self) -> dict[str, str]:
        trace_id = _trace_id_var.get()
        stack = _span_stack_var.get()
        context: dict[str, str] = {}
        if trace_id:
            context["trace_id"] = trace_id
        if stack:
            context["span_id"] = stack[-1]
            if len(stack) > 1:
                context["parent_span_id"] = stack[-2]
        return context

    def _elapsed_ms(self, started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)


def get_audit_logger(path: Path | None = None) -> AuditLogger:
    return AuditLogger(path or DEFAULT_AUDIT_LOG_PATH)
