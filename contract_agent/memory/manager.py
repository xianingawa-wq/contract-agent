from __future__ import annotations

from typing import Any

from contract_agent.memory.cold_store import ColdLayer
from contract_agent.memory.hot_store import HotLayer
from contract_agent.memory.warm_store import WarmLayer
from contract_agent.multi_agent.config import MultiAgentConfig
from contract_agent.multi_agent.protocol import PipelineState


class MemoryManager:
    """Unified access to all three memory tiers."""

    def __init__(self, config: MultiAgentConfig | None = None) -> None:
        self.config = config or MultiAgentConfig()
        self.hot = HotLayer(self.config)
        self.warm = WarmLayer()
        self.cold = ColdLayer()

    def save_pipeline_result(self, state: PipelineState) -> None:
        self.hot.set_pipeline_state(state)
        self.warm.save_pipeline_outputs(
            pipeline_id=state.pipeline_id,
            contract_id=state.contract_id,
            agent_outputs=state.agent_outputs,
        )

    def get_review_context(self, contract_id: str) -> dict[str, Any] | None:
        return self.warm.get_review_results(contract_id)

    def close(self) -> None:
        self.hot.close()
