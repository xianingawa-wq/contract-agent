import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from docx import Document

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import (
    BlockLocation,
    ClauseChunk,
    ContractParser,
    DocumentBlock,
    DocumentLoadError,
    DocumentParseError,
    DocumentMetadata,
    DocumentSpan,
    ParsedDocument,
    UnsupportedFileType,
    to_rag_documents,
)


class ContractParserServiceTests(unittest.TestCase):
    def test_parse_text_generates_metadata_spans_and_clause_chunks(self):
        document = ContractParser().parse_text("第一条 付款\n甲方应支付价款。", "inline.txt")

        self.assertEqual(document.metadata.file_name, "inline.txt")
        self.assertEqual(document.metadata.file_type, "txt")
        self.assertEqual(document.raw_text, "第一条 付款\n甲方应支付价款。")
        self.assertEqual(document.schema_version, "2.0")
        self.assertGreaterEqual(len(document.spans), 2)
        self.assertEqual(len(document.blocks), len(document.spans))
        self.assertTrue(document.detector_results)
        self.assertIn("converter", document.conversion_metadata)
        self.assertIn("第一条 付款", document.markdown_content)
        self.assertTrue(document.clause_chunks)
        self.assertEqual(document.clause_chunks[0].section_title, "付款")

    def test_parse_bytes_supports_txt_encodings(self):
        parser = ContractParser()

        utf8 = parser.parse_bytes("a.txt", "第一条 付款".encode("utf-8"))
        utf8_sig = parser.parse_bytes("b.txt", "第一条 付款".encode("utf-8-sig"))
        gb18030 = parser.parse_bytes("c.txt", "第一条 付款".encode("gb18030"))

        self.assertEqual(utf8.raw_text, "第一条 付款")
        self.assertEqual(utf8_sig.raw_text, "第一条 付款")
        self.assertEqual(gb18030.raw_text, "第一条 付款")

    def test_parse_docx_preserves_table_content_in_dom_markdown_chunks_and_rag(self):
        docx = Document()
        docx.add_paragraph("Project Application")
        table = docx.add_table(rows=3, cols=2)
        table.cell(0, 0).text = "Project Name"
        table.cell(0, 1).text = "Contract review with MCP and RAG"
        table.cell(1, 0).text = "Project Type"
        table.cell(1, 1).text = "Software"
        table.cell(2, 0).text = "Reason"
        table.cell(2, 1).text = "Improve contract review quality"
        buffer = BytesIO()
        docx.save(buffer)

        document = ContractParser().parse_bytes("project.docx", buffer.getvalue())

        self.assertIn("Project Name", document.raw_text)
        self.assertIn("Contract review with MCP and RAG", document.raw_text)
        self.assertEqual(len(document.tables), 1)
        self.assertEqual(
            document.tables[0].rows[0],
            ["Project Name", "Contract review with MCP and RAG"],
        )
        table_blocks = [block for block in document.blocks if block.block_type == "table"]
        self.assertEqual(len(table_blocks), 1)
        self.assertIn("| Project Name |", table_blocks[0].markdown or "")
        self.assertIn("Project Type | Software", document.markdown_content)
        self.assertTrue(any("Reason" in chunk.source_text for chunk in document.clause_chunks))
        self.assertTrue(
            any("Project Name" in item["page_content"] for item in to_rag_documents(document))
        )
        self.assertIsNotNone(document.semantic_graph)
        node_types = {node["type"] for node in document.semantic_graph.nodes}
        self.assertIn("document", node_types)
        self.assertIn("block", node_types)
        self.assertIn("chunk", node_types)
        self.assertIn("table", node_types)
        edge_types = {edge["type"] for edge in document.semantic_graph.edges}
        self.assertIn("contains", edge_types)
        self.assertIn("derived_from", edge_types)

    def test_parse_docx_preserves_adjacent_duplicate_table_cell_values(self):
        docx = Document()
        docx.add_paragraph("Penalty Table")
        table = docx.add_table(rows=1, cols=3)
        table.cell(0, 0).text = "Penalty"
        table.cell(0, 1).text = "10%"
        table.cell(0, 2).text = "10%"
        buffer = BytesIO()
        docx.save(buffer)

        document = ContractParser().parse_bytes("duplicate-cells.docx", buffer.getvalue())

        self.assertEqual(document.tables[0].rows[0], ["Penalty", "10%", "10%"])
        table_block = next(block for block in document.blocks if block.block_type == "table")
        self.assertIn("| Penalty | 10% | 10% |", table_block.markdown or "")

    def test_parse_docx_collapses_merged_table_cell_projection_by_xml_identity(self):
        docx = Document()
        docx.add_paragraph("Merged Table")
        table = docx.add_table(rows=1, cols=3)
        merged = table.cell(0, 0).merge(table.cell(0, 1))
        merged.text = "Merged label"
        table.cell(0, 2).text = "Value"
        buffer = BytesIO()
        docx.save(buffer)

        document = ContractParser().parse_bytes("merged-cells.docx", buffer.getvalue())

        self.assertEqual(document.tables[0].rows[0], ["Merged label", "", "Value"])
        table_block = next(block for block in document.blocks if block.block_type == "table")
        self.assertIn("| Merged label |  | Value |", table_block.markdown or "")

    def test_parse_docx_collapses_vertical_merged_cell_projection_by_xml_identity(self):
        docx = Document()
        docx.add_paragraph("Vertical Merge Table")
        table = docx.add_table(rows=2, cols=2)
        merged = table.cell(0, 0).merge(table.cell(1, 0))
        merged.text = "Vertical label"
        table.cell(0, 1).text = "Top"
        table.cell(1, 1).text = "Bottom"
        buffer = BytesIO()
        docx.save(buffer)

        document = ContractParser().parse_bytes("vertical-merged-cells.docx", buffer.getvalue())

        self.assertEqual(document.tables[0].rows, [["Vertical label", "Top"], ["", "Bottom"]])
        table_block = next(block for block in document.blocks if block.block_type == "table")
        self.assertIn("| Vertical label | Top |", table_block.markdown or "")
        self.assertIn("|  | Bottom |", table_block.markdown or "")

    def test_parse_docx_preserves_placeholders_for_rectangular_merged_cells(self):
        docx = Document()
        docx.add_paragraph("Rectangular Merge Table")
        table = docx.add_table(rows=2, cols=3)
        merged = table.cell(0, 0).merge(table.cell(1, 1))
        merged.text = "Merged block"
        table.cell(0, 2).text = "Top tail"
        table.cell(1, 2).text = "Bottom tail"
        buffer = BytesIO()
        docx.save(buffer)

        document = ContractParser().parse_bytes("rectangular-merged-cells.docx", buffer.getvalue())

        self.assertEqual(
            document.tables[0].rows,
            [["Merged block", "", "Top tail"], ["", "", "Bottom tail"]],
        )
        table_block = next(block for block in document.blocks if block.block_type == "table")
        self.assertIn("| Merged block |  | Top tail |", table_block.markdown or "")
        self.assertIn("|  |  | Bottom tail |", table_block.markdown or "")

    def test_parse_docx_keeps_all_placeholder_rows_for_fully_merged_rectangles(self):
        docx = Document()
        docx.add_paragraph("Fully Merged Rectangle")
        table = docx.add_table(rows=2, cols=2)
        merged = table.cell(0, 0).merge(table.cell(1, 1))
        merged.text = "Merged all"
        buffer = BytesIO()
        docx.save(buffer)

        document = ContractParser().parse_bytes("fully-merged-rectangle.docx", buffer.getvalue())

        self.assertEqual(document.tables[0].rows, [["Merged all", ""], ["", ""]])
        table_block = next(block for block in document.blocks if block.block_type == "table")
        self.assertIn("| Merged all |  |", table_block.markdown or "")
        self.assertIn("|  |  |", table_block.markdown or "")

    def test_semantic_graph_chunk_edges_do_not_grow_by_blocks_times_chunks(self):
        spans = []
        blocks = []
        chunks = []
        cursor = 0
        for index in range(20):
            text = f"Block {index}"
            start = cursor
            end = start + len(text)
            span_id = f"p1-b{index}"
            spans.append(
                DocumentSpan(
                    span_id=span_id,
                    page_no=1,
                    block_index=index,
                    start_offset=start,
                    end_offset=end,
                    text=text,
                )
            )
            blocks.append(
                DocumentBlock(
                    block_id=span_id,
                    block_type="paragraph",
                    text=text,
                    location=BlockLocation(
                        page_no=1,
                        block_index=index,
                        start_offset=start,
                        end_offset=end,
                        span_ids=[span_id],
                    ),
                )
            )
            chunks.append(
                ClauseChunk(
                    chunk_id=f"chunk-{index}",
                    chunk_level="sentence_group",
                    section_title="Body",
                    page_no=1,
                    start_offset=0,
                    end_offset=2000,
                    source_text=text,
                )
            )
            cursor = end + 1
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc-graph",
                file_name="graph.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text="\n".join(span.text for span in spans),
            spans=spans,
            blocks=blocks,
            clause_chunks=chunks,
        )

        graph = ContractParser()._build_semantic_graph(document)

        derived_edges = [edge for edge in graph.edges if edge["type"] == "derived_from"]
        self.assertLessEqual(len(derived_edges), len(chunks))

    def test_parse_path_delegates_to_bytes_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("第一条 付款", encoding="utf-8")

            document = ContractParser().parse_path(path)

        self.assertEqual(document.metadata.file_name, "contract.txt")
        self.assertEqual(document.raw_text, "第一条 付款")

    def test_parse_text_obeys_max_input_bytes(self):
        parser = ContractParser(parser_config=ParserConfig(max_input_bytes=8))

        with self.assertRaises(DocumentLoadError):
            parser.parse_text("123456789")

    def test_unsupported_suffix_raises_parser_exception(self):
        with self.assertRaises(UnsupportedFileType):
            ContractParser().parse_bytes("contract.xlsx", b"data")

    def test_empty_or_undecodable_text_raises_clear_parser_exception(self):
        parser = ContractParser()

        with self.assertRaises(DocumentParseError):
            parser.parse_text("   \n  ")
        with self.assertRaises(DocumentLoadError):
            parser.parse_bytes("contract.txt", b"\xff\xfe\x00\xff")


if __name__ == "__main__":
    unittest.main()
