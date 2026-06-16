import unittest

from contract_agent import cli as old_cli
from contract_agent import main as old_http
from contract_agent.interfaces import cli as new_cli
from contract_agent.interfaces import http as new_http


class InterfaceEntrypointTests(unittest.TestCase):
    def test_cli_root_path_reexports_interface_main(self):
        self.assertIs(old_cli.main, new_cli.main)

    def test_http_root_path_reexports_interface_app(self):
        self.assertIs(old_http.app, new_http.app)
        self.assertIs(old_http.root, new_http.root)

    def test_http_root_payload_stays_stable(self):
        payload = new_http.root()

        self.assertEqual(payload["service"], "agent-python")
        self.assertIn("Python app only keeps agent capabilities", payload["message"])


if __name__ == "__main__":
    unittest.main()
