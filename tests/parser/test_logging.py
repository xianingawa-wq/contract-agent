import unittest

from contract_agent.parser import ContractParser


class ParserLoggingTests(unittest.TestCase):
    def test_parser_logs_service_router_backend_chunk_and_output_events(self):
        parser = ContractParser()

        with self.assertLogs("contract_agent.parser", level="INFO") as captured:
            parser.parse_text("Contract\n1.1 Payment", "inline.txt")

        messages = "\n".join(captured.output)
        self.assertIn("[Parser][Service]", messages)
        self.assertIn("[Parser][Router]", messages)
        self.assertIn("[Parser][Chunk]", messages)
        self.assertIn("[Parser][Output]", messages)
        self.assertIn("backend=docling", messages)
        self.assertIn("chunks=", messages)
        self.assertNotIn("[Parser][Detector]", messages)
        self.assertNotIn("[Parser][Info]", messages)


if __name__ == "__main__":
    unittest.main()
