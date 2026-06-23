import threading
import time
import unittest

from contract_agent.config import MultiAgentConfig
from contract_agent.orchestration.message_queue import TaskMessageQueue
from contract_agent.orchestration.protocol import (
    AgentMode,
    AgentOutput,
    AgentStatus,
    AgentTask,
    AgentTaskStatus,
    PipelineState,
    PipelineStatus,
    TaskCommand,
    TaskCommandType,
    TaskNotification,
)
from contract_agent.orchestration.runtime import AgentRuntime
from contract_agent.orchestration.task_registry import TaskRegistry


class RuntimeProtocolTests(unittest.TestCase):
    def test_agent_task_and_notification_expose_runtime_identity(self):
        task = AgentTask(
            task_id="task-1",
            pipeline_id="pipeline-1",
            agent_id="parser",
            run_id="run-1",
            status=AgentTaskStatus.PENDING,
            input_summary="parse contract",
        )
        notification = TaskNotification.from_task(
            task,
            status=AgentTaskStatus.COMPLETED,
            summary="parsed",
            output=AgentOutput(agent_id="parser", status=AgentStatus.COMPLETED),
            duration_ms=12,
        )

        self.assertEqual(task.status, AgentTaskStatus.PENDING)
        self.assertEqual(notification.idempotency_key, ("task-1", "run-1", AgentTaskStatus.COMPLETED))
        self.assertEqual(notification.token_used, 0)


class TaskRegistryTests(unittest.TestCase):
    def test_rejects_invalid_transition_and_ignores_late_terminal_result(self):
        registry = TaskRegistry()
        task = registry.create_task("pipeline-1", "parser")

        with self.assertRaises(ValueError):
            registry.mark_completed(task.task_id, task.run_id, AgentOutput(agent_id="parser", status=AgentStatus.COMPLETED))

        registry.mark_running(task.task_id, task.run_id)
        killed = registry.mark_killed(task.task_id, task.run_id, "Agent 超时（1s）")
        self.assertEqual(killed.status, AgentTaskStatus.KILLED)

        late = registry.try_mark_completed(
            task.task_id,
            task.run_id,
            AgentOutput(agent_id="parser", status=AgentStatus.COMPLETED),
        )
        self.assertIsNone(late)
        self.assertEqual(registry.get_task(task.task_id).status, AgentTaskStatus.KILLED)

    def test_terminal_notification_recording_is_idempotent(self):
        registry = TaskRegistry()
        task = registry.create_task("pipeline-1", "parser")
        registry.mark_running(task.task_id, task.run_id)
        registry.mark_completed(task.task_id, task.run_id, AgentOutput(agent_id="parser", status=AgentStatus.COMPLETED))
        notification = TaskNotification.from_task(
            registry.get_task(task.task_id),
            status=AgentTaskStatus.COMPLETED,
            summary="ok",
        )

        self.assertTrue(registry.record_terminal_notification(notification))
        self.assertFalse(registry.record_terminal_notification(notification))


class TaskMessageQueueTests(unittest.TestCase):
    def test_resolves_commands_by_task_id_or_active_agent_and_deduplicates_notifications(self):
        registry = TaskRegistry()
        queue = TaskMessageQueue()
        task = registry.create_task("pipeline-1", "parser")
        registry.mark_running(task.task_id, task.run_id)

        by_task = TaskCommand(
            command_type=TaskCommandType.FOLLOW_UP,
            target=task.task_id,
            message="继续检查付款条款",
        )
        by_agent = TaskCommand(
            command_type=TaskCommandType.HEARTBEAT,
            target="parser",
            pipeline_id="pipeline-1",
            payload={"progress": 0.5},
        )

        self.assertEqual(queue.enqueue_command(by_task, registry), task.task_id)
        self.assertEqual(queue.enqueue_command(by_agent, registry), task.task_id)
        self.assertEqual(queue.enqueue_command(by_agent, registry), task.task_id)
        self.assertEqual(queue.pending_command_count(task.task_id), 2)
        self.assertEqual([cmd.command_type for cmd in queue.drain_commands(task.task_id)], [
            TaskCommandType.FOLLOW_UP,
            TaskCommandType.HEARTBEAT,
        ])
        registry.mark_completed(task.task_id, task.run_id, AgentOutput(agent_id="parser", status=AgentStatus.COMPLETED))
        self.assertEqual(queue.enqueue_command(by_agent, registry), task.task_id)
        self.assertEqual(queue.pending_command_count(task.task_id), 0)

        notification = TaskNotification.from_task(task, status=AgentTaskStatus.KILLED, summary="timeout")
        self.assertTrue(queue.enqueue_notification(notification))
        self.assertFalse(queue.enqueue_notification(notification))
        self.assertEqual(queue.drain_notifications("pipeline-1"), [notification])
        self.assertEqual(queue.drain_notifications("pipeline-1"), [])


