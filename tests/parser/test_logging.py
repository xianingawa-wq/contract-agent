import unittest

from contract_agent.parser import ContractParser


class ParserLoggingTests(unittest.TestCase):
    def test_parser_logs_convert_and_detector_events_with_internal_prefixes(self):
        parser = ContractParser()

        with self.assertLogs("contract_agent.parser", level="INFO") as captured:
            parser.parse_text("Contract\n1.1 Payment", "inline.txt")

        messages = "\n".join(captured.output)
        self.assertIn("[Parser][Convert]", messages)
        self.assertIn("[Parser][Detector]", messages)
        self.assertIn("converter=builtin", messages)
        self.assertIn("results=", messages)
        self.assertNotIn("[Parser][Info]", messages)


if __name__ == "__main__":
    unittest.main()
