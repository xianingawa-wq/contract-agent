import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from contract_agent.config import (
    MultiAgentConfig,
    ProfileLoadError,
    RetrievalConfig,
    Settings,
    configure_runtime,
    load_app_config,
    settings_snapshot,
)


class ConfigPackageTests(unittest.TestCase):
    def test_multi_agent_config_lives_in_config_package(self):
        config = MultiAgentConfig(agent_timeout_seconds=7, max_parallel_agents=2)

        self.assertEqual(config.agent_timeout_seconds, 7)
        self.assertEqual(config.max_parallel_agents, 2)

    def test_retrieval_config_lives_in_config_package_and_derives_from_settings(self):
        settings = Settings(
            retrieval_enable_rerank=False,
            retrieval_enable_hybrid=False,
            retrieval_fetch_k=20,
            retrieval_final_k=5,
            retrieval_dense_pool_k=40,
        )

        config = RetrievalConfig.from_settings(settings)

        self.assertFalse(config.enable_rerank)
        self.assertFalse(config.enable_hybrid)
        self.assertEqual(config.fetch_k, 20)
        self.assertEqual(config.final_k, 5)
        self.assertEqual(config.dense_pool_k, 40)

    def test_example_yaml_matches_app_config_schema(self):
        config = load_app_config(Path("config.example.yaml"), environ={})

        self.assertEqual(config.app.name, "Contract Review Agent")
        self.assertEqual(config.models.chat.model, "qwen-max")
        self.assertEqual(config.provider.embedding_batch_size, 10)
        self.assertEqual(config.vector_store.backend, "faiss")
        self.assertEqual(config.to_settings().vector_backend, "faiss")
        self.assertEqual(config.grpc.port, 50051)

    def test_load_app_config_derives_runtime_context_from_yaml(self):
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.yaml"
            path.write_text(
                "\n".join(
                    [
                        "models:",
                        "  chat:",
                        "    model: yaml-chat",
                        "retrieval:",
                        "  fetch_k: 20",
                        "multiagent:",
                        "  agent_timeout_seconds: 7",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_app_config(path)

        self.assertEqual(config.models.chat.model, "yaml-chat")
        self.assertEqual(config.to_settings().chat_model, "yaml-chat")
        self.assertEqual(config.to_retrieval_config().fetch_k, 20)
        self.assertEqual(config.to_multiagent_config().agent_timeout_seconds, 7)

        context = configure_runtime(config)

        self.assertEqual(context.settings.chat_model, "yaml-chat")
        self.assertEqual(settings_snapshot().chat_model, "yaml-chat")

    def test_empty_parser_trusted_roots_env_does_not_clear_yaml_roots(self):
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            trusted = root / "trusted"
            config_path = root / "config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "parser:",
                        "  allow_path_input: true",
                        "  trusted_path_roots:",
                        f"    - {trusted.as_posix()}",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_app_config(
                config_path,
                environ={"PARSER_TRUSTED_PATH_ROOTS": ""},
            )

        self.assertEqual(config.parser.trusted_path_roots, [trusted.as_posix()])

    def test_redis_url_environment_overlay_is_documented_and_applied(self):
        config = load_app_config(
            Path("missing-config.yaml"), environ={"REDIS_URL": "redis://redis:6379/2"}
        )
        env_example = Path(".env.example").read_text(encoding="utf-8")

        self.assertEqual(config.multiagent.redis_url, "redis://redis:6379/2")
        self.assertIn("REDIS_URL=", env_example)

    def test_invalid_agent_grpc_port_environment_value_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "AGENT_GRPC_PORT.*not-an-int"):
            load_app_config(
                Path("missing-config.yaml"),
                environ={"AGENT_GRPC_PORT": "not-an-int"},
            )

    def test_default_repo_local_cli_profile_path_is_gitignored(self):
        gitignore_lines = {
            line.strip()
            for line in Path(".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertTrue({".run/", ".run/cli_profile.yaml"} & gitignore_lines)

    def test_configure_runtime_logs_yaml_env_profile_and_injection(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            profile_path = tmp / "cli_profile.yaml"
            profile_path.write_text(
                "\n".join(
                    [
                        "models:",
                        "  chat:",
                        "    model: profile-chat",
                    ]
                ),
                encoding="utf-8",
            )
            config_path = tmp / "config.yaml"
            config_path.write_text(
                "\n".join(
                    [
                        "app:",
                        "  name: Logged Config Agent",
                        "models:",
                        "  chat:",
                        "    model: yaml-chat",
                        "grpc:",
                        "  port: 50052",
                        "profile:",
                        f"  path: {profile_path.as_posix()}",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertLogs("contract_agent.config.config_loader", level="INFO") as captured:
                context = configure_runtime(
                    config_path=config_path,
                    environ={"CHAT_MODEL": "env-chat", "CHAT_API_KEY": "super-secret-key"},
                )

        logs = "\n".join(captured.output)
        self.assertEqual(context.settings.chat_model, "profile-chat")
        self.assertIn("[Config][Info] Loaded runtime config file", logs)
        self.assertIn("[Config][Info] Applied environment config overlay keys", logs)
        self.assertIn("models.chat.model", logs)
        self.assertIn("models.chat.api_key", logs)
        self.assertIn("[Config][Info] Applied CLI profile config overlay keys", logs)
        self.assertIn("models.chat", logs)
        self.assertIn("[Config][Info] Runtime config injected", logs)
        self.assertNotIn("super-secret-key", logs)

    def test_configured_cli_profile_non_mapping_raises_clear_error(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            profile_path = tmp / "cli_profile.yaml"
            profile_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
            config_path = tmp / "config.yaml"
            config_path.write_text(
                "\n".join(["profile:", f"  path: {profile_path.as_posix()}"]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProfileLoadError, "CLI profile.*YAML mapping"):
                configure_runtime(config_path=config_path, environ={})

    def test_configured_cli_profile_corrupt_yaml_raises_clear_error(self):
        with TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            profile_path = tmp / "cli_profile.yaml"
            profile_path.write_text("models:\n  chat: [unterminated\n", encoding="utf-8")
            config_path = tmp / "config.yaml"
            config_path.write_text(
                "\n".join(["profile:", f"  path: {profile_path.as_posix()}"]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProfileLoadError, "CLI profile.*YAML 无效"):
                configure_runtime(config_path=config_path, environ={})


if __name__ == "__main__":
    unittest.main()
