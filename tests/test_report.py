import json
import unittest

from contract_agent.review.models import Finding, ReviewReport, Severity
from contract_agent.review.reporting import render_json, render_markdown


class ReportTests(unittest.TestCase):
    def test_renders_markdown_findings_grouped_by_severity(self):
        report = ReviewReport(
            summary="发现 1 个风险点。",
            findings=[
                Finding(
                    rule_id="payment.full_advance",
                    severity=Severity.HIGH,
                    title="全额预付款风险",
                    evidence="支付100%合同价款",
                    reason="买方资金和履约安全缺少保护。",
                    suggestion="建议改为分阶段付款，并设置验收条件。",
                )
            ],
            warnings=["未配置 LLM，已使用规则模式。"],
            llm_used=False,
        )

        markdown = render_markdown(report)

        self.assertIn("# 合同校审报告", markdown)
        self.assertIn("## 高风险", markdown)
        self.assertIn("全额预付款风险", markdown)
        self.assertIn("未配置 LLM", markdown)

    def test_renders_json_report(self):
        report = ReviewReport(summary="未发现明显风险。", findings=[], warnings=[], llm_used=False)

        payload = json.loads(render_json(report))

        self.assertEqual(payload["summary"], "未发现明显风险。")
        self.assertEqual(payload["findings"], [])
        self.assertFalse(payload["llm_used"])


if __name__ == "__main__":
    unittest.main()
