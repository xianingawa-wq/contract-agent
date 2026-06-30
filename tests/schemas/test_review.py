import json
import unittest
from datetime import datetime, timezone

from contract_agent.schemas.review import RiskItem
from contract_agent.review.reporting import render_json, render_markdown
from contract_agent.schemas.review import ReviewReport as PydanticReviewReport


def make_risk_item(**overrides):
    payload = {
        "rule_id": "GEN_001",
        "title": "缺少合同主体信息",
        "severity": "high",
        "description": "合同通常应明确双方主体名称及身份信息。",
        "evidence": "合同全文未发现相关关键词。",
        "suggestion": "建议补充完整的合同主体名称。",
    }
    payload.update(overrides)
    return RiskItem(**payload)


class ReviewSchemaTests(unittest.TestCase):
    def test_risk_item_rejects_negative_page_and_offsets(self):
        invalid_locations = [
            {"page_no": -1},
            {"page_no": 0},
            {"start_offset": -5, "end_offset": 0},
            {"start_offset": 0, "end_offset": -1},
        ]

        for location in invalid_locations:
            with self.subTest(location=location):
                with self.assertRaises(ValueError):
                    make_risk_item(**location)

    def test_risk_item_keeps_offset_order_validation(self):
        with self.assertRaises(ValueError):
            make_risk_item(start_offset=10, end_offset=1)


class PydanticReviewReportRenderingTests(unittest.TestCase):
    def test_render_json_accepts_pydantic_review_report(self):
        report = PydanticReviewReport(
            generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            overview="服务层审查完成",
            key_findings=["缺少付款节点"],
            next_actions=["补充验收后付款条款"],
        )

        payload = render_json(report)
        data = json.loads(payload)
        self.assertEqual(data["overview"], report.overview)
        self.assertEqual(data["key_findings"], report.key_findings)
        self.assertEqual(data["next_actions"], report.next_actions)

        self.assertIn('"overview": "服务层审查完成"', payload)
        self.assertIn('"key_findings": [', payload)
        self.assertIn('"next_actions": [', payload)

    def test_render_markdown_accepts_pydantic_review_report(self):
        report = PydanticReviewReport(
            generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
            overview="服务层审查完成",
            key_findings=["缺少付款节点"],
            next_actions=["补充验收后付款条款"],
        )

        markdown = render_markdown(report)

        self.assertIn("# 合同校审报告", markdown)
        self.assertIn("服务层审查完成", markdown)
        self.assertIn("缺少付款节点", markdown)
        self.assertIn("补充验收后付款条款", markdown)


if __name__ == "__main__":
    unittest.main()
