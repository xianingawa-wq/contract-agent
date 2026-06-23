import unittest

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import DocumentMetadata, DocumentSpan, ParsedDocument
from contract_agent.parser.chunker import ContractChunker


def document_from_lines(lines: list[str]) -> ParsedDocument:
    spans = []
    cursor = 0
    for index, line in enumerate(lines):
        spans.append(
            DocumentSpan(
                span_id=f"p1-b{index}",
                page_no=1,
                block_index=index,
                start_offset=cursor,
                end_offset=cursor + len(line),
                text=line,
            )
        )
        cursor += len(line) + 1
    return ParsedDocument(
        metadata=DocumentMetadata(
            doc_id="doc",
            file_name="contract.txt",
            file_type="txt",
            source_path="inline",
        ),
        raw_text="\n".join(lines),
        spans=spans,
    )


class ContractChunkerTests(unittest.TestCase):
    def test_splits_chinese_clause_numeric_levels_and_sub_items(self):
        document = document_from_lines(
            [
                "合同前言",
                "第一条 付款",
                "甲方应付款。",
                "1.1 支付时间",
                "付款期限为5日。",
                "（一）支付方式",
                "银行转账。",
            ]
        )

        chunks = ContractChunker().chunk(document)

        self.assertEqual(
            [chunk.chunk_level for chunk in chunks], ["preface", "clause", "sub_clause", "sub_item"]
        )
        self.assertEqual(chunks[1].clause_no, "第一条")
        self.assertEqual(chunks[2].parent_clause_no, "第一条")
        self.assertEqual(chunks[3].parent_clause_no, "第一条")

    def test_prev_next_links_are_correct(self):
        chunks = ContractChunker().chunk(
            document_from_lines(["第一条 付款", "内容", "第二条 交付", "内容"])
        )

        self.assertIsNone(chunks[0].prev_chunk_id)
        self.assertEqual(chunks[0].next_chunk_id, chunks[1].chunk_id)
        self.assertEqual(chunks[1].prev_chunk_id, chunks[0].chunk_id)
        self.assertIsNone(chunks[-1].next_chunk_id)

    def test_long_clause_split_keeps_neighbor_links(self):
        long_text = "。".join(["长句"] * 700) + "。"
        chunks = ContractChunker().chunk(document_from_lines(["第一条 长条款", long_text]))

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.chunk_level == "sentence_group" for chunk in chunks))
        self.assertIsNone(chunks[0].prev_chunk_id)
        self.assertEqual(chunks[0].next_chunk_id, chunks[1].chunk_id)
        self.assertEqual(chunks[-1].prev_chunk_id, chunks[-2].chunk_id)
        self.assertIsNone(chunks[-1].next_chunk_id)

    def test_chunk_thresholds_come_from_parser_config(self):
        long_text = "。".join(["长句"] * 30) + "。"
        chunks = ContractChunker(ParserConfig(chunk_max_chars=20, chunk_target_chars=10)).chunk(
            document_from_lines(["第一条 长条款", long_text])
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.source_text) <= 12 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
