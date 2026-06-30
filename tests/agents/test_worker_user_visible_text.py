import sys
import types
import unittest
from unittest.mock import patch

from contract_agent.agents import workers
from contract_agent.orchestration.protocol import AgentStatus
from contract_agent.parser import ClauseChunk, DocumentMetadata, ParsedDocument


MOJIBAKE_MARKERS = (
    "鐢叉柟",
    "鍏朵粬",
    "鏃犻",
    "鏈煡",
    "鏈",
    "鈥",
    "δժ",
)


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class FakeLlm:
    def __init__(self, content: str) -> None:
        self.content = content

    def __call__(self, prompt_value):
        return FakeMessage(self.content)


class WorkerUserVisibleTextTests(unittest.TestCase):
    def assert_no_mojibake(self, value) -> None:
        text = str(value)
        for marker in MOJIBAKE_MARKERS:
            self.assertNotIn(marker, text)

    def test_parser_fallback_uses_chinese_defaults(self):
        document = ParsedDocument(
            metadata=DocumentMetadata(
                doc_id="doc-1",
                file_name="contract.txt",
                file_type="txt",
                source_path="inline",
            ),
            raw_text="第一条 付款。",
            clause_chunks=[
                ClauseChunk(
                    chunk_id="chunk-1",
                    chunk_level="clause",
                    clause_no="1",
                    section_title="付款",
                    start_offset=0,
                    end_offset=6,
                    source_text="第一条 付款。",
                )
            ],
        )

        with patch(
            "contract_agent.provider.client.get_chat_model",
            return_value=FakeLlm('{"clauses": []}'),
        ):
            output = workers.parser_agent(
                {"contract_text": "第一条 付款。", "parsed_document": document}
            )

        self.assertEqual(output.structured_data["our_side"], "甲方")
        self.assertEqual(output.structured_data["parsed_clauses"][0]["type"], "其他")
        self.assert_no_mojibake(output.model_dump())

    def test_risk_checker_uses_chinese_default_side(self):
        with patch(
            "contract_agent.provider.client.get_chat_model",
            return_value=FakeLlm('{"findings": []}'),
        ):
            output = workers.risk_checker_agent(
                {
                    "contract_text": "第一条 付款。",
                    "parsed_clauses": [{"clause_no": "1", "summary": "付款"}],
                }
            )

        self.assertEqual(output.status, AgentStatus.COMPLETED)
        self.assert_no_mojibake(output.model_dump())

    def test_legal_ref_skip_summaries_and_unknown_source_are_chinese(self):
        no_findings = workers.legal_ref_agent({"risk_findings": []})
        self.assertEqual(no_findings.input_summary, "无风险发现，跳过法条引用")
        self.assert_no_mojibake(no_findings.model_dump())

        vector_store = object()
        retrieved_doc = types.SimpleNamespace(page_content="法律条文", metadata={})

        class FakeRetriever:
            def __init__(self, store, **kwargs) -> None:
                self.store = store

            def retrieve_documents_with_rerank(self, **kwargs):
                return [retrieved_doc]

        module = types.ModuleType("contract_agent.knowledge.rag.retriever")
        module.ContractKnowledgeRetriever = FakeRetriever

        with (
            patch.dict(sys.modules, {"contract_agent.knowledge.rag.retriever": module}),
            patch(
                "contract_agent.knowledge.rag.vector_store.load_vector_store",
                return_value=vector_store,
            ),
            patch(
                "contract_agent.provider.client.get_chat_model",
                return_value=FakeLlm('{"refs": []}'),
            ),
        ):
            output = workers.legal_ref_agent(
                {
                    "risk_findings": [{"summary": "付款期限不明确"}],
                    "detected_contract_type": "采购合同",
                }
            )

        self.assertEqual(output.status, AgentStatus.SKIPPED)
        self.assertEqual(output.input_summary, "检索并分析 0 条法律引用")
        self.assertEqual(output.structured_data["legal_refs"], [])
        self.assert_no_mojibake(output.model_dump())

    def test_redrafter_skip_summary_is_chinese(self):
        output = workers.redrafter_agent({"risk_findings": []})

        self.assertEqual(output.input_summary, "无风险发现，跳过改写")
        self.assert_no_mojibake(output.model_dump())


if __name__ == "__main__":
    unittest.main()
