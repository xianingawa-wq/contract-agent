from __future__ import annotations

import json
from typing import Any

from contract_agent.provider.interface import ToolCall


def input_to_messages(input: str | list[dict[str, Any]], instructions: str | None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})
    if isinstance(input, str):
        messages.append({"role": "user", "content": input})
    else:
        messages.extend(input)
    return messages


def extract_output_text(response: Any) -> str:
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


def extract_tool_calls(response: Any) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) != "function_call":
            continue
        calls.append(
            ToolCall(
                call_id=getattr(item, "call_id", "") or getattr(item, "id", ""),
                name=getattr(item, "name", ""),
                arguments=loads_json_object(getattr(item, "arguments", "{}") or "{}"),
            )
        )
    return calls


def loads_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        return {}


def with_strict_objects(schema: dict[str, Any]) -> dict[str, Any]:
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

__all__ = [
    "extract_output_text",
    "extract_tool_calls",
    "input_to_messages",
    "loads_json_object",
    "with_strict_objects",
]
