from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from contract_agent.core.config import settings
from contract_agent.report import render_json, render_markdown
from contract_agent.service import review_text


def main(argv: list[str] | None = None, *, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    _prefer_utf8(stdout)
    _prefer_utf8(stderr)
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "review":
        return _review_command(args, stdout, stderr)
    if args.command == "config":
        return _config_command(stdout)

    parser.print_help(stdout)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contract-agent")
    subcommands = parser.add_subparsers(dest="command")

    review = subcommands.add_parser("review", help="review a plain text contract")
    review.add_argument("path", help="path to a UTF-8 text contract")
    review.add_argument("--type", dest="contract_type", default=None, help="contract type, e.g. purchase")
    review.add_argument("--side", dest="our_side", default="甲方", help="our side, e.g. buyer, seller, 甲方")
    review.add_argument("--format", choices=("markdown", "json"), default="markdown")

    subcommands.add_parser("config", help="print active model configuration")
    return parser


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
