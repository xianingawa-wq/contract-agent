import unittest

from contract_agent.interfaces import cli as new_cli
from contract_agent.interfaces import http as new_http


class InterfaceEntrypointTests(unittest.TestCase):
    def test_cli_main_is_canonical_entrypoint(self):
        self.assertTrue(callable(new_cli.main))

    def test_http_root_payload_stays_stable(self):
        payload = new_http.root()

        self.assertEqual(payload["service"], "agent-python")
        self.assertIn("Python app only keeps agent capabilities", payload["message"])


if __name__ == "__main__":
    unittest.main()
