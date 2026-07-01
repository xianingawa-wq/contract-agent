import unittest

from contract_agent.parser.parsed.markdown_page_resolver import resolve_page_evidence


class MarkdownPageResolverTests(unittest.TestCase):
    def test_without_page_evidence_returns_none_for_body_lines(self):
        evidence = resolve_page_evidence(["Section 1 Payment", "Buyer shall pay."])

        self.assertEqual(evidence.line_page_numbers, [None, None])
        self.assertEqual(evidence.marker_count, 0)
        self.assertEqual(evidence.max_page_no, 0)

    def test_english_page_markers_assign_following_body_lines(self):
        evidence = resolve_page_evidence(
            [
                "Page 1 of 2",
                "Section 1 Payment",
                "",
                "Page 2 of 2",
                "Section 2 Delivery",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [1, 1, 1, 2, 2])
        self.assertEqual(evidence.marker_count, 2)
        self.assertEqual(evidence.max_page_no, 2)

    def test_chinese_page_markers_assign_following_body_lines(self):
        evidence = resolve_page_evidence(
            [
                "第 1 页，共 2 页",
                "Page one body",
                "第 2 页，共 2 页",
                "Page two body",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [1, 1, 2, 2])
        self.assertEqual(evidence.marker_count, 2)
        self.assertEqual(evidence.max_page_no, 2)

    def test_chinese_page_markers_accept_supported_digits(self):
        evidence = resolve_page_evidence(
            [
                "第两页",
                "Body on page two",
                "第一百零一页",
                "Body on page one hundred one",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [2, 2, 101, 101])
        self.assertEqual(evidence.marker_count, 2)
        self.assertEqual(evidence.max_page_no, 101)

    def test_inconsistent_page_marker_totals_are_not_used_as_page_evidence(self):
        evidence = resolve_page_evidence(
            [
                "Page 2 of 1",
                "Body should not receive impossible page evidence.",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [None, None])
        self.assertEqual(evidence.marker_count, 0)
        self.assertEqual(evidence.max_page_no, 0)

    def test_non_monotonic_explicit_page_markers_are_not_used_as_page_evidence(self):
        evidence = resolve_page_evidence(
            [
                "Page 2 of 3",
                "Body two",
                "Page 1 of 3",
                "Body one",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [None, None, None, None])
        self.assertEqual(evidence.marker_count, 0)
        self.assertEqual(evidence.max_page_no, 0)

    def test_explicit_page_markers_can_label_footer_segments(self):
        evidence = resolve_page_evidence(
            [
                "Body on page one",
                "Page 1 of 2",
                "---",
                "Body on page two",
                "Page 2 of 2",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [1, 1, 1, 2, 2])
        self.assertEqual(evidence.marker_count, 2)
        self.assertEqual(evidence.max_page_no, 2)

    def test_numeric_footer_sequence_assigns_page_before_each_footer(self):
        evidence = resolve_page_evidence(
            [
                "Page one body",
                "1",
                "---",
                "Page two body",
                "2",
                "---",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [1, 1, 1, 2, 2, 2])
        self.assertEqual(evidence.marker_count, 2)
        self.assertEqual(evidence.max_page_no, 2)

    def test_standalone_body_numbers_without_boundary_context_are_not_page_evidence(self):
        evidence = resolve_page_evidence(
            [
                "Payment amount",
                "1000",
                "",
                "Section number",
                "1",
            ]
        )

        self.assertEqual(evidence.line_page_numbers, [None, None, None, None, None])
        self.assertEqual(evidence.marker_count, 0)

    def test_metadata_table_pages_are_used_when_text_has_no_page_markers(self):
        evidence = resolve_page_evidence(
            ["Section 1 Payment", "Buyer shall pay."],
            conversion_metadata={
                "docling_tables": [
                    {"index": 3, "page": 7},
                ]
            },
        )

        self.assertEqual(evidence.line_page_numbers, [None, None])
        self.assertEqual(evidence.table_page_numbers, {3: 7})
        self.assertEqual(evidence.marker_count, 1)
        self.assertEqual(evidence.max_page_no, 7)
        self.assertEqual(evidence.sources, ["conversion_metadata"])

    def test_invalid_explicit_marker_does_not_block_metadata_table_pages(self):
        evidence = resolve_page_evidence(
            ["Page 2 of 1", "Body should not receive impossible page evidence."],
            conversion_metadata={
                "docling_tables": [
                    {"index": 0, "page": 5},
                ]
            },
        )

        self.assertEqual(evidence.line_page_numbers, [None, None])
        self.assertEqual(evidence.table_page_numbers, {0: 5})
        self.assertEqual(evidence.marker_count, 1)
        self.assertEqual(evidence.max_page_no, 5)
        self.assertEqual(evidence.sources, ["conversion_metadata"])


if __name__ == "__main__":
    unittest.main()
