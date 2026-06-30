import unittest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contract_agent.logger.audit import AuditLogger
from contract_agent.config import Settings, temporary_settings
from contract_agent.schemas.chat import ChatMessage, ChatRequest
from contract_agent.schemas.review import (
    ExtractedFields,
    ReviewReport,
    ReviewResponse,
    ReviewSummary,
)
from contract_agent.services.chat_service import ChatService
from contract_agent.services.review_service import ReviewService


class ServiceConfigInjectionTests(unittest.TestCase):
    def test_chat_service_uses_constructor_settings_for_missing_key_guard(self):
        service = ChatService(
            runtime_settings=Settings(chat_api_key=None, react_max_steps=7),
            review_service=object(),
        )

        with temporary_settings(chat_api_key="global-key", react_max_steps=1):
            self.assertEqual(service.settings.react_max_steps, 7)
            with self.assertRaisesRegex(RuntimeError, "CHAT_API_KEY"):
                service._require_llm()

    def test_review_service_uses_constructor_settings_for_health(self):
        service = ReviewService(
            runtime_settings=Settings(chat_api_key="injected-key", vector_backend="faiss")
        )

        with temporary_settings(chat_api_key=None, vector_backend="milvus"):
            health = service.health()

        self.assertIsInstance(health.llm_configured, bool)
        self.assertEqual(service.settings.chat_api_key, "injected-key")

    def test_chat_service_writes_trace_for_review_intent(self):
        class FakeReviewService:
            def review(self, payload):
                return ReviewResponse(
                    summary=ReviewSummary(
                        contract_type="采购合同", overall_risk="info", risk_count=0
                    ),
                    extracted_fields=ExtractedFields(),
                    risks=[],
                    report=ReviewReport(
                        generated_at=datetime.now(timezone.utc),
                        overview="ok",
                        key_findings=[],
                        next_actions=[],
                    ),
                )

        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(Path(tmp) / "trace.jsonl")
            service = ChatService(
                runtime_settings=Settings(chat_api_key="chat-key"),
                review_service=FakeReviewService(),  # type: ignore[arg-type]
                audit_logger=logger,
            )
            service._route_intent = lambda payload: {"intent": "review", "query": "审查合同"}  # type: ignore[method-assign]

            list(
                service.chat_stream(
                    ChatRequest(
                        messages=[ChatMessage(role="user", content="请审查合同")],
                        contract_text="甲方与乙方签订采购合同。",
                    )
                )
            )
            records = [
                json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()
            ]

        span_names = {
            record.get("span_name") for record in records if record["event"] == "span.completed"
        }
        self.assertIn("chat.route", span_names)
        self.assertIn("chat.review", span_names)
        self.assertIn("[Service][Chat]", {record.get("prefix") for record in records})
        self.assertEqual(len({record.get("trace_id") for record in records}), 1)

    def test_router_output_falls_back_when_query_is_not_text(self):
        service = ChatService.__new__(ChatService)
        payload = ChatRequest(messages=[ChatMessage(role="user", content="查询付款违约责任")])

        parsed = service._parse_router_output(
            '{"intent":"search","query":{"text":"付款违约"},"reason":{"why":"ok"}}',
            payload,
        )

        self.assertEqual(parsed["intent"], "search")
        self.assertEqual(parsed["query"], "查询付款违约责任")
        self.assertIsInstance(parsed["query"], str)
        self.assertIsInstance(parsed["reason"], str)

    def test_review_stream_yields_start_before_review_work_runs(self):
        calls: list[str] = []

        class FakeReviewService:
            def review(self, payload: Any) -> ReviewResponse:
                calls.append("review")
                return ReviewResponse(
                    summary=ReviewSummary(
                        contract_type="采购合同", overall_risk="info", risk_count=0
                    ),
                    extracted_fields=ExtractedFields(),
                    risks=[],
                    report=ReviewReport(
                        generated_at=datetime.now(timezone.utc),
                        overview="ok",
                        key_findings=[],
                        next_actions=[],
                    ),
                )

        service = ChatService(
            runtime_settings=Settings(chat_api_key="chat-key"),
            review_service=FakeReviewService(),  # type: ignore[arg-type]
        )
        service._route_intent = lambda payload: {"intent": "review", "query": "审查合同"}  # type: ignore[method-assign]

        stream = service.chat_stream(
            ChatRequest(
                messages=[ChatMessage(role="user", content="请审查合同")],
                contract_text="甲方与乙方签订采购合同。",
            )
        )
        first_event = next(stream)

        self.assertEqual(first_event["event"], "start")
        self.assertEqual(first_event["data"]["intent"], "review")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
