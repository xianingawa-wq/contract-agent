import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from contract_agent.knowledge.rag.legal_chunker import LegalKnowledgeChunker


class LegalKnowledgeChunkerTests(unittest.TestCase):
    def test_chunk_text_keeps_first_article_when_text_starts_with_utf8_bom(self):
        chunker = LegalKnowledgeChunker()

        chunks = chunker.chunk_text(
            text="\ufeff第一条 合同应当依法成立。\n第二条 当事人应当履行义务。",
            doc_name="bom-law.txt",
        )

        self.assertEqual([chunk.article_label for chunk in chunks], ["第一条", "第二条"])
        self.assertIn("合同应当依法成立", chunks[0].text)

    def test_chunk_file_keeps_first_article_from_utf8_sig_file(self):
        chunker = LegalKnowledgeChunker()

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "bom-law.txt"
            path.write_text(
                "第一条 合同应当依法成立。\n第二条 当事人应当履行义务。",
                encoding="utf-8-sig",
            )

            chunks = chunker.chunk_file(str(path))

        self.assertEqual([chunk.article_label for chunk in chunks], ["第一条", "第二条"])


if __name__ == "__main__":
    unittest.main()
