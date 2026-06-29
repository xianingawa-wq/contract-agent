import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.convertor.builtin_parser_impl import BuiltinParserImpl
from contract_agent.parser.exception import DocumentLoadError
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.parser_backend_contract import ParserBackendSupport
from contract_agent.parser.parser_backend_router import ParserBackendRouter
from contract_agent.parser.parser_source import ParserSource


class ParserBackendRouterTests(unittest.TestCase):
    def test_default_router_uses_docling_backend_for_text(self):
        router = ParserBackendRouter.default()
        with (
            patch(
                "contract_agent.parser.convertor.docling_parser_impl.DoclingParserImpl.supports",
                return_value=ParserBackendSupport(
                    supported=True,
                    confidence=1.0,
                    reason="stubbed docling",
                ),
            ),
            patch(
                "contract_agent.parser.convertor.docling_parser_impl.DoclingParserImpl.convert",
                return_value=MarkdownDocument(
                    markdown_content="第一条 付款",
                    file_name="inline.txt",
                    file_type="txt",
                    source_path="inline.txt",
                    backend_name="docling",
                ),
            ),
        ):
            result = router.convert(
                ParserSource.from_text("第一条 付款", file_name="inline.txt"),
                ParserConfig(),
            )

        self.assertEqual(result.backend_name, "docling")
        self.assertEqual(result.markdown_content, "第一条 付款")

    def test_builtin_backend_does_not_claim_legacy_doc_support(self):
        support = BuiltinParserImpl().supports(
            ParserSource.from_bytes("legacy.doc", b"fake"),
            ParserConfig(allowed_suffixes=[".doc"]),
        )

        self.assertFalse(support.supported)

    def test_optional_backend_enabled_without_feature_flag_is_rejected_before_routing(self):
        with self.assertRaisesRegex(ValueError, "parser.markitdown_enabled"):
            ParserConfig(
                default_converter="markitdown",
                enabled_converters=["markitdown", "builtin"],
                fallback_order=["markitdown", "builtin"],
                markitdown_enabled=False,
            )

    def test_missing_default_optional_backend_raises_even_when_fallback_is_allowed(self):
        router = ParserBackendRouter.default()
        config = ParserConfig(
            default_converter="markitdown",
            enabled_converters=["markitdown", "builtin"],
            fallback_order=["markitdown", "builtin"],
            markitdown_enabled=True,
            strict_converter_availability=False,
        )

        with patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(DocumentLoadError):
                router.convert(
                    ParserSource.from_text("第一条 付款", file_name="inline.txt"),
                    config,
                )

    def test_default_backend_unavailable_does_not_fallback_when_fallback_disabled(self):
        router = ParserBackendRouter.default()
        missing = ParserConfig(
            default_converter="markitdown",
            enabled_converters=["markitdown", "builtin"],
            fallback_order=["markitdown", "builtin"],
            markitdown_enabled=True,
            allow_converter_fallback=False,
        )
        with patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(DocumentLoadError):
                router.convert(
                    ParserSource.from_text("第一条 付款", file_name="inline.txt"),
                    missing,
                )

    def test_default_backend_runtime_failure_raises_even_when_fallback_is_allowed(self):
        router = ParserBackendRouter([BrokenParserImpl(), BuiltinParserImpl()])
        config = ParserConfig(
            default_converter="broken",
            enabled_converters=["broken", "builtin"],
            fallback_order=["broken", "builtin"],
        )

        with self.assertRaisesRegex(DocumentLoadError, "broken backend failed"):
            router.convert(ParserSource.from_text("第一条 付款", file_name="inline.txt"), config)

    def test_path_input_rejects_missing_and_directory_before_backend_routing(self):
        with tempfile.TemporaryDirectory() as tmp:
            router = ParserBackendRouter([BuiltinParserImpl()])
            config = ParserConfig(
                default_converter="builtin",
                enabled_converters=["builtin"],
                fallback_order=["builtin"],
                allow_path_input=True,
                trusted_path_roots=[tmp],
            )

            missing = Path(tmp) / "missing.txt"
            with self.assertRaises(DocumentLoadError):
                router.convert(ParserSource.from_path(missing), config)

            directory = Path(tmp) / "directory.txt"
            directory.mkdir()
            with self.assertRaises(DocumentLoadError):
                router.convert(ParserSource.from_path(directory), config)


class BrokenParserImpl:
    name = "broken"

    def supports(self, source: ParserSource, config: ParserConfig) -> ParserBackendSupport:
        return ParserBackendSupport(supported=True, confidence=1.0, reason="test backend")

    def convert(self, source: ParserSource, config: ParserConfig) -> MarkdownDocument:
        raise DocumentLoadError("broken backend failed")


if __name__ == "__main__":
    unittest.main()
