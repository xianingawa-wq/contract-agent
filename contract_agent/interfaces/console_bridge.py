from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from contract_agent.config import AppContext, configure_runtime
from contract_agent.config import create_model_profile_service
from contract_agent.config import settings_snapshot
from contract_agent.schemas.review import ReviewResponse
from contract_agent.trace.tokens import TokenTrace, estimate_tokens


BridgeResult = dict[str, Any]


def handle_bridge_command(
    command: str, payload: dict[str, Any], app_context: AppContext | None = None
) -> BridgeResult:
    normalized = command.strip().lower()
    if normalized == "estimate":
        return _ok(_handle_estimate(payload))
    if normalized == "config":
        return _ok(_handle_config())
    if normalized == "status":
        return _ok(_handle_status())
    if normalized == "chat":
        return _ok(_handle_chat(payload))
    if normalized == "review":
        context = app_context or configure_runtime()
        return _handle_review(payload, context)
    return _error("unknown_command", f"未知命令：{command}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="contract-agent-console-bridge")
    parser.add_argument("command", help="bridge command")
    parser.add_argument("--payload-json", default="{}", help="JSON payload")
    parser.add_argument("--config", default=None, help="path to runtime YAML config")
    args = parser.parse_args(argv)

    try:
        payload = json.loads(args.payload_json)
        if not isinstance(payload, dict):
            raise ValueError("payload must be a JSON object")
    except Exception as exc:
        _write_json(_error("invalid_payload", f"请求载荷不是合法 JSON 对象：{exc}"))
        return 2

    try:
        context = configure_runtime(config_path=args.config)
        _apply_profile_from_environment()
        result = handle_bridge_command(args.command, payload, context)
    except Exception as exc:
        result = _error("bridge_failed", f"命令执行失败：{exc}")
    _write_json(result)
    return 0 if result.get("ok") else 1


def _handle_estimate(payload: dict[str, Any]) -> dict[str, Any]:
    text = payload.get("text", "")
    content = "" if text is None else str(text)
    return {
        "text_length": len(content),
        "estimated_tokens": estimate_tokens(content),
    }


def _apply_profile_from_environment() -> None:
    profile_path = os.environ.get("CONTRACT_AGENT_PROFILE")
    if not profile_path:
        return
    profile_service = create_model_profile_service(Path(profile_path))
    if profile_service.has_profile():
        profile_service.apply_to_settings(profile_service.load())


def _handle_config() -> dict[str, Any]:
    current = settings_snapshot()
    return {
        "chat": {
            "provider": current.chat_provider,
            "base_url": current.chat_base_url or "",
            "model": current.chat_model,
            "api_key_configured": bool(current.chat_api_key),
        },
        "embedding": {
            "provider": current.embedding_provider,
            "base_url": current.embedding_base_url or "",
            "model": current.embedding_model,
            "api_key_configured": bool(current.embedding_api_key),
        },
        "rerank": {
            "provider": current.rerank_provider,
            "base_url": current.rerank_base_url or "",
            "model": current.rerank_model,
            "api_key_configured": bool(current.rerank_api_key),
        },
        "responses_api": current.llm_use_responses_api,
    }


def _handle_status() -> dict[str, Any]:
    current = settings_snapshot()
    return {
        "initialized": True,
        "database": {
            "configured": bool(current.postgres_dsn),
            "state": "configured" if current.postgres_dsn else "missing",
        },
        "models": _handle_config(),
    }


def _handle_chat(payload: dict[str, Any]) -> dict[str, Any]:
    message = str(payload.get("message", "")).strip()
    trace = TokenTrace()
    trace.add_input("message", message)
    reply = f"演示回复：已收到“{message}”。可使用 /help 查看内置命令。"
    trace.add_output("reply", reply)
    return {
        "reply": reply,
        "usage": trace.summary().model_dump(),
    }


def _handle_review(payload: dict[str, Any], app_context: AppContext) -> BridgeResult:
    path_value = str(payload.get("path", "")).strip()
    if not path_value:
        return _error("missing_path", "请提供合同文件路径。")
    path = Path(path_value)
    if not path.exists():
        return _error("file_not_found", f"文件不存在：{path}")
    if not path.is_file():
        return _error("not_a_file", f"不是文件：{path}")
    try:
        from contract_agent.services.review_service import ReviewService

        response = ReviewService(app_context=app_context).review_file(
            path.name,
            path.read_bytes(),
            contract_type=payload.get("contract_type"),
            our_side=str(payload.get("our_side", "甲方")),
        )
    except Exception as exc:
        return _review_error(exc, path)
    return _ok(_review_summary(response))


def _review_summary(response: ReviewResponse) -> dict[str, Any]:
    return {
        "contract_type": response.summary.contract_type,
        "overall_risk": response.summary.overall_risk,
        "risk_count": response.summary.risk_count,
        "overview": response.report.overview,
        "key_findings": list(response.report.key_findings),
        "trace": response.trace.model_dump() if response.trace else None,
    }


def _review_error(exc: Exception, path: Path) -> BridgeResult:
    detail = str(exc)
    normalized = detail.lower()
    if path.suffix.lower() == ".pdf" and (
        "std::bad_alloc" in normalized
        or "bad allocation" in normalized
        or "onnxruntime" in normalized
    ):
        return _error(
            "pdf_ocr_memory_exhausted",
            "PDF OCR 内存不足，当前文件在 Docling/RapidOCR 解析时耗尽内存。"
            "PowerShell 可先关闭 OCR 后重试："
            '$env:PARSER_DOCLING_ENABLE_OCR="false"; '
            '$env:PARSER_DOCLING_FORCE_FULL_PAGE_OCR="false"。'
            "然后重新运行 contract-agent console，或把 PDF 拆分成较小文件后再审查。",
        )
    return _error("review_failed", "审查失败：服务暂不可用，请检查模型、知识库和解析配置。")


def _ok(data: dict[str, Any]) -> BridgeResult:
    return {"ok": True, "data": data}


def _error(code: str, message: str) -> BridgeResult:
    return {"ok": False, "error": {"code": code, "message": message}}


def _write_json(payload: BridgeResult) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
