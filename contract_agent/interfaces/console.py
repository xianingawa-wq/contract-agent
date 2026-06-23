from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlalchemy import text

from contract_agent.interfaces.console_paths import DEFAULT_PROFILE_PATH
from contract_agent.model_config.factory import create_model_profile_service
from contract_agent.model_config.interface import (
    DEFAULT_PROVIDER_OPTIONS,
    ModelEndpointConfig,
    ModelProviderOption,
    ModelRole,
    ModelRuntimeConfig,
)
from contract_agent.runtime.config import settings_snapshot
from contract_agent.runtime.database import get_engine


class ComponentStatus:
    def __init__(self, name: str, state: str, detail: str = "") -> None:
        self.name = name
        self.state = state
        self.detail = detail


def run_console_demo(
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    profile_path: Path | None = None,
    skip_db_connect: bool = False,
) -> int:
    profile_service = create_model_profile_service(profile_path or DEFAULT_PROFILE_PATH)
    _write_welcome(stdout)

    if profile_service.has_profile():
        model_config = profile_service.load()
        stdout.write("Profile: ready\n")
    else:
        model_config = _run_initialization_wizard(stdin, stdout, profile_service.load())
        profile_service.save(model_config)

    profile_service.apply_to_settings(model_config)
    database_status = _check_database(skip_connect=skip_db_connect)
    model_statuses = _check_models(model_config)
    _write_init_status(stdout, database_status, model_statuses, model_config)
    _run_chat_loop(
        stdin=stdin,
        stdout=stdout,
        model_config=model_config,
        database_status=database_status,
        model_statuses=model_statuses,
    )
    return 0


def _write_welcome(stdout: TextIO) -> None:
    stdout.write("\n")
    stdout.write("========================================\n")
    stdout.write("          CONTRACT AGENT\n")
    stdout.write("========================================\n")
    stdout.write("Welcome to the local agent console.\n\n")


def _run_initialization_wizard(stdin: TextIO, stdout: TextIO, defaults: ModelRuntimeConfig) -> ModelRuntimeConfig:
    stdout.write("Initialization wizard\n")
    stdout.write("Configure chat, embedding, and rerank models separately.\n")
    return ModelRuntimeConfig(
        chat=_run_endpoint_wizard(stdin, stdout, "Chat", defaults.chat),
        embedding=_run_endpoint_wizard(stdin, stdout, "Embedding", defaults.embedding),
        rerank=_run_endpoint_wizard(stdin, stdout, "Rerank", defaults.rerank),
    )


