# Contract Agent

Independent contract review agent runtime extracted from `context-verify-agent`.

The project contains the Python agent capabilities for parsing contracts, running rule and LLM-assisted review, retrieving legal knowledge, orchestrating multi-agent workflows, and serving the existing gRPC contract used by the Java backend.

## Layout

- `contract_agent/`: Python package for agent runtime.
- `contract_agent/interfaces/`: CLI and minimal HTTP/FastAPI entrypoints.
- `contract_agent/runtime/`: environment-backed settings, database sessions, and schema initialization.
- `contract_agent/agent_rpc/`: gRPC service entrypoint.
- `contract_agent/review/`: local rule-review facade used by the CLI.
- `contract_agent/rulesets/`: built-in rule definitions consumed by the rule engine.
- `contract_agent/knowledge/`: persisted knowledge metadata, ingestion, vector stores, retrieval, and reranking.
- `contract_agent/memory/`: multi-agent hot/warm/cold memory stores and manager.
- `contract_agent/provider/`: model provider abstraction for chat, embeddings, structured output, and tool calls.
- `contract_agent/constants/`: LLM and agent prompt constants.
- `contract_agent/agents/`: reviewer, editor, parser, risk checker, legal reference, and redrafter roles.
- `contract_agent/orchestration/`: gateway, supervisor, protocol models, events, and pipeline orchestration.
- `contract_agent/logger/`: structured audit logging for review and agent execution flows.
- `knowledge/`: copied legal knowledge base inputs.
- `docs/architecture.md`: migration architecture report.

## Run

Install dependencies, then start the gRPC service:

```powershell
pip install -e .
contract-agent-grpc
```

The default gRPC port is `50051`; override it with `AGENT_GRPC_PORT`.

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

The demo shows a welcome banner, checks whether a local profile exists at `.run/cli_profile.json`, guides first-time model setup, checks the database component, verifies the configured model provider, then opens a small agent console. The console currently supports `/help`, `/status`, `/config`, and `/exit`, plus a demo agent reply for normal chat messages.

## Audit Logs

Service-backed review flows write structured JSONL audit events to `.run/audit.jsonl`. The logger records review start, rule-check completion, per-risk LLM enrichment, review completion, and review failure events so the audit path can be inspected after a run.

## LLM Configuration

`contract-agent` uses a provider abstraction with an OpenAI-compatible default. Official OpenAI and compatible services can be selected by environment variables:

```powershell
$env:LLM_PROVIDER = "openai_compatible"
$env:LLM_API_KEY = "..."
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_CHAT_MODEL = "gpt-4.1"
$env:LLM_EMBEDDING_MODEL = "text-embedding-3-large"
```

The older Qwen variables still work as aliases: `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_CHAT_MODEL`, and `QWEN_EMBEDDING_MODEL`.
