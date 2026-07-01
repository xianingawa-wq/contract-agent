import unittest

from contract_agent.parser import ContractParser, MarkdownDocument


class ParserLogicalBlockTests(unittest.TestCase):
    def test_wrapped_paragraph_is_one_block_and_one_chunk_with_offsets_aligned(self):
        markdown = "\n".join(
            [
                "Section 1 Payment",
                "Buyer shall pay within five days",
                "after receiving the invoice.",
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

        self.assertEqual(len(document.blocks), 1)
        self.assertEqual(len(document.clause_chunks), 1)
        self.assertEqual(
            document.blocks[0].text,
            "Section 1 Payment Buyer shall pay within five days after receiving the invoice.",
        )
        for chunk in document.clause_chunks:
            self.assertEqual(
                document.raw_text[chunk.start_offset : chunk.end_offset], chunk.source_text
            )

    def test_list_continuation_blockquote_and_fenced_code_keep_logical_boundaries(self):
        markdown = "\n".join(
            [
                "1. Payment obligation",
                "   continues on the next line.",
                "",
                "> Quoted notice",
                "> second quote line",
                "",
                "```text",
                "1. not parsed as a list",
                "```",
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

        self.assertEqual(
            [block.block_type for block in document.blocks],
            ["list_item", "blockquote", "fenced_code"],
        )
        self.assertEqual(
            document.blocks[0].text,
            "Payment obligation continues on the next line.",
        )
        self.assertEqual(document.blocks[1].text, "Quoted notice second quote line")
        self.assertEqual(document.blocks[2].text, "1. not parsed as a list")

    def test_heading_table_and_paragraph_boundaries_remain_separate(self):
        markdown = "\n".join(
            [
                "# Contract",
                "",
                "Intro paragraph",
                "",
                "| Item | Amount |",
                "| --- | --- |",
                "| Rent | 1000 |",
                "",
                "Tail paragraph",
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

        self.assertEqual(
            [block.block_type for block in document.blocks],
            ["title", "paragraph", "table", "paragraph"],
        )
        self.assertEqual(document.tables[0].rows, [["Item", "Amount"], ["Rent", "1000"]])
        self.assertTrue(document.clause_chunks)
        self.assertTrue(
            all(
                document.raw_text[chunk.start_offset : chunk.end_offset] == chunk.source_text
                for chunk in document.clause_chunks
            )
        )


if __name__ == "__main__":
    unittest.main()
