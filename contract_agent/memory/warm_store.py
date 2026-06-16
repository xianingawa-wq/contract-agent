from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from contract_agent.memory.models import AgentOutputRecord
from contract_agent.multi_agent.protocol import AgentOutput
from contract_agent.runtime.database import SessionLocal


class WarmLayer:
    """PostgreSQL-backed warm layer: structured agent outputs and conversation history."""

    def save_pipeline_outputs(
        self, pipeline_id: str, contract_id: str,
        agent_outputs: dict[str, AgentOutput],
    ) -> None:
        db = SessionLocal()
        try:
            for agent_id, output in agent_outputs.items():
                record = AgentOutputRecord(
                    pipeline_id=pipeline_id,
                    contract_id=contract_id,
                    agent_id=agent_id,
                    status=output.status.value,
                    output_json=output.model_dump(mode="json"),
                    created_at=datetime.now(timezone.utc),
                )
                db.add(record)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_review_results(self, contract_id: str) -> dict[str, Any] | None:
        db = SessionLocal()
        try:
            record = (
                db.query(AgentOutputRecord)
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
        finally:
            db.close()

    def get_agent_outputs_for_contract(
        self, contract_id: str, agent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        db = SessionLocal()
        try:
            q = db.query(AgentOutputRecord).filter(
                AgentOutputRecord.contract_id == contract_id
            )
            if agent_id:
                q = q.filter(AgentOutputRecord.agent_id == agent_id)
            records = q.order_by(AgentOutputRecord.created_at.desc()).limit(20).all()
            return [r.output_json for r in records if r.output_json]
        finally:
            db.close()
