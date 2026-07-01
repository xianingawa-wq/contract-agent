import unittest

from contract_agent.parser import ClauseChunk, DocumentMetadata, ParsedDocument
from contract_agent.services.rule_engine import RuleEngine


class RuleEnginePageEvidenceTests(unittest.TestCase):
    def test_risk_page_number_follows_source_chunk_even_when_unknown(self):
        engine = RuleEngine()
        rule = {
            "rule_id": "R-page",
            "title": "Page evidence",
            "severity": "low",
            "description": "desc",
            "suggestion": "suggest",
        }
        unknown_chunk = ClauseChunk(
            chunk_id="chunk-unknown",
            chunk_level="paragraph",
            section_title="Unknown page",
            page_no=None,
            start_offset=0,
            end_offset=7,
            source_text="Unknown",
        )
        known_chunk = ClauseChunk(
            chunk_id="chunk-known",
            chunk_level="paragraph",
            section_title="Known page",
            page_no=2,
            start_offset=8,
            end_offset=13,
            source_text="Known",
        )

        self.assertIsNone(engine._build_risk(rule, "Unknown", unknown_chunk).page_no)
        self.assertEqual(engine._build_risk(rule, "Known", known_chunk).page_no, 2)

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

        risks = RuleEngine().check("通用合同", document)
        page_by_evidence = {risk.evidence: risk.page_no for risk in risks}

        self.assertIsNone(page_by_evidence["付款"])
        self.assertEqual(page_by_evidence["支付"], 2)

    def test_related_chunks_do_not_match_unknown_page_numbers_as_same_page(self):
        target = ClauseChunk(
            chunk_id="target",
            chunk_level="paragraph",
            section_title="Target",
            page_no=None,
            start_offset=0,
            end_offset=6,
            source_text="Target",
        )
        other_unknown = ClauseChunk(
            chunk_id="other",
            chunk_level="paragraph",
            section_title="Other",
            page_no=None,
            start_offset=7,
            end_offset=12,
            source_text="Other",
        )
        same_page = ClauseChunk(
            chunk_id="same-page",
            chunk_level="paragraph",
            section_title="Same page",
            page_no=2,
            start_offset=13,
            end_offset=22,
            source_text="Same page",
        )
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text="Target\nOther\nSame page",
            clause_chunks=[target, other_unknown, same_page],
        )

        engine = RuleEngine()
        related = engine._related_chunks(document, target)

        self.assertEqual(related, [])

        known_raw_text = "Known target\nOther\nSame page"
        known_target = ClauseChunk(
            chunk_id="known-target",
            chunk_level="paragraph",
            section_title="Known target",
            page_no=2,
            start_offset=0,
            end_offset=12,
            source_text="Known target",
        )
        other_unknown_for_known = ClauseChunk(
            chunk_id="other",
            chunk_level="paragraph",
            section_title="Other",
            page_no=None,
            start_offset=13,
            end_offset=18,
            source_text="Other",
        )
        same_page_for_known = ClauseChunk(
            chunk_id="same-page",
            chunk_level="paragraph",
            section_title="Same page",
            page_no=2,
            start_offset=19,
            end_offset=28,
            source_text="Same page",
        )
        related_known = engine._related_chunks(
            ParsedDocument(
                metadata=document.metadata,
                raw_text=known_raw_text,
                clause_chunks=[known_target, other_unknown_for_known, same_page_for_known],
            ),
            known_target,
        )

        self.assertEqual([chunk.chunk_id for chunk in related_known], ["known-target", "same-page"])


if __name__ == "__main__":
    unittest.main()
