import unittest
from unittest.mock import patch

from contract_agent.parser import ClauseChunk, DocumentMetadata, ParsedDocument
from contract_agent.services.rule_engine import RuleEngine


class RuleEnginePageEvidenceTests(unittest.TestCase):
    def test_risk_page_number_follows_source_chunk_even_when_unknown(self):
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text="Unknown\nKnown",
            clause_chunks=[
                ClauseChunk(
                    chunk_id="chunk-unknown",
                    chunk_level="paragraph",
                    section_title="Unknown page",
                    page_no=None,
                    start_offset=0,
                    end_offset=7,
                    source_text="Unknown",
                ),
                ClauseChunk(
                    chunk_id="chunk-known",
                    chunk_level="paragraph",
                    section_title="Known page",
                    page_no=2,
                    start_offset=8,
                    end_offset=13,
                    source_text="Known",
                ),
            ],
        )

        with patch(
            "contract_agent.services.rule_engine.RULES",
            {
                "通用合同": [
                    {
                        "rule_id": "R-page",
                        "title": "Page evidence",
                        "severity": "low",
                        "description": "desc",
                        "risk_domain": "page",
                        "check_scope": "clause",
                        "exclusions": [],
                        "requires_cross_clause": False,
                        "trigger_keywords": ["Unknown", "Known"],
                        "must_have_any": [],
                        "suggestion": "suggest",
                    }
                ]
            },
        ):
            risks = RuleEngine().check("通用合同", document)

        pages_by_evidence = {risk.evidence: risk.page_no for risk in risks}
        self.assertIsNone(pages_by_evidence["Unknown"])
        self.assertEqual(pages_by_evidence["Known"], 2)

    def test_public_check_preserves_unknown_and_known_page_numbers_on_risks(self):
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text="付款\n支付",
            clause_chunks=[
                ClauseChunk(
                    chunk_id="unknown-payment",
                    chunk_level="paragraph",
                    section_title="Unknown payment",
                    page_no=None,
                    start_offset=0,
                    end_offset=2,
                    source_text="付款",
                ),
                ClauseChunk(
                    chunk_id="known-payment",
                    chunk_level="paragraph",
                    section_title="Known payment",
                    page_no=2,
                    start_offset=3,
                    end_offset=5,
                    source_text="支付",
                ),
            ],
        )

        with patch(
            "contract_agent.services.rule_engine.RULES",
            {
                "通用合同": [
                    {
                        "rule_id": "TEST_PAYMENT",
                        "title": "Payment evidence",
                        "severity": "medium",
                        "description": "desc",
                        "risk_domain": "付款",
                        "check_scope": "clause",
                        "exclusions": [],
                        "requires_cross_clause": False,
                        "trigger_keywords": ["付款", "支付"],
                        "must_have_any": [],
                        "suggestion": "suggest",
                    }
                ]
            },
        ):
            risks = RuleEngine().check("通用合同", document)
        payment_pages = [risk.page_no for risk in risks if risk.evidence == "付款"]
        pay_pages = [risk.page_no for risk in risks if risk.evidence == "支付"]

        self.assertTrue(payment_pages)
        self.assertTrue(pay_pages)
        self.assertTrue(all(page_no is None for page_no in payment_pages))
        self.assertTrue(all(page_no == 2 for page_no in pay_pages))

    def test_cross_clause_rules_do_not_use_unknown_page_numbers_as_same_page_support(self):
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text="Target breach\nOther cure\nKnown target breach\nSame page cure",
            clause_chunks=[
                ClauseChunk(
                    chunk_id="unknown-target",
                    chunk_level="paragraph",
                    section_title="Unknown target",
                    page_no=None,
                    start_offset=0,
                    end_offset=13,
                    source_text="Target breach",
                ),
                ClauseChunk(
                    chunk_id="other-unknown",
                    chunk_level="paragraph",
                    section_title="Other unknown",
                    page_no=None,
                    start_offset=14,
                    end_offset=24,
                    source_text="Other cure",
                ),
                ClauseChunk(
                    chunk_id="known-target",
                    chunk_level="paragraph",
                    section_title="Known target",
                    page_no=2,
                    start_offset=25,
                    end_offset=44,
                    source_text="Known target breach",
                ),
                ClauseChunk(
                    chunk_id="same-page",
                    chunk_level="paragraph",
                    section_title="Same page",
                    page_no=2,
                    start_offset=45,
                    end_offset=59,
                    source_text="Same page cure",
                ),
            ],
        )

        with patch(
            "contract_agent.services.rule_engine.RULES",
            {
                "通用合同": [
                    {
                        "rule_id": "R-cross-page",
                        "title": "Cross clause support",
                        "severity": "medium",
                        "description": "desc",
                        "risk_domain": "support",
                        "check_scope": "clause",
                        "exclusions": [],
                        "requires_cross_clause": True,
                        "trigger_keywords": ["breach"],
                        "must_have_any": ["cure"],
                        "suggestion": "suggest",
                    }
                ]
            },
        ):
            risks = RuleEngine().check("通用合同", document)

        self.assertEqual([risk.evidence for risk in risks], ["Target breach"])
        self.assertIsNone(risks[0].page_no)


if __name__ == "__main__":
    unittest.main()
