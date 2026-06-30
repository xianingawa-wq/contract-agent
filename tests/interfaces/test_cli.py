import io
import json
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
            contract_type="purchase",
            overall_risk="high",
            risk_count=1,
        ),
        extracted_fields=ExtractedFields(contract_name="Demo Contract"),
        risks=[],
        report=ReviewReport(
            generated_at=datetime.now(timezone.utc),
            overview="service review completed",
            key_findings=["payment risk found"],
            next_actions=["add acceptance-based payment term"],
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
            path.write_text("buyer pays 100 percent upfront.", encoding="utf-8")
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
        self.assertIn("service review completed", stdout.getvalue())
        self.assertIn("payment risk found", stdout.getvalue())
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
            path.write_text("buyer pays 100 percent upfront.", encoding="utf-8")
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
                        "purchase",
                        "--side",
                        "buyer",
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
            [
                (
                    "contract.txt",
                    "buyer pays 100 percent upfront.".encode("utf-8"),
                    "采购合同",
                    "甲方",
                )
            ],
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["summary"]["risk_count"], 1)
        self.assertEqual(payload["report"]["overview"], "service review completed")

    def test_review_command_accepts_config_after_subcommand(self):
        class UnexpectedReviewService:
            def __init__(self, app_context=None):
                self.app_context = app_context

            def review_file(self, file_name, content, contract_type, our_side):
                raise AssertionError("oversize file must be rejected before review service")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "contract.txt"
            path.write_text("123456789", encoding="utf-8")
            config_path = root / "config.yaml"
            config_path.write_text("limits:\n  max_upload_size_bytes: 4\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                UnexpectedReviewService,
            ):
                exit_code = main(
                    ["review", str(path), "--config", str(config_path)],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("文件大小超过限制", stderr.getvalue())

    def test_review_command_passes_chinese_defaults_and_aliases_to_service(self):
        class FakeReviewService:
            instances = []

            def __init__(self, app_context=None):
                self.calls = []
                FakeReviewService.instances.append(self)

            def review_file(self, file_name, content, contract_type, our_side):
                self.calls.append((contract_type, our_side))
                return make_review_response()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default_path = root / "default.txt"
            alias_path = root / "alias.txt"
            seller_path = root / "seller.txt"
            default_path.write_text("合同正文", encoding="utf-8")
            alias_path.write_text("合同正文", encoding="utf-8")
            seller_path.write_text("合同正文", encoding="utf-8")

            with patch(
                "contract_agent.services.review_service.ReviewService",
                FakeReviewService,
            ):
                default_code = main(
                    ["review", str(default_path)],
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
                buyer_code = main(
                    ["review", str(alias_path), "--type", "purchase", "--side", "buyer"],
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )
                seller_code = main(
                    ["review", str(seller_path), "--type", "general", "--side", "seller"],
                    stdout=io.StringIO(),
                    stderr=io.StringIO(),
                )

        self.assertEqual(default_code, 0)
        self.assertEqual(buyer_code, 0)
        self.assertEqual(seller_code, 0)
        calls = [instance.calls[0] for instance in FakeReviewService.instances]
        self.assertEqual(calls[0], (None, "甲方"))
        self.assertEqual(calls[1], ("采购合同", "甲方"))
        self.assertEqual(calls[2], ("通用合同", "乙方"))

    def test_review_command_passes_gbk_contract_bytes_without_unhandled_decode_error(self):
        class FakeReviewService:
            instances = []

            def __init__(self, app_context=None):
                self.calls = []
                FakeReviewService.instances.append(self)

            def review_file(self, file_name, content, contract_type, our_side):
                self.calls.append(content)
                return make_review_response()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbk_contract.txt"
            content = "甲方与乙方签订采购合同。".encode("gbk")
            path.write_bytes(content)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                FakeReviewService,
            ):
                exit_code = main(["review", str(path)], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(FakeReviewService.instances[0].calls[0], content)

    def test_review_command_parses_gbk_txt_without_docling_traceback(self):
        from contract_agent.services.review_service import ReviewService as RealReviewService

        class ParserOnlyReviewService(RealReviewService):
            documents = []

            def review_document(self, document, contract_type, our_side):
                self.__class__.documents.append(document)
                return make_review_response()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gbk_contract.txt"
            path.write_bytes("甲方与乙方签订采购合同。".encode("gbk"))
            stdout = io.StringIO()
            stderr = io.StringIO()
            process_stderr = io.StringIO()

            with (
                patch(
                    "contract_agent.services.review_service.ReviewService",
                    ParserOnlyReviewService,
                ),
                patch("sys.stderr", process_stderr),
            ):
                exit_code = main(["review", str(path)], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        self.assertNotIn("Traceback", process_stderr.getvalue())
        self.assertNotIn("UnicodeDecodeError", process_stderr.getvalue())
        self.assertIn("甲方与乙方签订采购合同", ParserOnlyReviewService.documents[0].raw_text)

    def test_review_command_reports_service_failure_without_traceback(self):
        class BrokenReviewService:
            def __init__(self, app_context=None):
                self.app_context = app_context

            def review_file(self, file_name, content, contract_type, our_side):
                raise ValueError("embedding unavailable")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("buyer pays 100 percent upfront.", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                BrokenReviewService,
            ):
                exit_code = main(
                    ["review", str(path), "--type", "purchase", "--side", "buyer"],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("审查失败", stderr.getvalue())
        self.assertNotIn("embedding unavailable", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_review_command_reports_parser_input_error_without_traceback(self):
        class BadInputReviewService:
            def __init__(self, app_context=None):
                self.app_context = app_context

            def review_file(self, file_name, content, contract_type, our_side):
                from contract_agent.parser import DocumentParseError

                raise DocumentParseError("文件正文为空，无法形成有效解析结果。")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.txt"
            path.write_text("   \n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                BadInputReviewService,
            ):
                exit_code = main(["review", str(path)], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("输入文件无法审查", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_review_command_rejects_oversize_file_before_service_reads_it(self):
        class UnexpectedReviewService:
            def __init__(self, app_context=None):
                self.app_context = app_context

            def review_file(self, file_name, content, contract_type, our_side):
                raise AssertionError("oversize file must be rejected before review service")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "contract.txt"
            path.write_text("123456789", encoding="utf-8")
            config_path = root / "config.yaml"
            config_path.write_text(
                "limits:\n  max_upload_size_bytes: 4\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "contract_agent.services.review_service.ReviewService",
                UnexpectedReviewService,
            ):
                exit_code = main(
                    ["--config", str(config_path), "review", str(path)],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("文件大小超过限制", stderr.getvalue())

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

    def test_config_command_uses_profile_path_from_config_without_default_profile_override(self):
        original_settings = settings.model_dump()
        original_profile_path = cli.DEFAULT_PROFILE_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                configured_profile = root / "configured_profile.yaml"
                default_profile = root / "default_profile.yaml"
                config_path = root / "config.yaml"
                configured_profile.write_text(
                    """
chat:
  model: configured-chat
""",
                    encoding="utf-8",
                )
                default_profile.write_text(
                    """
chat:
  model: default-chat
""",
                    encoding="utf-8",
                )
                config_path.write_text(
                    f"profile:\n  path: {configured_profile.as_posix()}\n",
                    encoding="utf-8",
                )
                cli.DEFAULT_PROFILE_PATH = default_profile
                stdout = io.StringIO()
                stderr = io.StringIO()

                exit_code = main(
                    ["--config", str(config_path), "config"],
                    stdout=stdout,
                    stderr=stderr,
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn("chat.model=configured-chat", stdout.getvalue())
            self.assertNotIn("chat.model=default-chat", stdout.getvalue())
        finally:
            cli.DEFAULT_PROFILE_PATH = original_profile_path
            for key, value in original_settings.items():
                setattr(settings, key, value)

    def test_config_command_reports_corrupt_profile_without_silent_fallback(self):
        original_profile_path = cli.DEFAULT_PROFILE_PATH
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile_path = Path(tmp) / "profile.yaml"
                profile_path.write_text(
                    "chat:\n  model: broken\n    bad-indent: true\n",
                    encoding="utf-8",
                )
                cli.DEFAULT_PROFILE_PATH = profile_path
                stdout = io.StringIO()
                stderr = io.StringIO()

                exit_code = main(["config"], stdout=stdout, stderr=stderr)

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("CLI profile", stderr.getvalue())
            self.assertIn("profile.yaml", stderr.getvalue())
        finally:
            cli.DEFAULT_PROFILE_PATH = original_profile_path


if __name__ == "__main__":
    unittest.main()
