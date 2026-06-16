import io
import tempfile
import unittest
from pathlib import Path

from contract_agent.cli import main


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


if __name__ == "__main__":
    unittest.main()
