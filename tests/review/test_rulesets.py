import unittest

from contract_agent.parser import ClauseChunk, DocumentMetadata, ParsedDocument
from contract_agent.services.rule_engine import RuleEngine


def make_purchase_document() -> ParsedDocument:
    text = "第二条 付款方式：甲方应于合同签订后5日内支付100%合同价款。"
    return ParsedDocument(
        metadata=DocumentMetadata(
            doc_id="doc-1",
            file_name="contract.txt",
            file_type="txt",
            source_path="inline",
            page_count=1,
        ),
        raw_text=text,
        clause_chunks=[
            ClauseChunk(
                chunk_id="chunk-1",
                chunk_level="clause",
                clause_no="2",
                section_title="付款方式",
                page_no=1,
                start_offset=0,
                end_offset=len(text),
                source_text=text,
            )
        ],
    )


class RulesetAliasTests(unittest.TestCase):
    def test_rule_engine_accepts_purchase_alias_from_rulesets(self):
        risks = RuleEngine().check("purchase", make_purchase_document())
        rule_ids = [risk.rule_id for risk in risks]

        self.assertIn("PAY_001", rule_ids)
        self.assertIn("ACC_001", rule_ids)


if __name__ == "__main__":
    unittest.main()
