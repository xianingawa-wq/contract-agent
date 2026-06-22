__all__ = [
    "Finding",
    "LLMEnricher",
    "ReviewReport",
    "ReviewRequest",
    "Severity",
    "normalize_contract_type",
    "normalize_side",
    "render_json",
    "render_markdown",
    "review_text",
    "run_rules",
]


def __getattr__(name: str):
    if name in {"Finding", "ReviewReport", "ReviewRequest", "Severity"}:
        from contract_agent.review.models import Finding, ReviewReport, ReviewRequest, Severity

        return {
            "Finding": Finding,
            "ReviewReport": ReviewReport,
            "ReviewRequest": ReviewRequest,
            "Severity": Severity,
        }[name]
    if name in {"render_json", "render_markdown"}:
        from contract_agent.review.reporting import render_json, render_markdown

        return {"render_json": render_json, "render_markdown": render_markdown}[name]
    if name in {"normalize_contract_type", "normalize_side", "run_rules"}:
        from contract_agent.review.rules import normalize_contract_type, normalize_side, run_rules

        return {
            "normalize_contract_type": normalize_contract_type,
            "normalize_side": normalize_side,
            "run_rules": run_rules,
        }[name]
    if name in {"LLMEnricher", "review_text"}:
        from contract_agent.review.service import LLMEnricher, review_text

        return {"LLMEnricher": LLMEnricher, "review_text": review_text}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
