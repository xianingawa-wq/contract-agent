# Contract Agent

Independent contract review agent runtime extracted from `context-verify-agent`.

The project contains the Python agent capabilities for parsing contracts, running rule and LLM-assisted review, retrieving legal knowledge, orchestrating multi-agent workflows, and serving the existing gRPC contract used by the Java backend.

## Layout

- `contract_agent/`: Python package for agent runtime.
- `contract_agent/interfaces/`: CLI and minimal HTTP/FastAPI entrypoints.
- `contract_agent/config/`: YAML runtime configuration, role-based model profiles, and AppContext injection.
- `contract_agent/runtime/`: database sessions and schema initialization.
- `contract_agent/agent_rpc/`: gRPC service entrypoint.
- `contract_agent/parser/`: closed contract parser package for text/file/path loading, metadata extraction, spans, and clause chunks.
- `contract_agent/review/`: local rule-review facade used by the CLI.
- `contract_agent/rulesets/`: built-in rule definitions consumed by the rule engine.
- `contract_agent/knowledge/`: persisted knowledge metadata, ingestion, vector stores, retrieval, and reranking.
- `contract_agent/memory/`: multi-agent hot/warm/cold memory stores and manager.
- `contract_agent/provider/`: model provider abstraction for chat, embeddings, structured output, and tool calls.
- `contract_agent/constants/`: LLM and agent prompt constants.
- `contract_agent/agents/`: reviewer, editor, parser, risk checker, legal reference, and redrafter roles.
- `contract_agent/orchestration/`: gateway, supervisor, protocol models, events, and pipeline orchestration.
- `contract_agent/logger/`: structured audit logging for review and agent execution flows.
- `contract_agent/trace/`: token usage tracing and estimated consumption summaries.
- `knowledge/`: copied legal knowledge base inputs.
- `docs/architecture.md`: migration architecture report.

## Run

Install dependencies, then start the gRPC service:

```powershell
pip install -e .
contract-agent-grpc
```

The default gRPC port is `50051`; override it in `.run/config.yaml` or, for deployment overlays, with `AGENT_GRPC_PORT`.

Run a local rule-based review without external services:

```powershell
contract-agent review .\contract.txt --type purchase --side buyer
contract-agent review .\contract.txt --format json
contract-agent config
```

Open the interactive CLI demo:

```powershell
contract-agent demo
```

The demo shows a welcome banner, checks whether a local profile exists at `.run/cli_profile.yaml`, guides first-time setup for separate chat, embedding, and rerank model endpoints, checks the database component, verifies the configured model providers, then opens a small agent console. The setup wizard offers provider presets for OpenAI, DashScope/Qwen, and a custom OpenAI-compatible URL. API keys are saved into the local YAML profile for later CLI runs, while `/config` only reports whether each key is configured. The console currently supports `/help`, `/status`, `/config`, and `/exit`, plus a demo agent reply for normal chat messages.

Provider and reranker construction use a consistent package layout:

```text
interface.py  # public Protocols and dataclasses
service.py    # orchestration that depends on interfaces
impl/         # concrete implementations
factory.py    # provider/profile/reranker creation
```

The `provider` and `knowledge.rag.rerank` packages follow this shape. Role-based model configuration now lives in `contract_agent.config` as `ModelRole`, `ModelEndpointConfig`, `ModelRuntimeConfig`, YAML profile stores, and `configure_runtime()`. Provider implementations are grouped by vendor: OpenAI code lives under `contract_agent.provider.impl.openai`, and DashScope/Qwen code lives under `contract_agent.provider.impl.dashscope`.

## Audit Logs

Service-backed review flows write structured JSONL audit events to `.run/audit.jsonl`. The logger records review start, rule-check completion, per-risk LLM enrichment, review completion, and review failure events so the audit path can be inspected after a run.

## Token Trace

Service-backed review responses include a `trace` object with estimated input, output, and total token usage. The first implementation uses local character-based estimates so users can see approximate consumption immediately; provider-reported token usage can replace those estimates later.

## LLM Configuration

`contract-agent` uses a provider abstraction with an OpenAI-compatible default. File-based runtime configuration is YAML, with `.run/config.yaml` as the primary runtime file and `.run/cli_profile.yaml` for CLI model profile overrides. Environment variables are deployment overlays and are read only by `contract_agent.config`.

Start from `config.example.yaml` and copy it to `.run/config.yaml` for local runtime configuration.

```powershell
$env:LLM_PROVIDER = "openai_compatible"
$env:LLM_API_KEY = "..."
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_CHAT_MODEL = "gpt-4.1"
$env:LLM_EMBEDDING_MODEL = "text-embedding-3-large"
```

The older Qwen variables still work as aliases: `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_CHAT_MODEL`, and `QWEN_EMBEDDING_MODEL`.
