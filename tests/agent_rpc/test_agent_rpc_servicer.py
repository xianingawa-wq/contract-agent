import unittest
import json
import tempfile
from pathlib import Path
from concurrent import futures
from unittest.mock import patch

import grpc

from contract_agent.agent_rpc import agent_pb2, agent_pb2_grpc
from contract_agent.agent_rpc.server import AgentRpcServicer, serve
from contract_agent.logger.audit import AuditLogger
from contract_agent.config import AppConfig, Settings, configure_runtime
from contract_agent.config.config_parser import ParserConfig
from contract_agent.orchestration.protocol import (
    AgentMode,
    AgentOutput,
    AgentStatus,
    PipelineStatus,
)
from contract_agent.schemas.review import (
    ExtractedFields,
    HealthResponse,
    ReviewReport,
    ReviewResponse,
    ReviewSummary,
)


class FakeReviewService:
    def health(self) -> HealthResponse:
        return HealthResponse(status="ok", llm_configured=True, knowledge_base_ready=False)


def _builtin_context():
    return configure_runtime(
        AppConfig.model_validate(
            {
                "parser": {
                    "default_converter": "builtin",
                    "enabled_converters": ["builtin"],
                    "fallback_order": ["builtin"],
                    "docling": {"enabled": False},
                },
                "models": {
                    "chat": {"api_key": "chat-key", "model": "qwen-max"},
                    "embedding": {"model": "text-embedding-v4"},
                    "rerank": {"provider": "qwen", "model": "qwen3-rerank"},
                },
            }
        )
    )


def make_review_response() -> ReviewResponse:
    from datetime import datetime, timezone

    return ReviewResponse(
        summary=ReviewSummary(contract_type="采购合同", overall_risk="info", risk_count=0),
        extracted_fields=ExtractedFields(),
        risks=[],
        report=ReviewReport(
            generated_at=datetime.now(timezone.utc),
            overview="ok",
            key_findings=[],
            next_actions=[],
        ),
    )


