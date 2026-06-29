from __future__ import annotations

import logging
import re
from pathlib import PurePath
from typing import Any

from contract_agent.logger.base import ComponentLogger, LogEvent, get_component_logger


PARSER_LOGGER_NAME = "contract_agent.parser"
ParserLogStage = str


def get_parser_logger() -> ComponentLogger:
    return get_component_logger(PARSER_LOGGER_NAME, "Parser")


def parser_log_event(
    stage: ParserLogStage,
    message: str,
    *args: Any,
    level: int = logging.INFO,
) -> LogEvent:
    return LogEvent(level, stage, message, args)


def safe_source_label(source_path: str | None) -> str:
    if not source_path:
        return "unknown"
    compact = re.sub(r"[\r\n\t]+", "/", str(source_path)).strip()
    if not compact:
        return "unknown"
    if compact.startswith("local:"):
        return compact
    normalized = compact.replace("\\", "/")
    return PurePath(normalized).name or "source"


def safe_log_text(value: object, *, max_chars: int = 240) -> str:
    compact = re.sub(r"[\r\n\t]+", " ", str(value)).strip()
    if len(compact) > max_chars:
        return compact[: max_chars - 3] + "..."
    return compact
