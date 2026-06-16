# Contract Agent Architecture Report

## Source System Findings

The original `context-verify-agent` repository contains a split product:

- `frontend/`: React UI for contract workflows.
- `backend-java/`: Spring Boot API and persistence-facing business backend.
- `app/`: Python agent runtime kept for contract parsing, review, chat, RAG, multi-agent orchestration, and gRPC.
- `knowledge/`: legal knowledge seed content and retrieval baselines.
- `tests/`: Python tests around parser, RAG, review service, chat service, and multi-agent flow.

The Python runtime is already conceptually isolated from the Java backend. Its public integration surface is primarily the original `app/agent_rpc/server.py`, which exposes health, parse, review, chat, redraft, embedding, and multi-agent review RPCs.

There is no single `app/agent` package in the source project. The agent closure is spread across:

- `app/core`: environment-backed runtime configuration.
- `app/llm`: LangChain prompt templates, Qwen/OpenAI-compatible model wiring, and reviewer/editor helpers.
- `app/services`: parser, extractor, classifier, rule review, chat, and ReAct-style tool runtime.
- `app/rag`: legal document loading, chunking, vector stores, retriever, reranker, and recall evaluation.
- `app/multi_agent`: gateway, pipeline, supervisor, specialist agents, memory, events, and protocol models.
- `app/agent_rpc`: gRPC integration boundary used by the Java backend.
- `app/db` and `app/schemas`: persistence models and Pydantic contracts required by the runtime.
- `knowledge`: legal seed content, ingested chunks, and recall baseline data.

## Extracted Runtime Boundary

The independent `contract-agent` project now owns the Python agent closure:

- `contract_agent/core`: environment-backed settings.
- `contract_agent/interfaces`: CLI and minimal HTTP/FastAPI adapters.
- `contract_agent/llm`: prompt templates and LLM client wiring.
- `contract_agent/review`: local CLI rule-review facade, report models, and renderers.
- `contract_agent/services`: deterministic parsing, extraction, classification, rule review, chat runtime, and review orchestration.
- `contract_agent/rag`: legal chunking, vector store construction, retrieval, reranking, and recall evaluation.
- `contract_agent/multi_agent`: gateway routing, single-agent path, supervisor loop, protocol models, memory tiers, and event publishing.
- `contract_agent/agent_rpc`: gRPC server and generated protobuf modules.
- `contract_agent/schemas`: Pydantic request and response contracts.
- `contract_agent/db`: optional PostgreSQL persistence for knowledge and multi-agent memory.
- `knowledge/`: copied legal knowledge base inputs.

The source repository should now treat `contract-agent` as the Python agent source of truth. Any remaining source-project Python entrypoints should be compatibility shims or process launchers, while the Java backend and frontend remain in `context-verify-agent`.

## Current Execution Flow

1. The caller submits contract text or a file through the gRPC service, Python service layer, or CLI.
2. `ReviewService` parses text, classifies contract type, extracts fields, runs deterministic rules, retrieves legal context, and asks the LLM to enrich each risk.
3. `ContractKnowledgeRetriever` loads Milvus or FAISS based on settings and can rerank retrieved chunks.
4. Multi-agent review routes through `GatewayRouter`; simple requests can run through `SingleAgentHandler`, while deeper flows use `SupervisorAgent` and specialist agents.
5. The supervisor uses the configured chat model to select agent calls and synthesize a final report.

## Migration Commit Plan

1. Extract the Python agent runtime and knowledge base into `contract-agent`.
2. Add a provider abstraction for chat, embeddings, structured outputs, and tool-call oriented model use.
3. Implement an OpenAI-compatible provider that supports official OpenAI and API-compatible services through base URL and model settings.
4. Add configuration-driven model switching and preserve Qwen-compatible environment aliases.
5. Add a CLI for local review and health/config inspection.
6. Run import, unit, and CLI checks; commit each phase with a focused message.

Implemented commit history:

- `9ca5d01 Initial project setup`
- `5a7bf08 Extract Python agent runtime`
- `797b7c3 Add OpenAI-compatible LLM provider`

The remaining commits after this report should keep the same discipline:

- CLI and local rule-review facade.
- Runtime entrypoint cleanup and import-light LLM provider hardening.
- Documentation/report updates.

## Risks

- Some source strings display mojibake in the current checkout. The migration preserves bytes and behavior rather than rewriting text content.
- Milvus, PostgreSQL, Redis, and external LLM calls remain optional runtime dependencies; local tests should avoid requiring live infrastructure.
- The copied generated protobuf files retain their original generated shape and may need regeneration if `proto/agent.proto` changes.
- Existing source code relies on LangChain chat model behavior. Provider abstraction must preserve `.invoke()` compatibility where existing chains expect it.

## OpenAI Documentation Notes

Context7 was requested, but no Context7 tool or plugin was available in this Codex session. Official OpenAI documentation was used instead:

- Responses API migration guide: https://developers.openai.com/api/docs/guides/migrate-to-responses
- Function calling guide: https://developers.openai.com/api/docs/guides/function-calling
- Structured Outputs guide: https://developers.openai.com/api/docs/guides/structured-outputs
- OpenAI Python SDK package: https://pypi.org/project/openai/

The implementation direction follows the current OpenAI guidance that the Responses API is the preferred interface for agent-like model calls, including multi-turn state and tools. Function calling is modeled as tool definitions, model-emitted calls, application-side execution, and tool-output continuation. Structured Outputs are implemented through JSON Schema with `strict: true`; helper code recursively adds `additionalProperties: false` for object schemas to keep outputs constrained.

The provider keeps Chat Completions fallback behavior because many OpenAI-compatible services support chat completions before they fully support Responses. This preserves current Qwen/DashScope behavior while allowing official OpenAI usage by configuration.

## Verification

Run from `E:\Progarms\contract-agent`:

```powershell
python -m compileall -q contract_agent tests
python -m unittest discover -s tests -v
python -c "from contract_agent.agent_rpc.server import AgentRpcServicer; print('import-ok')"
contract-agent config
```

Infrastructure-backed checks such as Milvus retrieval, PostgreSQL-backed multi-agent memory, and live OpenAI/Qwen calls require corresponding services and API keys.