class AgentRpcServicerTests(unittest.TestCase):
    def _capture_serve_bind_target(self, *, host_env: str | None = None, port: int = 50051) -> str:
        class ServerStarted(RuntimeError):
            pass

        class FakeServer:
            def __init__(self) -> None:
                self.targets: list[str] = []

            def add_insecure_port(self, target: str) -> int:
                self.targets.append(target)
                return 1

            def start(self) -> None:
                raise ServerStarted()

            def wait_for_termination(self) -> None:
                raise AssertionError("serve() should not wait after fake start")

        fake_server = FakeServer()
        context = configure_runtime(
            AppConfig.model_validate({"grpc": {"host": host_env or "127.0.0.1", "port": port}})
        )

        with (
            patch("contract_agent.agent_rpc.server.configure_runtime", return_value=context),
            patch("contract_agent.agent_rpc.server.grpc.server", return_value=fake_server),
            patch(
                "contract_agent.agent_rpc.server.agent_pb2_grpc.add_AgentRpcServiceServicer_to_server"
            ),
            self.assertRaises(ServerStarted),
        ):
            serve()

        self.assertEqual(len(fake_server.targets), 1)
        return fake_server.targets[0]

    def test_serve_binds_localhost_by_default(self):
        self.assertEqual(self._capture_serve_bind_target(), "127.0.0.1:50051")

    def test_serve_allows_explicit_grpc_host_override(self):
        target = self._capture_serve_bind_target(host_env="0.0.0.0", port=50052)

        self.assertEqual(target, "0.0.0.0:50052")

    def test_agent_rpc_docker_healthcheck_uses_agent_grpc_port(self):
        dockerfile = Path("contract_agent/agent_rpc/Dockerfile").read_text(encoding="utf-8")
        self.assertIn("AGENT_GRPC_HOST=0.0.0.0", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        healthcheck = dockerfile.split("HEALTHCHECK", 1)[1]

        self.assertIn("AGENT_GRPC_PORT", healthcheck)
        self.assertNotIn("50051), timeout", healthcheck)

    def test_health_uses_injected_services_without_starting_network_server(self):
        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        servicer.review_service = FakeReviewService()  # type: ignore[assignment]

        response = servicer.Health(agent_pb2.HealthRequest(), None)

        self.assertEqual(response.status, "ok")
        self.assertTrue(response.llm_configured)
        self.assertIn("review", response.capabilities)

    def test_redraft_missing_chat_key_returns_service_unavailable(self):
        servicer = AgentRpcServicer(
            runtime_settings=Settings(chat_api_key=None, llm_api_key=None, qwen_api_key=None)
        )

        response = servicer.Redraft(
            agent_pb2.RedraftRequest(
                contract_text="合同正文",
                contract_type="采购合同",
                our_side="甲方",
                accepted_issues_json="[]",
            ),
            None,
        )

        self.assertEqual(response.code, 503)
        self.assertIn("CHAT_API_KEY 或 LLM_API_KEY 未配置", response.error)

    def test_redraft_rejects_malformed_accepted_issues_without_calling_editor(self):
        class EditorSpy:
            def __init__(self) -> None:
                self.called = False

            def redraft_contract(self, **kwargs):
                self.called = True
                raise AssertionError("invalid accepted_issues_json must be rejected first")

        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        editor = EditorSpy()
        servicer.contract_editor = editor  # type: ignore[assignment]

        for accepted_issues_json in ["{}", '"text"', '["bad"]', "[{}]"]:
            with self.subTest(accepted_issues_json=accepted_issues_json):
                response = servicer.Redraft(
                    agent_pb2.RedraftRequest(
                        contract_text="合同正文",
                        contract_type="采购合同",
                        our_side="甲方",
                        accepted_issues_json=accepted_issues_json,
                    ),
                    None,
                )

                self.assertEqual(response.code, 400)
                self.assertFalse(editor.called)

    def test_redraft_treats_blank_accepted_issues_json_as_empty_list(self):
        class EditorSpy:
            def __init__(self) -> None:
                self.kwargs = None

            def redraft_contract(self, **kwargs):
                self.kwargs = kwargs
                return "修订稿"

        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        editor = EditorSpy()
        servicer.contract_editor = editor  # type: ignore[assignment]

        for raw_json in ["", "   "]:
            with self.subTest(raw_json=raw_json):
                editor.kwargs = None

                response = servicer.Redraft(
                    agent_pb2.RedraftRequest(
                        contract_text="合同正文",
                        contract_type="采购合同",
                        our_side="甲方",
                        accepted_issues_json=raw_json,
                    ),
                    None,
                )

                self.assertEqual(response.code, 200)
                self.assertIsNotNone(editor.kwargs)
                self.assertEqual(editor.kwargs["accepted_issues"], [])

    def test_redraft_rejects_blank_contract_text_without_calling_editor(self):
        class EditorSpy:
            def __init__(self) -> None:
                self.called = False

            def redraft_contract(self, **kwargs):
                self.called = True
                raise AssertionError("blank contract_text must be rejected first")

        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        editor = EditorSpy()
        servicer.contract_editor = editor  # type: ignore[assignment]

        response = servicer.Redraft(
            agent_pb2.RedraftRequest(
                contract_text="   ",
                contract_type="采购合同",
                our_side="甲方",
                accepted_issues_json="[]",
            ),
            None,
        )

        self.assertEqual(response.code, 400)
        self.assertFalse(editor.called)

    def test_redraft_defaults_blank_contract_type_and_our_side_before_calling_editor(self):
        class EditorSpy:
            def __init__(self) -> None:
                self.kwargs = None

            def redraft_contract(self, **kwargs):
                self.kwargs = kwargs
                return "修订稿"

        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        editor = EditorSpy()
        servicer.contract_editor = editor  # type: ignore[assignment]

        response = servicer.Redraft(
            agent_pb2.RedraftRequest(
                contract_text="合同正文",
                contract_type=" ",
                our_side=" ",
                accepted_issues_json='[{"message":" 风险 ","suggestion":" 建议 ","location":" 条款 "}]',
            ),
            None,
        )

        self.assertEqual(response.code, 200)
        self.assertEqual(json.loads(response.json), {"revised_text": "修订稿"})
        self.assertIsNotNone(editor.kwargs)
        self.assertEqual(editor.kwargs["contract_type"], servicer.settings.default_contract_type)
        self.assertEqual(editor.kwargs["our_side"], "甲方")
        self.assertEqual(
            editor.kwargs["accepted_issues"],
            [{"message": "风险", "suggestion": "建议", "location": "条款"}],
        )

    def test_health_writes_rpc_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(Path(tmp) / "trace.jsonl")
            servicer = AgentRpcServicer(
                runtime_settings=Settings(chat_api_key="chat-key"), audit_logger=logger
            )
            servicer.review_service = FakeReviewService()  # type: ignore[assignment]

            servicer.Health(agent_pb2.HealthRequest(), None)
            records = [
                json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(records[0]["event"], "trace.started")
        self.assertEqual(records[0]["operation"], "grpc.Health")
        self.assertEqual(records[0]["prefix"], "[RPC]")
        self.assertEqual(records[-1]["event"], "trace.completed")
        self.assertEqual(len({record.get("trace_id") for record in records}), 1)

    def test_review_multi_agent_grpc_reaches_supervisor_runtime_boundary(self):
        def fake_run(state, initial_input, on_event=None):
            state.status = PipelineStatus.COMPLETED
            state.agent_outputs["supervisor"] = AgentOutput(
                agent_id="supervisor",
                status=AgentStatus.COMPLETED,
                input_summary=initial_input["contract_type"],
                structured_data={"review_report": {"overall_risk": "low"}},
            )
            return state

        class FakeMemoryManager:
            def __init__(self, *args, **kwargs):
                self.saved_states = []

            def save_pipeline_result(self, state):
                self.saved_states.append(state)

        class FakeEventPublisher:
            def __init__(self, *args, **kwargs):
                pass

            def publish(self, event):
                pass

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        servicer = AgentRpcServicer(app_context=_builtin_context())
        agent_pb2_grpc.add_AgentRpcServiceServicer_to_server(servicer, server)
        port = server.add_insecure_port("127.0.0.1:0")

        with (
            patch("contract_agent.memory.manager.MemoryManager", FakeMemoryManager),
            patch("contract_agent.orchestration.events.EventPublisher", FakeEventPublisher),
            patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls,
        ):
            supervisor_cls.return_value.run.side_effect = fake_run
            server.start()
            try:
                channel = grpc.insecure_channel(f"127.0.0.1:{port}")
                stub = agent_pb2_grpc.AgentRpcServiceStub(channel)

                response = stub.ReviewMultiAgent(
                    agent_pb2.ReviewRequest(
                        contract_text="合同正文",
                        contract_type="采购合同",
                        our_side="甲方",
                    ),
                    timeout=5,
                )
            finally:
                server.stop(0)

        self.assertEqual(response.code, 200)
        payload = json.loads(response.json)
        self.assertEqual(payload["mode"], "multi_auto")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["report"], {"overall_risk": "low"})
        self.assertEqual(payload["agent_summaries"][0]["agent_id"], "supervisor")

    def test_review_multi_agent_non_streaming_includes_structured_agent_results(self):
        def fake_run(state, initial_input, on_event=None):
            state.status = PipelineStatus.COMPLETED
            state.agent_outputs["supervisor"] = AgentOutput(
                agent_id="supervisor",
                status=AgentStatus.COMPLETED,
                input_summary="summary",
                structured_data={"review_report": {"overall_risk": "medium"}},
            )
            state.agent_outputs["risk_checker"] = AgentOutput(
                agent_id="risk_checker",
                status=AgentStatus.COMPLETED,
                input_summary="risk",
                structured_data={"risk_findings": [{"rule_id": "RISK-1"}]},
            )
            state.agent_outputs["legal_ref"] = AgentOutput(
                agent_id="legal_ref",
                status=AgentStatus.COMPLETED,
                input_summary="legal",
                structured_data={"legal_refs": [{"article": "民法典第1条"}]},
            )
            state.agent_outputs["redrafter"] = AgentOutput(
                agent_id="redrafter",
                status=AgentStatus.COMPLETED,
                input_summary="redraft",
                structured_data={"redraft_suggestions": [{"after": "修订条款"}]},
            )
            return state

        class FakeMemoryManager:
            def __init__(self, *args, **kwargs):
                pass

            def save_pipeline_result(self, state):
                pass

        class FakeEventPublisher:
            def __init__(self, *args, **kwargs):
                pass

            def publish(self, event):
                pass

        servicer = AgentRpcServicer(app_context=_builtin_context())

        with (
            patch("contract_agent.memory.manager.MemoryManager", FakeMemoryManager),
            patch("contract_agent.orchestration.events.EventPublisher", FakeEventPublisher),
            patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls,
            patch(
                "contract_agent.services.review_gateway.GatewayRouter._detect_mode",
                return_value=AgentMode.MULTI_AUTO,
            ),
        ):
            supervisor_cls.return_value.run.side_effect = fake_run
            response = servicer.ReviewMultiAgent(
                agent_pb2.ReviewRequest(
                    contract_text="合同正文",
                    contract_type="采购合同",
                    our_side="甲方",
                ),
                None,
            )

        self.assertEqual(response.code, 200)
        payload = json.loads(response.json)
        self.assertEqual(payload["report"], {"overall_risk": "medium"})
        self.assertEqual(payload["risk_findings"], [{"rule_id": "RISK-1"}])
        self.assertEqual(payload["legal_refs"], [{"article": "民法典第1条"}])
        self.assertEqual(payload["redraft_suggestions"], [{"after": "修订条款"}])

    def test_review_file_input_uses_normalized_document_without_review_file_branch(self):
        class ReviewServiceSpy(FakeReviewService):
            def __init__(self):
                self.review_document_calls = []

            def review_document(self, document, contract_type, our_side):
                self.review_document_calls.append((document, contract_type, our_side))
                return make_review_response()

            def review_file(self, *args, **kwargs):
                raise AssertionError("Review RPC must not call review_file after normalization")

        service = ReviewServiceSpy()
        servicer = AgentRpcServicer(app_context=_builtin_context())
        servicer.review_service = service  # type: ignore[assignment]

        response = servicer.Review(
            agent_pb2.ReviewRequest(
                file=agent_pb2.FilePayload(
                    file_name="contract.txt",
                    content="第一条 付款".encode("utf-8"),
                ),
                contract_type="采购合同",
                our_side="甲方",
            ),
            None,
        )

        self.assertEqual(response.code, 200)
        self.assertEqual(len(service.review_document_calls), 1)
        document, contract_type, our_side = service.review_document_calls[0]
        self.assertEqual(document.raw_text, "第一条 付款")
        self.assertEqual(contract_type, "采购合同")
        self.assertEqual(our_side, "甲方")

    def test_review_text_input_obeys_effective_parser_limit_before_review_service(self):
        class ReviewServiceSpy(FakeReviewService):
            def review_document(self, *args, **kwargs):
                raise AssertionError("Review RPC must reject oversize text before review_document")

        context = configure_runtime(
            AppConfig.model_validate({"limits": {"max_upload_size_bytes": 8}})
        )
        servicer = AgentRpcServicer(app_context=context)
        servicer.review_service = ReviewServiceSpy()  # type: ignore[assignment]

        response = servicer.Review(
            agent_pb2.ReviewRequest(contract_text="123456789"),
            None,
        )

        self.assertEqual(response.code, 400)
        self.assertIn("parser.max_input_bytes", response.error)

    def test_review_multi_agent_file_input_passes_parsed_text_and_json_safe_document_to_supervisor(
        self,
    ):
        captured_inputs = []

        def fake_run(state, initial_input, on_event=None):
            captured_inputs.append(initial_input)
            state.status = PipelineStatus.COMPLETED
            state.agent_outputs["supervisor"] = AgentOutput(
                agent_id="supervisor",
                status=AgentStatus.COMPLETED,
                input_summary=initial_input["contract_text"],
                structured_data={"review_report": {"overall_risk": "low"}},
            )
            return state

        class FakeMemoryManager:
            def __init__(self, *args, **kwargs):
                pass

            def save_pipeline_result(self, state):
                pass

        class FakeEventPublisher:
            def __init__(self, *args, **kwargs):
                pass

            def publish(self, event):
                pass

        servicer = AgentRpcServicer(app_context=_builtin_context())

        with (
            patch("contract_agent.memory.manager.MemoryManager", FakeMemoryManager),
            patch("contract_agent.orchestration.events.EventPublisher", FakeEventPublisher),
            patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls,
        ):
            supervisor_cls.return_value.run.side_effect = fake_run
            response = servicer.ReviewMultiAgent(
                agent_pb2.ReviewRequest(
                    file=agent_pb2.FilePayload(
                        file_name="contract.txt",
                        content="第一条 付款".encode("utf-8"),
                    ),
                    contract_type="采购合同",
                    our_side="甲方",
                ),
                None,
            )

        self.assertEqual(response.code, 200)
        initial_input = captured_inputs[0]
        self.assertEqual(initial_input["contract_text"], "第一条 付款")
        self.assertEqual(initial_input["document_metadata"]["file_name"], "contract.txt")
        self.assertIn("raw_text", initial_input["parsed_document_data"])
        self.assertNotIn("parsed_document", initial_input)
        self.assertIn("document_blocks", initial_input)
        self.assertIn("llm_context", initial_input)
        self.assertIn("evidence_json", initial_input)
        self.assertIn("rag_documents", initial_input)
        self.assertTrue(initial_input["document_blocks"])
        self.assertIsInstance(initial_input["clause_chunks"], list)
        self.assertTrue(initial_input["clause_chunks"])
        self.assertTrue(initial_input["rag_documents"])
        self.assertEqual(initial_input["contract_type"], "采购合同")
        self.assertEqual(initial_input["our_side"], "甲方")
        json.dumps(initial_input, ensure_ascii=False)

    def test_review_multi_agent_single_mode_reuses_normalized_document_and_review_service(self):
        class ReviewServiceSpy(FakeReviewService):
            def __init__(self):
                self.review_document_calls = []

            def review_document(self, document, contract_type, our_side):
                self.review_document_calls.append((document, contract_type, our_side))
                return make_review_response()

            def review(self, *args, **kwargs):
                raise AssertionError("single mode must not reparse contract_text")

        from contract_agent.orchestration.protocol import AgentMode

        service = ReviewServiceSpy()
        servicer = AgentRpcServicer(app_context=_builtin_context())
        servicer.review_service = service  # type: ignore[assignment]

        with patch(
            "contract_agent.services.review_gateway.GatewayRouter._detect_mode",
            return_value=AgentMode.SINGLE,
        ):
            response = servicer.ReviewMultiAgent(
                agent_pb2.ReviewRequest(
                    file=agent_pb2.FilePayload(
                        file_name="contract.txt",
                        content=b"Section 1 Payment",
                    ),
                    contract_type="purchase",
                    our_side="buyer",
                ),
                None,
            )

        self.assertEqual(response.code, 200)
        self.assertEqual(len(service.review_document_calls), 1)
        document, contract_type, our_side = service.review_document_calls[0]
        self.assertEqual(document.metadata.file_name, "contract.txt")
        self.assertEqual(document.raw_text, "Section 1 Payment")
        self.assertEqual(contract_type, "purchase")
        self.assertEqual(our_side, "buyer")

    def test_review_multi_agent_single_mode_falls_back_for_legacy_review_service(self):
        class LegacyReviewService(FakeReviewService):
            def __init__(self):
                self.review_calls = []

            def review(self, request):
                self.review_calls.append(request)
                return make_review_response()

        from contract_agent.orchestration.protocol import AgentMode

        service = LegacyReviewService()
        servicer = AgentRpcServicer(app_context=_builtin_context())
        servicer.review_service = service  # type: ignore[assignment]

        with patch(
            "contract_agent.services.review_gateway.GatewayRouter._detect_mode",
            return_value=AgentMode.SINGLE,
        ):
            response = servicer.ReviewMultiAgent(
                agent_pb2.ReviewRequest(
                    file=agent_pb2.FilePayload(
                        file_name="contract.txt",
                        content=b"Section 1 Payment",
                    ),
                    contract_type="purchase",
                    our_side="buyer",
                ),
                None,
            )

        self.assertEqual(response.code, 200)
        self.assertEqual(len(service.review_calls), 1)
        request = service.review_calls[0]
        self.assertEqual(request.contract_text, "Section 1 Payment")
        self.assertEqual(request.contract_type, "purchase")
        self.assertEqual(request.our_side, "buyer")

    def test_review_multi_agent_single_mode_ignores_non_callable_review_document(self):
        class LegacyReviewService(FakeReviewService):
            review_document = None

            def __init__(self):
                self.review_calls = []

            def review(self, request):
                self.review_calls.append(request)
                return make_review_response()

        from contract_agent.orchestration.protocol import AgentMode

        service = LegacyReviewService()
        servicer = AgentRpcServicer(app_context=_builtin_context())
        servicer.review_service = service  # type: ignore[assignment]

        with patch(
            "contract_agent.services.review_gateway.GatewayRouter._detect_mode",
            return_value=AgentMode.SINGLE,
        ):
            response = servicer.ReviewMultiAgent(
                agent_pb2.ReviewRequest(
                    file=agent_pb2.FilePayload(
                        file_name="contract.txt",
                        content=b"Section 1 Payment",
                    ),
                    contract_type="purchase",
                    our_side="buyer",
                ),
                None,
            )

        self.assertEqual(response.code, 200)
        self.assertEqual(len(service.review_calls), 1)

    def test_review_multi_agent_parse_failure_writes_rpc_error_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(Path(tmp) / "rpc.jsonl")
            servicer = AgentRpcServicer(
                runtime_settings=Settings(chat_api_key="chat-key"),
                audit_logger=logger,
            )

            response = servicer.ReviewMultiAgent(
                agent_pb2.ReviewRequest(
                    file=agent_pb2.FilePayload(file_name="contract.exe", content=b"bad")
                ),
                None,
            )
            records = [
                json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(response.code, 400)
        rpc_errors = [record for record in records if record.get("event") == "grpc.error"]
        self.assertEqual(len(rpc_errors), 1, "Expected exactly one grpc.error audit record")
        rpc_error = rpc_errors[0]
        self.assertEqual(rpc_error["method"], "ReviewMultiAgent")
        self.assertEqual(rpc_error["code"], 400)
        self.assertEqual(rpc_error["error_type"], "UnsupportedFileType")

    def test_review_multi_agent_rejects_empty_request_before_pipeline_setup(self):
        with (
            patch("contract_agent.memory.manager.MemoryManager") as memory_cls,
            patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls,
        ):
            response = AgentRpcServicer(app_context=_builtin_context()).ReviewMultiAgent(
                agent_pb2.ReviewRequest(),
                None,
            )

        self.assertEqual(response.code, 400)
        self.assertFalse(memory_cls.called)
        self.assertFalse(supervisor_cls.called)

    def test_review_multi_agent_rejects_blank_text_before_pipeline_setup(self):
        with (
            patch("contract_agent.memory.manager.MemoryManager") as memory_cls,
            patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls,
        ):
            response = AgentRpcServicer(app_context=_builtin_context()).ReviewMultiAgent(
                agent_pb2.ReviewRequest(contract_text="   "),
                None,
            )

        self.assertEqual(response.code, 400)
        self.assertFalse(memory_cls.called)
        self.assertFalse(supervisor_cls.called)

    def test_review_multi_agent_stream_file_input_passes_parsed_text_to_supervisor(self):
        captured_inputs = []

        def fake_run(state, initial_input, on_event=None):
            captured_inputs.append(initial_input)
            state.status = PipelineStatus.COMPLETED
            return state

        servicer = AgentRpcServicer(app_context=_builtin_context())

        with patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls:
            supervisor_cls.return_value.run.side_effect = fake_run
            events = list(
                servicer.ReviewMultiAgentStream(
                    agent_pb2.ReviewRequest(
                        file=agent_pb2.FilePayload(
                            file_name="contract.txt",
                            content="第一条 付款".encode("utf-8"),
                        ),
                        contract_type="采购合同",
                        our_side="甲方",
                    ),
                    None,
                )
            )

        self.assertEqual(events[0].event, "pipeline_started")
        self.assertEqual(events[-1].event, "pipeline_completed")
        self.assertEqual(captured_inputs[0]["contract_text"], "第一条 付款")
        self.assertEqual(captured_inputs[0]["document_metadata"]["file_name"], "contract.txt")

    def test_review_multi_agent_stream_single_mode_falls_back_for_legacy_review_service(self):
        class LegacyReviewService(FakeReviewService):
            def __init__(self):
                self.review_calls = []

            def review(self, request):
                self.review_calls.append(request)
                return make_review_response()

        from contract_agent.orchestration.protocol import AgentMode

        service = LegacyReviewService()
        servicer = AgentRpcServicer(app_context=_builtin_context())
        servicer.review_service = service  # type: ignore[assignment]

        with patch(
            "contract_agent.services.review_gateway.GatewayRouter._detect_mode",
            return_value=AgentMode.SINGLE,
        ):
            events = list(
                servicer.ReviewMultiAgentStream(
                    agent_pb2.ReviewRequest(
                        file=agent_pb2.FilePayload(
                            file_name="contract.txt",
                            content=b"Section 1 Payment",
                        ),
                        contract_type="purchase",
                        our_side="buyer",
                    ),
                    None,
                )
            )

        self.assertEqual(events[0].event, "pipeline_completed")
        self.assertEqual(len(service.review_calls), 1)
        request = service.review_calls[0]
        self.assertEqual(request.contract_text, "Section 1 Payment")
        self.assertEqual(request.contract_type, "purchase")
        self.assertEqual(request.our_side, "buyer")

    def test_review_multi_agent_stream_parse_failure_yields_pipeline_failed_and_audit(self):
        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))

        events = list(
            servicer.ReviewMultiAgentStream(
                agent_pb2.ReviewRequest(
                    file=agent_pb2.FilePayload(file_name="contract.exe", content=b"bad")
                ),
                None,
            )
        )

        self.assertEqual(events[0].event, "pipeline_failed")
        payload = json.loads(events[0].data_json)
        self.assertEqual(payload["code"], 400)
        self.assertEqual(payload["error_type"], "UnsupportedFileType")
        self.assertIn("不支持", json.loads(events[0].data_json)["error"])

    def test_review_multi_agent_stream_parse_failure_writes_rpc_error_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            logger = AuditLogger(Path(tmp) / "rpc.jsonl")
            servicer = AgentRpcServicer(
                runtime_settings=Settings(chat_api_key="chat-key"),
                audit_logger=logger,
            )

            list(
                servicer.ReviewMultiAgentStream(
                    agent_pb2.ReviewRequest(
                        file=agent_pb2.FilePayload(file_name="contract.exe", content=b"bad")
                    ),
                    None,
                )
            )
            records = [
                json.loads(line) for line in logger.path.read_text(encoding="utf-8").splitlines()
            ]

        rpc_errors = [record for record in records if record.get("event") == "grpc.error"]
        self.assertEqual(len(rpc_errors), 1, "Expected exactly one grpc.error audit record")
        rpc_error = rpc_errors[0]
        self.assertEqual(rpc_error["method"], "ReviewMultiAgentStream")
        self.assertEqual(rpc_error["code"], 400)
        self.assertEqual(rpc_error["error_type"], "UnsupportedFileType")

    def test_review_multi_agent_stream_rejects_empty_request_before_pipeline_setup(self):
        with patch("contract_agent.orchestration.supervisor.SupervisorAgent") as supervisor_cls:
            events = list(
                AgentRpcServicer(app_context=_builtin_context()).ReviewMultiAgentStream(
                    agent_pb2.ReviewRequest(),
                    None,
                )
            )

        self.assertEqual(events[0].event, "pipeline_failed")
        payload = json.loads(events[0].data_json)
        self.assertEqual(payload["code"], 400)
        self.assertFalse(supervisor_cls.called)

    def test_parse_file_returns_400_for_corrupt_docx_and_pdf_uploads(self):
        servicer = AgentRpcServicer(app_context=_builtin_context())

        for file_name in ("bad.docx", "bad.pdf"):
            with self.subTest(file_name=file_name):
                response = servicer.ParseFile(
                    agent_pb2.ParseFileRequest(file_name=file_name, content=b"not a real file"),
                    None,
                )

                self.assertEqual(response.code, 400)
                self.assertNotIn("unexpected error", response.error)

    def test_embed_document_uses_source_type_as_doc_type_metadata(self):
        captured_chunks = []
        captured_documents = []

        class FakeRepository:
            def __init__(self, *args, **kwargs):
                pass

            def upsert_chunks(self, chunks, version):
                captured_chunks.extend(chunks)

        class FakeVectorStore:
            def add_documents(self, documents):
                captured_documents.extend(documents)

        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))

        with (
            patch("contract_agent.knowledge.repository.KnowledgeChunkRepository", FakeRepository),
            patch(
                "contract_agent.knowledge.rag.vector_store.load_vector_store",
                return_value=FakeVectorStore(),
            ),
            patch("contract_agent.knowledge.rag.vector_store.save_vector_store"),
        ):
            response = servicer.EmbedDocument(
                agent_pb2.EmbedDocumentRequest(
                    doc_id="clause-1",
                    text="违约责任条款",
                    source_type="clause",
                    title="违约责任",
                ),
                None,
            )

        self.assertEqual(response.code, 200)
        self.assertEqual(captured_chunks[0].doc_type, "clause")
        self.assertEqual(captured_documents[0].metadata["doc_type"], "clause")

    def test_embed_document_rejects_blank_required_fields_and_invalid_source_type(self):
        servicer = AgentRpcServicer(runtime_settings=Settings(chat_api_key="chat-key"))
        requests = [
            agent_pb2.EmbedDocumentRequest(doc_id="", text="正文", source_type="template"),
            agent_pb2.EmbedDocumentRequest(doc_id="doc-1", text="   ", source_type="template"),
            agent_pb2.EmbedDocumentRequest(doc_id="doc-1", text="正文", source_type="unknown"),
            agent_pb2.EmbedDocumentRequest(doc_id="doc-1", text="正文", source_type=""),
        ]

        for request in requests:
            with (
                self.subTest(request=request),
                patch("contract_agent.knowledge.repository.KnowledgeChunkRepository") as repo_cls,
                patch("contract_agent.knowledge.rag.vector_store.load_vector_store") as load_store,
            ):
                response = servicer.EmbedDocument(request, None)

                self.assertEqual(response.code, 400)
                self.assertFalse(repo_cls.called)
                self.assertFalse(load_store.called)

    def test_app_context_parser_config_is_passed_to_review_service_and_parser(self):
        context = configure_runtime(
            AppConfig.model_validate(
                {
                    "parser": {
                        "chunking": {"max_chars": 20, "target_chars": 10},
                    }
                }
            )
        )
        servicer = AgentRpcServicer(app_context=context)

        service = servicer._get_review_service()
        document = service.parse_file(
            "contract.txt",
            ("第一条 长条款\n" + "。".join(["长句"] * 30) + "。").encode("utf-8"),
        )

        self.assertIs(servicer.parser_config, context.parser_config)
        self.assertIs(service.parser_config, context.parser_config)
        self.assertGreater(len(document.clause_chunks), 1)

    def test_runtime_settings_without_context_derives_parser_config_snapshot(self):
        servicer = AgentRpcServicer(
            runtime_settings=Settings(
                parser_chunk_max_chars=20,
                parser_chunk_target_chars=10,
            )
        )

        self.assertIsInstance(servicer.parser_config, ParserConfig)
        self.assertEqual(servicer.parser_config.chunk_max_chars, 20)


if __name__ == "__main__":
    unittest.main()
