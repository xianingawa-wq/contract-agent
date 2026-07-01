import unittest

from contract_agent.parser import ContractParser, DocumentSpan, MarkdownDocument, to_rag_documents
from contract_agent.parser.parsed.markdown_metadata_builder import build_metadata


class ParserPageEvidenceTests(unittest.TestCase):
    def test_parse_markdown_without_page_evidence_keeps_page_numbers_unknown(self):
        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content="Section 1 Payment\nBuyer shall pay.",
                file_name="contract.md",
                file_type="md",
                source_path="contract.md",
                backend_name="builtin",
            )
        )

        self.assertEqual(document.metadata.page_count, 0)
        self.assertTrue(all(span.page_no is None for span in document.spans))
        self.assertTrue(all(block.location.page_no is None for block in document.blocks))
        self.assertTrue(all(chunk.page_no is None for chunk in document.clause_chunks))
        rag_documents = to_rag_documents(document)
        self.assertTrue(rag_documents)
        self.assertTrue(all(item["metadata"]["page_no"] is None for item in rag_documents))

    def test_parse_markdown_uses_page_markers_as_evidence_without_body_pollution(self):
        markdown = "\n".join(
            [
                "Page 1 of 2",
                "Section 1 Payment",
                "Buyer shall pay.",
                "",
                "Page 2 of 2",
                "Section 2 Delivery",
                "Seller shall deliver.",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertNotIn("Page 1 of 2", document.raw_text)
        self.assertNotIn("Page 2 of 2", document.raw_text)
        self.assertEqual(document.metadata.page_count, 2)
        self.assertEqual(
            [(block.text, block.location.page_no) for block in document.blocks],
            [
                ("Section 1 Payment Buyer shall pay.", 1),
                ("Section 2 Delivery Seller shall deliver.", 2),
            ],
        )
        self.assertEqual([chunk.page_no for chunk in document.clause_chunks], [1, 2])
        self.assertEqual(document.conversion_metadata["markdown_page_evidence"]["marker_count"], 2)

    def test_parse_markdown_removes_standalone_english_page_markers(self):
        markdown = "\n".join(
            [
                "Page 1",
                "Section 1 Payment",
                "Buyer shall pay.",
                "",
                "Page 2",
                "Section 2 Delivery",
                "Seller shall deliver.",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertNotIn("Page 1", document.raw_text)
        self.assertNotIn("Page 2", document.raw_text)
        self.assertEqual(
            [(block.text, block.location.page_no) for block in document.blocks],
            [
                ("Section 1 Payment Buyer shall pay.", 1),
                ("Section 2 Delivery Seller shall deliver.", 2),
            ],
        )

    def test_parse_markdown_uses_chinese_page_markers(self):
        markdown = "\n".join(
            [
                "第 1 页，共 2 页",
                "Page one body",
                "",
                "第 2 页，共 2 页",
                "Page two body",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertNotIn("第 1 页", document.raw_text)
        self.assertEqual(document.metadata.page_count, 2)
        self.assertEqual([block.location.page_no for block in document.blocks], [1, 2])

    def test_parse_markdown_uses_chinese_thousand_page_markers(self):
        markdown = "\n".join(
            [
                "共一千页 第十页",
                "Page ten body",
                "",
                "共一千页 第十一页",
                "Page eleven body",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertNotIn("共一千页", document.raw_text)
        self.assertEqual(document.metadata.page_count, 11)
        self.assertEqual([block.location.page_no for block in document.blocks], [10, 11])

    def test_parse_markdown_preserves_page_marker_like_body_text(self):
        markdown = "\n".join(
            [
                "Section 1 Notice",
                "The phrase Page 1 of 2 is part of this clause and must remain.",
                "Buyer shall pay.",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.md",
                file_type="md",
                source_path="contract.md",
                backend_name="builtin",
            )
        )

        self.assertIn("Page 1 of 2 is part of this clause", document.raw_text)
        self.assertTrue(any("Page 1 of 2" in block.text for block in document.blocks))
        self.assertTrue(
            any("Page 1 of 2" in item["page_content"] for item in to_rag_documents(document))
        )

    def test_page_marker_boundaries_keep_cross_page_paragraphs_separate(self):
        markdown = "\n".join(
            [
                "Page 1 of 2",
                "Body A",
                "Page 2 of 2",
                "Body B",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertEqual(
            [(block.text, block.location.page_no) for block in document.blocks],
            [("Body A", 1), ("Body B", 2)],
        )

    def test_parse_markdown_uses_docling_table_metadata_for_table_page(self):
        markdown = "\n".join(
            [
                "# Price table",
                "",
                "| Item | Amount |",
                "| --- | --- |",
                "| Rent | 1000 |",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={
                    "parser_backend": "docling",
                    "docling_tables": [
                        {
                            "index": 0,
                            "page": 3,
                            "bbox": {"top": 0.25, "bottom": 0.45},
                        }
                    ],
                },
            )
        )

        table_block = next(block for block in document.blocks if block.block_type == "table")
        self.assertEqual(document.metadata.page_count, 3)
        self.assertEqual(document.tables[0].page_no, 3)
        self.assertEqual(table_block.location.page_no, 3)
        self.assertEqual(
            document.conversion_metadata["markdown_page_evidence"]["sources"],
            ["conversion_metadata"],
        )

    def test_cross_page_pipe_table_rows_remain_contiguous_after_page_boundary_insertion(self):
        markdown = "\n".join(
            [
                "Page 1 of 2",
                "| Item | Amount |",
                "| --- | --- |",
                "| Rent | 1000 |",
                "Page 2 of 2",
                "| Deposit | 2000 |",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertEqual(len(document.tables), 1)
        self.assertEqual(
            document.tables[0].rows,
            [
                ["Item", "Amount"],
                ["Rent", "1000"],
                ["Deposit", "2000"],
            ],
        )
        self.assertEqual(document.blocks[0].block_type, "table")

    def test_cross_page_pipe_table_block_page_is_unknown_when_rows_span_pages(self):
        markdown = "\n".join(
            [
                "Page 1 of 2",
                "| Item | Amount |",
                "| --- | --- |",
                "| Rent | 1000 |",
                "Page 2 of 2",
                "| Deposit | 2000 |",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertEqual(document.blocks[0].block_type, "table")
        self.assertIsNone(document.blocks[0].location.page_no)
        self.assertIsNone(document.tables[0].page_no)

    def test_cross_page_pipe_prose_keeps_page_boundary(self):
        markdown = "\n".join(
            [
                "Page 1 of 2",
                "Party A | shall pay rent",
                "Page 2 of 2",
                "Party B | shall deliver invoice",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertEqual(
            [(block.text, block.location.page_no) for block in document.blocks],
            [
                ("Party A | shall pay rent", 1),
                ("Party B | shall deliver invoice", 2),
            ],
        )

    def test_cross_page_list_continuation_splits_by_page_evidence(self):
        markdown = "\n".join(
            [
                "Page 1 of 2",
                "1. Payment obligation",
                "Page 2 of 2",
                "   continues on page two.",
                "",
                "2. Delivery obligation",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={"parser_backend": "docling"},
            )
        )

        self.assertEqual(
            [(block.block_type, block.text, block.location.page_no) for block in document.blocks],
            [
                ("list_item", "Payment obligation", 1),
                ("paragraph", "continues on page two.", 2),
                ("list_item", "Delivery obligation", 2),
            ],
        )

    def test_merged_table_does_not_use_stale_docling_table_index_fallback(self):
        markdown = "\n".join(
            [
                "| Item | Amount |",
                "| --- | --- |",
                "| Page one | 100 |",
                "noise",
                "| Item | Amount |",
                "| --- | --- |",
                "| Page two | 200 |",
                "",
                "| Fee | Amount |",
                "| --- | --- |",
                "| Service | 300 |",
            ]
        )

        document = ContractParser().parse_markdown(
            MarkdownDocument(
                markdown_content=markdown,
                file_name="contract.pdf",
                file_type="pdf",
                source_path="contract.pdf",
                backend_name="docling",
                conversion_metadata={
                    "parser_backend": "docling",
                    "docling_tables": [
                        {"index": 0, "page": 1, "bbox": {"bottom": 0.95}},
                        {"index": 1, "page": 2, "bbox": {"top": 0.05}},
                        {"index": 2, "page": 3, "bbox": {"top": 0.40}},
                    ],
                },
            )
        )

        self.assertEqual(document.conversion_metadata["markdown_cleaner_merged_tables"], 1)
        self.assertEqual(
            document.conversion_metadata["markdown_cleaner_table_source_indexes"],
            [None, 2],
        )
        self.assertEqual([table.page_no for table in document.tables], [None, 3])

    def test_build_metadata_page_count_uses_only_concrete_page_numbers(self):
        no_pages = build_metadata(
            file_name="same.txt",
            source_path="same.txt",
            file_type="txt",
            raw_text="body",
            spans=[
                DocumentSpan(
                    span_id="s1",
                    page_no=None,
                    block_index=0,
                    start_offset=0,
                    end_offset=4,
                    text="body",
                )
            ],
        )
        mixed_pages = build_metadata(
            file_name="same.txt",
            source_path="same.txt",
            file_type="txt",
            raw_text="body page",
            spans=[
                DocumentSpan(
                    span_id="s1",
                    page_no=None,
                    block_index=0,
                    start_offset=0,
                    end_offset=4,
                    text="body",
                ),
                DocumentSpan(
                    span_id="s2",
                    page_no=2,
                    block_index=1,
                    start_offset=5,
                    end_offset=9,
                    text="page",
                ),
            ],
        )
        empty = build_metadata(
            file_name="empty.txt",
            source_path="empty.txt",
            file_type="txt",
            raw_text="",
            spans=[],
        )

        self.assertEqual(no_pages.page_count, 0)
        self.assertEqual(mixed_pages.page_count, 2)
        self.assertEqual(empty.page_count, 0)


if __name__ == "__main__":
    unittest.main()
