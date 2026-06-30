import json
import math
import unittest
from pathlib import Path, PurePosixPath

from contract_agent.parser import (
    BlockConfidence,
    BlockLocation,
    ClauseChunk,
    DocumentBlock,
    DocumentDefinition,
    DocumentFigure,
    DocumentMetadata,
    DocumentReference,
    DocumentSemanticGraph,
    DocumentSpan,
    DocumentTable,
    ParsedDocument,
)
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.parser_source import ParserSource, _local_source_path


def make_document() -> ParsedDocument:
    return ParsedDocument(
        metadata=DocumentMetadata(
            doc_id="doc-1",
            file_name="contract.txt",
            file_type="txt",
            source_path="inline",
            title="Purchase Contract",
            page_count=1,
        ),
        raw_text="Section 1 Payment\nContract body",
        spans=[
            DocumentSpan(
                span_id="p1-b0",
                page_no=1,
                block_index=0,
                start_offset=0,
                end_offset=17,
                text="Section 1 Payment",
            )
        ],
        clause_chunks=[
            ClauseChunk(
                chunk_id="chunk-1",
                chunk_level="clause",
                clause_no="1",
                section_title="Payment",
                page_no=1,
                start_offset=0,
                end_offset=17,
                source_text="Section 1 Payment",
            )
        ],
    )


