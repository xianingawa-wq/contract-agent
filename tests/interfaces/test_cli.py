import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from contract_agent.config import settings
from contract_agent.interfaces import cli
from contract_agent.interfaces.cli import main
from contract_agent.schemas.review import (
    ExtractedFields,
    ReviewReport,
    ReviewResponse,
    ReviewSummary,
)


def make_review_response() -> ReviewResponse:
    return ReviewResponse(
        summary=ReviewSummary(
            contract_type="采购合同",
            overall_risk="high",
            risk_count=1,
        ),
        extracted_fields=ExtractedFields(contract_name="采购合同"),
        risks=[],
        report=ReviewReport(
            generated_at=datetime.now(timezone.utc),
            overview="服务层审查完成",
            key_findings=["发现付款风险"],
            next_actions=["补充验收后付款"],
        ),
    )


class CliTests(unittest.TestCase):
    def test_review_command_prints_markdown_report(self):
        class FakeReviewService:
            def __init__(self, app_context=None):
                self.app_context = app_context

            def review_file(self, file_name, content, contract_type, our_side):
                return make_review_response()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("甲方支付100%合同价款。", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                FakeReviewService,
            ):
                exit_code = main(
                    ["review", str(path), "--type", "purchase", "--side", "buyer"],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("合同审查报告", stdout.getvalue())
        self.assertIn("服务层审查完成", stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_review_command_rejects_missing_file(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = main(
            ["review", "missing.txt", "--type", "purchase", "--side", "buyer"],
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("文件不存在", stderr.getvalue())

    def test_review_command_uses_service_llm_chain_for_json_output(self):
        class FakeReviewService:
            instances = []

            def __init__(self, app_context=None):
                self.app_context = app_context
                self.calls = []
                FakeReviewService.instances.append(self)

            def review_file(self, file_name, content, contract_type, our_side):
                self.calls.append((file_name, content, contract_type, our_side))
                return make_review_response()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("甲方支付100%合同价款。", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                FakeReviewService,
            ):
                exit_code = main(
                    [
                        "review",
                        str(path),
                        "--type",
                        "采购合同",
                        "--side",
                        "甲方",
                        "--format",
                        "json",
                    ],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(len(FakeReviewService.instances), 1)
        self.assertEqual(
            FakeReviewService.instances[0].calls,
            [("contract.txt", "甲方支付100%合同价款。".encode("utf-8"), "采购合同", "甲方")],
        )
        self.assertIn('"risk_count":1', stdout.getvalue())
        self.assertIn("服务层审查完成", stdout.getvalue())

    def test_review_command_reports_service_failure_without_traceback(self):
        class BrokenReviewService:
            def __init__(self, app_context=None):
                self.app_context = app_context

            def review_file(self, file_name, content, contract_type, our_side):
                raise ValueError("embedding unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("甲方支付100%合同价款。", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                BrokenReviewService,
            ):
                exit_code = main(
                    ["review", str(path), "--type", "采购合同", "--side", "甲方"],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("审查失败：embedding unavailable", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_config_command_loads_local_profile_without_printing_keys(self):
        original_settings = settings.model_dump()
        original_profile_path = cli.DEFAULT_PROFILE_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = Path(tmp) / "profile.yaml"
                cli.DEFAULT_PROFILE_PATH = profile_path
                profile_path.write_text(
                    """
chat:
  provider: openai_compatible
  base_url: https://chat.example.test/v1
  api_key: chat-secret
  model: chat-model
embedding:
  provider: openai_compatible
  base_url: https://embedding.example.test/v1
  api_key: embedding-secret
  model: embedding-model
rerank:
  provider: openai_compatible
  base_url: https://rerank.example.test/v1
  api_key: rerank-secret
  model: rerank-model
""",
                    encoding="utf-8",
                )
                stdout = io.StringIO()
                stderr = io.StringIO()

                exit_code = main(["config"], stdout=stdout, stderr=stderr)

            output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn("chat.model=chat-model", output)
            self.assertIn("embedding.model=embedding-model", output)
            self.assertIn("rerank.model=rerank-model", output)
            self.assertIn("chat.api_key_configured=True", output)
            self.assertNotIn("chat-secret", output)
            self.assertNotIn("embedding-secret", output)
            self.assertNotIn("rerank-secret", output)
        finally:
            cli.DEFAULT_PROFILE_PATH = original_profile_path
            for key, value in original_settings.items():
                setattr(settings, key, value)


if __name__ == "__main__":
    unittest.main()
