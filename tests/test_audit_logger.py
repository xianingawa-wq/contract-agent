import json
import tempfile
import unittest
from pathlib import Path

from contract_agent.schemas.review import RiskItem
from contract_agent.schemas.review import ReviewRequest
from contract_agent.services.review_service import ReviewService


class AuditLoggerTests(unittest.TestCase):
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

            events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]

        self.assertTrue(result.risks)
        event_names = [event["event"] for event in events]
        self.assertEqual(event_names[0], "review.started")
        self.assertIn("review.rules.completed", event_names)
        self.assertIn("review.risk.enriched", event_names)
        self.assertEqual(event_names[-1], "review.completed")
        self.assertTrue(all(event.get("timestamp") for event in events))
        self.assertTrue(all(event.get("scope") == "audit" for event in events))


if __name__ == "__main__":
    unittest.main()
