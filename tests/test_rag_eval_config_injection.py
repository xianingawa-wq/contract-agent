import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.documents import Document

from contract_agent.knowledge.rag.eval_recall import run_evaluation
from contract_agent.config import Settings


class FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def retrieve_documents(self, query: str, k: int = 3) -> list[Document]:
        self.calls.append((query, k))
        return [
            Document(
                page_content="中华人民共和国民法典合同编相关条款",
                metadata={"article_label": "民法典-合同编-001", "title": "民法典"},
            )
        ]


class RagEvalConfigInjectionTests(unittest.TestCase):
    def test_run_evaluation_uses_injected_runtime_settings_for_defaults(self):
        runtime_settings = Settings(
            retrieval_enable_rerank=False,
            retrieval_fetch_k=17,
            retrieval_final_k=9,
            rerank_model="injected-rerank",
            rerank_endpoint="https://rerank.example.test/api",
        )
        retriever = FakeRetriever()

        with TemporaryDirectory() as tmpdir:
            dataset_path = Path(tmpdir) / "dataset.jsonl"
            dataset_path.write_text(
                json.dumps(
                    {
                        "risk_id": "risk-1",
                        "contract_id": "contract-1",
                        "contract_type": "采购合同",
                        "query": "付款风险",
                        "gold_article_labels": ["民法典-合同编-001"],
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            result = run_evaluation(
                dataset_path=str(dataset_path),
                output_dir=str(Path(tmpdir) / "out"),
                k_values=[1],
                retriever=retriever,  # type: ignore[arg-type]
                runtime_settings=runtime_settings,
            )

            summary = json.loads(Path(result["summary_path"]).read_text(encoding="utf-8"))

        self.assertEqual(retriever.calls, [("付款风险", 1)])
        self.assertEqual(
            summary["retrieval_config"],
            {
                "use_rerank": False,
                "fetch_k": 17,
                "final_k": 9,
                "rerank_model": "injected-rerank",
                "rerank_endpoint": "https://rerank.example.test/api",
            },
        )


if __name__ == "__main__":
    unittest.main()
