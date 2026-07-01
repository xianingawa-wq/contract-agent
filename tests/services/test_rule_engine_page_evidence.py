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

        related = RuleEngine()._related_chunks(document, target)

        self.assertEqual(related, [])


if __name__ == "__main__":
    unittest.main()
