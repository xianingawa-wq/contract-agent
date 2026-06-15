from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI
from openai import OpenAI

from contract_agent.core.config import settings


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

    def chat_model(self) -> ChatOpenAI:
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


class OpenAICompatibleEmbeddings(Embeddings):
    def __init__(self, config: LLMConfig) -> None:
        kwargs: dict[str, Any] = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)
        self.model = config.embedding_model
        self.chunk_size = 10

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.chunk_size):
            batch = [text if isinstance(text, str) else str(text) for text in texts[start : start + self.chunk_size]]
            response = self.client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in response.data)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        response = self.client.embeddings.create(model=self.model, input=text)
        return response.data[0].embedding


class OpenAICompatibleProvider:
    """Provider for OpenAI and services implementing the OpenAI API shape."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        kwargs: dict[str, Any] = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)

    def chat_model(self) -> ChatOpenAI:
        kwargs: dict[str, Any] = {
            "api_key": self.config.api_key,
            "model": self.config.chat_model,
            "temperature": self.config.temperature,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return ChatOpenAI(**kwargs)

    def embeddings(self) -> Embeddings:
        return OpenAICompatibleEmbeddings(self.config)

    def create_response(
        self,
        *,
        input: str | list[dict[str, Any]],
        instructions: str | None = None,
        model: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
    ) -> ModelResponse:
        if self.config.use_responses_api:
            try:
                return self._responses_create(
                    input=input,
                    instructions=instructions,
                    model=model,
                    tools=tools,
                    previous_response_id=previous_response_id,
                )
            except Exception:
                if tools or previous_response_id:
                    raise
        return self._chat_completion_create(input=input, instructions=instructions, model=model, tools=tools)

    def structured_output(
        self,
        *,
        input: str | list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        instructions: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        strict_schema = _with_strict_objects(schema)
        if self.config.use_responses_api:
            try:
                response = self.client.responses.create(
                    model=model or self.config.chat_model,
                    instructions=instructions,
                    input=input,
                    text={
                        "format": {
                            "type": "json_schema",
                            "name": schema_name,
                            "schema": strict_schema,
                            "strict": True,
                        }
                    },
                )
                return _loads_json(_extract_output_text(response))
            except Exception:
                pass

        completion = self.client.chat.completions.create(
            model=model or self.config.chat_model,
            messages=_input_to_messages(input, instructions),
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": strict_schema,
                    "strict": True,
                },
            },
        )
        return _loads_json(completion.choices[0].message.content or "{}")

    def run_tool_loop(
        self,
        *,
        input: str | list[dict[str, Any]],
        tools: list[dict[str, Any]],
        handlers: dict[str, Callable[[dict[str, Any]], Any]],
        instructions: str | None = None,
        model: str | None = None,
        max_rounds: int = 5,
    ) -> ModelResponse:
        response = self.create_response(input=input, instructions=instructions, model=model, tools=tools)
        for _ in range(max_rounds):
            if not response.tool_calls:
                return response
            tool_outputs = []
            for call in response.tool_calls:
                if call.name not in handlers:
                    raise RuntimeError(f"No handler registered for tool call: {call.name}")
                result = handlers[call.name](call.arguments)
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )
            response = self.create_response(
                input=tool_outputs,
                instructions=instructions,
                model=model,
                tools=tools,
                previous_response_id=getattr(response.raw, "id", None),
            )
        raise RuntimeError("Tool loop exceeded max rounds.")

    def _responses_create(
        self,
        *,
        input: str | list[dict[str, Any]],
        instructions: str | None,
        model: str | None,
        tools: list[dict[str, Any]] | None,
        previous_response_id: str | None,
    ) -> ModelResponse:
        kwargs: dict[str, Any] = {"model": model or self.config.chat_model, "input": input}
        if instructions:
            kwargs["instructions"] = instructions
        if tools:
            kwargs["tools"] = tools
        if previous_response_id:
            kwargs["previous_response_id"] = previous_response_id
        response = self.client.responses.create(**kwargs)
        return ModelResponse(
            text=_extract_output_text(response),
            raw=response,
            tool_calls=_extract_tool_calls(response),
        )

    def _chat_completion_create(
        self,
        *,
        input: str | list[dict[str, Any]],
        instructions: str | None,
        model: str | None,
        tools: list[dict[str, Any]] | None,
    ) -> ModelResponse:
        completion = self.client.chat.completions.create(
            model=model or self.config.chat_model,
            messages=_input_to_messages(input, instructions),
            tools=tools,
        )
        message = completion.choices[0].message
        tool_calls = [
            ToolCall(
                call_id=call.id,
                name=call.function.name,
                arguments=_loads_json(call.function.arguments or "{}"),
            )
            for call in (message.tool_calls or [])
        ]
        return ModelResponse(text=message.content or "", raw=completion, tool_calls=tool_calls)


def get_provider() -> LLMProvider:
    config = LLMConfig(
        provider=settings.llm_provider,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        chat_model=settings.llm_chat_model,
        embedding_model=settings.llm_embedding_model,
        temperature=settings.llm_temperature,
        use_responses_api=settings.llm_use_responses_api,
    )
    if config.provider.strip().lower() in {"openai", "openai_compatible", "qwen", "dashscope"}:
        return OpenAICompatibleProvider(config)
    raise ValueError(f"Unsupported LLM_PROVIDER: {config.provider}")


def _input_to_messages(input: str | list[dict[str, Any]], instructions: str | None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})
    if isinstance(input, str):
        messages.append({"role": "user", "content": input})
    else:
        messages.extend(input)
    return messages


def _extract_output_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                parts.append(str(text))
    return "\n".join(parts)


def _extract_tool_calls(response: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "function_call":
            continue
        calls.append(
            ToolCall(
                call_id=getattr(item, "call_id", "") or getattr(item, "id", ""),
                name=getattr(item, "name", ""),
                arguments=_loads_json(getattr(item, "arguments", "{}") or "{}"),
            )
        )
    return calls


def _loads_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {}


def _with_strict_objects(schema: dict[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(schema))

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            node.setdefault("additionalProperties", False)
        for value in node.values():
            if isinstance(value, dict):
                visit(value)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

    visit(copied)
    return copied
