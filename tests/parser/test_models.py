import json
import unittest
from pathlib import Path

from contract_agent.parser import (
    BlockConfidence,
    BlockLocation,
    ClauseChunk,
    DetectorResult,
    DocumentBlock,
    DocumentMetadata,
    DocumentSpan,
    ParsedDocument,
)


def make_document() -> ParsedDocument:
    return ParsedDocument(
        metadata=DocumentMetadata(
            doc_id="doc-1",
            file_name="contract.txt",
            file_type="txt",
            source_path="inline",
            title="采购合同",
            page_count=1,
        ),
        raw_text="第一条 付款\n合同正文",
        spans=[
            DocumentSpan(
                span_id="p1-b0",
                page_no=1,
                block_index=0,
                start_offset=0,
                end_offset=5,
                text="第一条 付款",
            )
        ],
        clause_chunks=[
            ClauseChunk(
                chunk_id="chunk-1",
                chunk_level="clause",
                clause_no="第一条",
                section_title="付款",
                page_no=1,
                start_offset=0,
                end_offset=5,
                source_text="第一条 付款",
            )
        ],
    )


class ParserModelTests(unittest.TestCase):
    def test_parsed_document_keeps_existing_and_extension_fields(self):
        document = make_document()

        self.assertEqual(document.metadata.file_name, "contract.txt")
        self.assertEqual(document.raw_text, "第一条 付款\n合同正文")
        self.assertEqual(len(document.spans), 1)
        self.assertEqual(len(document.clause_chunks), 1)
        self.assertEqual(document.schema_version, "2.0")
        self.assertEqual(document.blocks, [])
        self.assertEqual(document.detector_results, [])
        self.assertEqual(document.markdown_content, "")
        self.assertEqual(document.conversion_metadata, {})
        self.assertEqual(document.html_content, "")
        self.assertEqual(document.tables, [])
        self.assertEqual(document.figures, [])
        self.assertEqual(document.definitions, [])
        self.assertEqual(document.references, [])
        self.assertIsNone(document.semantic_graph)

    def test_document_block_detector_result_defaults_are_stable(self):
        block = DocumentBlock(
            block_id="p1-b0",
            block_type="paragraph",
            text="正文",
            location=BlockLocation(block_index=0),
        )
        result = DetectorResult(
            result_id="r1",
            detector_name="metadata",
            result_type="metadata.title",
            value={"title": "采购合同"},
            confidence=0.8,
        )

        self.assertEqual(block.location.page_no, None)
        self.assertEqual(block.location.span_ids, [])
        self.assertEqual(block.confidence, BlockConfidence())
        self.assertEqual(block.metadata, {})
        self.assertEqual(result.block_ids, [])
        self.assertEqual(result.span_ids, [])
        self.assertIsNone(result.reason)

    def test_extension_fields_use_independent_default_collections(self):
        first = make_document()
        second = make_document()

        first.tables.append({"table_id": "t1", "rows": [["a"]]})
        first.figures.append({"figure_id": "f1"})
        first.definitions.append({"term": "价款", "definition": "合同金额"})
        first.references.append({"source_span_id": "p1-b0", "target": "第二条"})

        self.assertEqual(second.tables, [])
        self.assertEqual(second.figures, [])
        self.assertEqual(second.definitions, [])
        self.assertEqual(second.references, [])

        first.blocks.append(
            DocumentBlock(
                block_id="p1-b0",
                block_type="paragraph",
                text="正文",
                location=BlockLocation(block_index=0),
            )
        )
        first.detector_results.append(
            DetectorResult(
                result_id="r1",
                detector_name="metadata",
                result_type="metadata.title",
                value={"title": "采购合同"},
                confidence=0.8,
            )
        )

        self.assertEqual(second.blocks, [])
        self.assertEqual(second.detector_results, [])

    def test_model_dump_json_round_trip_is_stable(self):
        document = make_document()

        dumped = document.model_dump(mode="json")
        json.dumps(dumped, ensure_ascii=False)
        restored = ParsedDocument.model_validate(dumped)

        self.assertEqual(restored, document)

    def test_json_fields_reject_non_json_safe_values(self):
        with self.assertRaises(ValueError):
            DocumentBlock(
                block_id="p1-b0",
                block_type="paragraph",
                text="正文",
                location=BlockLocation(block_index=0),
                metadata={"raw": b"bytes"},
            )

        with self.assertRaises(ValueError):
            DetectorResult(
                result_id="r1",
                detector_name="metadata",
                result_type="metadata.title",
                value={"path": Path("contract.txt")},
                confidence=0.8,
            )


if __name__ == "__main__":
    unittest.main()
