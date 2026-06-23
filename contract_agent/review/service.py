from __future__ import annotations

from typing import Protocol

from contract_agent.review.models import Finding, ReviewReport, ReviewRequest
from contract_agent.review.rules import normalize_side, run_rules


class LLMEnricher(Protocol):
    def enrich(self, request: ReviewRequest, findings: list[Finding]) -> list[Finding] | None: ...


def review_text(
    text: str,
    *,
    contract_type: str | None = None,
    our_side: str = "甲方",
    llm_client: LLMEnricher | None = None,
) -> ReviewReport:
    request = ReviewRequest(
        text=text, contract_type=contract_type, our_side=normalize_side(our_side)
    )
    findings = run_rules(request)
    warnings: list[str] = []
    llm_used = False

    if llm_client is None:
        warnings.append("未配置 LLM，已使用规则模式生成校审结果。")
    else:
        try:
            enriched = llm_client.enrich(request, findings)
            if enriched is not None:
                findings = enriched
            llm_used = True
        except Exception as exc:
            warnings.append(f"LLM 调用失败，已保留规则模式结果：{exc}")

    return ReviewReport(
        summary=_summary(findings),
        findings=findings,
        warnings=warnings,
        llm_used=llm_used,
    )


def _summary(findings: list[Finding]) -> str:
    if not findings:
        return "未发现明显风险。"
    high = sum(1 for finding in findings if finding.severity == "high")
    medium = sum(1 for finding in findings if finding.severity == "medium")
    return f"发现 {len(findings)} 个风险点，其中高风险 {high} 个、中风险 {medium} 个。"
