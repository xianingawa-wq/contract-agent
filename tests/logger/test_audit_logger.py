import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from contract_agent.schemas.review import RiskItem
from contract_agent.schemas.review import ReviewRequest
from contract_agent.services.review_service import ReviewService


class AuditLoggerTests(unittest.TestCase):
    def test_audit_logger_normalizes_non_json_payloads_without_breaking_trace(self):
        from contract_agent.logger.audit import AuditLogger

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "trace.jsonl"
            logger = AuditLogger(log_path)
            business_executed = False

            with logger.trace(
                "debug.operation",
                started_at=datetime(2026, 6, 30, tzinfo=timezone.utc),
                source_path=Path("contracts/demo.txt"),
            ):
                business_executed = True

            records = [
                json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(business_executed)
        started = records[0]
        self.assertEqual(started["event"], "trace.started")
        self.assertEqual(started["started_at"], "2026-06-30T00:00:00+00:00")
        self.assertEqual(started["source_path"], "contracts/demo.txt")

    def test_audit_logger_payload_cannot_override_reserved_fields(self):
        from contract_agent.logger.audit import AuditLogger

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "trace.jsonl"
            logger = AuditLogger(log_path)

            with logger.trace("debug.operation") as trace_id:
                with logger.span("stage.outer") as span_id:
                    logger.emit(
                        "custom.event",
                        timestamp="not-a-time",
                        scope="wrong",
                        prefix="wrong",
                        trace_id="wrong",
                        span_id="wrong",
                        parent_span_id="wrong",
                    )

            custom = next(
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if json.loads(line)["event"] == "custom.event"
            )

        self.assertNotEqual(custom["timestamp"], "not-a-time")
        self.assertEqual(custom["scope"], "audit")
        self.assertEqual(custom["prefix"], "[Audit]")
        self.assertEqual(custom["trace_id"], trace_id)
        self.assertEqual(custom["span_id"], span_id)
        self.assertNotIn("parent_span_id", custom)

    def test_audit_logger_handles_non_string_keys_cycles_and_deep_payloads(self):
        from contract_agent.logger.audit import AuditLogger

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "trace.jsonl"
            logger = AuditLogger(log_path, _extra={42: "answer"})
            cyclic: dict[str, object] = {}
            cyclic["self"] = cyclic
            deep: object = "leaf"
            for _ in range(32):
                deep = {"child": deep}

            logger.emit("custom.event", cyclic=cyclic, deep=deep)

            record = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertEqual(record["42"], "answer")
        self.assertEqual(record["cyclic"]["self"], "<cycle>")
        self.assertIn("<max-depth>", json.dumps(record["deep"], ensure_ascii=False))

    def test_audit_logger_records_trace_spans_and_failures(self):
        from contract_agent.logger.audit import AuditLogger

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "trace.jsonl"
            logger = AuditLogger(log_path)

            with self.assertRaises(ValueError):
                with logger.trace("debug.operation", request_id="req-1") as trace_id:
                    with logger.span("stage.outer", item_count=2):
                        logger.emit("custom.event", detail="inside")
                        with logger.span("stage.inner"):
                            raise ValueError("boom")

            records = [
                json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        event_names = [record["event"] for record in records]
        self.assertEqual(event_names[0], "trace.started")
        self.assertIn("span.started", event_names)
        self.assertIn("custom.event", event_names)
        self.assertIn("span.failed", event_names)
        self.assertEqual(event_names[-1], "trace.failed")
        self.assertTrue(all(record.get("trace_id") == trace_id for record in records))

        outer_started = next(
            record
            for record in records
            if record.get("span_name") == "stage.outer" and record["event"] == "span.started"
        )
        inner_failed = next(
            record
            for record in records
            if record.get("span_name") == "stage.inner" and record["event"] == "span.failed"
        )
        custom = next(record for record in records if record["event"] == "custom.event")

        self.assertEqual(custom["span_id"], outer_started["span_id"])
        self.assertEqual(inner_failed["parent_span_id"], outer_started["span_id"])
        self.assertEqual(inner_failed["error_type"], "ValueError")
        self.assertIn("duration_ms", inner_failed)
        self.assertTrue(all(record.get("prefix") == "[Audit]" for record in records))

    def test_audit_logger_can_create_component_prefixed_child_logger(self):
        from contract_agent.logger.audit import AuditLogger

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "trace.jsonl"
            logger = AuditLogger(log_path).with_prefix("[Knowledge][RAG]", scope="rag")

            logger.emit("rag.test")
            record = json.loads(log_path.read_text(encoding="utf-8"))

        self.assertEqual(record["prefix"], "[Knowledge][RAG]")
        self.assertEqual(record["scope"], "rag")

    def test_review_service_writes_structured_audit_events(self):
        from contract_agent.logger.audit import AuditLogger

        class FakeRetriever:
            def retrieve_documents_with_rerank(self, **kwargs):
                return []

        class FakeReviewer:
            def enrich_risk(self, risk, contract_type, clause_text, retrieved_contexts):
                risk.ai_explanation = "demo explanation"
                return risk

        class FakeRuleEngine:
            def check(self, contract_type, document):
                return [
                    RiskItem(
                        rule_id="DEMO_001",
                        title="demo risk",
                        severity="high",
                        description="demo description",
                        evidence="demo evidence",
                        suggestion="demo suggestion",
                    )
                ]

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            service = ReviewService(audit_logger=AuditLogger(log_path))
            service.rule_engine = FakeRuleEngine()
            service._require_knowledge_retriever = lambda: FakeRetriever()
            service._require_llm_reviewer = lambda: FakeReviewer()

            result = service.review(
                ReviewRequest(
                    contract_text="甲方应于合同签订后3日内支付100%合同价款。",
                    contract_type="purchase",
                    our_side="buyer",
                )
            )

            events = [
                json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertTrue(result.risks)
        self.assertIsNotNone(result.trace)
        self.assertGreater(result.trace.estimated_total_tokens, 0)
        event_names = [event["event"] for event in events]
        self.assertEqual(event_names[0], "trace.started")
        self.assertIn("review.started", event_names)
        self.assertIn("review.rules.completed", event_names)
        self.assertIn("review.risk.enriched", event_names)
        self.assertIn("review.completed", event_names)
        self.assertEqual(event_names[-1], "trace.completed")
        self.assertTrue(all(event.get("timestamp") for event in events))
        self.assertTrue(all(event.get("scope") == "review" for event in events))
        self.assertTrue(all(event.get("prefix") == "[Service][Review]" for event in events))

    def test_review_service_audit_events_share_trace_context(self):
        from contract_agent.logger.audit import AuditLogger

        class FakeRetriever:
            def retrieve_documents_with_rerank(self, **kwargs):
                return []

        class FakeReviewer:
            def enrich_risk(self, risk, contract_type, clause_text, retrieved_contexts):
                return risk

        class FakeRuleEngine:
            def check(self, contract_type, document):
                return []

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            service = ReviewService(audit_logger=AuditLogger(log_path))
            service.rule_engine = FakeRuleEngine()
            service._require_knowledge_retriever = lambda: FakeRetriever()
            service._require_llm_reviewer = lambda: FakeReviewer()

            service.review(
                ReviewRequest(
                    contract_text="甲方与乙方签订采购合同。",
                    contract_type="purchase",
                    our_side="buyer",
                )
            )

            events = [
                json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        trace_ids = {event.get("trace_id") for event in events}
        self.assertEqual(len(trace_ids), 1)
        self.assertNotIn(None, trace_ids)
        self.assertIn("[Service][Review]", {event.get("prefix") for event in events})
        self.assertIn("trace.started", [event["event"] for event in events])
        self.assertIn("trace.completed", [event["event"] for event in events])
        self.assertIn(
            "review.rules",
            {event.get("span_name") for event in events if event["event"] == "span.completed"},
        )

    def test_review_service_preserves_parse_audit_span(self):
        from contract_agent.logger.audit import AuditLogger

        class FakeRetriever:
            def retrieve_documents_with_rerank(self, **kwargs):
                return []

        class FakeReviewer:
            def enrich_risk(self, risk, contract_type, clause_text, retrieved_contexts):
                return risk

        class FakeRuleEngine:
            def check(self, contract_type, document):
                return []

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            service = ReviewService(audit_logger=AuditLogger(log_path))
            service.rule_engine = FakeRuleEngine()
            service._require_knowledge_retriever = lambda: FakeRetriever()
            service._require_llm_reviewer = lambda: FakeReviewer()

            service.review(
                ReviewRequest(
                    contract_text="甲方与乙方签订采购合同。",
                    contract_type="purchase",
                    our_side="buyer",
                )
            )

            events = [
                json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()
            ]

        parse_events = [event for event in events if event.get("span_name") == "review.parse"]
        self.assertEqual(
            [event["event"] for event in parse_events],
            ["span.started", "span.completed"],
        )
        self.assertEqual(parse_events[0]["parser"], "text")


if __name__ == "__main__":
    unittest.main()
