import unittest

from contract_agent.config import (
    AppConfig,
    configure_runtime,
    load_settings_from_env,
    temporary_settings,
)
from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import ContractParser


class ParserConfigTests(unittest.TestCase):
    def test_parser_config_defaults_match_design(self):
        config = ParserConfig()

        self.assertEqual(config.default_converter, "docling")
        self.assertEqual(config.enabled_converters, ["docling", "builtin"])
        self.assertEqual(config.fallback_order, ["docling", "builtin"])
        self.assertTrue(config.allow_converter_fallback)
        self.assertFalse(config.strict_converter_availability)
        self.assertEqual(
            config.allowed_suffixes,
            [
                ".txt",
                ".doc",
                ".docx",
                ".pdf",
                ".md",
                ".markdown",
                ".html",
                ".htm",
                ".csv",
                ".xlsx",
            ],
        )
        self.assertFalse(config.allow_path_input)
        self.assertFalse(config.allow_url_input)
        self.assertEqual(config.trusted_path_roots, [])
        self.assertIsNone(config.max_input_bytes)
        self.assertTrue(config.preserve_raw_text)
        self.assertEqual(config.detector_profile, "builtin_zh_contract_v1")
        self.assertEqual(
            config.enabled_detectors,
            ["metadata", "clause_header", "definition", "reference"],
        )
        self.assertIsNone(config.detector_rules_path)
        self.assertEqual(config.min_detector_confidence, 0.60)
        self.assertTrue(config.store_detector_reasons)
        self.assertEqual(config.chunk_max_chars, 1200)
        self.assertEqual(config.chunk_target_chars, 500)
        self.assertEqual(config.min_header_confidence, 0.65)
        self.assertFalse(config.markitdown_enabled)
        self.assertTrue(config.docling_enabled)
        self.assertTrue(config.docling_enable_ocr)
        self.assertEqual(config.docling_ocr_lang, ["chinese"])
        self.assertTrue(config.docling_force_full_page_ocr)
        self.assertEqual(config.docling_bitmap_area_threshold, 0.02)
        self.assertEqual(config.docling_text_score, 0.35)
        self.assertTrue(config.docling_do_table_structure)
        self.assertTrue(config.docling_compact_tables)
        self.assertFalse(config.docling_enable_remote_services)
        self.assertEqual(
            config.docling_supported_suffixes,
            [".pdf", ".docx", ".md", ".markdown", ".html", ".htm", ".csv", ".xlsx"],
        )

    def test_parser_config_rejects_empty_allowed_suffixes_after_normalization(self):
        with self.assertRaisesRegex(ValueError, "allowed_suffixes"):
            ParserConfig(allowed_suffixes=["", "  "])

    def test_settings_env_parser_values_parse_lists_numbers_booleans_and_empty_optionals(self):
        settings = load_settings_from_env(
            {
                "PARSER_DEFAULT_CONVERTER": "markitdown",
                "PARSER_ENABLED_CONVERTERS": "builtin, markitdown,,",
                "PARSER_FALLBACK_ORDER": "markitdown,builtin",
                "PARSER_ALLOW_CONVERTER_FALLBACK": "false",
                "PARSER_ALLOWED_SUFFIXES": ".txt,.docx",
                "PARSER_DOCLING_SUPPORTED_SUFFIXES": ".pdf,.docx",
                "PARSER_TRUSTED_PATH_ROOTS": "",
                "PARSER_MAX_INPUT_BYTES": "",
                "PARSER_MIN_DETECTOR_CONFIDENCE": "0.72",
                "PARSER_CHUNK_MAX_CHARS": "900",
                "PARSER_MARKITDOWN_ENABLED": "true",
            }
        )

        self.assertEqual(settings.parser_default_converter, "markitdown")
        self.assertEqual(settings.parser_enabled_converters, ["builtin", "markitdown"])
        self.assertEqual(settings.parser_fallback_order, ["markitdown", "builtin"])
        self.assertFalse(settings.parser_allow_converter_fallback)
        self.assertEqual(settings.parser_allowed_suffixes, [".txt", ".docx"])
        self.assertEqual(settings.parser_docling_supported_suffixes, [".pdf", ".docx"])
        self.assertEqual(settings.parser_trusted_path_roots, [])
        self.assertIsNone(settings.parser_max_input_bytes)
        self.assertEqual(settings.parser_min_detector_confidence, 0.72)
        self.assertEqual(settings.parser_chunk_max_chars, 900)
        self.assertTrue(settings.parser_markitdown_enabled)

    def test_runtime_settings_default_parser_uses_docling(self):
        settings = load_settings_from_env({})

        self.assertEqual(settings.parser_default_converter, "docling")
        self.assertEqual(settings.parser_enabled_converters, ["docling", "builtin"])
        self.assertEqual(settings.parser_fallback_order, ["docling", "builtin"])
        self.assertTrue(settings.parser_docling_enabled)
        self.assertEqual(
            settings.parser_docling_supported_suffixes,
            [".pdf", ".docx", ".md", ".markdown", ".html", ".htm", ".csv", ".xlsx"],
        )

    def test_app_config_to_parser_config_flattens_nested_parser_section_and_upload_limit(self):
        app_config = AppConfig.model_validate(
            {
                "limits": {"max_upload_size_bytes": 2048},
                "parser": {
                    "default_converter": "docling",
                    "enabled_converters": ["builtin", "docling"],
                    "fallback_order": ["docling", "builtin"],
                    "max_input_bytes": 4096,
                    "detectors": {
                        "enabled": ["metadata"],
                        "profile": "custom",
                        "min_confidence": 0.8,
                        "store_reasons": False,
                    },
                    "chunking": {
                        "max_chars": 800,
                        "target_chars": 300,
                        "min_header_confidence": 0.7,
                    },
                    "docling": {"enabled": True, "supported_suffixes": [".pdf", ".docx"]},
                },
            }
        )

        parser_config = app_config.to_parser_config()

        self.assertEqual(parser_config.enabled_converters, ["builtin", "docling"])
        self.assertEqual(parser_config.fallback_order, ["docling", "builtin"])
        self.assertEqual(parser_config.max_input_bytes, 2048)
        self.assertEqual(parser_config.enabled_detectors, ["metadata"])
        self.assertEqual(parser_config.detector_profile, "custom")
        self.assertEqual(parser_config.min_detector_confidence, 0.8)
        self.assertFalse(parser_config.store_detector_reasons)
        self.assertEqual(parser_config.chunk_max_chars, 800)
        self.assertEqual(parser_config.chunk_target_chars, 300)
        self.assertEqual(parser_config.min_header_confidence, 0.7)
        self.assertTrue(parser_config.docling_enabled)
        self.assertEqual(parser_config.docling_supported_suffixes, [".pdf", ".docx"])

        stricter_parser_config = AppConfig.model_validate(
            {
                "limits": {"max_upload_size_bytes": 8192},
                "parser": {"max_input_bytes": 4096},
            }
        ).to_parser_config()
        self.assertEqual(stricter_parser_config.max_input_bytes, 4096)

    def test_environment_overlay_and_app_context_include_parser_config(self):
        with temporary_settings():
            context = configure_runtime(
                AppConfig(),
                environ={
                    "PARSER_DEFAULT_CONVERTER": "markitdown",
                    "PARSER_ENABLED_CONVERTERS": "builtin,markitdown",
                    "PARSER_FALLBACK_ORDER": "markitdown,builtin",
                    "PARSER_MARKITDOWN_ENABLED": "true",
                    "PARSER_CHUNK_TARGET_CHARS": "256",
                    "PARSER_DOCLING_SUPPORTED_SUFFIXES": ".pdf,.docx",
                },
            )

            self.assertEqual(context.config.parser.enabled_converters, ["builtin", "markitdown"])
            self.assertEqual(context.parser_config.fallback_order, ["markitdown", "builtin"])
            self.assertTrue(context.parser_config.markitdown_enabled)
            self.assertEqual(context.parser_config.chunk_target_chars, 256)
            self.assertEqual(context.parser_config.docling_supported_suffixes, [".pdf", ".docx"])

    def test_parser_config_normalizes_docling_supported_suffixes(self):
        config = ParserConfig(docling_supported_suffixes=["pdf", ".DOCX", " md ", "", ".pdf"])

        self.assertEqual(config.docling_supported_suffixes, [".pdf", ".docx", ".md"])

    def test_contract_parser_uses_injected_parser_config_without_global_mutation(self):
        parser = ContractParser(
            parser_config=ParserConfig(
                default_converter="builtin",
                enabled_converters=["builtin"],
                fallback_order=["builtin"],
                docling_enabled=False,
                chunk_max_chars=20,
                chunk_target_chars=10,
            )
        )
        document = parser.parse_text("第一条 长条款\n" + "。".join(["长句"] * 30) + "。")

        self.assertEqual(parser.parser_config.chunk_max_chars, 20)
        self.assertGreater(len(document.clause_chunks), 1)

    def test_parser_config_rejects_converter_order_that_hides_default(self):
        with self.assertRaisesRegex(ValueError, "fallback_order"):
            ParserConfig(
                default_converter="markitdown",
                enabled_converters=["builtin", "markitdown"],
                fallback_order=["builtin"],
            )

    def test_parser_config_rejects_fallback_order_that_does_not_start_with_default(self):
        with self.assertRaisesRegex(ValueError, "default_converter"):
            ParserConfig(
                default_converter="markitdown",
                enabled_converters=["builtin", "markitdown"],
                fallback_order=["builtin", "markitdown"],
                markitdown_enabled=True,
            )

    def test_parser_config_rejects_optional_converter_enabled_without_adapter_flag(self):
        cases = [
            (
                "markitdown",
                {"markitdown_enabled": False},
                "parser.markitdown_enabled",
            ),
            (
                "docling",
                {"docling_enabled": False},
                "parser.docling_enabled",
            ),
        ]
        for converter, flags, message in cases:
            with self.subTest(converter=converter):
                with self.assertRaisesRegex(ValueError, message):
                    ParserConfig(
                        default_converter=converter,
                        enabled_converters=[converter, "builtin"],
                        fallback_order=[converter, "builtin"],
                        **flags,
                    )

    def test_parser_config_rejects_fallback_converter_not_enabled(self):
        with self.assertRaisesRegex(ValueError, "enabled_converters"):
            ParserConfig(
                default_converter="builtin",
                enabled_converters=["builtin"],
                fallback_order=["builtin", "docling"],
            )

    def test_parser_config_rejects_empty_fallback_order(self):
        with self.assertRaisesRegex(ValueError, "fallback_order"):
            ParserConfig(
                default_converter="builtin",
                enabled_converters=["builtin"],
                fallback_order=[],
            )

    def test_parser_config_rejects_chunk_target_above_max(self):
        with self.assertRaisesRegex(ValueError, "chunk_target_chars"):
            ParserConfig(chunk_max_chars=100, chunk_target_chars=200)

    def test_parser_config_rejects_unimplemented_url_input(self):
        with self.assertRaisesRegex(ValueError, "allow_url_input"):
            ParserConfig(allow_url_input=True)

    def test_parser_config_rejects_unimplemented_docling_remote_services(self):
        with self.assertRaisesRegex(ValueError, "docling_enable_remote_services"):
            ParserConfig(
                default_converter="docling",
                enabled_converters=["docling"],
                fallback_order=["docling"],
                docling_enabled=True,
                docling_enable_remote_services=True,
            )

    def test_parser_config_rejects_invalid_docling_quality_options(self):
        cases = [
            {"docling_ocr_lang": []},
            {"docling_bitmap_area_threshold": -0.1},
            {"docling_text_score": 1.2},
        ]
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    ParserConfig(**values)


if __name__ == "__main__":
    unittest.main()
