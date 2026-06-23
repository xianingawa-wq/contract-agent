from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    api_key: str | None
    base_url: str | None
    chat_model: str
    embedding_model: str
    temperature: float = 0
    use_responses_api: bool = True
    embedding_batch_size: int = 10
