import io
import json
import tempfile
import unittest
from pathlib import Path

from contract_agent.interfaces.cli import main
from contract_agent.interfaces.console import _ask


class FlushTrackingStringIO(io.StringIO):
    def __init__(self):
        super().__init__()
        self.flush_count = 0

    def flush(self):
        self.flush_count += 1


class CliDemoTests(unittest.TestCase):
    def test_initialization_prompt_is_flushed_before_waiting_for_input(self):
        stdin = io.StringIO("\n")
        stdout = FlushTrackingStringIO()

        value = _ask(stdin, stdout, "Provider", "openai_compatible")

        self.assertEqual(value, "openai_compatible")
        self.assertGreater(stdout.flush_count, 0)

    def test_demo_guides_first_time_model_configuration_and_enters_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            stdin = io.StringIO(
                "\n".join(
                    [
                        "3",
                        "https://chat.example.test/v1",
                        "chat-secret",
                        "demo-chat",
                        "3",
                        "https://embedding.example.test/v1",
                        "embedding-secret",
                        "demo-embedding",
                        "3",
                        "https://rerank.example.test/v1",
                        "rerank-secret",
                        "demo-rerank",
                        "/status",
                        "/exit",
                    ]
                )
                + "\n"
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                ["demo", "--profile", str(profile_path), "--skip-db-connect"],
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
            )

            output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr.getvalue(), "")
            self.assertIn("CONTRACT AGENT", output)
            self.assertIn("Initialization wizard", output)
            self.assertIn("Database: skipped", output)
            self.assertIn("Chat provider: openai_compatible", output)
            self.assertIn("Embedding provider: openai_compatible", output)
            self.assertIn("Rerank provider: openai_compatible", output)
            self.assertIn("Active chat model: demo-chat", output)
            self.assertIn("Embedding model: demo-embedding", output)
            self.assertIn("Rerank model: demo-rerank", output)
            self.assertIn("Agent console", output)
            self.assertIn("Initialized: yes", output)

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(profile["chat"]["provider"], "openai_compatible")
            self.assertEqual(profile["chat"]["base_url"], "https://chat.example.test/v1")
            self.assertEqual(profile["chat"]["api_key"], "chat-secret")
            self.assertEqual(profile["chat"]["model"], "demo-chat")
            self.assertEqual(profile["embedding"]["base_url"], "https://embedding.example.test/v1")
            self.assertEqual(profile["embedding"]["api_key"], "embedding-secret")
            self.assertEqual(profile["embedding"]["model"], "demo-embedding")
            self.assertEqual(profile["rerank"]["base_url"], "https://rerank.example.test/v1")
            self.assertEqual(profile["rerank"]["api_key"], "rerank-secret")
            self.assertEqual(profile["rerank"]["model"], "demo-rerank")

    def test_demo_reuses_existing_profile_and_handles_chat_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "chat": {
                            "provider": "openai_compatible",
                            "base_url": "https://chat.example.test/v1",
                            "api_key": "saved-chat-key",
                            "model": "saved-chat",
                        },
                        "embedding": {
                            "provider": "openai_compatible",
                            "base_url": "https://embedding.example.test/v1",
                            "api_key": "saved-embedding-key",
                            "model": "saved-embedding",
                        },
                        "rerank": {
                            "provider": "openai_compatible",
                            "base_url": "https://rerank.example.test/v1",
                            "api_key": "saved-rerank-key",
                            "model": "saved-rerank",
                        },
                    }
                ),
                encoding="utf-8",
            )
            stdin = io.StringIO("hello agent\n/config\n/exit\n")
            stdout = io.StringIO()
            stderr = io.StringIO()

            exit_code = main(
                ["demo", "--profile", str(profile_path), "--skip-db-connect"],
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
            )

        output = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Profile: ready", output)
        self.assertNotIn("Initialization wizard", output)
        self.assertIn("Agent: demo reply", output)
        self.assertIn("chat.model=saved-chat", output)
        self.assertIn("embedding.model=saved-embedding", output)
        self.assertIn("rerank.model=saved-rerank", output)
        self.assertIn("chat.api_key_configured=True", output)
        self.assertNotIn("saved-chat-key", output)


if __name__ == "__main__":
    unittest.main()
