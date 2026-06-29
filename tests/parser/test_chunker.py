import unittest

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import (
    BlockLocation,
    DocumentBlock,
    DocumentMetadata,
    DocumentSpan,
    ParsedDocument,
)
from contract_agent.parser.parsed.markdown_chunker import ContractChunker


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
    def test_chunks_each_span_without_detector_dependency(self):
        chunks = ContractChunker().chunk(
            document_from_lines(["合同前言", "第一条 付款", "甲方应付款。"])
        )

        self.assertEqual([chunk.chunk_level for chunk in chunks], ["span", "span", "span"])
        self.assertEqual(
            [chunk.source_text for chunk in chunks], ["合同前言", "第一条 付款", "甲方应付款。"]
        )
        self.assertTrue(all(chunk.section_title for chunk in chunks))

    def test_prev_next_links_are_correct(self):
        chunks = ContractChunker().chunk(
            document_from_lines(["第一条 付款", "内容", "第二条 交付", "内容"])
        )

        self.assertIsNone(chunks[0].prev_chunk_id)
        self.assertEqual(chunks[0].next_chunk_id, chunks[1].chunk_id)
        self.assertEqual(chunks[1].prev_chunk_id, chunks[0].chunk_id)
        self.assertIsNone(chunks[-1].next_chunk_id)

    def test_long_chunk_split_keeps_neighbor_links(self):
        long_text = "Long sentence. " * 700
        chunks = ContractChunker().chunk(document_from_lines([long_text]))

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.chunk_level == "sentence_group" for chunk in chunks))
        self.assertIsNone(chunks[0].prev_chunk_id)
        self.assertEqual(chunks[0].next_chunk_id, chunks[1].chunk_id)
        self.assertEqual(chunks[-1].prev_chunk_id, chunks[-2].chunk_id)
        self.assertIsNone(chunks[-1].next_chunk_id)

    def test_chunk_thresholds_come_from_parser_config(self):
        long_text = "Long. " * 30
        chunks = ContractChunker(ParserConfig(chunk_max_chars=20, chunk_target_chars=10)).chunk(
            document_from_lines([long_text])
        )

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.source_text) <= 12 for chunk in chunks))

    def test_split_long_chunks_preserves_offsets_for_each_part(self):
        text = "Alpha. Beta. Gamma."
        chunks = ContractChunker(ParserConfig(chunk_max_chars=10, chunk_target_chars=8)).chunk(
            document_from_lines([text])
        )

        self.assertEqual([chunk.source_text for chunk in chunks], ["Alpha.", " Beta.", " Gamma."])
        self.assertEqual(
            [(chunk.start_offset, chunk.end_offset) for chunk in chunks],
            [(0, 6), (6, 12), (12, 19)],
        )

    def test_span_chunk_offsets_align_after_trimming_boundary_whitespace(self):
        raw_text = "  Payment obligation  "
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text=raw_text,
            spans=[
                DocumentSpan(
                    span_id="p1-b0",
                    page_no=1,
                    block_index=0,
                    start_offset=0,
                    end_offset=len(raw_text),
                    text=raw_text,
                )
            ],
        )

        chunk = ContractChunker().chunk(document)[0]

        self.assertEqual(chunk.source_text, "Payment obligation")
        self.assertEqual(raw_text[chunk.start_offset : chunk.end_offset], chunk.source_text)

    def test_block_chunk_offsets_align_after_trimming_boundary_whitespace(self):
        raw_text = "  Delivery obligation  "
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text=raw_text,
            blocks=[
                DocumentBlock(
                    block_id="p1-b0",
                    block_type="paragraph",
                    text=raw_text,
                    location=BlockLocation(
                        page_no=1,
                        block_index=0,
                        start_offset=0,
                        end_offset=len(raw_text),
                    ),
                )
            ],
        )

        chunk = ContractChunker().chunk(document)[0]

        self.assertEqual(chunk.source_text, "Delivery obligation")
        self.assertEqual(raw_text[chunk.start_offset : chunk.end_offset], chunk.source_text)

    def test_unpunctuated_long_sentence_is_hard_split_to_target_chars(self):
        text = "abcdefghij"
        chunks = ContractChunker(ParserConfig(chunk_max_chars=5, chunk_target_chars=4)).chunk(
            document_from_lines([text])
        )

        self.assertEqual([chunk.source_text for chunk in chunks], ["abcd", "efgh", "ij"])
        self.assertTrue(all(len(chunk.source_text) <= 4 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
