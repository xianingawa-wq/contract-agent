import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
import yaml

from contract_agent.config import ModelEndpointConfig, ModelRole, ModelRuntimeConfig
from contract_agent.config import apply_model_runtime_config
from contract_agent.config import (
    EnvironmentChatConfigSource,
    EnvironmentEmbeddingConfigSource,
    EnvironmentRerankConfigSource,
    Settings,
    load_settings_from_env,
    settings,
    settings_snapshot,
    temporary_settings,
    update_settings,
)
from contract_agent.config.config_parser import ParserConfig


class RuntimeConfigTests(unittest.TestCase):
    def test_load_settings_from_env_keeps_defaults_instance_scoped(self):
        first = load_settings_from_env({"CHAT_MODEL": "chat-a", "LLM_API_KEY": "key-a"})
        second = load_settings_from_env({"CHAT_MODEL": "chat-b", "LLM_API_KEY": "key-b"})

        self.assertIsInstance(first, Settings)
        self.assertEqual(first.chat_model, "chat-a")
        self.assertEqual(first.chat_api_key, "key-a")
        self.assertEqual(second.chat_model, "chat-b")
        self.assertEqual(second.chat_api_key, "key-b")

    def test_settings_snapshot_is_detached_from_global_mutations(self):
        with temporary_settings(chat_model="snapshot-model"):
            snapshot = settings_snapshot()
            settings.chat_model = "mutated-model"

            self.assertEqual(snapshot.chat_model, "snapshot-model")
            self.assertEqual(settings.chat_model, "mutated-model")

    def test_parser_config_from_settings_snapshot_is_detached_from_global_mutations(self):
        with temporary_settings(parser_chunk_max_chars=777):
            snapshot = settings_snapshot()
            parser_config = ParserConfig.from_settings(snapshot)
            settings.parser_chunk_max_chars = 123

            self.assertEqual(parser_config.chunk_max_chars, 777)
            self.assertEqual(settings.parser_chunk_max_chars, 123)

    def test_runtime_settings_default_vector_backend_uses_local_faiss(self):
        settings_from_env = load_settings_from_env({})

        self.assertEqual(Settings().vector_backend, "faiss")
        self.assertEqual(settings_from_env.vector_backend, "faiss")

    def test_role_environment_sources_use_construction_time_snapshot(self):
        with temporary_settings(
            chat_model="snapshot-chat",
            embedding_model="snapshot-embedding",
            rerank_model="snapshot-rerank",
        ):
            chat_source = EnvironmentChatConfigSource()
            embedding_source = EnvironmentEmbeddingConfigSource()
            rerank_source = EnvironmentRerankConfigSource()

        with temporary_settings(
            chat_model="changed-chat",
            embedding_model="changed-embedding",
            rerank_model="changed-rerank",
        ):
            self.assertEqual(chat_source.load().model, "snapshot-chat")
            self.assertEqual(embedding_source.load().model, "snapshot-embedding")
            self.assertEqual(rerank_source.load().model, "snapshot-rerank")

    def test_role_environment_sources_honor_explicit_settings_injection(self):
        injected = Settings(
            chat_model="injected-chat",
            embedding_model="injected-embedding",
            rerank_model="injected-rerank",
        )

        self.assertEqual(EnvironmentChatConfigSource(injected).load().model, "injected-chat")
        self.assertEqual(
            EnvironmentEmbeddingConfigSource(injected).load().model, "injected-embedding"
        )
        self.assertEqual(EnvironmentRerankConfigSource(injected).load().model, "injected-rerank")

    def test_update_settings_validates_types_before_mutating_global_settings(self):
        with temporary_settings(retrieval_fetch_k=12, chat_model="before-invalid-update"):
            with self.assertRaises(ValidationError):
                update_settings(
                    {
                        "retrieval_fetch_k": "not-an-int",
                        "chat_model": "must-not-be-written",
                    }
                )

            snapshot = settings_snapshot()

        self.assertEqual(snapshot.retrieval_fetch_k, 12)
        self.assertEqual(snapshot.chat_model, "before-invalid-update")

    def test_update_settings_accepts_numeric_strings_after_validation(self):
        with temporary_settings(retrieval_fetch_k=12):
            update_settings({"retrieval_fetch_k": "20"})
            snapshot = settings_snapshot()

        self.assertEqual(snapshot.retrieval_fetch_k, 20)
        self.assertIs(type(snapshot.retrieval_fetch_k), int)

    def test_empty_environ_mapping_does_not_read_process_environment(self):
        with patch.dict("os.environ", {"CHAT_MODEL": "leaked-real-env"}, clear=False):
            settings_from_empty_env = load_settings_from_env({})

        self.assertNotEqual(settings_from_empty_env.chat_model, "leaked-real-env")
        self.assertEqual(settings_from_empty_env.chat_model, Settings().chat_model)

    def test_public_config_import_survives_invalid_integer_environment_value(self):
        env = {
            **os.environ,
            "EMBEDDING_BATCH_SIZE": "not-an-int",
            "PYTHONPATH": str(Path.cwd()),
        }

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import contract_agent.config.config_runtime as runtime; "
                "print(runtime.settings.embedding_batch_size)",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(Settings().embedding_batch_size))

    def test_parser_env_overlays_settings(self):
        settings_from_env = load_settings_from_env(
            {
                "PARSER_ENABLED_DETECTORS": "metadata,clause_header",
                "PARSER_CHUNK_TARGET_CHARS": "256",
                "PARSER_DOCLING_OCR_LANG": "chinese,en",
                "PARSER_DOCLING_COMPACT_TABLES": "false",
                "PARSER_DOCLING_ENABLE_REMOTE_SERVICES": "true",
            }
        )

        self.assertEqual(settings_from_env.parser_enabled_detectors, ["metadata", "clause_header"])
        self.assertEqual(settings_from_env.parser_chunk_target_chars, 256)
        self.assertEqual(settings_from_env.parser_docling_ocr_lang, ["chinese", "en"])
        self.assertFalse(settings_from_env.parser_docling_compact_tables)
        self.assertTrue(settings_from_env.parser_docling_enable_remote_services)

    def test_parser_example_fields_match_settings_and_parser_config(self):
        field_map = {
            "PARSER_DEFAULT_CONVERTER": (
                ("default_converter",),
                "parser_default_converter",
                "default_converter",
            ),
            "PARSER_ENABLED_CONVERTERS": (
                ("enabled_converters",),
                "parser_enabled_converters",
                "enabled_converters",
            ),
            "PARSER_FALLBACK_ORDER": (
                ("fallback_order",),
                "parser_fallback_order",
                "fallback_order",
            ),
            "PARSER_ALLOW_CONVERTER_FALLBACK": (
                ("allow_converter_fallback",),
                "parser_allow_converter_fallback",
                "allow_converter_fallback",
            ),
            "PARSER_STRICT_CONVERTER_AVAILABILITY": (
                ("strict_converter_availability",),
                "parser_strict_converter_availability",
                "strict_converter_availability",
            ),
            "PARSER_ALLOWED_SUFFIXES": (
                ("allowed_suffixes",),
                "parser_allowed_suffixes",
                "allowed_suffixes",
            ),
            "PARSER_ALLOW_PATH_INPUT": (
                ("allow_path_input",),
                "parser_allow_path_input",
                "allow_path_input",
            ),
            "PARSER_ALLOW_URL_INPUT": (
                ("allow_url_input",),
                "parser_allow_url_input",
                "allow_url_input",
            ),
            "PARSER_TRUSTED_PATH_ROOTS": (
                ("trusted_path_roots",),
                "parser_trusted_path_roots",
                "trusted_path_roots",
            ),
            "PARSER_MAX_INPUT_BYTES": (
                ("max_input_bytes",),
                "parser_max_input_bytes",
                "max_input_bytes",
            ),
            "PARSER_PRESERVE_RAW_TEXT": (
                ("preserve_raw_text",),
                "parser_preserve_raw_text",
                "preserve_raw_text",
            ),
            "PARSER_ENABLED_DETECTORS": (
                ("detectors", "enabled"),
                "parser_enabled_detectors",
                "enabled_detectors",
            ),
            "PARSER_DETECTOR_PROFILE": (
                ("detectors", "profile"),
                "parser_detector_profile",
                "detector_profile",
            ),
            "PARSER_DETECTOR_RULES_PATH": (
                ("detectors", "rules_path"),
                "parser_detector_rules_path",
                "detector_rules_path",
            ),
            "PARSER_MIN_DETECTOR_CONFIDENCE": (
                ("detectors", "min_confidence"),
                "parser_min_detector_confidence",
                "min_detector_confidence",
            ),
            "PARSER_STORE_DETECTOR_REASONS": (
                ("detectors", "store_reasons"),
                "parser_store_detector_reasons",
                "store_detector_reasons",
            ),
            "PARSER_CHUNK_MAX_CHARS": (
                ("chunking", "max_chars"),
                "parser_chunk_max_chars",
                "chunk_max_chars",
            ),
            "PARSER_CHUNK_TARGET_CHARS": (
                ("chunking", "target_chars"),
                "parser_chunk_target_chars",
                "chunk_target_chars",
            ),
            "PARSER_MIN_HEADER_CONFIDENCE": (
                ("chunking", "min_header_confidence"),
                "parser_min_header_confidence",
                "min_header_confidence",
            ),
            "PARSER_MARKITDOWN_ENABLED": (
                ("markitdown", "enabled"),
                "parser_markitdown_enabled",
                "markitdown_enabled",
            ),
            "PARSER_DOCLING_ENABLED": (
                ("docling", "enabled"),
                "parser_docling_enabled",
                "docling_enabled",
            ),
            "PARSER_DOCLING_ENABLE_OCR": (
                ("docling", "enable_ocr"),
                "parser_docling_enable_ocr",
                "docling_enable_ocr",
            ),
            "PARSER_DOCLING_OCR_LANG": (
                ("docling", "ocr_lang"),
                "parser_docling_ocr_lang",
                "docling_ocr_lang",
            ),
            "PARSER_DOCLING_FORCE_FULL_PAGE_OCR": (
                ("docling", "force_full_page_ocr"),
                "parser_docling_force_full_page_ocr",
                "docling_force_full_page_ocr",
            ),
            "PARSER_DOCLING_BITMAP_AREA_THRESHOLD": (
                ("docling", "bitmap_area_threshold"),
                "parser_docling_bitmap_area_threshold",
                "docling_bitmap_area_threshold",
            ),
            "PARSER_DOCLING_TEXT_SCORE": (
                ("docling", "text_score"),
                "parser_docling_text_score",
                "docling_text_score",
            ),
            "PARSER_DOCLING_DO_TABLE_STRUCTURE": (
                ("docling", "do_table_structure"),
                "parser_docling_do_table_structure",
                "docling_do_table_structure",
            ),
            "PARSER_DOCLING_COMPACT_TABLES": (
                ("docling", "compact_tables"),
                "parser_docling_compact_tables",
                "docling_compact_tables",
            ),
            "PARSER_DOCLING_ENABLE_REMOTE_SERVICES": (
                ("docling", "enable_remote_services"),
                "parser_docling_enable_remote_services",
                "docling_enable_remote_services",
            ),
        }
        repo_root = Path(__file__).resolve().parents[2]
        env_keys = {
            line.split("=", 1)[0]
            for line in (repo_root / ".env.example").read_text(encoding="utf-8").splitlines()
            if line.startswith("PARSER_")
        }
        parser_yaml = yaml.safe_load(
            (repo_root / "config.example.yaml").read_text(encoding="utf-8")
        )["parser"]

        self.assertEqual(env_keys, set(field_map))
        for env_key, (yaml_path, settings_field, parser_field) in field_map.items():
            with self.subTest(env_key=env_key):
                cursor = parser_yaml
                for part in yaml_path:
                    self.assertIn(part, cursor)
                    cursor = cursor[part]
                self.assertIn(settings_field, Settings.model_fields)
                self.assertIn(parser_field, ParserConfig.model_fields)

    def test_apply_model_runtime_config_updates_related_aliases_together(self):
        config = ModelRuntimeConfig(
            chat=ModelEndpointConfig(
                role=ModelRole.CHAT,
                provider="openai",
                base_url="https://chat.example.test/v1",
                api_key="chat-key",
                model="chat-model",
            ),
            embedding=ModelEndpointConfig(
                role=ModelRole.EMBEDDING,
                provider="openai_compatible",
                base_url="https://embedding.example.test/v1",
                api_key="embedding-key",
                model="embedding-model",
            ),
            rerank=ModelEndpointConfig(
                role=ModelRole.RERANK,
                provider="qwen",
                base_url="https://rerank.example.test/v1",
                api_key="rerank-key",
                model="rerank-model",
            ),
        )

        with temporary_settings():
            apply_model_runtime_config(config)
            snapshot = settings_snapshot()

            self.assertEqual(snapshot.chat_model, "chat-model")
            self.assertEqual(snapshot.llm_chat_model, "chat-model")
            self.assertEqual(snapshot.embedding_model, "embedding-model")
            self.assertEqual(snapshot.llm_embedding_model, "embedding-model")
            self.assertEqual(snapshot.qwen_api_key, "chat-key")
            self.assertEqual(snapshot.langchain_embedding_model, "embedding-model")
            self.assertEqual(snapshot.rerank_model, "rerank-model")


if __name__ == "__main__":
    unittest.main()