def _run_endpoint_wizard(
    stdin: TextIO,
    stdout: TextIO,
    label: str,
    defaults: ModelEndpointConfig,
) -> ModelEndpointConfig:
    stdout.write(f"\n{label} provider\n")
    for option in DEFAULT_PROVIDER_OPTIONS:
        detail = option.base_url or "enter your own URL"
        stdout.write(f"  {option.key}. {option.label} ({detail})\n")
    selected = _ask(stdin, stdout, "Select provider", _default_provider_key(defaults))
    option = _find_provider_option(selected) or ModelProviderOption(selected, selected, selected, defaults.base_url)

    base_url = option.base_url
    if option.key == "3":
        base_url = _ask(stdin, stdout, f"{label} base URL", defaults.base_url)

    api_key = _ask_api_key(stdin, stdout, f"{label} API key", defaults.api_key)
    model = _ask(stdin, stdout, f"{label} model", defaults.model)
    return ModelEndpointConfig(
        role=defaults.role,
        provider=option.provider,
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


def _find_provider_option(value: str) -> ModelProviderOption | None:
    normalized = value.strip().lower()
    for option in DEFAULT_PROVIDER_OPTIONS:
        if normalized in {option.key, option.provider.lower(), option.label.lower()}:
            return option
    return None


def _default_provider_key(defaults: ModelEndpointConfig) -> str:
    for option in DEFAULT_PROVIDER_OPTIONS:
        if defaults.provider.lower() == option.provider.lower() and (
            not option.base_url or defaults.base_url.rstrip("/") == option.base_url.rstrip("/")
        ):
            return option.key
    return "3"


def _ask(stdin: TextIO, stdout: TextIO, label: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    stdout.write(f"{label}{suffix}: ")
    stdout.flush()
    value = stdin.readline()
    if value == "":
        stdout.write("\n")
        return default
    value = value.strip()
    return value or default


def _ask_api_key(stdin: TextIO, stdout: TextIO, label: str, existing: str) -> str:
    suffix = " [configured; press Enter to keep]" if existing else ""
    stdout.write(f"{label}{suffix}: ")
    stdout.flush()
    value = stdin.readline()
    if value == "":
        stdout.write("\n")
        return existing
    value = value.strip()
    return value or existing


def _check_database(*, skip_connect: bool) -> ComponentStatus:
    current = settings_snapshot()
    if not current.postgres_dsn:
        return ComponentStatus("Database", "missing", "POSTGRES_DSN is not configured")
    if skip_connect:
        return ComponentStatus("Database", "skipped", current.postgres_dsn)
    try:
        with get_engine(current).connect() as connection:
            connection.execute(text("SELECT 1"))
        return ComponentStatus("Database", "ok", current.postgres_dsn)
    except Exception as exc:
        return ComponentStatus("Database", "failed", str(exc))


def _check_models(model_config: ModelRuntimeConfig) -> list[ComponentStatus]:
    return [
        _check_model_endpoint("Chat provider", model_config.chat),
        _check_model_endpoint("Embedding provider", model_config.embedding),
        _check_model_endpoint("Rerank provider", model_config.rerank),
    ]


def _check_model_endpoint(name: str, endpoint: ModelEndpointConfig) -> ComponentStatus:
    supported = {"openai", "openai_compatible", "qwen", "dashscope"}
    if endpoint.provider.strip().lower() not in supported:
        return ComponentStatus(name, "failed", f"unsupported provider: {endpoint.provider}")
    if not endpoint.api_key_configured:
        return ComponentStatus(name, endpoint.provider, "API key not configured; demo replies only")
    return ComponentStatus(name, endpoint.provider, "ready")


def _write_init_status(
    stdout: TextIO,
    database_status: ComponentStatus,
    model_statuses: list[ComponentStatus],
    model_config: ModelRuntimeConfig,
) -> None:
    stdout.write("\nInit checks\n")
    stdout.write(f"{database_status.name}: {database_status.state}\n")
    if database_status.detail:
        stdout.write(f"  {database_status.detail}\n")
    for model_status in model_statuses:
        stdout.write(f"{model_status.name}: {model_status.state}\n")
        if model_status.detail:
            stdout.write(f"  {model_status.detail}\n")
    stdout.write(f"Active chat model: {model_config.chat.model}\n")
    stdout.write(f"Embedding model: {model_config.embedding.model}\n")
    stdout.write(f"Rerank model: {model_config.rerank.model}\n\n")


def _run_chat_loop(
    *,
    stdin: TextIO,
    stdout: TextIO,
    model_config: ModelRuntimeConfig,
    database_status: ComponentStatus,
    model_statuses: list[ComponentStatus],
) -> None:
    stdout.write("Agent console\n")
    stdout.write("Type /help for commands, /exit to quit.\n")
    while True:
        stdout.write("You> ")
        stdout.flush()
        raw = stdin.readline()
        if raw == "":
            stdout.write("\n")
            return
        message = raw.strip()
        if not message:
            continue
        if message in {"/exit", "/quit"}:
            stdout.write("Bye.\n")
            return
        if message == "/help":
            stdout.write("Commands: /help, /status, /config, /exit\n")
            continue
        if message == "/status":
            stdout.write("Initialized: yes\n")
            stdout.write(f"Database: {database_status.state}\n")
            for model_status in model_statuses:
                stdout.write(f"{model_status.name}: {model_status.state}\n")
            stdout.write(f"Active chat model: {model_config.chat.model}\n")
            continue
        if message == "/config":
            _write_endpoint_config(stdout, ModelRole.CHAT.value, model_config.chat)
            _write_endpoint_config(stdout, ModelRole.EMBEDDING.value, model_config.embedding)
            _write_endpoint_config(stdout, ModelRole.RERANK.value, model_config.rerank)
            continue
        stdout.write(f"Agent: demo reply from {model_config.chat.model}: {message}\n")


def _write_endpoint_config(stdout: TextIO, prefix: str, endpoint: ModelEndpointConfig) -> None:
    stdout.write(f"{prefix}.provider={endpoint.provider}\n")
    stdout.write(f"{prefix}.base_url={endpoint.base_url}\n")
    stdout.write(f"{prefix}.model={endpoint.model}\n")
    stdout.write(f"{prefix}.api_key_configured={endpoint.api_key_configured}\n")
