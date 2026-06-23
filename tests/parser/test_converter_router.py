import unittest
from unittest.mock import patch

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ParseSource
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

    def test_optional_converter_not_enabled_by_adapter_flag_is_not_implicitly_used(self):
        router = ConverterRouter.default()
        result = router.convert(
            ParseSource.from_text("第一条 付款", file_name="inline.txt"),
            ParserConfig(
                enabled_converters=["markitdown", "builtin"],
                fallback_order=["markitdown", "builtin"],
                markitdown_enabled=False,
            ),
        )

        self.assertEqual(result.converter_name, "builtin")
        self.assertTrue(any("markitdown" in warning for warning in result.warnings))

    def test_missing_optional_converter_falls_back_or_raises_when_strict(self):
        router = ConverterRouter.default()
        config = ParserConfig(
            enabled_converters=["markitdown", "builtin"],
            fallback_order=["markitdown", "builtin"],
            markitdown_enabled=True,
            strict_converter_availability=False,
        )

        with patch("importlib.util.find_spec", return_value=None):
            result = router.convert(
                ParseSource.from_text("第一条 付款", file_name="inline.txt"), config
            )

        self.assertEqual(result.converter_name, "builtin")
        self.assertTrue(any("markitdown" in warning for warning in result.warnings))

        strict = config.model_copy(update={"strict_converter_availability": True})
        with patch("importlib.util.find_spec", return_value=None):
            with self.assertRaises(DocumentLoadError):
                router.convert(ParseSource.from_text("第一条 付款", file_name="inline.txt"), strict)


if __name__ == "__main__":
    unittest.main()
