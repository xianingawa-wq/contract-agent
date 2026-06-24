import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from docx import Document

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import (
    ContractParser,
    DocumentLoadError,
    DocumentParseError,
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
