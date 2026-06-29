import unittest

from contract_agent.parser import ContractParser
from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.parser_source import ParserSource


class ParserLoggingTests(unittest.TestCase):
    def test_parser_logs_service_router_backend_chunk_and_output_events(self):
        parser = ContractParser(
            parser_config=ParserConfig(
                default_converter="builtin",
                enabled_converters=["builtin"],
                fallback_order=["builtin"],
            )
        )

        with self.assertLogs("contract_agent.parser", level="INFO") as captured:
            parser.parse_text("Contract\n1.1 Payment", "inline.txt")

        messages = "\n".join(captured.output)
        self.assertIn("[Parser][Service]", messages)
        self.assertIn("[Parser][Router]", messages)
        self.assertIn("[Parser][Chunk]", messages)
        self.assertIn("[Parser][Output]", messages)
        self.assertIn("backend=builtin", messages)
        self.assertIn("chunks=", messages)
        self.assertNotIn("[Parser][Detector]", messages)
        self.assertNotIn("[Parser][Info]", messages)

    def test_parser_logs_redact_untrusted_source_paths(self):
        parser = ContractParser(
            parser_config=ParserConfig(
                default_converter="builtin",
                enabled_converters=["builtin"],
                fallback_order=["builtin"],
            )
        )
        source = ParserSource.from_text(
            "Contract\n1.1 Payment",
            file_name="unsafe\nsecret/path/contract.txt",
        )
        source.source_path = "C:/secret/customer\ncontract.txt"

        with self.assertLogs("contract_agent.parser", level="INFO") as captured:
            parser.convert_to_markdown(source)

        messages = "\n".join(captured.output)
        self.assertIn("source=contract.txt", messages)
        self.assertNotIn("C:/secret", messages)
        self.assertNotIn("customer\ncontract", messages)


if __name__ == "__main__":
    unittest.main()
