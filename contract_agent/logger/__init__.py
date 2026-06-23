from contract_agent.logger.base import (
    ComponentLogger,
    Debug,
    Error,
    Info,
    LogEvent,
    Warn,
    get_component_logger,
)

__all__ = [
    "AuditLogger",
    "ComponentLogger",
    "Debug",
    "Error",
    "Info",
    "LogEvent",
    "Warn",
    "get_audit_logger",
    "get_component_logger",
]


def __getattr__(name: str):
    if name in {"AuditLogger", "get_audit_logger"}:
        from contract_agent.logger.audit import AuditLogger, get_audit_logger

        exports = {
            "AuditLogger": AuditLogger,
            "get_audit_logger": get_audit_logger,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
