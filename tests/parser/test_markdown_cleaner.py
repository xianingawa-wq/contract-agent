import unittest

from contract_agent.parser import ContractParser, MarkdownDocument


class MarkdownCleanerTests(unittest.TestCase):
    def test_parse_markdown_removes_page_furniture_before_chunking(self):
        markdown = "\n".join(
            [
                "# 房屋租赁合同",
                "",
                "Confidential",
                "第1页 共2页",
                "",
                "第一条 租金",
                "租金每月1000元。",
                "",
                "Page 2 of 2",
                "Confidential",
                "",
                "第二条 期限",
                "租期一年。",
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

        self.assertNotIn("Confidential", document.raw_text)
        self.assertNotIn("第1页", document.raw_text)
        self.assertNotIn("Page 2", document.raw_text)
        self.assertNotIn("Confidential", document.markdown_content)
        self.assertTrue(
            any("租金每月1000元" in chunk.source_text for chunk in document.clause_chunks)
        )
        self.assertEqual(document.conversion_metadata["markdown_cleaner_removed_lines"], 4)

    def test_parse_markdown_merges_table_split_by_page_furniture(self):
        markdown = "\n".join(
            [
                "# 费用表",
                "",
                "| 项目 | 金额 |",
                "| --- | --- |",
                "| 租金 | 1000 |",
                "",
                "第1页 共2页",
                "Confidential",
                "",
                "| 押金 | 2000 |",
                "| 服务费 | 300 |",
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
            [["项目", "金额"], ["租金", "1000"], ["押金", "2000"], ["服务费", "300"]],
        )
        self.assertEqual(document.conversion_metadata["markdown_cleaner_merged_tables"], 1)

    def test_parse_markdown_merges_table_interrupted_by_short_ocr_noise(self):
        markdown = "\n".join(
            [
                "# Payment plan",
                "",
                "| year | item | amount | total | date |",
                "| - | - | - | - | - |",
                "| year 1 | rent | + 2200 | 2464 | 2027-02-19 |",
                "",
                "ANHUYOUQU",
                "",
                "OGA",
                "",
                "|  | service fee | + 264 |  |  |",
                "| - | - | - | - | - |",
                "| year 1 | rent | + 2200 | 2464 | 2027-03-19 |",
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
        self.assertNotIn("ANHUYOUQU", document.raw_text)
        self.assertNotIn("OGA", document.raw_text)
        self.assertIn(["", "service fee", "+ 264", "", ""], document.tables[0].rows)
        self.assertIn(
            ["year 1", "rent", "+ 2200", "2464", "2027-03-19"],
            document.tables[0].rows,
        )
        self.assertEqual(document.conversion_metadata["markdown_cleaner_merged_tables"], 1)
        self.assertEqual(document.conversion_metadata["markdown_cleaner_removed_lines"], 2)

    def test_parse_markdown_keeps_body_text_between_tables(self):
        markdown = "\n".join(
            [
                "# Payment plan",
                "",
                "| year | item | amount | total | date |",
                "| - | - | - | - | - |",
                "| year 1 | rent | + 2200 | 2464 | 2027-02-19 |",
                "",
                "Business note: keep the next table separate.",
                "",
                "| year | item | amount | total | date |",
                "| - | - | - | - | - |",
                "| year 1 | deposit | + 2200 | 2200 | 2027-03-19 |",
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

        self.assertEqual(len(document.tables), 2)
        self.assertIn("Business note: keep the next table separate.", document.raw_text)
        self.assertEqual(document.conversion_metadata["markdown_cleaner_merged_tables"], 0)
        self.assertEqual(document.conversion_metadata["markdown_cleaner_removed_lines"], 0)

    def test_parse_markdown_does_not_merge_adjacent_tables_without_layout_evidence(self):
        markdown = "\n".join(
            [
                "# 费用表",
                "",
                "| 项目 | 金额 |",
                "| --- | --- |",
                "| 租金 | 1000 |",
                "",
                "| 项目 | 金额 |",
                "| --- | --- |",
                "| 付款方式 | 月付 |",
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

        self.assertEqual(len(document.tables), 2)
        self.assertEqual(document.conversion_metadata["markdown_cleaner_merged_tables"], 0)

    def test_parse_markdown_merges_cross_page_tables_when_docling_bbox_is_continuous(self):
        markdown = "\n".join(
            [
                "# 费用表",
                "",
                "| 项目 | 金额 |",
                "| --- | --- |",
                "| 租金 | 1000 |",
                "",
                "| 项目 | 金额 |",
                "| --- | --- |",
                "| 付款方式 | 月付 |",
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
                            "page": 1,
                            "bbox": {"top": 0.72, "bottom": 0.95},
                        },
                        {
                            "index": 1,
                            "page": 2,
                            "bbox": {"top": 0.04, "bottom": 0.18},
                        },
                    ],
                },
            )
        )

        self.assertEqual(len(document.tables), 1)
        self.assertEqual(
            document.tables[0].rows,
            [["项目", "金额"], ["租金", "1000"], ["付款方式", "月付"]],
        )
        self.assertEqual(document.conversion_metadata["markdown_cleaner_merged_tables"], 1)

    def test_parse_markdown_merges_cross_page_tables_with_different_continuation_header(self):
        markdown = "\n".join(
            [
                "# 维修责任",
                "",
                "| 维修责任 | 维修责任 | 维修责任 |",
                "| --- | --- | --- |",
                "| 品类 | 物品 | 交房标准 |",
                "| 厨卫维修 | 浴霸 | 正常使用 |",
                "",
                "|  | 使用； | 更换责任。 | 其他 |",
                "| --- | --- | --- | --- |",
                "| 墙体结构 | 建筑主体正常 | 建筑主体 | 其他 |",
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
                            "page": 15,
                            "bbox": {"top": 0.06, "bottom": 0.92},
                        },
                        {
                            "index": 1,
                            "page": 16,
                            "bbox": {"top": 0.06, "bottom": 0.93},
                        },
                    ],
                },
            )
        )

        self.assertEqual(len(document.tables), 1)
        self.assertEqual(document.conversion_metadata["markdown_cleaner_merged_tables"], 1)
        self.assertTrue(any(row[0] == "墙体结构" for row in document.tables[0].rows))

    def test_parse_markdown_removes_repeated_header_near_page_numbers_after_first(self):
        markdown = "\n".join(
            [
                "XX公司合同",
                "第1页 共2页",
                "",
                "第一条 正文",
                "第一页正文。",
                "",
                "XX公司合同",
                "第2页 共2页",
                "",
                "第二条 正文",
                "第二页正文。",
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

        self.assertEqual(document.raw_text.count("XX公司合同"), 1)
        self.assertIn("第一页正文", document.raw_text)
        self.assertIn("第二页正文", document.raw_text)

    def test_parse_markdown_removes_numeric_only_page_footers_in_sequence(self):
        markdown = "\n".join(
            [
                "# 房屋租赁合同",
                "",
                "第一条 正文",
                "第一页正文。",
                "",
                "1",
                "",
                "第二条 正文",
                "第二页正文。",
                "",
                "2",
                "",
                "第三条 正文",
                "第三页正文。",
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

        non_empty_lines = [
            line.strip() for line in document.markdown_content.splitlines() if line.strip()
        ]
        self.assertNotIn("1", non_empty_lines)
        self.assertNotIn("2", non_empty_lines)
        self.assertIn("第一页正文", document.raw_text)
        self.assertIn("第三页正文", document.raw_text)
        self.assertEqual(document.conversion_metadata["markdown_cleaner_removed_lines"], 2)

    def test_parse_markdown_keeps_body_numbers_that_are_not_page_sequence(self):
        markdown = "\n".join(
            [
                "# 房屋租赁合同",
                "",
                "第一条 金额",
                "1000",
                "",
                "第二条 编号",
                "1",
                "",
                "本条继续说明。",
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

        non_empty_lines = [
            line.strip() for line in document.markdown_content.splitlines() if line.strip()
        ]
        self.assertIn("1000", non_empty_lines)
        self.assertIn("1", non_empty_lines)
        self.assertIn("本条继续说明", document.raw_text)
        self.assertEqual(document.conversion_metadata["markdown_cleaner_removed_lines"], 0)


if __name__ == "__main__":
    unittest.main()
