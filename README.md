# Contract Agent

Independent contract review agent runtime extracted from `context-verify-agent`.

The project contains the Python agent capabilities for parsing contracts, running rule and LLM-assisted review, retrieving legal knowledge, orchestrating multi-agent workflows, and serving the existing gRPC contract used by the Java backend.

## Layout

- `contract_agent/`: Python package for agent runtime.
- `contract_agent/interfaces/`: CLI and minimal HTTP/FastAPI entrypoints.
- `contract_agent/runtime/`: environment-backed runtime settings.
- `contract_agent/agent_rpc/`: gRPC service entrypoint.
- `contract_agent/review/`: local rule-review facade used by the CLI.
- `contract_agent/rulesets/`: built-in rule definitions consumed by the rule engine.
- `contract_agent/multi_agent/`: gateway, supervisor, protocols, memory, and agents.
- `contract_agent/llm/`: prompts and model client/provider integration.
- `contract_agent/rag/`: knowledge ingestion, vector stores, retrieval, and reranking.
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
