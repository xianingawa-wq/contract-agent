from __future__ import annotations

import logging
from typing import Any

from contract_agent.memory.repository import AgentOutputRepository
from contract_agent.orchestration.protocol import AgentOutput
from contract_agent.config import Settings, settings_snapshot

logger = logging.getLogger(__name__)


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
        try:
            self.repository.save_pipeline_outputs(pipeline_id, contract_id, agent_outputs)
        except Exception as exc:
            logger.warning("Warm 层持久化已降级跳过：%s", exc)

    def get_review_results(self, contract_id: str) -> dict[str, Any] | None:
        try:
            return self.repository.get_latest_review_report(contract_id)
        except Exception as exc:
            logger.warning("Warm 层读取已降级跳过：%s", exc)
            return None

    def get_agent_outputs_for_contract(
        self,
        contract_id: str,
        agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            return self.repository.list_outputs(contract_id, agent_id=agent_id, limit=20)
        except Exception as exc:
            logger.warning("Warm 层列表读取已降级跳过：%s", exc)
            return []
