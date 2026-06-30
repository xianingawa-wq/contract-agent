import unittest

from contract_agent.memory import cold_store, hot_store, manager, models, repository, warm_store
from contract_agent.config import Settings, temporary_settings
from contract_agent.orchestration.protocol import (
    AgentMode,
    AgentOutput,
    AgentStatus,
    PipelineState,
    PipelineStatus,
)
from contract_agent.runtime import database


class MemoryPersistenceTests(unittest.TestCase):
    def test_memory_model_is_canonical(self):
        self.assertEqual(models.AgentOutputRecord.__tablename__, "agent_outputs")

    def test_memory_stores_are_canonical(self):
        self.assertTrue(hasattr(hot_store, "HotLayer"))
        self.assertTrue(hasattr(warm_store, "WarmLayer"))
        self.assertTrue(hasattr(cold_store, "ColdLayer"))
        self.assertTrue(hasattr(manager, "MemoryManager"))
        self.assertTrue(hasattr(repository, "AgentOutputRepository"))

    def test_cold_layer_uses_chinese_unknown_source_when_document_has_no_title(self):
        class FakeDocument:
            page_content = "合同内容"
            metadata = {}

        class FakeRetriever:
            def __init__(self, store) -> None:
                self.store = store

            def retrieve_documents(self, query, k):
                return [FakeDocument()]

        layer = cold_store.ColdLayer()
        layer.is_available = lambda: True

        from unittest.mock import patch

        with (
            patch(
                "contract_agent.knowledge.rag.vector_store.load_vector_store", return_value=object()
            ),
            patch(
                "contract_agent.knowledge.rag.retriever.ContractKnowledgeRetriever",
                FakeRetriever,
            ),
        ):
            results = layer.search("付款", top_k=1)

        self.assertEqual(results[0]["source"], "未知")

    def test_memory_manager_degrades_when_warm_persistence_has_no_postgres_dsn(self):
        class FakeHotLayer:
            def __init__(self, config) -> None:
                self.saved_state = None

            def set_pipeline_state(self, state) -> None:
                self.saved_state = state

            def close(self) -> None:
                pass

        from unittest.mock import patch

        runtime_settings = Settings(postgres_dsn=None)
        state = PipelineState(
            pipeline_id="pipeline-no-dsn",
            contract_id="contract-no-dsn",
            mode=AgentMode.MULTI_AUTO,
            team="review",
            status=PipelineStatus.COMPLETED,
            agent_outputs={
                "summarizer": AgentOutput(
                    agent_id="summarizer",
                    status=AgentStatus.COMPLETED,
                    structured_data={"review_report": {"summary": "完成"}},
                )
            },
        )

        with patch("contract_agent.memory.manager.HotLayer", FakeHotLayer):
            memory = manager.MemoryManager(runtime_settings=runtime_settings)
            memory.save_pipeline_result(state)

        self.assertIs(memory.hot.saved_state, state)

    def test_agent_output_repository_persists_and_filters_outputs(self):
        database._engine = None
        database._session_factory = None
        try:
            with temporary_settings(postgres_dsn="sqlite+pysqlite:///:memory:"):
                repo = repository.AgentOutputRepository()
                repo.save_pipeline_outputs(
                    "pipeline-1",
                    "contract-1",
                    {
                        "summarizer": AgentOutput(
                            agent_id="summarizer",
                            status=AgentStatus.COMPLETED,
                            structured_data={"review_report": {"overall_risk": "medium"}},
                        ),
                        "risk_checker": AgentOutput(
                            agent_id="risk_checker",
                            status=AgentStatus.COMPLETED,
                            structured_data={"risk_count": 2},
                        ),
                    },
                )

                self.assertEqual(
                    repo.get_latest_review_report("contract-1"),
                    {"overall_risk": "medium"},
                )
                all_outputs = repo.list_outputs("contract-1")
                risk_outputs = repo.list_outputs("contract-1", agent_id="risk_checker")

                self.assertEqual(len(all_outputs), 2)
                self.assertEqual(len(risk_outputs), 1)
                self.assertEqual(risk_outputs[0]["agent_id"], "risk_checker")
        finally:
            database._engine = None
            database._session_factory = None

    def test_warm_layer_delegates_to_repository(self):
        class FakeRepository:
            def __init__(self) -> None:
                self.saved = None

            def save_pipeline_outputs(self, pipeline_id, contract_id, agent_outputs):
                self.saved = (pipeline_id, contract_id, agent_outputs)

            def get_latest_review_report(self, contract_id):
                return {"contract_id": contract_id}

            def list_outputs(self, contract_id, agent_id=None, limit=20):
                return [{"contract_id": contract_id, "agent_id": agent_id, "limit": limit}]

        fake = FakeRepository()
        layer = warm_store.WarmLayer(repository=fake)

        layer.save_pipeline_outputs("pipeline-2", "contract-2", {})

        self.assertEqual(fake.saved, ("pipeline-2", "contract-2", {}))
        self.assertEqual(layer.get_review_results("contract-2"), {"contract_id": "contract-2"})
        self.assertEqual(
            layer.get_agent_outputs_for_contract("contract-2", agent_id="summarizer"),
            [{"contract_id": "contract-2", "agent_id": "summarizer", "limit": 20}],
        )


if __name__ == "__main__":
    unittest.main()