class AgentRuntimeTests(unittest.TestCase):
    def test_fails_before_execution_when_context_cannot_be_deepcopied(self):
        runtime = AgentRuntime(MultiAgentConfig(agent_timeout_seconds=1, max_parallel_agents=1))
        executed = False

        def parser(ctx):
            nonlocal executed
            executed = True
            return AgentOutput(agent_id="parser", status=AgentStatus.COMPLETED)

        runtime.register_agent("parser", parser)
        lock = threading.Lock()
        task = runtime.spawn("pipeline-1", "parser", {"lock": lock}, timeout_seconds=1)
        notifications = runtime.collect("pipeline-1", [task.task_id], timeout_seconds=1)
        runtime.close(wait=False)

        self.assertFalse(executed)
        self.assertEqual(notifications[0].status, AgentTaskStatus.FAILED)
        self.assertIn("上下文隔离失败", notifications[0].error_message)

    def test_timeout_marks_task_killed_and_ignores_late_worker_result(self):
        runtime = AgentRuntime(MultiAgentConfig(agent_timeout_seconds=0.05, max_parallel_agents=1))

        def slow_agent(ctx):
            time.sleep(0.2)
            return AgentOutput(
                agent_id="parser",
                status=AgentStatus.COMPLETED,
                structured_data={"late": True},
            )

        runtime.register_agent("parser", slow_agent)
        task = runtime.spawn("pipeline-1", "parser", {}, timeout_seconds=0.05)
        notifications = runtime.collect("pipeline-1", [task.task_id], timeout_seconds=0.05)
        self.assertEqual(notifications[0].status, AgentTaskStatus.KILLED)
        self.assertIn("超时", notifications[0].error_message)

        time.sleep(0.25)
        stored = runtime.registry.get_task(task.task_id)
        runtime.close(wait=False)

        self.assertEqual(stored.status, AgentTaskStatus.KILLED)
        self.assertIsNone(stored.output)

    def test_running_cancel_command_is_drained_and_marks_cancel_requested(self):
        runtime = AgentRuntime(MultiAgentConfig(agent_timeout_seconds=1, max_parallel_agents=1))
        started = threading.Event()
        release = threading.Event()

        def blocking_agent(ctx):
            started.set()
            release.wait(1)
            return AgentOutput(agent_id="parser", status=AgentStatus.COMPLETED, input_summary="done")

        runtime.register_agent("parser", blocking_agent)
        task = runtime.spawn("pipeline-1", "parser", {}, timeout_seconds=1)
        self.assertTrue(started.wait(1))

        runtime.queue.enqueue_command(
            TaskCommand(
                command_type=TaskCommandType.CANCEL,
                target=task.task_id,
                message="stop",
            ),
            runtime.registry,
        )

        notifications_holder = []
        collector = threading.Thread(
            target=lambda: notifications_holder.extend(
                runtime.collect("pipeline-1", [task.task_id], timeout_seconds=1)
            )
        )
        collector.start()
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if runtime.registry.get_task(task.task_id).status == AgentTaskStatus.CANCEL_REQUESTED:
                break
            time.sleep(0.01)

        self.assertEqual(runtime.registry.get_task(task.task_id).status, AgentTaskStatus.CANCEL_REQUESTED)
        self.assertEqual(runtime.queue.pending_command_count(task.task_id), 0)
        release.set()
        collector.join(1)
        runtime.close(wait=False)

        self.assertEqual(notifications_holder[0].status, AgentTaskStatus.COMPLETED)
        self.assertEqual(runtime.registry.get_task(task.task_id).status, AgentTaskStatus.COMPLETED)

    def test_success_notification_carries_agent_output_usage(self):
        runtime = AgentRuntime(MultiAgentConfig(agent_timeout_seconds=1, max_parallel_agents=2))

        def parser(ctx):
            return AgentOutput(
                agent_id="parser",
                status=AgentStatus.COMPLETED,
                input_summary="parsed",
                token_used=7,
                llm_calls=1,
            )

        runtime.register_agent("parser", parser)
        task = runtime.spawn("pipeline-1", "parser", {"contract_text": "合同"}, timeout_seconds=1)
        notifications = runtime.collect("pipeline-1", [task.task_id], timeout_seconds=1)
        runtime.close(wait=False)

        self.assertEqual(notifications[0].status, AgentTaskStatus.COMPLETED)
        self.assertEqual(notifications[0].output.input_summary, "parsed")
        self.assertEqual(notifications[0].token_used, 7)
        self.assertEqual(notifications[0].llm_calls, 1)


class RuntimePublicApiTests(unittest.TestCase):
    def test_orchestration_package_reexports_runtime_building_blocks(self):
        from contract_agent.orchestration import AgentRuntime as ExportedRuntime
        from contract_agent.orchestration import TaskMessageQueue as ExportedQueue
        from contract_agent.orchestration import TaskRegistry as ExportedRegistry

        self.assertIs(ExportedRuntime, AgentRuntime)
        self.assertIs(ExportedQueue, TaskMessageQueue)
        self.assertIs(ExportedRegistry, TaskRegistry)


class RuntimeStateFactoryTests(unittest.TestCase):
    def test_pipeline_state_remains_compatible_with_runtime_protocol_imports(self):
        state = PipelineState(
            pipeline_id="pipeline-compat",
            contract_id="contract-1",
            mode=AgentMode.MULTI_AUTO,
            team="review",
            status=PipelineStatus.PENDING,
        )

        self.assertEqual(state.status, PipelineStatus.PENDING)


if __name__ == "__main__":
    unittest.main()
