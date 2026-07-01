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
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 3)

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
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 2)

    def test_lazy_list_continuation_stays_with_list_item(self):
        blocks = collect_logical_blocks(
            [
                "1. Payment obligation",
                "continues without indentation.",
                "",
                "2. Delivery obligation",
            ]
        )

        self.assertEqual([block.block_type for block in blocks], ["list_item", "list_item"])
        self.assertEqual(
            blocks[0].text,
            "Payment obligation continues without indentation.",
        )

    def test_nested_and_multi_paragraph_list_continuation_stays_with_list_item(self):
        blocks = collect_logical_blocks(
            [
                "1. Payment obligation",
                "    - Buyer shall pay rent.",
                "    - Buyer shall pay deposit.",
                "",
                "    Continued payment paragraph.",
                "",
                "2. Delivery obligation",
            ]
        )

        self.assertEqual([block.block_type for block in blocks], ["list_item", "list_item"])
        self.assertEqual(
            blocks[0].text,
            "Payment obligation Buyer shall pay rent. Buyer shall pay deposit. "
            "Continued payment paragraph.",
        )
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 5)
        self.assertEqual(
            blocks[0].markdown,
            "1. Payment obligation\n"
            "    - Buyer shall pay rent.\n"
            "    - Buyer shall pay deposit.\n"
            "\n"
            "    Continued payment paragraph.",
        )

    def test_two_space_nested_list_marker_stays_with_parent_list_item(self):
        blocks = collect_logical_blocks(
            [
                "- Parent obligation",
                "  - Child obligation",
                "",
                "- Next obligation",
            ]
        )

        self.assertEqual([block.block_type for block in blocks], ["list_item", "list_item"])
        self.assertEqual(blocks[0].text, "Parent obligation Child obligation")
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 2)

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
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 2)

    def test_blockquote_lazy_continuation_stays_with_quote(self):
        blocks = collect_logical_blocks(
            [
                "> Important notice",
                "continued without quote marker.",
                "",
                "Tail paragraph",
            ]
        )

        self.assertEqual([block.block_type for block in blocks], ["blockquote", "paragraph"])
        self.assertEqual(blocks[0].text, "Important notice continued without quote marker.")
        self.assertEqual(
            blocks[0].markdown,
            "> Important notice\ncontinued without quote marker.",
        )

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
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 4)

    def test_tilde_fenced_code_lines_form_one_block(self):
        blocks = collect_logical_blocks(
            [
                "~~~text",
                "line one",
                "1. not a list item",
                "~~~",
            ]
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, "fenced_code")
        self.assertEqual(blocks[0].text, "line one\n1. not a list item")
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 4)

    def test_long_fence_requires_closing_fence_at_least_as_long(self):
        blocks = collect_logical_blocks(
            [
                "````",
                "line one",
                "```",
                "still code",
                "````",
                "Tail paragraph",
            ]
        )

        self.assertEqual([block.block_type for block in blocks], ["fenced_code", "paragraph"])
        self.assertEqual(blocks[0].text, "line one\n```\nstill code")

    def test_indented_code_fence_inside_fenced_code_is_not_closing_fence(self):
        blocks = collect_logical_blocks(
            [
                "```",
                "line one",
                "    ```",
                "still code",
                "```",
                "Tail paragraph",
            ]
        )

        self.assertEqual([block.block_type for block in blocks], ["fenced_code", "paragraph"])
        self.assertEqual(blocks[0].text, "line one\n    ```\nstill code")

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
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 1)
        self.assertEqual(blocks[1].line_start, 1)
        self.assertEqual(blocks[1].line_end, 2)
        self.assertEqual(blocks[2].line_start, 2)
        self.assertEqual(blocks[2].line_end, 5)
        self.assertEqual(blocks[3].line_start, 5)
        self.assertEqual(blocks[3].line_end, 6)

    def test_empty_and_whitespace_only_input_returns_no_blocks(self):
        self.assertEqual(collect_logical_blocks([]), [])
        self.assertEqual(collect_logical_blocks(["", "   ", "\t"]), [])

    def test_unclosed_fenced_code_consumes_until_end_of_input(self):
        blocks = collect_logical_blocks(
            [
                "```text",
                "line one",
                "line two",
            ]
        )

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, "fenced_code")
        self.assertEqual(blocks[0].text, "line one\nline two")
        self.assertEqual(blocks[0].line_start, 0)
        self.assertEqual(blocks[0].line_end, 3)


if __name__ == "__main__":
    unittest.main()
