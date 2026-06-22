from __future__ import annotations

from typing import TYPE_CHECKING

from contract_agent.orchestration.config import MultiAgentConfig
from contract_agent.orchestration.protocol import AgentOutput, PipelineState

if TYPE_CHECKING:
    import redis


class HotLayer:
    """Redis-backed hot layer: current pipeline state + recent dialogue rounds."""

    def __init__(self, config: MultiAgentConfig) -> None:
        self.config = config
        self._client: redis.Redis | None = None

    @property
    def client(self) -> redis.Redis:
        import redis

        if self._client is None:
            self._client = redis.from_url(self.config.redis_url, decode_responses=True)
        return self._client

    def set_pipeline_state(self, state: PipelineState) -> None:
        key = f"pipeline:{state.pipeline_id}"
        self.client.setex(key, self.config.redis_ttl_seconds, state.model_dump_json())

    def get_pipeline_state(self, pipeline_id: str) -> PipelineState | None:
        key = f"pipeline:{pipeline_id}"
        raw = self.client.get(key)
        if not raw:
            return None
        return PipelineState.model_validate_json(raw)

    def set_agent_output(self, pipeline_id: str, output: AgentOutput) -> None:
        key = f"agent_output:{pipeline_id}:{output.agent_id}"
        self.client.setex(key, self.config.redis_ttl_seconds, output.model_dump_json())

    def get_agent_output(self, pipeline_id: str, agent_id: str) -> AgentOutput | None:
        key = f"agent_output:{pipeline_id}:{agent_id}"
        raw = self.client.get(key)
        if not raw:
            return None
        return AgentOutput.model_validate_json(raw)

    def delete_pipeline(self, pipeline_id: str) -> None:
        self.client.delete(f"pipeline:{pipeline_id}")

    def refresh_ttl(self, pipeline_id: str) -> None:
        self.client.expire(f"pipeline:{pipeline_id}", self.config.redis_ttl_seconds)

    def close(self) -> None:
        if self._client:
            self._client.close()
