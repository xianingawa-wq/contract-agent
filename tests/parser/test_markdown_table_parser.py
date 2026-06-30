import unittest

from contract_agent.parser.parsed.markdown_table_parser import (
    collect_table_lines,
    is_table_start,
    parse_table_rows,
    table_text,
)


class MarkdownTableParserTests(unittest.TestCase):
    def test_parse_table_rows_preserves_escaped_pipes_and_empty_cells(self):
        rows = parse_table_rows(
            "\n".join(
                [
                    "| left | middle | right |",
                    "| --- | --- | --- |",
                    "| A\\|B |  | tail |",
                ]
            )
        )

        self.assertEqual(rows, [["left", "middle", "right"], ["A|B", "", "tail"]])
        self.assertEqual(table_text(rows), "left | middle | right\nA|B |  | tail")

    def test_parse_table_rows_splits_escaped_pipes_by_odd_even_backslashes(self):
        rows = parse_table_rows(
            "\n".join(
                [
                    r"| odd | even-left | even-right | tail |",
                    r"| --- | --- | --- | --- |",
                    r"| A\|B | C\\|D | end |",
                ]
            )
        )

        self.assertEqual(
            rows,
            [["odd", "even-left", "even-right", "tail"], ["A|B", r"C\\", "D", "end"]],
        )

    def test_tables_without_outer_pipes_are_valid(self):
        lines = [
            "item | amount",
            "--- | ---",
            "rent | 1000",
        ]

        self.assertTrue(is_table_start(lines, 0))
        self.assertEqual(parse_table_rows("\n".join(lines)), [["item", "amount"], ["rent", "1000"]])

    def test_separator_validation_rejects_empty_or_too_short_cells(self):
        self.assertFalse(is_table_start(["item | amount", "- | ---"], 0))
        self.assertFalse(is_table_start(["item | amount", "   | ---"], 0))
        self.assertEqual(parse_table_rows("item | amount\n- | ---\nrent | 1000"), [])

    def test_collect_table_lines_stops_on_incompatible_column_count(self):
        lines = [
            "| item | amount |",
            "| --- | --- |",
            "| rent | 1000 |",
            "| subtotal |",
            "| after | table |",
        ]

        table_lines, next_index = collect_table_lines(lines, 0)

        self.assertEqual(
            table_lines,
            [
                "| item | amount |",
                "| --- | --- |",
                "| rent | 1000 |",
            ],
        )
        self.assertEqual(next_index, 3)


if __name__ == "__main__":
    unittest.main()
