from __future__ import annotations

import json
from dataclasses import asdict

from contract_agent.review.models import Finding, ReviewReport as LocalReviewReport, Severity
from contract_agent.schemas.review import ReviewReport as SchemaReviewReport


ReviewReport = LocalReviewReport | SchemaReviewReport


_SEVERITY_LABELS = {
    Severity.HIGH: "高风险",
    Severity.MEDIUM: "中风险",
    Severity.LOW: "低风险",
    Severity.INFO: "提示",
}


def render_markdown(report: ReviewReport) -> str:
    if isinstance(report, SchemaReviewReport):
        return _render_schema_markdown(report)
    if not isinstance(report, LocalReviewReport):
        raise TypeError("render_markdown 仅支持本地 ReviewReport 或 schemas.review.ReviewReport。")

    lines = ["# 合同校审报告", "", report.summary, ""]

    if report.warnings:
        lines.extend(["## 运行提示", ""])
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    if not report.findings:
        lines.extend(["## 风险发现", "", "暂未发现明确风险。", ""])
        return "\n".join(lines).rstrip() + "\n"

    for severity in (Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
        grouped = [finding for finding in report.findings if finding.severity == severity]
        if not grouped:
            continue
        lines.extend([f"## {_SEVERITY_LABELS[severity]}", ""])
        for finding in grouped:
            lines.extend(_render_finding(finding))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_json(report: ReviewReport) -> str:
    if isinstance(report, SchemaReviewReport):
        payload = report.model_dump(mode="json")
    elif isinstance(report, LocalReviewReport):
        payload = asdict(report)
    else:
        raise TypeError("render_json 仅支持本地 ReviewReport 或 schemas.review.ReviewReport。")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_schema_markdown(report: SchemaReviewReport) -> str:
    lines = ["# 合同校审报告", "", report.overview, ""]

    if report.key_findings:
        lines.extend(["## 关键发现", ""])
        lines.extend(f"- {finding}" for finding in report.key_findings)
        lines.append("")

    if report.next_actions:
        lines.extend(["## 下一步", ""])
        lines.extend(f"- {action}" for action in report.next_actions)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_finding(finding: Finding) -> list[str]:
    lines = [f"### {finding.title}"]
    if finding.clause:
        lines.append(f"- 位置：{finding.clause}")
    lines.extend(
        [
            f"- 证据：{finding.evidence}",
            f"- 原因：{finding.reason}",
            f"- 建议：{finding.suggestion}",
        ]
    )
    return lines
