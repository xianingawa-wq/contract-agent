from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone
from typing import Any, Callable

from contract_agent.llm.agent_prompts import supervisor_prompt
from contract_agent.llm_provider.client import get_chat_model
from contract_agent.multi_agent.config import MultiAgentConfig
from contract_agent.multi_agent.protocol import (
    AgentOutput,
    AgentStatus,
    PipelineEvent,
    PipelineState,
    PipelineStatus,
)


class SupervisorAgent:
    """ReAct-loop Supervisor that dynamically orchestrates sub-agents."""

    def __init__(self, config: MultiAgentConfig | None = None) -> None:
        self.config = config or MultiAgentConfig()
        self._agents: dict[str, Callable[[dict[str, Any]], AgentOutput]] = {}
        self._llm = get_chat_model()

    def register_agent(self, agent_id: str, fn: Callable[[dict[str, Any]], AgentOutput]) -> None:
        self._agents[agent_id] = fn

    def run(
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

            accumulated = self._build_accumulated(state.agent_outputs)

            decision_prompt = supervisor_prompt.format(
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

        with ThreadPoolExecutor(max_workers=self.config.max_parallel_agents) as pool:
            futures = {}
            for aid in agent_ids:
                normalized = aid.removeprefix("call_")
                fn = self._agents.get(normalized)
                if fn is None:
                    results[normalized] = AgentOutput(
                        agent_id=normalized,
                        status=AgentStatus.FAILED,
                        error_message=f"未知 Agent: {normalized}",
                    )
                    continue
                self._emit(on_event, PipelineEvent(
                    pipeline_id=state.pipeline_id,
                    event_type="agent_started",
                    agent_id=normalized,
                    round=round_num,
                ))
                futures[normalized] = pool.submit(fn, ctx)

            for aid, future in futures.items():
                try:
                    output = future.result(timeout=timeout)
                    results[aid] = output
                    self._emit(on_event, PipelineEvent(
                        pipeline_id=state.pipeline_id,
                        event_type="agent_completed",
                        agent_id=aid,
                        round=round_num,
                        data={
                            "input_summary": output.input_summary,
                            "findings_count": len(output.findings),
                            "token_used": output.token_used,
                        },
                    ))
                except FutureTimeout:
                    results[aid] = AgentOutput(
                        agent_id=aid,
                        status=AgentStatus.FAILED,
                        error_message=f"Agent 超时（{timeout}s）",
                    )
                    self._emit(on_event, PipelineEvent(
                        pipeline_id=state.pipeline_id,
                        event_type="agent_failed",
                        agent_id=aid,
                        round=round_num,
                        data={"error": f"Timeout after {timeout}s"},
                    ))
                except Exception as exc:
                    results[aid] = AgentOutput(
                        agent_id=aid,
                        status=AgentStatus.FAILED,
                        error_message=str(exc),
                    )
                    self._emit(on_event, PipelineEvent(
                        pipeline_id=state.pipeline_id,
                        event_type="agent_failed",
                        agent_id=aid,
                        round=round_num,
                        data={"error": str(exc)},
                    ))

        return results

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

    def _estimate_tokens(self, text: str) -> int:
        return len(text) // 3

    def _emit(self, on_event: Callable | None, event: PipelineEvent) -> None:
        if on_event:
            on_event(event)
