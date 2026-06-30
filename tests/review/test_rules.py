import unittest

from contract_agent.review.models import ReviewRequest, Severity
from contract_agent.review.rules import run_rules


class RuleTests(unittest.TestCase):
    def test_general_contract_runs_common_rules_once(self):
        request = ReviewRequest(
            text="保密协议正文。双方承担保密义务。",
            contract_type="general",
            our_side="buyer",
        )

        findings = run_rules(request)
        rule_ids = [finding.rule_id for finding in findings]

        self.assertIn("GEN_001", rule_ids)
        self.assertEqual(len(rule_ids), len(set(rule_ids)))

    def test_flags_full_advance_payment_for_buyer(self):
        request = ReviewRequest(
            text="第二条 付款方式：甲方应于合同签订后5日内支付100%合同价款。",
            contract_type="purchase",
            our_side="buyer",
        )

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

        findings = run_rules(request)

        titles = [finding.title for finding in findings]
        self.assertIn("争议管辖可能不利", titles)

    def test_missing_contract_type_runs_only_common_rules_for_non_purchase_text(self):
        request = ReviewRequest(
            text="保密协议正文。双方承担保密义务。",
            contract_type=None,
            our_side="buyer",
        )

        findings = run_rules(request)
        rule_ids = [finding.rule_id for finding in findings]

        self.assertIn("GEN_001", rule_ids)
        self.assertNotIn("ACC_001", rule_ids)


if __name__ == "__main__":
    unittest.main()
