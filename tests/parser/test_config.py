import unittest

from contract_agent.config import AppConfig, configure_runtime, load_settings_from_env
from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser import ContractParser


class ParserConfigTests(unittest.TestCase):
    def test_parser_config_defaults_match_design(self):
        config = ParserConfig()

        self.assertEqual(config.default_converter, "builtin")
        self.assertEqual(config.enabled_converters, ["builtin"])
        self.assertEqual(config.fallback_order, ["builtin"])
        self.assertTrue(config.allow_converter_fallback)
        self.assertFalse(config.strict_converter_availability)
        self.assertEqual(config.allowed_suffixes, [".txt", ".docx", ".pdf"])
        self.assertTrue(config.allow_path_input)
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
        self.assertFalse(config.docling_enabled)
        self.assertFalse(config.docling_enable_ocr)
        self.assertFalse(config.docling_enable_remote_services)

    def test_settings_env_parser_values_parse_lists_numbers_booleans_and_empty_optionals(self):
        settings = load_settings_from_env(
            {
                "PARSER_DEFAULT_CONVERTER": "markitdown",
                "PARSER_ENABLED_CONVERTERS": "builtin, markitdown,,",
                "PARSER_FALLBACK_ORDER": "markitdown,builtin",
                "PARSER_ALLOW_CONVERTER_FALLBACK": "false",
                "PARSER_ALLOWED_SUFFIXES": ".txt,.docx",
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
        self.assertEqual(settings.parser_trusted_path_roots, [])
        self.assertIsNone(settings.parser_max_input_bytes)
        self.assertEqual(settings.parser_min_detector_confidence, 0.72)
        self.assertEqual(settings.parser_chunk_max_chars, 900)
        self.assertTrue(settings.parser_markitdown_enabled)

    def test_app_config_to_parser_config_flattens_nested_parser_section_and_upload_limit(self):
        app_config = AppConfig.model_validate(
            {
                "limits": {"max_upload_size_bytes": 2048},
                "parser": {
                    "default_converter": "builtin",
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
                    "docling": {"enabled": True, "enable_ocr": True},
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
        self.assertTrue(parser_config.docling_enable_ocr)

    def test_environment_overlay_and_app_context_include_parser_config(self):
        context = configure_runtime(
            AppConfig(),
            environ={
                "PARSER_ENABLED_CONVERTERS": "builtin,markitdown",
                "PARSER_FALLBACK_ORDER": "markitdown,builtin",
                "PARSER_MARKITDOWN_ENABLED": "true",
                "PARSER_CHUNK_TARGET_CHARS": "256",
            },
        )

        self.assertEqual(context.config.parser.enabled_converters, ["builtin", "markitdown"])
        self.assertEqual(context.parser_config.fallback_order, ["markitdown", "builtin"])
        self.assertTrue(context.parser_config.markitdown_enabled)
        self.assertEqual(context.parser_config.chunk_target_chars, 256)

    def test_contract_parser_uses_injected_parser_config_without_global_mutation(self):
        parser = ContractParser(
            parser_config=ParserConfig(chunk_max_chars=20, chunk_target_chars=10)
        )
        document = parser.parse_text("第一条 长条款\n" + "。".join(["长句"] * 30) + "。")

        self.assertEqual(parser.parser_config.chunk_max_chars, 20)
        self.assertGreater(len(document.clause_chunks), 1)


if __name__ == "__main__":
    unittest.main()
