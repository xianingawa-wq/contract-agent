from __future__ import annotations

import json
from dataclasses import asdict

from contract_agent.models import Finding, ReviewReport, Severity


_SEVERITY_LABELS = {
    Severity.HIGH: "高风险",
    Severity.MEDIUM: "中风险",
    Severity.LOW: "低风险",
    Severity.INFO: "提示",
}


def render_markdown(report: ReviewReport) -> str:
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
    return json.dumps(asdict(report), ensure_ascii=False, indent=2)


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

