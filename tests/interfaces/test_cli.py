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
                    "purchase",
                    "buyer",
                )
            ],
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["summary"]["risk_count"], 1)
        self.assertEqual(payload["report"]["overview"], "service review completed")

    def test_review_command_defaults_our_side_to_chinese_party_a(self):
        class FakeReviewService:
            calls = []

            def __init__(self, app_context=None):
                self.app_context = app_context

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
                exit_code = main(["review", str(path)], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeReviewService.calls[0][3], "甲方")
        self.assertNotEqual(FakeReviewService.calls[0][3], "鐢叉柟")

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

    def test_review_command_rejects_oversize_file_before_service_reads_it(self):
        class UnexpectedReviewService:
            def __init__(self, app_context=None):
                raise AssertionError("oversize file must be rejected before service construction")

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

    def test_console_command_reports_missing_frontend_build(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with (
            patch("contract_agent.interfaces.cli.CONSOLE_FRONTEND_ENTRY", Path("missing.js")),
            patch("contract_agent.interfaces.cli.CONSOLE_FRONTEND_SOURCE_DIR", Path("missing-src")),
        ):
            exit_code = main(["console"], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("React CLI 前端尚未构建", stderr.getvalue())
        self.assertIn("frontend/console", stderr.getvalue())

    def test_console_command_launches_frontend_when_build_exists(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / "cli.js"
            entry.write_text("console.log('ok')", encoding="utf-8")

            with (
                patch("contract_agent.interfaces.cli.CONSOLE_FRONTEND_ENTRY", entry),
                patch("contract_agent.interfaces.cli._run_console_frontend") as run_frontend,
            ):
                run_frontend.return_value = 0
                exit_code = main(
                    ["--config", "config.example.yaml", "console", "--profile", "profile.yaml"],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        run_frontend.assert_called_once()
        args = run_frontend.call_args.args[0]
        self.assertEqual(args.profile, "profile.yaml")
        self.assertEqual(args.config, "config.example.yaml")
        self.assertFalse(args.initconfig)

    def test_console_command_can_reinitialize_profile_before_launch(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / "cli.js"
            entry.write_text("console.log('ok')", encoding="utf-8")

            with (
                patch("contract_agent.interfaces.cli.CONSOLE_FRONTEND_ENTRY", entry),
                patch("contract_agent.interfaces.cli.run_config_initialization") as init_config,
                patch("contract_agent.interfaces.cli._run_console_frontend") as run_frontend,
            ):
                init_config.return_value = 0
                run_frontend.return_value = 0
                exit_code = main(
                    ["console", "--profile", "profile.yaml", "--initconfig"],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 0)
        init_config.assert_called_once()
        run_frontend.assert_called_once()
        self.assertEqual(run_frontend.call_args.args[0].profile, "profile.yaml")

    def test_console_command_stops_when_reinitialize_profile_fails(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / "cli.js"
            entry.write_text("console.log('ok')", encoding="utf-8")

            with (
                patch("contract_agent.interfaces.cli.CONSOLE_FRONTEND_ENTRY", entry),
                patch("contract_agent.interfaces.cli.run_config_initialization") as init_config,
                patch("contract_agent.interfaces.cli._run_console_frontend") as run_frontend,
            ):
                init_config.return_value = 2
                exit_code = main(
                    ["console", "--profile", "profile.yaml", "--initconfig"],
                    stdout=stdout,
                    stderr=stderr,
                )

        self.assertEqual(exit_code, 2)
        init_config.assert_called_once()
        run_frontend.assert_not_called()

    def test_console_command_uses_source_frontend_when_dist_is_missing(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "frontend" / "console"
            source_dir.mkdir(parents=True)
            (source_dir / "package.json").write_text("{}", encoding="utf-8")
            (source_dir / "node_modules").mkdir()

            with (
                patch(
                    "contract_agent.interfaces.cli.CONSOLE_FRONTEND_ENTRY", Path(tmp) / "dist.js"
                ),
                patch("contract_agent.interfaces.cli.CONSOLE_FRONTEND_SOURCE_DIR", source_dir),
                patch("contract_agent.interfaces.cli._run_console_frontend") as run_frontend,
            ):
                run_frontend.return_value = 0
                exit_code = main(["console"], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        args = run_frontend.call_args.args[0]
        self.assertEqual(args.frontend_mode, "source")

    def test_console_command_reports_missing_frontend_dependencies(self):
        stdout = io.StringIO()
        stderr = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "frontend" / "console"
            source_dir.mkdir(parents=True)
            (source_dir / "package.json").write_text("{}", encoding="utf-8")

            with (
                patch(
                    "contract_agent.interfaces.cli.CONSOLE_FRONTEND_ENTRY", Path(tmp) / "dist.js"
                ),
                patch("contract_agent.interfaces.cli.CONSOLE_FRONTEND_SOURCE_DIR", source_dir),
            ):
                exit_code = main(["console"], stdout=stdout, stderr=stderr)

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("React CLI 前端依赖尚未安装", stderr.getvalue())
        self.assertIn("npm install", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
