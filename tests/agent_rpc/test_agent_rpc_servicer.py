import unittest
import json
import tempfile
from pathlib import Path
from concurrent import futures
from unittest.mock import patch

import grpc

from contract_agent.agent_rpc import agent_pb2, agent_pb2_grpc
from contract_agent.agent_rpc.server import AgentRpcServicer
from contract_agent.logger.audit import AuditLogger
from contract_agent.config import Settings
from contract_agent.orchestration.protocol import AgentOutput, AgentStatus, PipelineStatus
from contract_agent.schemas.review import HealthResponse


class FakeReviewService:
    def health(self) -> HealthResponse:
        return HealthResponse(status="ok", llm_configured=True, knowledge_base_ready=False)


class AgentRpcServicerTests(unittest.TestCase):
    def test_health_uses_injected_services_without_starting_network_server(self):
        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        servicer.review_service = FakeReviewService()  # type: ignore[assignment]

        response = servicer.Health(agent_pb2.HealthRequest(), None)

        self.assertEqual(response.status, "ok")
        self.assertTrue(response.llm_configured)
        self.assertIn("review", response.capabilities)

    def test_redraft_missing_chat_key_returns_service_unavailable(self):
        servicer = AgentRpcServicer(
            runtime_settings=Settings(chat_api_key=None, llm_api_key=None, qwen_api_key=None)
        )

        response = servicer.Redraft(
            agent_pb2.RedraftRequest(
                contract_text="合同正文",
                contract_type="采购合同",
                our_side="甲方",
                accepted_issues_json="[]",
            ),
            None,
        )

        self.assertEqual(response.code, 503)
        self.assertIn("CHAT_API_KEY 或 LLM_API_KEY 未配置", response.error)

    def test_health_writes_rpc_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(Path(tmp) / "trace.jsonl")
            servicer = AgentRpcServicer(
                runtime_settings=Settings(chat_api_key="chat-key"), audit_logger=logger
            )
            servicer.review_service = FakeReviewService()  # type: ignore[assignment]

            servicer.Health(agent_pb2.HealthRequest(), None)
            records = [
                json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(records[0]["event"], "trace.started")
        self.assertEqual(records[0]["operation"], "grpc.Health")
        self.assertEqual(records[0]["prefix"], "[RPC]")
        self.assertEqual(records[-1]["event"], "trace.completed")
        self.assertEqual(len({record.get("trace_id") for record in records}), 1)

    def test_review_multi_agent_grpc_reaches_supervisor_runtime_boundary(self):
        def fake_run(state, initial_input, on_event=None):
            state.status = PipelineStatus.COMPLETED
            state.agent_outputs["supervisor"] = AgentOutput(
                agent_id="supervisor",
                status=AgentStatus.COMPLETED,
                input_summary=initial_input["contract_type"],
                structured_data={"review_report": {"overall_risk": "low"}},
            )
            return state

        class FakeMemoryManager:
            def __init__(self, *args, **kwargs):
                self.saved_states = []

            def save_pipeline_result(self, state):
                self.saved_states.append(state)

        class FakeEventPublisher:
            def __init__(self, *args, **kwargs):
                pass

            def publish(self, event):
                pass

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        agent_pb2_grpc.add_AgentRpcServiceServicer_to_server(servicer, server)
        port = server.add_insecure_port("127.0.0.1:0")

        with (
            patch("contract_agent.memory.manager.MemoryManager", FakeMemoryManager),
            patch("contract_agent.orchestration.events.EventPublisher", FakeEventPublisher),
            patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls,
        ):
            supervisor_cls.return_value.run.side_effect = fake_run
            server.start()
            try:
                channel = grpc.insecure_channel(f"127.0.0.1:{port}")
                stub = agent_pb2_grpc.AgentRpcServiceStub(channel)

                response = stub.ReviewMultiAgent(
                    agent_pb2.ReviewRequest(
                        contract_text="合同正文",
                        contract_type="采购合同",
                        our_side="甲方",
                    ),
                    timeout=5,
                )
            finally:
                server.stop(0)

        self.assertEqual(response.code, 200)
        payload = json.loads(response.json)
        self.assertEqual(payload["mode"], "multi_auto")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["report"], {"overall_risk": "low"})
        self.assertEqual(payload["agent_summaries"][0]["agent_id"], "supervisor")


if __name__ == "__main__":
    unittest.main()
