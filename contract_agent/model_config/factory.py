from __future__ import annotations

from pathlib import Path

from contract_agent.model_config.impl.env_source import EnvironmentModelConfigSource
from contract_agent.model_config.impl.json_profile_store import JsonModelProfileStore
from contract_agent.model_config.interface import DEFAULT_MODEL_PROFILE_PATH
from contract_agent.model_config.service import ModelConfigResolver, ModelProfileService


def create_model_config_resolver(profile_path: Path | None = None) -> ModelConfigResolver:
    store = JsonModelProfileStore(profile_path or DEFAULT_MODEL_PROFILE_PATH)
    return ModelConfigResolver(EnvironmentModelConfigSource(), store)


def create_model_profile_service(profile_path: Path | None = None) -> ModelProfileService:
    store = JsonModelProfileStore(profile_path or DEFAULT_MODEL_PROFILE_PATH)
    resolver = ModelConfigResolver(EnvironmentModelConfigSource(), store)
    return ModelProfileService(resolver, store)
