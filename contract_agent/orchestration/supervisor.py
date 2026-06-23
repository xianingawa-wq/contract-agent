from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable

from contract_agent.logger.audit import AuditLogger, get_audit_logger
from contract_agent.provider.client import get_chat_model
from contract_agent.config import MultiAgentConfig
from contract_agent.orchestration.protocol import (
    AgentOutput,
    AgentStatus,
    AgentTaskStatus,
    PipelineEvent,
    PipelineState,
    PipelineStatus,
    TaskNotification,
)
from contract_agent.orchestration.runtime import AgentRuntime


REVIEW_AGENT_DEPENDENCIES: dict[str, list[str]] = {
    "parser": [],
    "risk_checker": ["parser"],
    "legal_ref": ["risk_checker"],
    "redrafter": ["legal_ref"],
    "summarizer": ["redrafter"],
}


FALLBACK_SUPERVISOR_PROMPT = """\
你是合同审查协调员(Supervisor)。你可以调用子Agent来完成任务。

当前合同：
  合同类型：{contract_type}
  我方角色：{our_side}
  合同文本：{contract_text}

已有信息：
{accumulated_results}

当前轮次：{round}/{max_rounds}

请输出严格JSON（无其他文本）：
{{"thought": "思考过程，≤40字", "action": "call_agents|finish", "agents": ["agent_id", ...], "final_report": {{"overall_risk": "high|medium|low|info", "summary": "审查总结", "key_findings": []}}}}
"""


