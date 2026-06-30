from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from contract_agent.interfaces.console import run_console_demo
from contract_agent.interfaces.console_paths import DEFAULT_PROFILE_PATH
from contract_agent.config import (
    AppContext,
    ParserConfig,
    ProfileLoadError,
    configure_runtime,
    create_model_profile_service,
)
from contract_agent.config import settings_snapshot
from contract_agent.schemas.review import ReviewResponse


_CONTRACT_TYPE_ALIASES = {
    "purchase": "采购合同",
    "procurement": "采购合同",
    "general": "通用合同",
}
_SIDE_ALIASES = {
    "buyer": "甲方",
    "seller": "乙方",
    "party_a": "甲方",
    "party_b": "乙方",
}


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
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    try:
        app_context = configure_runtime(config_path=getattr(args, "config", None))
        if args.command not in {None, "demo"} and getattr(args, "config", None) is None:
            _load_default_profile_if_present()
    except (OSError, ValueError, ProfileLoadError) as exc:
        stderr.write(f"{exc}\n")
        return 2

    if args.command in {None, "demo"}:
        return _demo_command(args, stdin, stdout, stderr)
    if args.command == "review":
        return _review_command(args, stdout, stderr, app_context)
    if args.command == "config":
        return _config_command(stdout)

    parser.print_help(stdout)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contract-agent")
    _add_config_argument(parser)
    subcommands = parser.add_subparsers(dest="command")

    demo = subcommands.add_parser("demo", help="open the interactive local agent console demo")
    _add_config_argument(demo)
    demo.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE_PATH),
        help="path to local CLI initialization profile",
    )
    demo.add_argument(
        "--skip-db-connect",
        action="store_true",
        help="show database configuration without opening a connection",
    )

    review = subcommands.add_parser("review", help="review a plain text contract")
    _add_config_argument(review)
    review.add_argument("path", help="path to a text contract")
    review.add_argument(
        "--type", dest="contract_type", default=None, help="contract type, e.g. purchase"
    )
    review.add_argument(
        "--side", dest="our_side", default="甲方", help="our side, e.g. buyer, seller, 甲方"
    )
    review.add_argument("--format", choices=("markdown", "json"), default="markdown")

    config = subcommands.add_parser("config", help="print active model configuration")
    _add_config_argument(config)
    return parser


def _add_config_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=argparse.SUPPRESS,
        help="path to runtime YAML config",
    )


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


def _review_command(
    args: argparse.Namespace, stdout: TextIO, stderr: TextIO, app_context: AppContext
) -> int:
    path = Path(args.path)
    if not path.exists():
        stderr.write(f"文件不存在：{path}\n")
        return 2
    if not path.is_file():
        stderr.write(f"不是文件：{path}\n")
        return 2

    from contract_agent.services.review_service import ReviewService

    try:
        service = ReviewService(app_context=app_context)
        if hasattr(service, "parser_config"):
            service.parser_config = _parser_config_for_cli_review(path, app_context)
        max_input_bytes = app_context.parser_config.max_input_bytes
        if max_input_bytes is not None and path.stat().st_size > max_input_bytes:
            stderr.write(f"文件大小超过限制：{max_input_bytes} bytes\n")
            return 2
        response = service.review_file(
            path.name,
            path.read_bytes(),
            contract_type=_normalize_contract_type_arg(args.contract_type),
            our_side=_normalize_side_arg(args.our_side),
        )
    except _parser_error_types() as exc:
        stderr.write(f"输入文件无法审查：{exc}\n")
        return 2
    except Exception as exc:
        from contract_agent.parser import ParserError

        if isinstance(exc, ParserError):
            stderr.write(f"输入文件无法审查：{exc}\n")
            return 2
        stderr.write("审查失败：服务暂不可用，请检查模型和知识库配置。\n")
        return 1

    if args.format == "json":
        stdout.write(response.model_dump_json())
        stdout.write("\n")
    else:
        stdout.write(_render_service_review_markdown(response))
    return 0


