import unittest

from contract_agent.config import temporary_settings
from contract_agent.review.service import review_text


def _builtin_parser_settings():
    return {
        "parser_default_converter": "builtin",
        "parser_enabled_converters": ["builtin"],
        "parser_fallback_order": ["builtin"],
        "parser_docling_enabled": False,
    }


class ServiceTests(unittest.TestCase):
    def test_review_text_rejects_blank_contract(self):
        with self.assertRaises(ValueError) as exc:
            review_text("   ", contract_type="purchase")

        self.assertIn("合同正文为空", str(exc.exception))

    def test_missing_contract_type_does_not_default_to_procurement_rules(self):
        report = review_text(
            "甲方与乙方签订保密协议。双方承担保密义务。违约责任按实际损失赔偿。",
            contract_type=None,
            llm_client=None,
        )

        self.assertNotIn("ACC_001", [finding.rule_id for finding in report.findings])

    def test_reviews_contract_without_llm_configuration(self):
        with temporary_settings(**_builtin_parser_settings()):
            report = review_text(
                "甲方应于合同签订后5日内支付100%合同价款。",
                contract_type="purchase",
                our_side="buyer",
                llm_client=None,
            )

        self.assertFalse(report.llm_used)
        self.assertTrue(report.findings)
        self.assertIn("规则模式", report.warnings[0])

    def test_keeps_rule_report_when_llm_fails(self):
        class BrokenLlm:
            def enrich(self, request, findings):
                raise RuntimeError("network down")

        with temporary_settings(**_builtin_parser_settings()):
            report = review_text(
                "甲方应于合同签订后5日内支付100%合同价款。",
                contract_type="purchase",
                our_side="buyer",
                llm_client=BrokenLlm(),
            )

        self.assertFalse(report.llm_used)
        self.assertTrue(report.findings)
        self.assertIn("LLM 调用失败", report.warnings[0])


if __name__ == "__main__":
    unittest.main()