class SupervisorAgent:
    """ReAct-loop Supervisor that dynamically orchestrates sub-agents."""

    def __init__(
        self,
        config: MultiAgentConfig | None = None,
        llm: Any | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.config = config or MultiAgentConfig()
        self._agents: dict[str, Callable[[dict[str, Any]], AgentOutput]] = {}
        self.runtime = AgentRuntime(self.config)
        self._llm = llm or get_chat_model()
        self.audit_logger = (audit_logger or get_audit_logger()).with_prefix(
            "[Orchestration][Supervisor]",
            scope="orchestration",
        )

    def register_agent(self, agent_id: str, fn: Callable[[dict[str, Any]], AgentOutput]) -> None:
        self._agents[agent_id] = fn
        self.runtime.register_agent(agent_id, fn)

    def run(
        self,
        state: PipelineState,
        initial_input: dict[str, Any],
        on_event: Callable[[PipelineEvent], None] | None = None,
    ) -> PipelineState:
        with self.audit_logger.trace("supervisor", trace_id=state.pipeline_id, pipeline_id=state.pipeline_id):
            with self.audit_logger.span("supervisor.run", mode=state.mode.value, team=state.team):
                return self._run_traced(state, initial_input, on_event)

    def _run_traced(
        self,
        state: PipelineState,
        initial_input: dict[str, Any],
        on_event: Callable[[PipelineEvent], None] | None = None,
    ) -> PipelineState:
        state.status = PipelineStatus.RUNNING
        ctx = dict(initial_input)
        state.agent_outputs = {}
        total_tokens = 0

        for round_num in range(1, self.config.supervisor_max_rounds + 1):
            if state.status == PipelineStatus.CANCELLED:
                break

            with self.audit_logger.span("supervisor.round", round=round_num):
                accumulated = self._build_accumulated(state.agent_outputs)

                decision_prompt = self._format_supervisor_prompt(
                    contract_type=ctx.get("contract_type", ""),
                    our_side=ctx.get("our_side", "甲方"),
                    contract_text=self._truncate_text(ctx.get("contract_text", "")),
                    accumulated_results=accumulated,
                    round=round_num,
                    max_rounds=self.config.supervisor_max_rounds,
                )

                llm_result = self._llm.invoke(decision_prompt)
                decision = self._parse_supervisor_json(llm_result.content)
                total_tokens += self._estimate_tokens(llm_result.content)

            self._emit(on_event, PipelineEvent(
                pipeline_id=state.pipeline_id,
                event_type="supervisor_thinking",
                agent_id=None,
                data={
                    "thought": decision.get("thought", ""),
                    "action": decision.get("action", ""),
                    "agents": decision.get("agents", []),
                },
                round=round_num,
            ))

            if decision.get("action") == "finish" or round_num == self.config.supervisor_max_rounds:
                final_report = decision.get("final_report", {})
                if not final_report:
                    final_report = {
                        "overall_risk": "info",
                        "summary": "已达最大轮次，基于已有信息输出。",
                        "key_findings": [],
                    }
                report_agent = AgentOutput(
                    agent_id="supervisor",
                    status=AgentStatus.COMPLETED,
                    input_summary=final_report.get("summary", "")[:100],
                    structured_data={"review_report": final_report},
                    token_used=total_tokens,
                    llm_calls=round_num,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                )
                state.agent_outputs["supervisor"] = report_agent
                state.status = PipelineStatus.COMPLETED
                state.completed_at = datetime.now(timezone.utc)
                state.token_used_total = total_tokens
                self._emit(on_event, PipelineEvent(
                    pipeline_id=state.pipeline_id,
                    event_type="supervisor_finished",
                    data={"report": final_report},
                ))
                return state

            agent_ids = decision.get("agents", [])
            self._emit(on_event, PipelineEvent(
                pipeline_id=state.pipeline_id,
                event_type="agent_called",
                data={"agents": agent_ids},
                round=round_num,
            ))

            results = self._parallel_execute(agent_ids, ctx, state, on_event, round_num)
            for agent_id, output in results.items():
                state.agent_outputs[agent_id] = output
                ctx.update(output.structured_data)
                total_tokens += output.token_used

            self._emit(on_event, PipelineEvent(
                pipeline_id=state.pipeline_id,
                event_type="round_complete",
                data={"round": round_num, "completed_agents": list(results.keys())},
                round=round_num,
            ))

        # Force finish if loop exhausted
        state.status = PipelineStatus.COMPLETED
        state.completed_at = datetime.now(timezone.utc)
        state.token_used_total = total_tokens
        self._emit(on_event, PipelineEvent(
            pipeline_id=state.pipeline_id,
            event_type="supervisor_finished",
            data={"forced": True},
        ))
        return state

    def _parallel_execute(
        self, agent_ids: list[str], ctx: dict, state: PipelineState,
        on_event: Callable | None, round_num: int = 0,
    ) -> dict[str, AgentOutput]:
        results: dict[str, AgentOutput] = {}
        timeout = self.config.agent_timeout_seconds

        completed = {
            aid
            for aid, output in state.agent_outputs.items()
            if output.status == AgentStatus.COMPLETED
        }
        failed = {
            aid
            for aid, output in state.agent_outputs.items()
            if output.status in {AgentStatus.FAILED, AgentStatus.SKIPPED, AgentStatus.CANCELLED}
        }

        pending = self._normalize_agent_ids(agent_ids)
        while pending:
            batch, skipped = self._select_execution_batch(pending, state.team, completed, failed)
            for aid, output in skipped.items():
                results[aid] = output
                failed.add(aid)
                self._emit(on_event, PipelineEvent(
                    pipeline_id=state.pipeline_id,
                    event_type="agent_skipped",
                    agent_id=aid,
                    round=round_num,
                    data={"error": output.error_message},
                ))
            pending = [aid for aid in pending if aid not in skipped]

            if not batch:
                for aid in pending:
                    unmet = self._unmet_dependencies(aid, state.team, completed)
                    output = AgentOutput(
                        agent_id=aid,
                        status=AgentStatus.SKIPPED,
                        error_message=f"依赖未满足: {', '.join(unmet) if unmet else '无可执行批次'}",
                    )
                    results[aid] = output
                    self._emit(on_event, PipelineEvent(
                        pipeline_id=state.pipeline_id,
                        event_type="agent_skipped",
                        agent_id=aid,
                        round=round_num,
                        data={"error": output.error_message},
                    ))
                break

            pending = [aid for aid in pending if aid not in batch]
            tasks = [
                self.runtime.spawn(
                    state.pipeline_id,
                    aid,
                    ctx,
                    timeout_seconds=timeout,
                    on_event=on_event,
                    round_num=round_num,
                )
                for aid in batch
            ]
            notifications = self.runtime.collect(
                state.pipeline_id,
                [task.task_id for task in tasks],
                timeout_seconds=timeout,
                on_event=on_event,
                round_num=round_num,
            )
            for notification in notifications:
                with self.audit_logger.span("supervisor.agent", agent_id=notification.agent_id, round=round_num):
                    output = self._notification_to_output(notification)
                results[notification.agent_id] = output
                if output.status == AgentStatus.COMPLETED:
                    completed.add(notification.agent_id)
                    ctx.update(output.structured_data)
                else:
                    failed.add(notification.agent_id)

        return results

    def _select_execution_batch(
        self,
        pending: list[str],
        team: str,
        completed: set[str],
        failed: set[str],
    ) -> tuple[list[str], dict[str, AgentOutput]]:
        dependencies = REVIEW_AGENT_DEPENDENCIES if team == "review" else {}
        runnable: list[str] = []
        skipped: dict[str, AgentOutput] = {}

        for aid in pending:
            deps = dependencies.get(aid, [])
            failed_deps = [dep for dep in deps if dep in failed]
            if failed_deps:
                skipped[aid] = AgentOutput(
                    agent_id=aid,
                    status=AgentStatus.SKIPPED,
                    error_message=f"上游失败: {', '.join(failed_deps)}",
                )
                continue
            if all(dep in completed for dep in deps):
                runnable.append(aid)

        return runnable[: self.config.max_parallel_agents], skipped

    def _unmet_dependencies(self, agent_id: str, team: str, completed: set[str]) -> list[str]:
        dependencies = REVIEW_AGENT_DEPENDENCIES if team == "review" else {}
        return [dep for dep in dependencies.get(agent_id, []) if dep not in completed]

    def _normalize_agent_ids(self, agent_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for aid in agent_ids:
            name = aid.removeprefix("call_")
            if name not in seen:
                normalized.append(name)
                seen.add(name)
        return normalized

    def _notification_to_output(self, notification: TaskNotification) -> AgentOutput:
        if notification.output is not None:
            return notification.output
        status = AgentStatus.FAILED
        if notification.status == AgentTaskStatus.CANCELLED:
            status = AgentStatus.CANCELLED
        return AgentOutput(
            agent_id=notification.agent_id,
            status=status,
            error_message=notification.error_message,
        )

    def _build_accumulated(self, agent_outputs: dict[str, AgentOutput]) -> str:
        if not agent_outputs:
            return "（尚无任何Agent执行结果）"
        lines = []
        for aid, ao in agent_outputs.items():
            lines.append(f"[{aid}] status={ao.status.value} | {ao.input_summary}")
            if ao.findings:
                for f in ao.findings[:3]:
                    lines.append(f"  - [{f.risk}] {f.summary[:80]}")
            if ao.error_message:
                lines.append(f"  ERROR: {ao.error_message[:120]}")
        return "\n".join(lines)

    def _parse_supervisor_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            text = m.group(0)
        text = re.sub(r',(\s*[}\]])', r'\1', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {
                "thought": "JSON parse failed",
                "action": "finish",
                "final_report": {
                    "overall_risk": "info",
                    "summary": "审查未完成（系统异常）",
                    "key_findings": [],
                },
            }

    def _truncate_text(self, text: str, max_chars: int = 1500) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + f"\n\n…(合同全文共 {len(text)} 字符，此处仅展示开头部分)…"

    def _format_supervisor_prompt(self, **kwargs: Any) -> str:
        try:
            from contract_agent.constants.agent_prompts import supervisor_prompt

            return supervisor_prompt.format(**kwargs)
        except ImportError:
            return FALLBACK_SUPERVISOR_PROMPT.format(**kwargs)

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 3

    def _emit(self, on_event: Callable | None, event: PipelineEvent) -> None:
        if on_event:
            on_event(event)