def _render_service_review_markdown(response: ReviewResponse) -> str:
    lines = [
        "# 合同审查报告",
        "",
        f"- 合同类型：{response.summary.contract_type}",
        f"- 整体风险：{response.summary.overall_risk}",
        f"- 风险数量：{response.summary.risk_count}",
        "",
        "## 审查概览",
        "",
        response.report.overview,
        "",
    ]

    if response.report.key_findings:
        lines.extend(["## 关键发现", ""])
        lines.extend(f"- {finding}" for finding in response.report.key_findings)
        lines.append("")

    extracted_fields = response.extracted_fields.model_dump(exclude_none=True)
    if extracted_fields:
        lines.extend(["## 抽取信息", ""])
        for key, value in extracted_fields.items():
            lines.append(f"- {key}: {value}")
        lines.append("")

    lines.extend(["## 风险发现", ""])
    if response.risks:
        for risk in response.risks:
            lines.extend(
                [
                    f"### {risk.title}",
                    f"- 等级：{risk.severity}",
                    f"- 证据：{risk.evidence}",
                    f"- 说明：{risk.ai_explanation or risk.description}",
                    f"- 建议：{risk.suggestion}",
                    "",
                ]
            )
    else:
        lines.extend(["暂未发现明确风险。", ""])

    if response.report.next_actions:
        lines.extend(["## 下一步", ""])
        lines.extend(f"- {action}" for action in response.report.next_actions)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _normalize_contract_type_arg(contract_type: str | None) -> str | None:
    if contract_type is None:
        return None
    normalized = contract_type.strip()
    if not normalized:
        return None
    return _CONTRACT_TYPE_ALIASES.get(normalized.lower(), normalized)


def _normalize_side_arg(our_side: str | None) -> str:
    if our_side is None:
        return "甲方"
    normalized = our_side.strip()
    if not normalized:
        return "甲方"
    return _SIDE_ALIASES.get(normalized.lower(), normalized)


def _parser_config_for_cli_review(path: Path, app_context: AppContext) -> ParserConfig:
    parser_config = app_context.parser_config
    if path.suffix.lower() != ".txt":
        return parser_config
    data = parser_config.model_dump()
    data["default_converter"] = "builtin"
    data["enabled_converters"] = _prepend_unique("builtin", parser_config.enabled_converters)
    data["fallback_order"] = _prepend_unique("builtin", parser_config.fallback_order)
    return ParserConfig.model_validate(data)


def _prepend_unique(item: str, values: list[str]) -> list[str]:
    result = [item]
    result.extend(value for value in values if value != item)
    return result


def _parser_error_types() -> tuple[type[Exception], ...]:
    from contract_agent.parser import ParserError, ReviewInputError

    return (ParserError, ReviewInputError)


def _config_command(stdout: TextIO) -> int:
    current = settings_snapshot()
    stdout.write(f"chat.provider={current.chat_provider}\n")
    stdout.write(f"chat.base_url={current.chat_base_url or ''}\n")
    stdout.write(f"chat.model={current.chat_model}\n")
    stdout.write(f"chat.api_key_configured={bool(current.chat_api_key)}\n")
    stdout.write(f"embedding.provider={current.embedding_provider}\n")
    stdout.write(f"embedding.base_url={current.embedding_base_url or ''}\n")
    stdout.write(f"embedding.model={current.embedding_model}\n")
    stdout.write(f"embedding.api_key_configured={bool(current.embedding_api_key)}\n")
    stdout.write(f"rerank.provider={current.rerank_provider}\n")
    stdout.write(f"rerank.base_url={current.rerank_base_url or ''}\n")
    stdout.write(f"rerank.model={current.rerank_model}\n")
    stdout.write(f"rerank.api_key_configured={bool(current.rerank_api_key)}\n")
    stdout.write(f"responses_api={current.llm_use_responses_api}\n")
    return 0


def _load_default_profile_if_present() -> None:
    profile_service = create_model_profile_service(DEFAULT_PROFILE_PATH)
    if profile_service.has_profile():
        profile_service.apply_to_settings(profile_service.load())


def _prefer_utf8(stream: TextIO) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
