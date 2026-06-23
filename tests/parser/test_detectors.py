import tempfile
import unittest
from pathlib import Path

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import ContractParser
from contract_agent.parser.detectors import DetectorRegistry, RuleRegistry


class ParserDetectorTests(unittest.TestCase):
    def test_metadata_detector_outputs_explainable_results_and_projects_to_metadata(self):
        document = ContractParser().parse_text(
            "\n".join(
                [
                    "采购合同",
                    "甲方：北京甲方科技有限公司",
                    "乙方：上海乙方服务有限公司",
                    "签署日期：2026年6月23日",
                    "第一条 付款",
                    "甲方应支付价款。",
                ]
            )
        )

        result_types = {result.result_type for result in document.detector_results}
        self.assertIn("metadata.title", result_types)
        self.assertIn("metadata.party", result_types)
        self.assertIn("metadata.signed_date", result_types)
        self.assertIn("metadata.contract_type_hint", result_types)
        self.assertTrue(all(result.confidence >= 0.6 for result in document.detector_results))
        self.assertTrue(all(result.reason for result in document.detector_results))
        self.assertEqual(document.metadata.title, "采购合同")
        self.assertEqual(document.metadata.party_a, "北京甲方科技有限公司")
        self.assertEqual(document.metadata.party_b, "上海乙方服务有限公司")
        self.assertEqual(document.metadata.signed_date, "2026年6月23日")
        self.assertEqual(document.metadata.contract_type_hint, "采购合同")

    def test_clause_definition_and_reference_detectors_return_structured_candidates(self):
        document = ContractParser().parse_text(
            "\n".join(
                [
                    "服务合同",
                    "第一条 定义",
                    "本合同所称服务，是指乙方提供的软件运维服务。",
                    "第二条 付款",
                    "付款安排见第一条及附件一。",
                    "（一）支付方式",
                    "银行转账。",
                ]
            )
        )

        clause_results = [
            result
            for result in document.detector_results
            if result.detector_name == "clause_header"
        ]
        self.assertGreaterEqual(len(clause_results), 3)
        self.assertEqual(clause_results[0].value["clause_no"], "第一条")
        self.assertEqual(clause_results[0].value["level"], "clause")
        self.assertTrue(document.definitions)
        self.assertTrue(document.references)

    def test_external_rule_path_overrides_builtin_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.yaml"
            path.write_text(
                "\n".join(
                    [
                        "rules:",
                        "  - rule_id: metadata.contract_type.purchase.v1",
                        "    detector_name: metadata",
                        "    keywords: ['采购']",
                        "    confidence: 0.91",
                        "    reason_template: '外部采购规则'",
                        "    metadata:",
                        "      result_type: metadata.contract_type_hint",
                        "      contract_type_hint: 外部采购合同",
                    ]
                ),
                encoding="utf-8",
            )

            registry = DetectorRegistry.default(
                ParserConfig(detector_rules_path=str(path), min_detector_confidence=0.6)
            )
            document = ContractParser(detector_registry=registry).parse_text(
                "采购合同\n第一条 付款"
            )

        self.assertEqual(document.metadata.contract_type_hint, "外部采购合同")

    def test_invalid_external_rule_detector_name_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.yaml"
            path.write_text(
                "\n".join(
                    [
                        "rules:",
                        "  - rule_id: bad.v1",
                        "    detector_name: unknown",
                        "    reason_template: bad",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                RuleRegistry.from_config(ParserConfig(detector_rules_path=str(path)))


if __name__ == "__main__":
    unittest.main()
