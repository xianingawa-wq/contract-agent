import tempfile
import unittest
from pathlib import Path

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import (
    ContractParser,
    ParsedReviewInput,
    ReviewInputError,
    normalize_review_input,
)


class ReviewInputNormalizerTests(unittest.TestCase):
    def test_text_input_normalizes_to_parsed_review_input(self):
        normalized = normalize_review_input(
            contract_text="第一条 付款",
            contract_type="采购合同",
            our_side="甲方",
        )

        self.assertIsInstance(normalized, ParsedReviewInput)
        self.assertEqual(normalized.source_kind, "text")
        self.assertEqual(normalized.contract_text, "第一条 付款")
        self.assertEqual(normalized.document.raw_text, "第一条 付款")
        self.assertEqual(normalized.contract_type, "采购合同")
        self.assertEqual(normalized.our_side, "甲方")

    def test_file_bytes_input_normalizes_to_bytes_or_grpc_file(self):
        from_bytes = normalize_review_input(
            file_name="contract.txt",
            content="第一条 付款".encode("utf-8"),
        )
        from_grpc = normalize_review_input(
            file_name="contract.txt",
            content="第一条 付款".encode("utf-8"),
            source_kind="grpc_file",
        )

        self.assertEqual(from_bytes.source_kind, "bytes")
        self.assertEqual(from_bytes.contract_text, "第一条 付款")
        self.assertEqual(from_grpc.source_kind, "grpc_file")
        self.assertEqual(from_grpc.contract_text, "第一条 付款")

    def test_file_path_input_normalizes_to_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("第一条 付款", encoding="utf-8")

            normalized = normalize_review_input(
                file_path=path,
                parser=ContractParser(
                    parser_config=ParserConfig(
                        default_converter="builtin",
                        enabled_converters=["builtin"],
                        fallback_order=["builtin"],
                        allow_path_input=True,
                        trusted_path_roots=[tmp],
                    )
                ),
            )

        self.assertEqual(normalized.source_kind, "path")
        self.assertEqual(normalized.contract_text, "第一条 付款")

    def test_blank_text_does_not_shadow_file_path_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("Path body", encoding="utf-8")

            normalized = normalize_review_input(
                contract_text="   ",
                file_path=path,
                parser=ContractParser(
                    parser_config=ParserConfig(
                        default_converter="builtin",
                        enabled_converters=["builtin"],
                        fallback_order=["builtin"],
                        allow_path_input=True,
                        trusted_path_roots=[tmp],
                    )
                ),
            )

        self.assertEqual(normalized.source_kind, "path")
        self.assertEqual(normalized.contract_text, "Path body")

    def test_invalid_inputs_raise_review_input_error(self):
        cases = [
            {},
            {"contract_text": ""},
            {"contract_text": "text", "file_name": "a.txt", "content": b"text"},
            {"file_name": "a.txt"},
            {"content": b"text"},
            {"file_name": "a.txt", "content": b""},
            {"contract_text": "text", "source_kind": "bytes"},
            {"file_name": "a.txt", "content": b"text", "source_kind": "text"},
        ]

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ReviewInputError):
                    normalize_review_input(**kwargs)

    def test_grpc_file_kind_is_plain_bytes_input_boundary(self):
        normalized = normalize_review_input(
            file_name="contract.txt",
            content=b"Plain bytes",
            source_kind="grpc_file",
        )

        self.assertEqual(normalized.source_kind, "grpc_file")
        self.assertEqual(normalized.contract_text, "Plain bytes")

    def test_path_input_obeys_injected_parser_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "contract.txt"
            path.write_text("第一条 付款", encoding="utf-8")

            with self.assertRaises(ReviewInputError):
                normalize_review_input(
                    file_path=path,
                    parser=ContractParser(parser_config=ParserConfig(allow_path_input=False)),
                )


if __name__ == "__main__":
    unittest.main()
