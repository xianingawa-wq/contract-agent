from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent import futures
from typing import TYPE_CHECKING

import grpc

from contract_agent.logger.audit import AuditLogger, get_audit_logger
from contract_agent.runtime.config import Settings, settings_snapshot
from contract_agent.schemas.chat import ChatRequest
from contract_agent.schemas.review import ReviewRequest

from contract_agent.orchestration.protocol import AgentMode, GatewayResponse, PipelineState, PipelineStatus

if TYPE_CHECKING:
    from contract_agent.agents.editor import ContractEditor
    from contract_agent.services.chat_service import ChatService
    from contract_agent.services.review_service import ReviewService

try:
    from contract_agent.agent_rpc import agent_pb2, agent_pb2_grpc
except Exception as exc:  # pragma: no cover
    raise RuntimeError("Missing gRPC generated files. Run: ./contract_agent/agent_rpc/gen_proto.sh") from exc


class AgentRpcServicer(agent_pb2_grpc.AgentRpcServiceServicer):
    def __init__(self, runtime_settings: Settings | None = None, audit_logger: AuditLogger | None = None) -> None:
        self.settings = runtime_settings or settings_snapshot()
        self.base_audit_logger = audit_logger or get_audit_logger()
        self.audit_logger = self.base_audit_logger.with_prefix("[RPC]", scope="rpc")
        self.review_service: "ReviewService | None" = None
        self.chat_service: "ChatService | None" = None
        self.contract_editor: "ContractEditor | None" = None
        self._embed_lock = threading.Lock()

    def _get_review_service(self) -> "ReviewService":
        if self.review_service is None:
            from contract_agent.services.review_service import ReviewService

            self.review_service = ReviewService(runtime_settings=self.settings, audit_logger=self.base_audit_logger)
        return self.review_service

    def _get_chat_service(self) -> "ChatService":
        if self.chat_service is None:
            from contract_agent.services.chat_service import ChatService

            self.chat_service = ChatService(runtime_settings=self.settings, audit_logger=self.base_audit_logger)
        return self.chat_service

    def Health(self, request, context):
        with self.audit_logger.trace("grpc.Health"):
            health = self._get_review_service().health()
            return agent_pb2.HealthResponse(
                status=health.status,
                llm_configured=health.llm_configured,
                knowledge_base_ready=health.knowledge_base_ready,
                version="agent-python-1.0",
                capabilities=["health", "parse", "review", "chat", "redraft", "embed"],
            )

    def ParseFile(self, request, context):
        with self.audit_logger.trace("grpc.ParseFile", file_name=request.file_name, content_bytes=len(request.content)):
            try:
                doc = self._get_review_service().parse_file(request.file_name, request.content)
                payload = {"document": doc.model_dump(mode="json")}
                return agent_pb2.JsonResponse(code=200, json=json.dumps(payload, ensure_ascii=False))
            except ValueError as exc:
                self._emit_rpc_error("ParseFile", 400, exc)
                return agent_pb2.JsonResponse(code=400, error=str(exc))
            except RuntimeError as exc:
                self._emit_rpc_error("ParseFile", 503, exc)
                return agent_pb2.JsonResponse(code=503, error=str(exc))
            except Exception as exc:
                self._emit_rpc_error("ParseFile", 500, exc)
                return agent_pb2.JsonResponse(code=500, error=f"unexpected error: {exc}")

    def Review(self, request, context):
        with self.audit_logger.trace("grpc.Review", contract_type=request.contract_type or None):
            try:
                if request.HasField("contract_text"):
                    result = self._get_review_service().review(
                        ReviewRequest(
                            contract_text=request.contract_text,
                            contract_type=request.contract_type or None,
                            our_side=request.our_side or "甲方",
                        )
                    )
                else:
                    result = self._get_review_service().review_file(
                        file_name=request.file.file_name,
                        content=request.file.content,
                        contract_type=request.contract_type or None,
                        our_side=request.our_side or "甲方",
                    )
                return agent_pb2.JsonResponse(code=200, json=result.model_dump_json())
            except ValueError as exc:
                self._emit_rpc_error("Review", 400, exc)
                return agent_pb2.JsonResponse(code=400, error=str(exc))
            except RuntimeError as exc:
                self._emit_rpc_error("Review", 503, exc)
                return agent_pb2.JsonResponse(code=503, error=str(exc))
            except Exception as exc:
                self._emit_rpc_error("Review", 500, exc)
                return agent_pb2.JsonResponse(code=500, error=f"unexpected error: {exc}")

    def Chat(self, request, context):
        with self.audit_logger.trace("grpc.Chat", payload_bytes=len(request.payload_json)):
            try:
                payload = json.loads(request.payload_json)
                chat_request = ChatRequest.model_validate(payload)
                result = self._get_chat_service().chat(chat_request)
                return agent_pb2.JsonResponse(code=200, json=result.model_dump_json())
            except ValueError as exc:
                self._emit_rpc_error("Chat", 400, exc)
                return agent_pb2.JsonResponse(code=400, error=str(exc))
            except RuntimeError as exc:
                self._emit_rpc_error("Chat", 503, exc)
                return agent_pb2.JsonResponse(code=503, error=str(exc))
            except Exception as exc:
                self._emit_rpc_error("Chat", 500, exc)
                return agent_pb2.JsonResponse(code=500, error=f"unexpected error: {exc}")

    def ChatStream(self, request, context):
        try:
            payload = json.loads(request.payload_json)
            chat_request = ChatRequest.model_validate(payload)
            for event in self._get_chat_service().chat_stream(chat_request):
                yield agent_pb2.ChatStreamResponse(
                    event=str(event.get("event", "message")),
                    data_json=json.dumps(event.get("data", {}), ensure_ascii=False),
                )
        except ValueError as exc:
            yield agent_pb2.ChatStreamResponse(
                event="error",
                data_json=json.dumps({"error": str(exc)}, ensure_ascii=False),
            )
        except RuntimeError as exc:
            yield agent_pb2.ChatStreamResponse(
                event="error",
                data_json=json.dumps({"error": str(exc)}, ensure_ascii=False),
            )
        except Exception as exc:
            yield agent_pb2.ChatStreamResponse(
                event="error",
                data_json=json.dumps({"error": f"chat stream internal error: {exc}"}, ensure_ascii=False),
            )

    def Redraft(self, request, context):
        with self.audit_logger.trace("grpc.Redraft", contract_type=request.contract_type):
            try:
                accepted_issues = json.loads(request.accepted_issues_json)
                if not self.settings.chat_api_key:
                    raise RuntimeError("CHAT_API_KEY 或 LLM_API_KEY 未配置，无法生成合同修订稿。QWEN_API_KEY 仍可作为兼容别名。")
                if self.contract_editor is None:
                    from contract_agent.agents.editor import ContractEditor

                    self.contract_editor = ContractEditor(runtime_settings=self.settings)
                editor = self.contract_editor
                revised = editor.redraft_contract(
                    contract_text=request.contract_text,
                    contract_type=request.contract_type,
                    our_side=request.our_side,
                    accepted_issues=accepted_issues,
                )
                return agent_pb2.JsonResponse(code=200, json=json.dumps({"revised_text": revised}, ensure_ascii=False))
            except ValueError as exc:
                self._emit_rpc_error("Redraft", 400, exc)
                return agent_pb2.JsonResponse(code=400, error=str(exc))
            except RuntimeError as exc:
                self._emit_rpc_error("Redraft", 503, exc)
                return agent_pb2.JsonResponse(code=503, error=str(exc))
            except Exception as exc:
                self._emit_rpc_error("Redraft", 500, exc)
                return agent_pb2.JsonResponse(code=500, error=f"unexpected error: {exc}")

    def ReviewMultiAgent(self, request, context):
        """Multi-agent review with pipeline orchestration."""
        import json

        from contract_agent.orchestration.gateway import GatewayRouter
        from contract_agent.agents.workers import (
            parser_agent, risk_checker_agent, legal_ref_agent,
            redrafter_agent,
        )
        from contract_agent.memory.manager import MemoryManager
        from contract_agent.orchestration.events import EventPublisher
        from contract_agent.orchestration.config import MultiAgentConfig

        try:
            config = MultiAgentConfig()
            gateway = GatewayRouter(config)
            memory = MemoryManager(config, runtime_settings=self.settings)
            publisher = EventPublisher()

            contract_text = request.contract_text or ""
            clause_count = len(contract_text) // 100

            mode = gateway._detect_mode(contract_text, clause_count)

            if mode == AgentMode.SINGLE:
                from contract_agent.orchestration.single import SingleAgentHandler
                state = PipelineState(
                    pipeline_id=str(uuid.uuid4()),
                    contract_id=contract_text[:64] or "unknown",
                    mode=AgentMode.SINGLE,
                    team="review",
                    status=PipelineStatus.PENDING,
                )
                single = SingleAgentHandler(runtime_settings=self.settings)
                state, result = single.run_review(
                    state,
                    contract_text=contract_text,
                    contract_type=request.contract_type,
                    our_side=request.our_side,
                )
                return agent_pb2.JsonResponse(code=200, json=json.dumps(result, ensure_ascii=False))

            # Multi-agent path — ReAct Supervisor
            route_resp = gateway.route(
                user_message="审查合同",
                contract_id=contract_text[:64],
                explicit_mode=mode,
                contract_clause_count=clause_count,
            )
            state = gateway.create_pipeline_state(route_resp, contract_id=contract_text[:64] or "unknown")

            from contract_agent.orchestration.supervisor import SupervisorAgent
            supervisor = SupervisorAgent(config, audit_logger=self.audit_logger)
            for agent_id, agent_fn in [
                ("parser", parser_agent),
                ("risk_checker", risk_checker_agent),
                ("legal_ref", legal_ref_agent),
                ("redrafter", redrafter_agent),
            ]:
                supervisor.register_agent(agent_id, agent_fn)

            initial_input = {
                "contract_text": contract_text,
                "contract_type": request.contract_type or None,
                "our_side": request.our_side or "甲方",
            }

            state = supervisor.run(state, initial_input, on_event=publisher.publish)

            # Save to memory tiers (best-effort)
            try:
                memory.save_pipeline_result(state)
            except Exception:
                pass

            report = {}
            supervisor_output = state.agent_outputs.get("supervisor")
            if supervisor_output:
                report = supervisor_output.structured_data.get("review_report", {})

            return agent_pb2.JsonResponse(
                code=200,
                json=json.dumps({
                    "pipeline_id": state.pipeline_id,
                    "mode": state.mode.value,
                    "status": state.status.value,
                    "report": report,
                    "agent_summaries": [
                        {
                            "agent_id": aid,
                            "status": ao.status.value,
                            "input_summary": ao.input_summary,
                            "findings_count": len(ao.findings),
                            "error_message": ao.error_message,
                        }
                        for aid, ao in state.agent_outputs.items()
                    ] + [
                        {
                            "agent_id": err["agent_id"],
                            "status": "failed",
                            "input_summary": "",
                            "findings_count": 0,
                            "error_message": err["error"],
                        }
                        for err in state.errors
                        if err["agent_id"] not in state.agent_outputs
                    ],
                }, ensure_ascii=False),
            )
        except ValueError as exc:
            return agent_pb2.JsonResponse(code=400, error=str(exc))
        except RuntimeError as exc:
            return agent_pb2.JsonResponse(code=503, error=str(exc))
        except Exception as exc:
            return agent_pb2.JsonResponse(code=500, error=f"multi-agent error: {exc}")

    def ReviewMultiAgentStream(self, request, context):
        """Multi-agent review with streaming events via gRPC server-streaming."""
        import json
        import uuid

        from contract_agent.orchestration.gateway import GatewayRouter
        from contract_agent.orchestration.supervisor import SupervisorAgent
        from contract_agent.agents.workers import (
            parser_agent, risk_checker_agent, legal_ref_agent, redrafter_agent,
        )
        from contract_agent.memory.manager import MemoryManager
        from contract_agent.orchestration.config import MultiAgentConfig

        try:
            config = MultiAgentConfig()
            gateway = GatewayRouter(config)
            supervisor = SupervisorAgent(config, audit_logger=self.audit_logger)
            memory = MemoryManager(config, runtime_settings=self.settings)

            for agent_id, agent_fn in [
                ("parser", parser_agent),
                ("risk_checker", risk_checker_agent),
                ("legal_ref", legal_ref_agent),
                ("redrafter", redrafter_agent),
            ]:
                supervisor.register_agent(agent_id, agent_fn)

            contract_text = request.contract_text or ""
            clause_count = len(contract_text) // 100
            mode = gateway._detect_mode(contract_text, clause_count)

            if mode == AgentMode.SINGLE:
                from contract_agent.orchestration.single import SingleAgentHandler
                state = PipelineState(
                    pipeline_id=str(uuid.uuid4()),
                    contract_id=contract_text[:64] or "unknown",
                    mode=AgentMode.SINGLE,
                    team="review",
                    status=PipelineStatus.PENDING,
                )
                single = SingleAgentHandler(runtime_settings=self.settings)
                state, result = single.run_review(state, contract_text=contract_text, contract_type=request.contract_type, our_side=request.our_side)
                yield agent_pb2.ChatStreamResponse(
                    event="pipeline_completed",
                    data_json=json.dumps({"pipeline_id": state.pipeline_id, "mode": "single", "result": result}, ensure_ascii=False),
                )
                return

            route_resp = gateway.route(
                user_message="审查合同",
                contract_id=contract_text[:64],
                explicit_mode=mode,
                contract_clause_count=clause_count,
            )
            state = gateway.create_pipeline_state(route_resp, contract_id=contract_text[:64] or "unknown")

            initial_input = {
                "contract_text": contract_text,
                "contract_type": request.contract_type or None,
                "our_side": request.our_side or "甲方",
            }

            # Emit pipeline_started immediately so frontend knows we're live
            yield agent_pb2.ChatStreamResponse(
                event="pipeline_started",
                data_json=json.dumps({"pipeline_id": state.pipeline_id, "mode": state.mode.value}, ensure_ascii=False),
            )

            # Real-time streaming: run pipeline in background thread, yield events via queue
            import queue
            import threading

            event_queue: queue.Queue = queue.Queue()
            _SENTINEL = object()

            def pipeline_runner():
                try:
                    state_result = supervisor.run(state, initial_input, on_event=lambda e: event_queue.put(e))
                    event_queue.put((_SENTINEL, state_result))
                except Exception as exc:
                    event_queue.put((_SENTINEL, None, exc))

            thread = threading.Thread(target=pipeline_runner, daemon=True)
            thread.start()

            while True:
                item = event_queue.get()
                if isinstance(item, tuple) and item[0] is _SENTINEL:
                    state = item[1]
                    if state is None:
                        raise item[2]  # re-raise exception from thread
                    break
                event = item
                data = {
                    "event_type": event.event_type,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "pipeline_id": event.pipeline_id,
                    "agent_id": event.agent_id,
                    "round": event.round,
                    "data": event.data,
                }
                yield agent_pb2.ChatStreamResponse(
                    event=event.event_type,
                    data_json=json.dumps(data, ensure_ascii=False),
                )

            # Final result — include actual findings from agents, not just LLM summary
            report = {}
            risk_findings = []
            redraft_suggestions = []
            legal_refs = []

            supervisor_output = state.agent_outputs.get("supervisor")
            if supervisor_output:
                report = supervisor_output.structured_data.get("review_report", {})

            risk_out = state.agent_outputs.get("risk_checker")
            if risk_out:
                risk_findings = risk_out.structured_data.get("risk_findings", [])

            redraft_out = state.agent_outputs.get("redrafter")
            if redraft_out:
                redraft_suggestions = redraft_out.structured_data.get("redraft_suggestions", [])

            legal_out = state.agent_outputs.get("legal_ref")
            if legal_out:
                legal_refs = legal_out.structured_data.get("legal_refs", [])

            final = {
                "event_type": "pipeline_completed",
                "pipeline_id": state.pipeline_id,
                "mode": state.mode.value,
                "status": state.status.value,
                "report": report,
                "risk_findings": risk_findings,
                "redraft_suggestions": redraft_suggestions,
                "legal_refs": legal_refs,
                "agent_summaries": [
                    {
                        "agent_id": aid,
                        "status": ao.status.value,
                        "input_summary": ao.input_summary,
                        "findings_count": len(ao.findings),
                        "error_message": ao.error_message,
                    }
                    for aid, ao in state.agent_outputs.items()
                ],
            }
            yield agent_pb2.ChatStreamResponse(
                event="pipeline_completed",
                data_json=json.dumps(final, ensure_ascii=False),
            )

        except Exception as exc:
            yield agent_pb2.ChatStreamResponse(
                event="pipeline_failed",
                data_json=json.dumps({"error": str(exc)}, ensure_ascii=False),
            )

    def EmbedDocument(self, request, context):
        with self.audit_logger.trace("grpc.EmbedDocument", doc_id=request.doc_id, source_type=request.source_type):
            try:
                from contract_agent.knowledge.repository import KnowledgeChunkRepository
                from contract_agent.schemas.knowledge import KnowledgeChunk
                from contract_agent.knowledge.rag.knowledge_documents import build_knowledge_documents
                from contract_agent.knowledge.rag.vector_store import load_vector_store, save_vector_store, build_vector_store

                chunk = KnowledgeChunk(
                    chunk_id=request.doc_id,
                    doc_name=request.title or "template",
                    doc_type="template",
                    title=request.title or "template",
                    text=request.text,
                    source_path=f"template/{request.source_type}",
                )
                repo = KnowledgeChunkRepository(runtime_settings=self.settings)
                repo.upsert_chunks([chunk], version="template")

                documents = build_knowledge_documents([chunk])

                with self._embed_lock:
                    try:
                        vector_store = load_vector_store(
                            self.settings.knowledge_vector_store_dir,
                            runtime_settings=self.settings,
                        )
                        vector_store.add_documents(documents)
                    except Exception:
                        vector_store = build_vector_store(documents, runtime_settings=self.settings)
                    save_vector_store(vector_store, self.settings.knowledge_vector_store_dir, runtime_settings=self.settings)

                return agent_pb2.JsonResponse(code=200, json=json.dumps({"status": "ok", "doc_id": request.doc_id}))
            except Exception as exc:
                self._emit_rpc_error("EmbedDocument", 500, exc)
                return agent_pb2.JsonResponse(code=500, error=f"embed failed: {exc}")

    def _emit_rpc_error(self, method: str, code: int, exc: Exception) -> None:
        self.audit_logger.emit(
            "grpc.error",
            method=method,
            code=code,
            error_type=type(exc).__name__,
            error=str(exc),
        )


def serve() -> None:
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=16),
        options=[
            ("grpc.max_send_message_length", 10 * 1024 * 1024),
            ("grpc.max_receive_message_length", 10 * 1024 * 1024),
        ],
    )
    agent_pb2_grpc.add_AgentRpcServiceServicer_to_server(AgentRpcServicer(), server)
    port = int(os.getenv("AGENT_GRPC_PORT", "50051"))
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
