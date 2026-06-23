import unittest
import json
import tempfile
from pathlib import Path

from contract_agent.agent_rpc import agent_pb2
from contract_agent.agent_rpc.server import AgentRpcServicer
from contract_agent.logger.audit import AuditLogger
from contract_agent.runtime.config import Settings
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
        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key=None, llm_api_key=None, qwen_api_key=None))

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
            servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"), audit_logger=logger)
            servicer.review_service = FakeReviewService()  # type: ignore[assignment]

            servicer.Health(agent_pb2.HealthRequest(), None)
            records = [json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(records[0]["event"], "trace.started")
        self.assertEqual(records[0]["operation"], "grpc.Health")
        self.assertEqual(records[0]["prefix"], "[RPC]")
        self.assertEqual(records[-1]["event"], "trace.completed")
        self.assertEqual(len({record.get("trace_id") for record in records}), 1)


if __name__ == "__main__":
    unittest.main()
