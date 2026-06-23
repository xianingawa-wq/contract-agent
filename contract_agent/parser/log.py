from __future__ import annotations

import logging
from typing import Any, Literal

from contract_agent.logger.base import ComponentLogger, LogEvent, get_component_logger


PARSER_LOGGER_NAME = "contract_agent.parser"
ParserLogStage = Literal["Convert", "Detector"]


def get_parser_logger() -> ComponentLogger:
    return get_component_logger(PARSER_LOGGER_NAME, "Parser")


def parser_log_event(
    stage: ParserLogStage,
    message: str,
    *args: Any,
    level: int = logging.INFO,
) -> LogEvent:
    return LogEvent(level, stage, message, args)
