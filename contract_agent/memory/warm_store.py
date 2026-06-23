from __future__ import annotations

from typing import Any

from contract_agent.memory.repository import AgentOutputRepository
from contract_agent.orchestration.protocol import AgentOutput
from contract_agent.config import Settings, settings_snapshot


class WarmLayer:
    """PostgreSQL-backed warm layer: structured agent outputs and conversation history."""

    def __init__(
        self,
        repository: AgentOutputRepository | None = None,
        runtime_settings: Settings | None = None,
    ) -> None:
        self.settings = runtime_settings or settings_snapshot()
        self.repository = repository or AgentOutputRepository(runtime_settings=self.settings)

    def save_pipeline_outputs(
        self,
        pipeline_id: str,
        contract_id: str,
        agent_outputs: dict[str, AgentOutput],
    ) -> None:
        self.repository.save_pipeline_outputs(pipeline_id, contract_id, agent_outputs)

    def get_review_results(self, contract_id: str) -> dict[str, Any] | None:
        return self.repository.get_latest_review_report(contract_id)

    def get_agent_outputs_for_contract(
        self,
        contract_id: str,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repository.list_outputs(contract_id, agent_id=agent_id, limit=20)
