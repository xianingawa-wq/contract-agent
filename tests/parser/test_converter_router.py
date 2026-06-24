import unittest
from unittest.mock import patch

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ConversionResult, ConverterSupport, ParseSource
from contract_agent.parser.converters.builtin import BuiltinConverter
from contract_agent.parser.converters.router import ConverterRouter
from contract_agent.parser.exceptions import DocumentLoadError


class ConverterRouterTests(unittest.TestCase):
    def test_default_router_uses_builtin_converter_for_text(self):
        router = ConverterRouter.default()
        result = router.convert(
            ParseSource.from_text("第一条 付款", file_name="inline.txt"),
            ParserConfig(),
        )

        self.assertEqual(result.converter_name, "builtin")
        self.assertEqual(result.document.raw_text, "第一条 付款")
        self.assertTrue(result.document.blocks)

    def test_optional_converter_enabled_without_adapter_flag_is_rejected_before_routing(self):
        with self.assertRaisesRegex(ValueError, "parser.markitdown_enabled"):
            ParserConfig(
                default_converter="markitdown",
                enabled_converters=["markitdown", "builtin"],
                fallback_order=["markitdown", "builtin"],
                markitdown_enabled=False,
            )

    def test_missing_default_optional_converter_raises_even_when_fallback_is_allowed(self):
        router = ConverterRouter.default()
        config = ParserConfig(
            default_converter="markitdown",
            enabled_converters=["markitdown", "builtin"],
            fallback_order=["markitdown", "builtin"],
            markitdown_enabled=True,
            strict_converter_availability=False,
        )

        with patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(DocumentLoadError):
                router.convert(ParseSource.from_text("第一条 付款", file_name="inline.txt"), config)

    def test_default_converter_unavailable_does_not_fallback_when_fallback_disabled(self):
        router = ConverterRouter.default()
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
                    ParseSource.from_text("第一条 付款", file_name="inline.txt"), missing
                )

    def test_default_converter_runtime_failure_raises_even_when_fallback_is_allowed(self):
        router = ConverterRouter([BrokenConverter(), BuiltinConverter()])
        config = ParserConfig(
            default_converter="broken",
            enabled_converters=["broken", "builtin"],
            fallback_order=["broken", "builtin"],
        )

        with self.assertRaisesRegex(DocumentLoadError, "broken converter failed"):
            router.convert(ParseSource.from_text("第一条 付款", file_name="inline.txt"), config)


class BrokenConverter:
    name = "broken"

    def supports(self, source: ParseSource, config: ParserConfig) -> ConverterSupport:
        return ConverterSupport(supported=True, confidence=1.0, reason="test converter")

    def convert(self, source: ParseSource, config: ParserConfig) -> ConversionResult:
        raise DocumentLoadError("broken converter failed")


if __name__ == "__main__":
    unittest.main()
