from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from contract_agent.memory.models import AgentOutputRecord
from contract_agent.orchestration.protocol import AgentOutput
from contract_agent.config import Settings, settings_snapshot
from contract_agent.runtime.database import session_scope
from contract_agent.runtime.schema import ensure_runtime_schema


def _agent_output_to_dict(output: AgentOutput) -> dict[str, Any]:
    if hasattr(output, "model_dump"):
        return output.model_dump(mode="json")
    return output.dict()


class AgentOutputRepository:
    """Repository for persisted multi-agent outputs."""

    def __init__(
        self, runtime_settings: Settings | None = None, ensure_schema: bool = False
    ) -> None:
        self.settings = runtime_settings or settings_snapshot()
        self._auto_ensure_schema = ensure_schema
        self._schema_ready = False
        if ensure_schema:
            self._ensure_schema()

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return
        ensure_runtime_schema(self.settings)
        self._schema_ready = True

    def save_pipeline_outputs(
        self,
        pipeline_id: str,
        contract_id: str,
        agent_outputs: dict[str, AgentOutput],
    ) -> None:
        if self._auto_ensure_schema:
            self._ensure_schema()
        with session_scope(self.settings) as session:
            for agent_id, output in agent_outputs.items():
                session.add(
                    AgentOutputRecord(
                        pipeline_id=pipeline_id,
                        contract_id=contract_id,
                        agent_id=agent_id,
                        status=output.status.value,
                        output_json=_agent_output_to_dict(output),
                        created_at=datetime.now(timezone.utc),
                    )
                )

    def get_latest_review_report(self, contract_id: str) -> dict[str, Any] | None:
        if self._auto_ensure_schema:
            self._ensure_schema()
        with session_scope(self.settings) as session:
            record = (
                session.query(AgentOutputRecord)
                .filter(
                    AgentOutputRecord.contract_id == contract_id,
                    AgentOutputRecord.agent_id == "summarizer",
                    AgentOutputRecord.status == "completed",
                )
                .order_by(AgentOutputRecord.created_at.desc())
                .first()
            )
            if record and record.output_json:
                return record.output_json.get("structured_data", {}).get("review_report")
            return None

    def list_outputs(
        self,
        contract_id: str,
        agent_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if self._auto_ensure_schema:
            self._ensure_schema()
        with session_scope(self.settings) as session:
            query = session.query(AgentOutputRecord).filter(
                AgentOutputRecord.contract_id == contract_id
            )
            if agent_id:
                query = query.filter(AgentOutputRecord.agent_id == agent_id)
            records = query.order_by(AgentOutputRecord.created_at.desc()).limit(limit).all()
            return [record.output_json for record in records if record.output_json]
