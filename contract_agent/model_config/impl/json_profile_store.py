from __future__ import annotations

import json
from pathlib import Path

from contract_agent.model_config.impl.env_source import EnvironmentModelConfigSource
from contract_agent.model_config.impl.json_profile_codec import JsonModelProfileCodec
from contract_agent.model_config.interface import ModelRuntimeConfig


class JsonModelProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.codec = JsonModelProfileCodec()

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> ModelRuntimeConfig:
        fallback = EnvironmentModelConfigSource().load()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback
        if not isinstance(raw, dict):
            return fallback
        return self.codec.decode(raw, fallback)

    def save(self, config: ModelRuntimeConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.codec.encode(config), indent=2), encoding="utf-8")
