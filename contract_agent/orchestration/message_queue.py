from __future__ import annotations

from collections import defaultdict, deque
from threading import RLock

from contract_agent.orchestration.protocol import TaskCommand, TaskNotification
from contract_agent.orchestration.task_registry import TaskRegistry


class TaskMessageQueue:
    """Thread-safe in-memory command and notification queue for task runtime."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._commands_by_task: dict[str, deque[TaskCommand]] = defaultdict(deque)
        self._command_targets: dict[str, str] = {}
        self._notifications_by_pipeline: dict[str, deque[TaskNotification]] = defaultdict(deque)
        self._notification_keys: set[tuple] = set()

    def enqueue_command(self, command: TaskCommand, registry: TaskRegistry | None = None) -> str:
        with self._lock:
            known_target = self._command_targets.get(command.command_id)
            if known_target is not None:
                return known_target

        task_id = self._resolve_command_target(command, registry)
        with self._lock:
            known_target = self._command_targets.get(command.command_id)
            if known_target is not None:
                return known_target
            self._command_targets[command.command_id] = task_id
            self._commands_by_task[task_id].append(command)
            count = len(self._commands_by_task[task_id])
        if registry is not None:
            registry.set_pending_command_count(task_id, count)
        return task_id

    def drain_commands(self, task_id: str, registry: TaskRegistry | None = None) -> list[TaskCommand]:
        with self._lock:
            commands = list(self._commands_by_task.pop(task_id, deque()))
        if registry is not None:
            registry.set_pending_command_count(task_id, 0)
        return commands

    def pending_command_count(self, task_id: str) -> int:
        with self._lock:
            return len(self._commands_by_task.get(task_id, ()))

    def enqueue_notification(self, notification: TaskNotification) -> bool:
        with self._lock:
            key = notification.idempotency_key
            if key in self._notification_keys:
                return False
            self._notification_keys.add(key)
            self._notifications_by_pipeline[notification.pipeline_id].append(notification)
            return True

    def drain_notifications(self, pipeline_id: str) -> list[TaskNotification]:
        with self._lock:
            return list(self._notifications_by_pipeline.pop(pipeline_id, deque()))

    def _resolve_command_target(self, command: TaskCommand, registry: TaskRegistry | None) -> str:
        if registry is None:
            return command.target

        try:
            return registry.get_task(command.target).task_id
        except KeyError:
            pass

        if command.pipeline_id is None:
            raise ValueError("按 agent_id 发送命令时必须提供 pipeline_id")

        active_task = registry.resolve_active_task(command.pipeline_id, command.target)
        if active_task is None:
            raise ValueError(f"未找到可接收命令的任务: {command.target}")
        return active_task.task_id
