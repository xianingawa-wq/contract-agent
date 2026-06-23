import unittest

from contract_agent.memory import cold_store, hot_store, manager, models, repository, warm_store
from contract_agent.orchestration.protocol import AgentOutput, AgentStatus
from contract_agent.runtime import database
from contract_agent.runtime.config import temporary_settings


class MemoryPersistenceTests(unittest.TestCase):
    def test_memory_model_is_canonical(self):
        self.assertEqual(models.AgentOutputRecord.__tablename__, "agent_outputs")

    def test_memory_stores_are_canonical(self):
        self.assertTrue(hasattr(hot_store, "HotLayer"))
        self.assertTrue(hasattr(warm_store, "WarmLayer"))
        self.assertTrue(hasattr(cold_store, "ColdLayer"))
        self.assertTrue(hasattr(manager, "MemoryManager"))
        self.assertTrue(hasattr(repository, "AgentOutputRepository"))

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
