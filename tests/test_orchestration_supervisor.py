import unittest

from contract_agent.orchestration.config import MultiAgentConfig
from contract_agent.orchestration.protocol import AgentMode, AgentOutput, AgentStatus, PipelineState, PipelineStatus
from contract_agent.orchestration.supervisor import SupervisorAgent


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeSupervisorLlm:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def invoke(self, prompt: str) -> FakeMessage:
        self.prompts.append(prompt)
        return FakeMessage(self.responses.pop(0))


class SupervisorAgentTests(unittest.TestCase):
    def test_react_loop_calls_registered_agent_then_finishes(self):
        llm = FakeSupervisorLlm(
            [
                '{"thought":"先解析合同","action":"call_agents","agents":["parser"]}',
                '{"thought":"信息足够","action":"finish","final_report":{"overall_risk":"low","summary":"完成","key_findings":["无重大风险"]}}',
            ]
        )
        supervisor = SupervisorAgent(
            MultiAgentConfig(supervisor_max_rounds=3, max_parallel_agents=1, agent_timeout_seconds=2),
            llm=llm,
        )
        events = []

        def parser_agent(ctx):
            return AgentOutput(
                agent_id="parser",
                status=AgentStatus.COMPLETED,
                input_summary=f"parsed {ctx['contract_type']}",
                structured_data={"parsed": True},
                token_used=6,
            )

        supervisor.register_agent("parser", parser_agent)
        state = PipelineState(
            pipeline_id="pipeline-1",
            contract_id="contract-1",
            mode=AgentMode.MULTI_AUTO,
            team="review",
            status=PipelineStatus.PENDING,
        )

        result = supervisor.run(
            state,
            {"contract_text": "合同正文", "contract_type": "采购合同", "our_side": "甲方"},
            on_event=events.append,
        )

        self.assertEqual(result.status, PipelineStatus.COMPLETED)
        self.assertIn("parser", result.agent_outputs)
        self.assertIn("supervisor", result.agent_outputs)
        self.assertEqual(result.agent_outputs["supervisor"].structured_data["review_report"]["summary"], "完成")
        self.assertGreater(result.token_used_total, 6)
        self.assertEqual(
            [event.event_type for event in events],
            [
                "supervisor_thinking",
                "agent_called",
                "agent_started",
                "agent_completed",
                "round_complete",
                "supervisor_thinking",
                "supervisor_finished",
            ],
        )

    def test_unknown_agent_is_reported_as_failed_output(self):
        llm = FakeSupervisorLlm(
            [
                '{"thought":"调用未知agent","action":"call_agents","agents":["call_missing"]}',
                '{"thought":"收尾","action":"finish","final_report":{"summary":"完成","key_findings":[]}}',
            ]
        )
        supervisor = SupervisorAgent(MultiAgentConfig(supervisor_max_rounds=2), llm=llm)
        state = PipelineState(
            pipeline_id="pipeline-2",
            contract_id="contract-2",
            mode=AgentMode.MULTI_AUTO,
            team="review",
            status=PipelineStatus.PENDING,
        )

        result = supervisor.run(state, {"contract_text": "合同正文"})

        self.assertEqual(result.status, PipelineStatus.COMPLETED)
        self.assertEqual(result.agent_outputs["missing"].status, AgentStatus.FAILED)
        self.assertEqual(result.agent_outputs["missing"].error_message, "未知 Agent: missing")
        self.assertEqual(result.agent_outputs["supervisor"].status, AgentStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()
