from __future__ import annotations

import json
from typing import Any, Callable

from langchain_core.embeddings import Embeddings
from openai import OpenAI

from contract_agent.provider.impl.openai.embeddings import OpenAIEmbeddings
from contract_agent.provider.impl.openai.message_codec import (
    extract_output_text,
    extract_tool_calls,
    input_to_messages,
    loads_json_object,
    with_strict_objects,
)
from contract_agent.config import LLMConfig
from contract_agent.provider.interface import ModelResponse, ToolCall


class OpenAIProvider:
    """Provider for OpenAI and OpenAI-compatible API endpoints."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        kwargs: dict[str, Any] = {"api_key": config.api_key}
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self.client = OpenAI(**kwargs)

    def chat_model(self):
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "api_key": self.config.api_key,
            "model": self.config.chat_model,
            "temperature": self.config.temperature,
        }
        if self.config.base_url:
            kwargs["base_url"] = self.config.base_url
        return ChatOpenAI(**kwargs)

    def embeddings(self) -> Embeddings:
        return OpenAIEmbeddings(self.config)

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
        return self._chat_completion_create(
            input=input, instructions=instructions, model=model, tools=tools
        )

    def structured_output(
        self,
        *,
        input: str | list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        instructions: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        strict_schema = with_strict_objects(schema)
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
                return loads_json_object(extract_output_text(response))
            except Exception:
                pass

        completion = self.client.chat.completions.create(
            model=model or self.config.chat_model,
            messages=input_to_messages(input, instructions),
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": strict_schema,
                    "strict": True,
                },
            },
        )
        return loads_json_object(completion.choices[0].message.content or "{}")

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
        response = self.create_response(
            input=input, instructions=instructions, model=model, tools=tools
        )
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
            text=extract_output_text(response),
            raw=response,
            tool_calls=extract_tool_calls(response),
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
            messages=input_to_messages(input, instructions),
            tools=tools,
        )
        message = completion.choices[0].message
        tool_calls = [
            ToolCall(
                call_id=call.id,
                name=call.function.name,
                arguments=loads_json_object(call.function.arguments or "{}"),
            )
            for call in (message.tool_calls or [])
        ]
        return ModelResponse(text=message.content or "", raw=completion, tool_calls=tool_calls)
