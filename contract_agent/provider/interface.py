from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from langchain_core.embeddings import Embeddings

if TYPE_CHECKING:
    from langchain_openai import ChatOpenAI


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str | None
    base_url: str | None
    chat_model: str
    embedding_model: str
    temperature: float = 0
    use_responses_api: bool = True


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ModelResponse:
    text: str
    raw: Any
    tool_calls: list[ToolCall]


class LLMProvider(Protocol):
    config: LLMConfig

    def chat_model(self) -> "ChatOpenAI":
        ...

    def embeddings(self) -> Embeddings:
        ...

    def create_response(
        self,
        *,
        input: str | list[dict[str, Any]],
        instructions: str | None = None,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
    ) -> ModelResponse:
        ...

    def structured_output(
        self,
        *,
        input: str | list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        instructions: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        ...
