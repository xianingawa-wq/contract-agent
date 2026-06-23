from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from contract_agent.orchestration.protocol import AgentMode, PipelineState, PipelineStatus
from contract_agent.runtime.config import Settings
from contract_agent.services.review_service import ReviewService
from contract_agent.schemas.review import ReviewRequest


class SingleAgentHandler:
    """Handles single-agent mode: direct LLM call, no pipeline overhead."""

    def __init__(self, runtime_settings: Settings | None = None, review_service: ReviewService | None = None) -> None:
        self.review_service = review_service or ReviewService(runtime_settings=runtime_settings)

    def run_review(
        self,
        state: PipelineState,
        contract_text: str,
        contract_type: str | None = None,
        our_side: str = "甲方",
    ) -> tuple[PipelineState, dict[str, Any]]:
        state.status = PipelineStatus.RUNNING
        try:
            result = self.review_service.review(
                ReviewRequest(
                    contract_text=contract_text,
                    contract_type=contract_type,
                    our_side=our_side,
                )
            )
            state.status = PipelineStatus.COMPLETED
            state.completed_at = datetime.now(timezone.utc)
            return state, {"review_result": result.model_dump(mode="json")}
        except Exception as exc:
            state.status = PipelineStatus.FAILED
            state.errors.append({"agent_id": "single_agent", "error": str(exc)})
            state.completed_at = datetime.now(timezone.utc)
            return state, {"error": str(exc)}
