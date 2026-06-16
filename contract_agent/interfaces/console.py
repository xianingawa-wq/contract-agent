from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from sqlalchemy import text

from contract_agent.runtime.config import PROJECT_ROOT, settings
from contract_agent.runtime.database import get_engine


DEFAULT_PROFILE_PATH = PROJECT_ROOT / ".run" / "cli_profile.json"


@dataclass(frozen=True)
class ConsoleProfile:
    provider: str
    base_url: str
    chat_model: str
    embedding_model: str
    api_key_configured: bool

    @classmethod
    def from_settings(cls) -> "ConsoleProfile":
        return cls(
            provider=settings.llm_provider,
            base_url=settings.llm_base_url or "",
            chat_model=settings.llm_chat_model,
            embedding_model=settings.llm_embedding_model,
            api_key_configured=bool(settings.llm_api_key),
        )

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> "ConsoleProfile":
        fallback = cls.from_settings()
        return cls(
            provider=str(raw.get("provider") or fallback.provider),
            base_url=str(raw.get("base_url") or fallback.base_url),
            chat_model=str(raw.get("chat_model") or fallback.chat_model),
            embedding_model=str(raw.get("embedding_model") or fallback.embedding_model),
            api_key_configured=bool(raw.get("api_key_configured")),
        )

    def to_json(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "chat_model": self.chat_model,
            "embedding_model": self.embedding_model,
            "api_key_configured": self.api_key_configured,
        }


@dataclass(frozen=True)
class ComponentStatus:
    name: str
    state: str
    detail: str = ""


def run_console_demo(
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    profile_path: Path | None = None,
    skip_db_connect: bool = False,
) -> int:
    profile_path = profile_path or DEFAULT_PROFILE_PATH
    _write_welcome(stdout)

    if profile_path.exists():
        profile = _load_profile(profile_path)
        stdout.write("Profile: ready\n")
    else:
        profile = _run_initialization_wizard(stdin, stdout)
        _save_profile(profile_path, profile)

    database_status = _check_database(skip_connect=skip_db_connect)
    model_status = _check_model(profile)
    _write_init_status(stdout, database_status, model_status, profile)
    _run_chat_loop(stdin=stdin, stdout=stdout, profile=profile, database_status=database_status, model_status=model_status)
    return 0


def _write_welcome(stdout: TextIO) -> None:
    stdout.write("\n")
    stdout.write("========================================\n")
    stdout.write("          CONTRACT AGENT\n")
    stdout.write("========================================\n")
    stdout.write("Welcome to the local agent console.\n\n")


def _run_initialization_wizard(stdin: TextIO, stdout: TextIO) -> ConsoleProfile:
    defaults = ConsoleProfile.from_settings()
    stdout.write("Initialization wizard\n")
    stdout.write("Configure the model provider for this local CLI profile.\n")
    provider = _ask(stdin, stdout, "Provider", defaults.provider)
    base_url = _ask(stdin, stdout, "Base URL", defaults.base_url)
    chat_model = _ask(stdin, stdout, "Chat model", defaults.chat_model)
    embedding_model = _ask(stdin, stdout, "Embedding model", defaults.embedding_model)
    api_key_answer = _ask(stdin, stdout, "API key configured in environment? (yes/no)", "yes" if defaults.api_key_configured else "no")
    return ConsoleProfile(
        provider=provider,
        base_url=base_url,
        chat_model=chat_model,
        embedding_model=embedding_model,
        api_key_configured=api_key_answer.strip().lower() in {"1", "true", "yes", "y", "on"},
    )


def _ask(stdin: TextIO, stdout: TextIO, label: str, default: str) -> str:
    suffix = f" [{default}]" if default else ""
    stdout.write(f"{label}{suffix}: ")
    value = stdin.readline()
    if value == "":
        stdout.write("\n")
        return default
    value = value.strip()
    return value or default


def _load_profile(path: Path) -> ConsoleProfile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ConsoleProfile.from_settings()
    if not isinstance(raw, dict):
        return ConsoleProfile.from_settings()
    return ConsoleProfile.from_json(raw)


def _save_profile(path: Path, profile: ConsoleProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_json(), indent=2), encoding="utf-8")


def _check_database(*, skip_connect: bool) -> ComponentStatus:
    if not settings.postgres_dsn:
        return ComponentStatus("Database", "missing", "POSTGRES_DSN is not configured")
    if skip_connect:
        return ComponentStatus("Database", "skipped", settings.postgres_dsn)
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return ComponentStatus("Database", "ok", settings.postgres_dsn)
    except Exception as exc:
        return ComponentStatus("Database", "failed", str(exc))


def _check_model(profile: ConsoleProfile) -> ComponentStatus:
    supported = {"openai", "openai_compatible", "qwen", "dashscope"}
    if profile.provider.strip().lower() not in supported:
        return ComponentStatus("Model provider", "failed", f"unsupported provider: {profile.provider}")
    if not profile.api_key_configured:
        return ComponentStatus("Model provider", profile.provider, "API key not configured; demo replies only")
    return ComponentStatus("Model provider", profile.provider, "ready")


def _write_init_status(
    stdout: TextIO,
    database_status: ComponentStatus,
    model_status: ComponentStatus,
    profile: ConsoleProfile,
) -> None:
    stdout.write("\nInit checks\n")
    stdout.write(f"{database_status.name}: {database_status.state}\n")
    if database_status.detail:
        stdout.write(f"  {database_status.detail}\n")
    stdout.write(f"{model_status.name}: {model_status.state}\n")
    if model_status.detail:
        stdout.write(f"  {model_status.detail}\n")
    stdout.write(f"Active model: {profile.chat_model}\n")
    stdout.write(f"Embedding model: {profile.embedding_model}\n\n")


def _run_chat_loop(
    *,
    stdin: TextIO,
    stdout: TextIO,
    profile: ConsoleProfile,
    database_status: ComponentStatus,
    model_status: ComponentStatus,
) -> None:
    stdout.write("Agent console\n")
    stdout.write("Type /help for commands, /exit to quit.\n")
    while True:
        stdout.write("You> ")
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
            stdout.write(f"Model provider: {model_status.state}\n")
            stdout.write(f"Active model: {profile.chat_model}\n")
            continue
        if message == "/config":
            stdout.write(f"provider={profile.provider}\n")
            stdout.write(f"base_url={profile.base_url}\n")
            stdout.write(f"chat_model={profile.chat_model}\n")
            stdout.write(f"embedding_model={profile.embedding_model}\n")
            stdout.write(f"api_key_configured={profile.api_key_configured}\n")
            continue
        stdout.write(f"Agent: demo reply from {profile.chat_model}: {message}\n")