class ParserModelTests(unittest.TestCase):
    def test_parsed_document_keeps_existing_and_extension_fields(self):
        document = make_document()

        self.assertEqual(document.metadata.file_name, "contract.txt")
        self.assertEqual(document.raw_text, "Section 1 Payment\nContract body")
        self.assertEqual(len(document.spans), 1)
        self.assertEqual(len(document.clause_chunks), 1)
        self.assertEqual(document.schema_version, "2.0")
        self.assertEqual(document.blocks, [])
        self.assertEqual(document.markdown_content, "")
        self.assertEqual(document.conversion_metadata, {})
        self.assertEqual(document.html_content, "")
        self.assertEqual(document.tables, [])
        self.assertEqual(document.figures, [])
        self.assertEqual(document.definitions, [])
        self.assertEqual(document.references, [])
        self.assertIsNone(document.semantic_graph)

    def test_document_block_defaults_are_stable(self):
        block = DocumentBlock(
            block_id="p1-b0",
            block_type="paragraph",
            text="body",
            location=BlockLocation(block_index=0),
        )

        self.assertEqual(block.location.page_no, None)
        self.assertEqual(block.location.span_ids, [])
        self.assertEqual(block.confidence, BlockConfidence())
        self.assertEqual(block.metadata, {})

    def test_extension_fields_use_independent_default_collections(self):
        first = make_document()
        second = make_document()

        first.tables.append(DocumentTable(table_id="t1", rows=[["a"]]))
        first.figures.append(DocumentFigure(figure_id="f1"))
        first.definitions.append(DocumentDefinition(term="price", definition="amount"))
        first.references.append(DocumentReference(source_span_id="p1-b0", target="section 2"))

        self.assertEqual(second.tables, [])
        self.assertEqual(second.figures, [])
        self.assertEqual(second.definitions, [])
        self.assertEqual(second.references, [])

        first.blocks.append(
            DocumentBlock(
                block_id="p1-b0",
                block_type="paragraph",
                text="body",
                location=BlockLocation(block_index=0),
            )
        )

        self.assertEqual(second.blocks, [])

    def test_model_dump_json_round_trip_is_stable(self):
        document = make_document()

        dumped = document.model_dump(mode="json")
        json.dumps(dumped, ensure_ascii=False)
        restored = ParsedDocument.model_validate(dumped)

        self.assertEqual(restored, document)

    def test_json_fields_reject_non_json_safe_values(self):
        with self.assertRaises(ValueError) as exc:
            DocumentBlock(
                block_id="p1-b0",
                block_type="paragraph",
                text="body",
                location=BlockLocation(block_index=0),
                metadata={"raw": b"bytes"},
            )
        self.assertIn("metadata", str(exc.exception))
        self.assertIn("JSON-compatible", str(exc.exception))

        with self.assertRaises(ValueError) as exc:
            ParsedDocument(
                metadata=DocumentMetadata(
                    doc_id="doc-1",
                    file_name="contract.txt",
                    file_type="txt",
                    source_path="inline",
                ),
                raw_text="body",
                conversion_metadata={"path": Path("contract.txt")},
            )
        self.assertIn("conversion_metadata", str(exc.exception))
        self.assertIn("JSON-compatible", str(exc.exception))

    def test_json_fields_reject_non_finite_floats_and_extension_metadata(self):
        cases = [
            lambda: DocumentBlock(
                block_id="p1-b0",
                block_type="paragraph",
                text="body",
                location=BlockLocation(block_index=0),
                metadata={"score": math.nan},
            ),
            lambda: DocumentTable(table_id="t1", metadata={"score": math.inf}),
            lambda: DocumentFigure(figure_id="f1", metadata={"raw": b"bytes"}),
            lambda: DocumentSemanticGraph(nodes=[{"raw": b"bytes"}]),
            lambda: DocumentSemanticGraph(edges=[{"score": math.inf}]),
            lambda: DocumentSemanticGraph(metadata={"path": Path("contract.txt")}),
            lambda: MarkdownDocument(
                markdown_content="body",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
                backend_name="test",
                conversion_metadata={"score": math.nan},
            ),
        ]
        for index, build in enumerate(cases):
            with self.subTest(case=f"json-safe-{index}"):
                with self.assertRaises(ValueError):
                    build()

    def test_location_offsets_and_page_indexes_are_validated(self):
        with self.assertRaises(ValueError):
            DocumentMetadata(
                doc_id="bad",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
                page_count=-7,
            )
        with self.assertRaises(ValueError):
            DocumentSpan(
                span_id="bad",
                page_no=0,
                block_index=0,
                start_offset=0,
                end_offset=1,
                text="x",
            )
        with self.assertRaises(ValueError):
            DocumentSpan(
                span_id="bad",
                page_no=1,
                block_index=-1,
                start_offset=0,
                end_offset=1,
                text="x",
            )
        with self.assertRaises(ValueError):
            DocumentSpan(
                span_id="bad",
                page_no=1,
                block_index=0,
                start_offset=5,
                end_offset=4,
                text="x",
            )
        with self.assertRaises(ValueError):
            ClauseChunk(
                chunk_id="bad",
                chunk_level="paragraph",
                section_title="bad",
                page_no=1,
                start_offset=5,
                end_offset=4,
                source_text="x",
            )
        with self.assertRaises(ValueError):
            BlockLocation(block_index=0, start_offset=5, end_offset=4)

    def test_parser_source_kind_must_match_payload(self):
        invalid_sources = [
            lambda: ParserSource(
                kind="text",
                file_name="contract.txt",
                content=b"body",
                source_path="contract.txt",
                file_type="txt",
            ),
            lambda: ParserSource(
                kind="bytes",
                file_name="contract.txt",
                text="body",
                source_path="contract.txt",
                file_type="txt",
            ),
            lambda: ParserSource(
                kind="path",
                file_name="contract.txt",
                text="body",
                source_path="contract.txt",
                file_type="txt",
            ),
        ]

        for index, build in enumerate(invalid_sources):
            with self.subTest(case=f"invalid-source-{index}"):
                with self.assertRaises(ValueError):
                    build()

    def test_parser_source_from_path_keeps_stable_safe_path_identifier(self):
        path = Path("fixtures\nunsafe") / "contract.txt"

        source = ParserSource.from_path(path)

        self.assertTrue(source.local_path.is_absolute())
        self.assertEqual(source.file_name, "contract.txt")
        self.assertTrue(source.source_path.startswith("local:"))
        self.assertIn("contract.txt", source.source_path)
        self.assertNotIn("\n", source.source_path)

    def test_parser_source_from_path_sanitizes_local_file_name(self):
        source = ParserSource.from_path(Path("contract\nsecret\x1b.txt"))

        self.assertEqual(source.file_name, "contract\nsecret\x1b.txt")
        self.assertIn("contract_secret_.txt", source.source_path)
        self.assertNotIn("\n", source.source_path)
        self.assertNotIn("\x1b", source.source_path)

    def test_local_source_path_sanitizes_posix_filename_separators(self):
        source_path = _local_source_path(PurePosixPath("contract\\secret.txt"))

        self.assertIn("contract_secret.txt", source_path)
        self.assertNotIn("\\", source_path)

    def test_parser_source_from_path_distinguishes_same_name_files(self):
        first = ParserSource.from_path(Path("first") / "contract.txt")
        second = ParserSource.from_path(Path("second") / "contract.txt")

        self.assertEqual(first.file_name, second.file_name)
        self.assertNotEqual(first.source_path, second.source_path)


if __name__ == "__main__":
    unittest.main()
