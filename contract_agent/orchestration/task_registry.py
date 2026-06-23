from __future__ import annotations

from datetime import datetime, timezone
from threading import RLock

from contract_agent.orchestration.protocol import (
    AgentOutput,
    AgentTask,
    AgentTaskStatus,
    TaskNotification,
)


TERMINAL_TASK_STATUSES = frozenset(
    {
        AgentTaskStatus.COMPLETED,
        AgentTaskStatus.FAILED,
        AgentTaskStatus.KILLED,
        AgentTaskStatus.CANCELLED,
    }
)


class TaskRegistry:
    """Thread-safe in-memory registry for worker task lifecycle state."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._tasks: dict[str, AgentTask] = {}
        self._terminal_notification_keys: set[tuple[str, str, AgentTaskStatus]] = set()

    def create_task(
        self,
        pipeline_id: str,
        agent_id: str,
        input_summary: str = "",
        timeout_seconds: float | None = None,
        attempt: int = 1,
    ) -> AgentTask:
        task = AgentTask(
            pipeline_id=pipeline_id,
            agent_id=agent_id,
            input_summary=input_summary,
            timeout_seconds=timeout_seconds,
            attempt=attempt,
        )
        with self._lock:
            self._tasks[task.task_id] = task
            return self._copy_task(task)

    def get_task(self, task_id: str) -> AgentTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"未知任务: {task_id}")
            return self._copy_task(task)

    def list_tasks(self, pipeline_id: str | None = None) -> list[AgentTask]:
        with self._lock:
            tasks = self._tasks.values()
            if pipeline_id is not None:
                tasks = [task for task in tasks if task.pipeline_id == pipeline_id]
            return [self._copy_task(task) for task in tasks]

    def resolve_active_task(self, pipeline_id: str, agent_id: str) -> AgentTask | None:
        with self._lock:
            candidates = [
                task
                for task in self._tasks.values()
                if task.pipeline_id == pipeline_id
                and task.agent_id == agent_id
                and task.status not in TERMINAL_TASK_STATUSES
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda task: task.created_at, reverse=True)
            return self._copy_task(candidates[0])

    def set_pending_command_count(self, task_id: str, count: int) -> None:
        with self._lock:
            task = self._require_task(task_id)
            task.pending_command_count = count

    def mark_running(self, task_id: str, run_id: str) -> AgentTask:
        with self._lock:
            task = self._require_task(task_id, run_id)
            self._ensure_transition(task, AgentTaskStatus.RUNNING, {AgentTaskStatus.PENDING})
            task.status = AgentTaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)
            return self._copy_task(task)

    def mark_cancelled(self, task_id: str, run_id: str, message: str | None = None) -> AgentTask:
        with self._lock:
            task = self._require_task(task_id, run_id)
            self._ensure_transition(task, AgentTaskStatus.CANCELLED, {AgentTaskStatus.PENDING})
            task.status = AgentTaskStatus.CANCELLED
            task.error_message = message
            task.completed_at = datetime.now(timezone.utc)
            return self._copy_task(task)

    def request_cancel(self, task_id: str, run_id: str, message: str | None = None) -> AgentTask:
        with self._lock:
            task = self._require_task(task_id, run_id)
            if task.status == AgentTaskStatus.PENDING:
                return self.mark_cancelled(task_id, run_id, message)
            self._ensure_transition(
                task, AgentTaskStatus.CANCEL_REQUESTED, {AgentTaskStatus.RUNNING}
            )
            task.status = AgentTaskStatus.CANCEL_REQUESTED
            task.error_message = message
            return self._copy_task(task)

    def mark_completed(self, task_id: str, run_id: str, output: AgentOutput) -> AgentTask:
        with self._lock:
            task = self._require_task(task_id, run_id)
            self._ensure_transition(
                task,
                AgentTaskStatus.COMPLETED,
                {AgentTaskStatus.RUNNING, AgentTaskStatus.CANCEL_REQUESTED},
            )
            task.status = AgentTaskStatus.COMPLETED
            task.output = output
            task.error_message = None
            task.completed_at = datetime.now(timezone.utc)
            task.progress = 1.0
            return self._copy_task(task)

    def try_mark_completed(
        self, task_id: str, run_id: str, output: AgentOutput
    ) -> AgentTask | None:
        with self._lock:
            task = self._require_task(task_id, run_id)
            if task.status in TERMINAL_TASK_STATUSES:
                return None
            return self.mark_completed(task_id, run_id, output)

    def mark_failed(self, task_id: str, run_id: str, message: str) -> AgentTask:
        with self._lock:
            task = self._require_task(task_id, run_id)
            self._ensure_transition(
                task,
                AgentTaskStatus.FAILED,
                {
                    AgentTaskStatus.PENDING,
                    AgentTaskStatus.RUNNING,
                    AgentTaskStatus.CANCEL_REQUESTED,
                },
            )
            task.status = AgentTaskStatus.FAILED
            task.error_message = message
            task.completed_at = datetime.now(timezone.utc)
            return self._copy_task(task)

    def try_mark_failed(self, task_id: str, run_id: str, message: str) -> AgentTask | None:
        with self._lock:
            task = self._require_task(task_id, run_id)
            if task.status in TERMINAL_TASK_STATUSES:
                return None
            return self.mark_failed(task_id, run_id, message)

    def mark_killed(self, task_id: str, run_id: str, message: str) -> AgentTask:
        with self._lock:
            task = self._require_task(task_id, run_id)
            self._ensure_transition(
                task,
                AgentTaskStatus.KILLED,
                {
                    AgentTaskStatus.PENDING,
                    AgentTaskStatus.RUNNING,
                    AgentTaskStatus.CANCEL_REQUESTED,
                },
            )
            task.status = AgentTaskStatus.KILLED
            task.error_message = message
            task.completed_at = datetime.now(timezone.utc)
            return self._copy_task(task)

    def try_mark_killed(self, task_id: str, run_id: str, message: str) -> AgentTask | None:
        with self._lock:
            task = self._require_task(task_id, run_id)
            if task.status in TERMINAL_TASK_STATUSES:
                return None
            return self.mark_killed(task_id, run_id, message)

    def record_terminal_notification(self, notification: TaskNotification) -> bool:
        if notification.status not in TERMINAL_TASK_STATUSES:
            raise ValueError(f"非终态通知不可记录: {notification.status.value}")
        with self._lock:
            key = notification.idempotency_key
            if key in self._terminal_notification_keys:
                return False
            self._terminal_notification_keys.add(key)
            return True

    def _require_task(self, task_id: str, run_id: str | None = None) -> AgentTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"未知任务: {task_id}")
        if run_id is not None and task.run_id != run_id:
            raise ValueError(f"任务运行 ID 不匹配: {task_id}")
        return task

    def _ensure_transition(
        self,
        task: AgentTask,
        to_status: AgentTaskStatus,
        allowed_from: set[AgentTaskStatus],
    ) -> None:
        if task.status not in allowed_from:
            raise ValueError(f"非法任务状态转换: {task.status.value} -> {to_status.value}")

    def _copy_task(self, task: AgentTask) -> AgentTask:
        copy_method = getattr(task, "model_copy", None)
        if copy_method is not None:
            return copy_method(deep=True)
        return task.copy(deep=True)
