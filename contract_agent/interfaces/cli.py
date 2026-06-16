from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from contract_agent.interfaces.console import DEFAULT_PROFILE_PATH, run_console_demo
from contract_agent.runtime.config import settings
from contract_agent.review.reporting import render_json, render_markdown
from contract_agent.review.service import review_text


def main(
    argv: list[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    _prefer_utf8(stdout)
    _prefer_utf8(stderr)
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command in {None, "demo"}:
        return _demo_command(args, stdin, stdout, stderr)
    if args.command == "review":
        return _review_command(args, stdout, stderr)
    if args.command == "config":
        return _config_command(stdout)

    parser.print_help(stdout)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contract-agent")
    subcommands = parser.add_subparsers(dest="command")

    demo = subcommands.add_parser("demo", help="open the interactive local agent console demo")
    demo.add_argument("--profile", default=str(DEFAULT_PROFILE_PATH), help="path to local CLI initialization profile")
    demo.add_argument("--skip-db-connect", action="store_true", help="show database configuration without opening a connection")

    review = subcommands.add_parser("review", help="review a plain text contract")
    review.add_argument("path", help="path to a UTF-8 text contract")
    review.add_argument("--type", dest="contract_type", default=None, help="contract type, e.g. purchase")
    review.add_argument("--side", dest="our_side", default="甲方", help="our side, e.g. buyer, seller, 甲方")
    review.add_argument("--format", choices=("markdown", "json"), default="markdown")

    subcommands.add_parser("config", help="print active model configuration")
    return parser


def _demo_command(args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    profile = Path(getattr(args, "profile", str(DEFAULT_PROFILE_PATH)))
    skip_db_connect = bool(getattr(args, "skip_db_connect", False))
    return run_console_demo(
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        profile_path=profile,
        skip_db_connect=skip_db_connect,
    )


def _review_command(args: argparse.Namespace, stdout: TextIO, stderr: TextIO) -> int:
    path = Path(args.path)
    if not path.exists():
        stderr.write(f"文件不存在：{path}\n")
        return 2
    if not path.is_file():
        stderr.write(f"不是文件：{path}\n")
        return 2

    text = path.read_text(encoding="utf-8-sig")
    report = review_text(text, contract_type=args.contract_type, our_side=args.our_side)
    if args.format == "json":
        stdout.write(render_json(report))
        stdout.write("\n")
    else:
        stdout.write(render_markdown(report))
    return 0


def _config_command(stdout: TextIO) -> int:
    stdout.write(f"provider={settings.llm_provider}\n")
    stdout.write(f"chat_model={settings.llm_chat_model}\n")
    stdout.write(f"embedding_model={settings.llm_embedding_model}\n")
    stdout.write(f"base_url={settings.llm_base_url or ''}\n")
    stdout.write(f"responses_api={settings.llm_use_responses_api}\n")
    return 0


def _prefer_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
