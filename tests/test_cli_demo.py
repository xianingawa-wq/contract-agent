import io
import json
import tempfile
import unittest
from pathlib import Path

from contract_agent.interfaces.cli import main


class CliDemoTests(unittest.TestCase):
    def test_demo_guides_first_time_model_configuration_and_enters_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            stdin = io.StringIO(
                "\n".join(
                    [
                        "openai_compatible",
                        "https://example.test/v1",
                        "demo-chat",
                        "demo-embedding",
                        "",
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
            self.assertIn("Model provider: openai_compatible", output)
            self.assertIn("Active model: demo-chat", output)
            self.assertIn("Agent console", output)
            self.assertIn("Initialized: yes", output)

            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertEqual(profile["provider"], "openai_compatible")
            self.assertEqual(profile["chat_model"], "demo-chat")

    def test_demo_reuses_existing_profile_and_handles_chat_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "provider": "openai_compatible",
                        "base_url": "https://example.test/v1",
                        "chat_model": "saved-chat",
                        "embedding_model": "saved-embedding",
                        "api_key_configured": False,
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
        self.assertIn("chat_model=saved-chat", output)


if __name__ == "__main__":
    unittest.main()
