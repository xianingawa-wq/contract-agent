# Contract Agent

Independent contract review agent runtime extracted from `context-verify-agent`.

The project contains the Python agent capabilities for parsing contracts, running rule and LLM-assisted review, retrieving legal knowledge, orchestrating multi-agent workflows, and serving the existing gRPC contract used by the Java backend.

## Layout

- `contract_agent/`: Python package for agent runtime.
- `contract_agent/agent_rpc/`: gRPC service entrypoint.
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
