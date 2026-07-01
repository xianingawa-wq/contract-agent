import unittest

from contract_agent.parser.parsed.markdown_logical_block_collector import collect_logical_blocks


class MarkdownLogicalBlockCollectorTests(unittest.TestCase):
    def test_wrapped_paragraph_lines_form_one_logical_block(self):
        blocks = collect_logical_blocks(
            [
                "Section 1 Payment",
                "Buyer shall pay within five days",
                "after receiving the invoice.",
            ]
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, "paragraph")
        self.assertEqual(
            blocks[0].markdown,
            "Section 1 Payment\nBuyer shall pay within five days\nafter receiving the invoice.",
        )
        self.assertEqual(
            blocks[0].text,
            "Section 1 Payment Buyer shall pay within five days after receiving the invoice.",
        )

    def test_list_continuation_stays_with_list_item(self):
        blocks = collect_logical_blocks(
            [
                "1. Payment obligation",
                "   continues on the next line.",
                "",
                "2. Delivery obligation",
            ]
        )

        self.assertEqual([block.block_type for block in blocks], ["list_item", "list_item"])
        self.assertEqual(
            blocks[0].text,
            "Payment obligation continues on the next line.",
        )

    def test_blockquote_lines_form_one_block_with_markdown_preserved(self):
        blocks = collect_logical_blocks(
            [
                "> Important notice",
                "> keep the original quote marker.",
            ]
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, "blockquote")
        self.assertEqual(
            blocks[0].markdown, "> Important notice\n> keep the original quote marker."
        )
        self.assertEqual(blocks[0].text, "Important notice keep the original quote marker.")

    def test_fenced_code_lines_form_one_block(self):
        blocks = collect_logical_blocks(
            [
                "```text",
                "line one",
                "1. not a list item",
                "```",
            ]
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, "fenced_code")
        self.assertEqual(blocks[0].text, "line one\n1. not a list item")

    def test_heading_table_and_paragraph_boundaries_stay_separate(self):
        blocks = collect_logical_blocks(
            [
                "# Contract",
                "Intro paragraph",
                "| Item | Amount |",
                "| --- | --- |",
                "| Rent | 1000 |",
                "Tail paragraph",
            ]
        )

        self.assertEqual(
            [block.block_type for block in blocks],
            ["title", "paragraph", "table", "paragraph"],
        )
        self.assertEqual(blocks[2].line_start, 2)
        self.assertEqual(blocks[2].line_end, 5)


if __name__ == "__main__":
    unittest.main()
