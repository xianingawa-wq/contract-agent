import unittest

from contract_agent.parser.parsed.markdown_table_parser import parse_table_rows, table_text


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


if __name__ == "__main__":
    unittest.main()
