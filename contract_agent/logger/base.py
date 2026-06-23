from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LogEvent:
    level: int
    level_label: str
    message: str
    args: tuple[Any, ...] = ()


def Debug(message: str, *args: Any) -> LogEvent:
    return LogEvent(logging.DEBUG, "Debug", message, args)


def Info(message: str, *args: Any) -> LogEvent:
    return LogEvent(logging.INFO, "Info", message, args)


def Warn(message: str, *args: Any) -> LogEvent:
    return LogEvent(logging.WARNING, "Warn", message, args)


def Error(message: str, *args: Any) -> LogEvent:
    return LogEvent(logging.ERROR, "Error", message, args)


class ComponentLogger:
    def __init__(self, name: str, component: str) -> None:
        self._logger = logging.getLogger(name)
        self.component = component

    def handle(self, event: LogEvent, **kwargs: Any) -> None:
        self._logger.log(
            event.level,
            self._format_message(event.level_label, event.message),
            *event.args,
            **kwargs,
        )

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.handle(Debug(message, *args), **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.handle(Info(message, *args), **kwargs)

    def warn(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.handle(Warn(message, *args), **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.warn(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.handle(Error(message, *args), **kwargs)

    def _format_message(self, level_label: str, message: str) -> str:
        return f"[{self.component}][{level_label}] {message}"


def get_component_logger(name: str, component: str) -> ComponentLogger:
    return ComponentLogger(name, component)
