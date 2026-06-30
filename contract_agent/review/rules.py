from __future__ import annotations

from contract_agent.review.models import Finding, ReviewRequest, Severity
from contract_agent.parser import ContractParser
from contract_agent.services.rule_engine import RuleEngine


_COMMON_CONTRACT_TYPE = "通用合同"
_RULE_ENGINE_COMMON_ONLY_TYPE = "__common_only__"

_CONTRACT_TYPE_ALIASES = {
    "purchase": "采购合同",
    "procurement": "采购合同",
    "general": _COMMON_CONTRACT_TYPE,
}

_SIDE_ALIASES = {
    "buyer": "甲方",
    "seller": "乙方",
    "party_a": "甲方",
    "party_b": "乙方",
}


def normalize_contract_type(contract_type: str | None) -> str:
    if not contract_type:
        return _COMMON_CONTRACT_TYPE
    normalized = contract_type.strip()
    if not normalized:
        return _COMMON_CONTRACT_TYPE
    return _CONTRACT_TYPE_ALIASES.get(normalized.lower(), normalized)


def normalize_side(our_side: str | None) -> str:
    if not our_side:
        return "甲方"
    return _SIDE_ALIASES.get(our_side.strip().lower(), our_side)


def run_rules(request: ReviewRequest) -> list[Finding]:
    parser = ContractParser()
    document = parser.parse_text(request.text)
    contract_type = normalize_contract_type(request.contract_type)
    engine_contract_type = (
        _RULE_ENGINE_COMMON_ONLY_TYPE if contract_type == _COMMON_CONTRACT_TYPE else contract_type
    )
    risks = RuleEngine().check(engine_contract_type, document)

    findings = [
        Finding(
            rule_id=risk.rule_id,
            severity=Severity(risk.severity),
            title=risk.title,
            evidence=risk.evidence,
            reason=risk.ai_explanation or risk.description,
            suggestion=risk.suggestion,
            clause=risk.clause_no or risk.section_title,
            domain=risk.risk_domain,
        )
        for risk in risks
    ]
    return _with_cli_compatibility_findings(request, findings)


def _with_cli_compatibility_findings(
    request: ReviewRequest, findings: list[Finding]
) -> list[Finding]:
    text = request.text
    titles = {finding.title for finding in findings}

    if ("100%" in text or "全额" in text) and "全额预付款风险" not in titles:
        findings.insert(
            0,
            Finding(
                rule_id="payment.full_advance",
                severity=Severity.HIGH,
                title="全额预付款风险",
                evidence=_line_with(text, ["100%", "全额", "预付款"]) or text[:120],
                reason="买方资金和履约安全缺少保护。",
                suggestion="建议改为分阶段付款，并设置验收、质保金或履约担保条件。",
                domain="付款",
            ),
        )

    if "乙方所在地人民法院" in text and "争议管辖可能不利" not in titles:
        findings.append(
            Finding(
                rule_id="jurisdiction.counterparty_forum",
                severity=Severity.MEDIUM,
                title="争议管辖可能不利",
                evidence=_line_with(text, ["乙方所在地人民法院"]) or "乙方所在地人民法院",
                reason="由对方所在地法院管辖会增加我方维权成本。",
                suggestion="建议约定我方所在地法院、仲裁机构，或采用更中立的争议解决方式。",
                domain="争议解决",
            )
        )

    return findings


def _line_with(text: str, keywords: list[str]) -> str | None:
    for line in text.splitlines():
        if any(keyword in line for keyword in keywords):
            return line.strip()
    return None
