import unittest
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from contract_agent.config import settings
from contract_agent.config import configure_runtime


class ConsoleBridgeTests(unittest.TestCase):
    def test_estimate_command_returns_token_count_for_text(self):
        from contract_agent.interfaces.console_bridge import handle_bridge_command

        result = handle_bridge_command("estimate", {"text": "abcd" * 3})

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["text_length"], 12)
        self.assertEqual(result["data"]["estimated_tokens"], 3)

    def test_config_command_masks_api_keys(self):
        from contract_agent.interfaces.console_bridge import handle_bridge_command

        original_settings = settings.model_dump()
        try:
            settings.chat_provider = "openai_compatible"
            settings.chat_base_url = "https://chat.example.test/v1"
            settings.chat_api_key = "chat-secret"
            settings.chat_model = "demo-chat"
            settings.embedding_api_key = ""
            settings.rerank_api_key = "rerank-secret"

            result = handle_bridge_command("config", {})
        finally:
            for key, value in original_settings.items():
                setattr(settings, key, value)

        self.assertTrue(result["ok"])
        data = result["data"]
        self.assertEqual(data["chat"]["model"], "demo-chat")
        self.assertTrue(data["chat"]["api_key_configured"])
        self.assertFalse(data["embedding"]["api_key_configured"])
        self.assertTrue(data["rerank"]["api_key_configured"])
        self.assertNotIn("chat-secret", str(result))
        self.assertNotIn("rerank-secret", str(result))

    def test_chat_command_returns_demo_reply_and_token_usage(self):
        from contract_agent.interfaces.console_bridge import handle_bridge_command

        result = handle_bridge_command("chat", {"message": "请总结这份合同"})

        self.assertTrue(result["ok"])
        data = result["data"]
        self.assertIn("请总结这份合同", data["reply"])
        self.assertGreater(data["usage"]["estimated_input_tokens"], 0)
        self.assertGreater(data["usage"]["estimated_output_tokens"], 0)
        self.assertGreater(data["usage"]["estimated_total_tokens"], 0)

    def test_unknown_command_returns_structured_error(self):
        from contract_agent.interfaces.console_bridge import handle_bridge_command

        result = handle_bridge_command("unknown", {})

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "unknown_command")
        self.assertIn("未知命令", result["error"]["message"])

    def test_review_command_identifies_pdf_ocr_memory_failure(self):
        from contract_agent.interfaces.console_bridge import handle_bridge_command

        class BrokenReviewService:
            def __init__(self, app_context=None):
                self.app_context = app_context

            def review_file(self, file_name, content, contract_type, our_side):
                raise RuntimeError(
                    "Stage preprocess failed for run 1, pages [2]: std::bad_alloc\n"
                    "ONNXRuntimeError: Status Message: bad allocation"
                )

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.pdf"
            path.write_bytes(b"%PDF-1.7")
            with patch("contract_agent.services.review_service.ReviewService", BrokenReviewService):
                result = handle_bridge_command(
                    "review",
                    {"path": str(path)},
                    configure_runtime(),
                )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "pdf_ocr_memory_exhausted")
        self.assertIn("PDF OCR", result["error"]["message"])
        self.assertIn("关闭 OCR", result["error"]["message"])
        self.assertIn("PARSER_DOCLING_ENABLE_OCR", result["error"]["message"])
        self.assertIn("PARSER_DOCLING_FORCE_FULL_PAGE_OCR", result["error"]["message"])
        self.assertIn("false", result["error"]["message"])

    def test_module_cli_writes_json_response(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "contract_agent.interfaces.console_bridge",
                "estimate",
                "--payload-json",
                '{"text":"abcd"}',
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["estimated_tokens"], 1)
        self.assertEqual(completed.stderr, "")

    def test_module_cli_chat_stdout_is_ascii_safe_for_node_bridge(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "contract_agent.interfaces.console_bridge",
                "chat",
                "--payload-json",
                json.dumps({"message": "dfdfdfd"}, ensure_ascii=False),
            ],
            check=False,
            capture_output=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(completed.stderr, b"")
        self.assertTrue(all(byte < 128 for byte in completed.stdout), completed.stdout)
        payload = json.loads(completed.stdout.decode("ascii"))
        self.assertEqual(
            payload["data"]["reply"],
            "演示回复：已收到“dfdfdfd”。可使用 /help 查看内置命令。",
        )

    def test_module_cli_applies_profile_from_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = os.path.join(tmp, "profile.yaml")
            with open(profile_path, "w", encoding="utf-8") as profile:
                profile.write(
                    """
chat:
  provider: openai_compatible
  base_url: https://chat.example.test/v1
  api_key: chat-secret
  model: profile-chat
embedding:
  provider: openai_compatible
  base_url: https://embedding.example.test/v1
  api_key: embedding-secret
  model: profile-embedding
rerank:
  provider: openai_compatible
  base_url: https://rerank.example.test/v1
  api_key: rerank-secret
  model: profile-rerank
"""
                )
            env = {**os.environ, "CONTRACT_AGENT_PROFILE": profile_path}

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "contract_agent.interfaces.console_bridge",
                    "config",
                ],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )

        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["data"]["chat"]["model"], "profile-chat")
        self.assertEqual(payload["data"]["embedding"]["model"], "profile-embedding")
        self.assertEqual(payload["data"]["rerank"]["model"], "profile-rerank")
        self.assertNotIn("chat-secret", completed.stdout)


if __name__ == "__main__":
    unittest.main()
