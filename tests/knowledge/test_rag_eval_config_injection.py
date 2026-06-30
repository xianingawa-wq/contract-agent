import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from langchain_core.documents import Document

from contract_agent.knowledge.rag.eval_recall import (
    RecallSample,
    compare_with_baseline,
    evaluate_samples,
    run_evaluation,
)
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


class FakeRerankRetriever:
    last_rerank_meta: dict[str, object] = {}

    def retrieve_documents(self, query: str, k: int = 3) -> list[Document]:
        return [
            Document(page_content=str(idx), metadata={"article_label": str(idx)})
            for idx in range(k)
        ]

    def retrieve_documents_with_rerank(
        self,
        *,
        query: str,
        fetch_k: int | None = None,
        final_k: int | None = None,
        use_rerank: bool | None = None,
    ) -> list[Document]:
        return [
            Document(page_content=str(idx), metadata={"article_label": str(idx)})
            for idx in range(fetch_k or 0)
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

    def test_evaluate_samples_rejects_recall_k_larger_than_rerank_candidate_pool(self):
        sample = RecallSample(
            risk_id="risk-1",
            contract_id="contract-1",
            contract_type="采购合同",
            query="付款风险",
            gold_article_labels=["19"],
        )

        with self.assertRaisesRegex(ValueError, "fetch_k.*max k"):
            evaluate_samples(
                [sample],
                FakeRerankRetriever(),  # type: ignore[arg-type]
                [20],
                use_rerank=True,
                fetch_k=12,
                final_k=4,
            )

    def test_baseline_comparison_marks_dataset_and_config_mismatch_incompatible(self):
        baseline = {
            "dataset_path": "baseline.jsonl",
            "k_values": [1, 3],
            "filters": {"contract_types": ["采购合同"], "severities": []},
            "retrieval_config": {"use_rerank": True, "fetch_k": 12, "final_k": 4},
            "overall": {"recall_at_1": 1.0, "ndcg_at_1": 1.0, "mrr": 1.0},
            "by_contract_type": {},
            "by_severity": {},
        }
        current = {
            "dataset_path": "current.jsonl",
            "k_values": [1, 5],
            "filters": {"contract_types": ["租赁合同"], "severities": []},
            "retrieval_config": {"use_rerank": True, "fetch_k": 20, "final_k": 5},
            "overall": {"recall_at_1": 0.0, "ndcg_at_1": 0.0, "mrr": 0.0},
            "by_contract_type": {},
            "by_severity": {},
        }

        comparison = compare_with_baseline(current, baseline)

        self.assertIs(comparison.get("compatible"), False)
        self.assertEqual(
            set(comparison["mismatches"]),
            {"dataset_path", "filters", "k_values", "retrieval_config"},
        )
        self.assertEqual(comparison["overall"], {})


if __name__ == "__main__":
    unittest.main()
