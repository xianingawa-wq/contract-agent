from __future__ import annotations

import copy
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock
from typing import Any, Callable

from contract_agent.config import MultiAgentConfig
from contract_agent.orchestration.message_queue import TaskMessageQueue
from contract_agent.orchestration.protocol import (
    AgentOutput,
    AgentTask,
    AgentTaskStatus,
    PipelineEvent,
    TaskCommandType,
    TaskNotification,
)
from contract_agent.orchestration.task_registry import TaskRegistry, TERMINAL_TASK_STATUSES


AgentFn = Callable[[dict[str, Any]], AgentOutput]
EventCallback = Callable[[PipelineEvent], None]


class AgentRuntime:
    """Local in-process worker runtime for multi-agent orchestration."""

    def __init__(
        self,
        config: MultiAgentConfig | None = None,
        registry: TaskRegistry | None = None,
        queue: TaskMessageQueue | None = None,
    ) -> None:
        self.config = config or MultiAgentConfig()
        self.registry = registry or TaskRegistry()
        self.queue = queue or TaskMessageQueue()
        self._agents: dict[str, AgentFn] = {}
        self._executor = ThreadPoolExecutor(max_workers=self.config.max_parallel_agents)
        self._lock = RLock()
        self._futures: dict[str, Future[None]] = {}
        self._timed_out_futures: set[Future[None]] = set()

    def register_agent(self, agent_id: str, fn: AgentFn) -> None:
        self._agents[agent_id] = fn

    def has_agent(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def spawn(
        self,
        pipeline_id: str,
        agent_id: str,
        context: dict[str, Any],
        timeout_seconds: float | None = None,
        input_summary: str = "",
        on_event: EventCallback | None = None,
        round_num: int | None = None,
    ) -> AgentTask:
        timeout = timeout_seconds if timeout_seconds is not None else self.config.agent_timeout_seconds
        task = self.registry.create_task(
            pipeline_id=pipeline_id,
            agent_id=agent_id,
            input_summary=input_summary,
            timeout_seconds=timeout,
        )

        worker = self._agents.get(agent_id)
        if worker is None:
            failed = self.registry.mark_failed(task.task_id, task.run_id, f"未知 Agent: {agent_id}")
            self._enqueue_terminal_notification(
                failed,
                AgentTaskStatus.FAILED,
                f"未知 Agent: {agent_id}",
                on_event,
                round_num,
            )
            return failed

        try:
            isolated_context = copy.deepcopy(context)
        except Exception as exc:
            message = f"上下文隔离失败: {exc}"
            failed = self.registry.mark_failed(task.task_id, task.run_id, message)
            self._enqueue_terminal_notification(
                failed,
                AgentTaskStatus.FAILED,
                message,
                on_event,
                round_num,
            )
            return failed

        self._prune_timed_out_futures()
        if len(self._timed_out_futures) >= self.config.max_parallel_agents:
            message = "运行时容量不足：已有超时任务仍占用执行线程"
            failed = self.registry.mark_failed(task.task_id, task.run_id, message)
            self._enqueue_terminal_notification(
                failed,
                AgentTaskStatus.FAILED,
                message,
                on_event,
                round_num,
            )
            return failed

        future = self._executor.submit(
            self._run_worker,
            task.task_id,
            task.run_id,
            worker,
            isolated_context,
            on_event,
            round_num,
        )
        with self._lock:
            self._futures[task.task_id] = future
        return task

    def collect(
        self,
        pipeline_id: str,
        task_ids: list[str],
        timeout_seconds: float | None = None,
        on_event: EventCallback | None = None,
        round_num: int | None = None,
    ) -> list[TaskNotification]:
        timeout = timeout_seconds if timeout_seconds is not None else self.config.agent_timeout_seconds
        deadline = time.monotonic() + timeout
        pending = set(task_ids)
        notifications: list[TaskNotification] = []

        while pending:
            drained = self.queue.drain_notifications(pipeline_id)
            for notification in drained:
                notifications.append(notification)
                pending.discard(notification.task_id)
                with self._lock:
                    self._futures.pop(notification.task_id, None)

            now = time.monotonic()
            if not pending:
                break
            self._drain_runtime_commands(pending, on_event, round_num)
            if now >= deadline:
                self._kill_pending_tasks(pending, on_event, round_num)
                continue

            time.sleep(min(0.01, max(0.0, deadline - now)))

        return notifications

    def close(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _run_worker(
        self,
        task_id: str,
        run_id: str,
        worker: AgentFn,
        context: dict[str, Any],
        on_event: EventCallback | None,
        round_num: int | None,
    ) -> None:
        started = time.monotonic()
        try:
            commands = self.queue.drain_commands(task_id, self.registry)
            if any(command.command_type == TaskCommandType.CANCEL for command in commands):
                task = self.registry.mark_cancelled(task_id, run_id, "任务启动前已取消")
                self._enqueue_terminal_notification(
                    task,
                    AgentTaskStatus.CANCELLED,
                    "任务启动前已取消",
                    on_event,
                    round_num,
                    duration_ms=self._elapsed_ms(started),
                )
                return

            task = self.registry.mark_running(task_id, run_id)
            self._emit_event(on_event, "agent_started", task, round_num)
            output = worker(context)
            if not isinstance(output, AgentOutput):
                raise TypeError(f"Agent {task.agent_id} 返回值不是 AgentOutput")

            completed = self.registry.try_mark_completed(task_id, run_id, output)
            if completed is None:
                return
            self._enqueue_terminal_notification(
                completed,
                AgentTaskStatus.COMPLETED,
                output.input_summary,
                on_event,
                round_num,
                output=output,
                duration_ms=self._elapsed_ms(started),
            )
        except Exception as exc:
            failed = self.registry.try_mark_failed(task_id, run_id, str(exc))
            if failed is None:
                return
            self._enqueue_terminal_notification(
                failed,
                AgentTaskStatus.FAILED,
                str(exc),
                on_event,
                round_num,
                duration_ms=self._elapsed_ms(started),
            )

    def _drain_runtime_commands(
        self,
        pending: set[str],
        on_event: EventCallback | None,
        round_num: int | None,
    ) -> None:
        for task_id in list(pending):
            task = self.registry.get_task(task_id)
            if task.status in TERMINAL_TASK_STATUSES:
                continue
            commands = self.queue.drain_commands(task_id, self.registry)
            if not commands:
                continue
            cancel_requested = any(command.command_type == TaskCommandType.CANCEL for command in commands)
            if not cancel_requested:
                continue

            with self._lock:
                future = self._futures.get(task_id)
            if future is not None and task.status == AgentTaskStatus.PENDING:
                future.cancel()

            try:
                updated = self.registry.request_cancel(task.task_id, task.run_id, "任务取消请求已接收")
            except ValueError:
                continue

            if updated.status == AgentTaskStatus.CANCELLED:
                self._enqueue_terminal_notification(
                    updated,
                    AgentTaskStatus.CANCELLED,
                    "任务启动前已取消",
                    on_event,
                    round_num,
                )

    def _kill_pending_tasks(
        self,
        pending: set[str],
        on_event: EventCallback | None,
        round_num: int | None,
    ) -> None:
        for task_id in list(pending):
            with self._lock:
                future = self._futures.get(task_id)
            task = self.registry.get_task(task_id)
            if task.status in TERMINAL_TASK_STATUSES:
                pending.discard(task_id)
                continue

            if future is not None:
                future.cancel()
                with self._lock:
                    self._timed_out_futures.add(future)

            message = f"Agent 超时（{task.timeout_seconds}s）"
            killed = self.registry.try_mark_killed(task.task_id, task.run_id, message)
            if killed is None:
                pending.discard(task_id)
                continue
            self._enqueue_terminal_notification(
                killed,
                AgentTaskStatus.KILLED,
                message,
                on_event,
                round_num,
            )

    def _enqueue_terminal_notification(
        self,
        task: AgentTask,
        status: AgentTaskStatus,
        summary: str,
        on_event: EventCallback | None,
        round_num: int | None,
        output: AgentOutput | None = None,
        duration_ms: int = 0,
    ) -> None:
        notification = TaskNotification.from_task(
            task,
            status=status,
            summary=summary,
            output=output,
            error_message=task.error_message,
            duration_ms=duration_ms,
        )
        if self.registry.record_terminal_notification(notification):
            self.queue.enqueue_notification(notification)
            event_type = {
                AgentTaskStatus.COMPLETED: "agent_completed",
                AgentTaskStatus.FAILED: "agent_failed",
                AgentTaskStatus.KILLED: "agent_failed",
                AgentTaskStatus.CANCELLED: "agent_skipped",
            }.get(status, "agent_failed")
            self._emit_event(on_event, event_type, task, round_num, notification)

    def _emit_event(
        self,
        on_event: EventCallback | None,
        event_type: str,
        task: AgentTask,
        round_num: int | None,
        notification: TaskNotification | None = None,
    ) -> None:
        if on_event is None:
            return
        data = {
            "task_id": task.task_id,
            "run_id": task.run_id,
            "task_status": task.status.value,
            "pending_command_count": task.pending_command_count,
            "transcript_path": task.transcript_path,
        }
        if notification is not None:
            data.update({
                "duration_ms": notification.duration_ms,
                "token_used": notification.token_used,
                "llm_calls": notification.llm_calls,
                "error": notification.error_message,
            })
            if notification.output is not None:
                data.update({
                    "input_summary": notification.output.input_summary,
                    "findings_count": len(notification.output.findings),
                })
        on_event(PipelineEvent(
            pipeline_id=task.pipeline_id,
            event_type=event_type,  # type: ignore[arg-type]
            agent_id=task.agent_id,
            round=round_num,
            data=data,
        ))

    def _elapsed_ms(self, started: float) -> int:
        return max(0, int((time.monotonic() - started) * 1000))

    def _prune_timed_out_futures(self) -> None:
        with self._lock:
            self._timed_out_futures = {future for future in self._timed_out_futures if not future.done()}
