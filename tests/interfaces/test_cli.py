import io
import tempfile
import unittest
from pathlib import Path

from contract_agent.interfaces import cli
from contract_agent.interfaces.cli import main
from contract_agent.config import settings


class CliTests(unittest.TestCase):
    def test_review_command_prints_markdown_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("甲方应于合同签订后5日内支付100%合同价款。", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                ["review", str(path), "--type", "purchase", "--side", "buyer"],
                stdout=stdout,
                stderr=stderr,
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("合同校审报告", stdout.getvalue())
        self.assertIn("全额预付款", stdout.getvalue())
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
