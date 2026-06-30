import unittest

from contract_agent.config import temporary_settings
from contract_agent.review.models import ReviewRequest, Severity
from contract_agent.review.rules import run_rules


def _builtin_parser_settings():
    return {
        "parser_default_converter": "builtin",
        "parser_enabled_converters": ["builtin"],
        "parser_fallback_order": ["builtin"],
        "parser_docling_enabled": False,
    }


class RuleTests(unittest.TestCase):
    def test_flags_full_advance_payment_for_buyer(self):
        request = ReviewRequest(
            text="第二条 付款方式：甲方应于合同签订后5日内支付100%合同价款。",
            contract_type="purchase",
            our_side="buyer",
        )

        with temporary_settings(**_builtin_parser_settings()):
            findings = run_rules(request)

        self.assertEqual(findings[0].severity, Severity.HIGH)
        self.assertIn("全额预付款", findings[0].title)
        self.assertIn("100%", findings[0].evidence)

    def test_flags_dispute_resolution_against_buyer(self):
        request = ReviewRequest(
            text="争议解决：双方同意由乙方所在地人民法院管辖。",
            contract_type="purchase",
            our_side="buyer",
        )

        with temporary_settings(**_builtin_parser_settings()):
            findings = run_rules(request)

        titles = [finding.title for finding in findings]
        self.assertIn("争议管辖可能不利", titles)


if __name__ == "__main__":
    unittest.main()
