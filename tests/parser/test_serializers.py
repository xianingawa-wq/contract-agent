import json
import unittest

from contract_agent.parser import (
    BlockLocation,
    DetectorResult,
    DocumentBlock,
    DocumentMetadata,
    ParsedDocument,
)
from contract_agent.parser.serializers import (
    to_evidence_json,
    to_llm_context,
    to_markdown,
    to_plain_text,
    to_rag_documents,
)


class ParserSerializerTests(unittest.TestCase):
    def make_document(self) -> ParsedDocument:
        return ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc-1",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
                title="采购合同",
                contract_type_hint="采购合同",
                page_count=1,
            ),
            raw_text="",
            blocks=[
                DocumentBlock(
                    block_id="p1-b0",
                    block_type="title",
                    text="采购合同",
                    location=BlockLocation(page_no=1, block_index=0),
                ),
                DocumentBlock(
                    block_id="p1-b1",
                    block_type="clause_header",
                    text="第一条 付款",
                    level=1,
                    location=BlockLocation(page_no=1, block_index=1),
                    metadata={"clause_no": "第一条"},
                ),
            ],
            detector_results=[
                DetectorResult(
                    result_id="r1",
                    detector_name="clause_header",
                    rule_id="clause.header.zh.article.v1",
                    result_type="clause_header",
                    value={"clause_no": "第一条", "title": "付款"},
                    block_ids=["p1-b1"],
                    confidence=0.9,
                    reason="命中条款标题规则",
                )
            ],
        )

    def test_plain_text_markdown_llm_context_and_rag_outputs_use_blocks(self):
        document = self.make_document()

        self.assertEqual(to_plain_text(document), "采购合同\n第一条 付款")
        self.assertIn("# 采购合同", to_markdown(document))
        llm_context = to_llm_context(document)
        self.assertIn("p1-b1", llm_context)
        self.assertIn("page=1", llm_context)
        self.assertIn("confidence=1.00", llm_context)
        rag_documents = to_rag_documents(document)
        self.assertEqual(rag_documents[0]["metadata"]["doc_id"], "doc-1")
        self.assertEqual(rag_documents[1]["metadata"]["block_id"], "p1-b1")
        json.dumps(rag_documents, ensure_ascii=False)

    def test_evidence_json_is_json_safe_and_includes_detector_reasons(self):
        evidence = to_evidence_json(self.make_document())

        self.assertIn("blocks", evidence)
        self.assertIn("detector_results", evidence)
        self.assertEqual(evidence["detector_results"][0]["reason"], "命中条款标题规则")
        json.dumps(evidence, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
