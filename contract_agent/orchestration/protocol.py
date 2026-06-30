from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field


class AgentMode(str, Enum):
    SINGLE = "single"
    MULTI_AUTO = "multi_auto"
    MULTI_MANUAL = "multi_manual"


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class AgentTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    KILLED = "killed"
    CANCELLED = "cancelled"


class TaskCommandType(str, Enum):
    FOLLOW_UP = "follow_up"
    CANCEL = "cancel"
    HEARTBEAT = "heartbeat"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class AgentFinding(BaseModel):
    clause: str
    risk: Literal["high", "medium", "low", "info"]
    summary: str
    suggestion: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    agent_id: str
    status: AgentStatus
    input_summary: str = ""
    findings: list[AgentFinding] = Field(default_factory=list)
    structured_data: dict[str, Any] = Field(default_factory=dict)
    next_agent_hints: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    token_used: int = 0
    llm_calls: int = 0


class AgentTask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_id: str
    agent_id: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    status: AgentTaskStatus = AgentTaskStatus.PENDING
    input_summary: str = ""
    progress: float = 0.0
    pending_command_count: int = 0
    attempt: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    timeout_seconds: float | None = None
    transcript_path: str | None = None
    output: AgentOutput | None = None
    error_message: str | None = None


class TaskCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command_type: TaskCommandType
    target: str
    pipeline_id: str | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TaskNotification(BaseModel):
    task_id: str
    pipeline_id: str
    agent_id: str
    run_id: str
    status: AgentTaskStatus
    summary: str = ""
    output: AgentOutput | None = None
    error_message: str | None = None
    duration_ms: int = 0
    token_used: int = 0
    llm_calls: int = 0
    tool_uses: int = 0
    transcript_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def idempotency_key(self) -> tuple[str, str, AgentTaskStatus]:
        return (self.task_id, self.run_id, self.status)

    @classmethod
    def from_task(
        cls,
        task: AgentTask,
        status: AgentTaskStatus | None = None,
        summary: str = "",
        output: AgentOutput | None = None,
        error_message: str | None = None,
        duration_ms: int = 0,
        tool_uses: int = 0,
    ) -> "TaskNotification":
        resolved_output = output if output is not None else task.output
        return cls(
            task_id=task.task_id,
            pipeline_id=task.pipeline_id,
            agent_id=task.agent_id,
            run_id=task.run_id,
            status=status or task.status,
            summary=summary or task.input_summary,
            output=resolved_output,
            error_message=error_message if error_message is not None else task.error_message,
            duration_ms=duration_ms,
            token_used=resolved_output.token_used if resolved_output else 0,
            llm_calls=resolved_output.llm_calls if resolved_output else 0,
            tool_uses=tool_uses,
            transcript_path=task.transcript_path,
        )


class PipelineState(BaseModel):
    pipeline_id: str
    contract_id: str
    mode: AgentMode
    team: Literal["review", "dialogue"]
    status: PipelineStatus
    current_agent: str | None = None
    agent_outputs: dict[str, AgentOutput] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    token_used_total: int = 0


class GatewayRequest(BaseModel):
    request_id: str
    team: Literal["review", "dialogue"]
    mode: AgentMode
    contract_id: str | None = None
    user_message: str = ""
    context_ids: list[str] = Field(default_factory=list)


class GatewayResponse(BaseModel):
    request_id: str
    pipeline_id: str | None = None
    contract_id: str | None = None
    mode: AgentMode
    team: Literal["review", "dialogue"]
    error: str | None = None


class PipelineEvent(BaseModel):
    pipeline_id: str
    event_type: Literal[
        "pipeline_started",
        "pipeline_completed",
        "pipeline_failed",
        "agent_started",
        "agent_completed",
        "agent_failed",
        "agent_skipped",
        "pipeline_cancelled",
        "compression_triggered",
        "supervisor_thinking",
        "supervisor_finished",
        "agent_called",
        "round_complete",
    ]
    agent_id: str | None = None
    round: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PipelineEventType(str, Enum):
    PIPELINE_STARTED = "pipeline_started"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    PIPELINE_CANCELLED = "pipeline_cancelled"
    AGENT_STARTED = "agent_started"
    AGENT_COMPLETED = "agent_completed"
    AGENT_FAILED = "agent_failed"
    AGENT_SKIPPED = "agent_skipped"
    COMPRESSION_TRIGGERED = "compression_triggered"
    SUPERVISOR_THINKING = "supervisor_thinking"
    SUPERVISOR_FINISHED = "supervisor_finished"
    AGENT_CALLED = "agent_called"
    ROUND_COMPLETE = "round_complete"
