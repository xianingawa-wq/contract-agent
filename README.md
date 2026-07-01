# Contract Agent

[简体中文](README.zh-CN.md) | English

Contract Agent is a Python runtime for contract review. It parses contract files, runs local rule checks, enriches findings with LLM reasoning, retrieves legal references from a bundled knowledge base, and exposes the workflow through CLI, HTTP/FastAPI, and gRPC entrypoints.

The repository is organized as an independent agent service that can be run locally for review demos or deployed behind an existing backend through the gRPC contract.

## Quick Start

Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Create a local runtime config:

```bash
mkdir -p .run
cp config.example.yaml .run/config.yaml
```

Edit `.run/config.yaml` and fill in model API keys for chat, embedding, and rerank as needed. Environment variables can override deployment-sensitive values.

Run the interactive local console:

```bash
contract-agent demo
```

Run a contract review from the CLI:

```bash
contract-agent review ./contract.txt --type purchase --side buyer
contract-agent review ./contract.txt --format json
```

Start the gRPC service:

```bash
contract-agent-grpc
```

The default gRPC bind address is `127.0.0.1:50051`. Override it in `.run/config.yaml` or with `AGENT_GRPC_HOST` and `AGENT_GRPC_PORT`.

## Configuration

Runtime configuration is YAML-first:

- `config.example.yaml`: committed example config.
- `.run/config.yaml`: local runtime config, ignored by git.
- `.run/cli_profile.yaml`: optional CLI profile created by the demo wizard, ignored by git.
- Environment variables: deployment overlays for secrets and service addresses.

Common model settings:

```bash
export LLM_PROVIDER=openai_compatible
export LLM_API_KEY=...
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_CHAT_MODEL=gpt-4.1
export LLM_EMBEDDING_MODEL=text-embedding-3-large
```

The default example config is compatible with DashScope/Qwen-style OpenAI-compatible endpoints. Legacy `QWEN_*` variables are still accepted as aliases.

## Package Architecture

```text
contract_agent/interfaces/       CLI and HTTP/FastAPI entrypoints
contract_agent/agent_rpc/        gRPC service, protobuf bindings, Docker entrypoint
contract_agent/config/           YAML loading, environment overlays, AppContext injection
contract_agent/runtime/          Database schema and SQLAlchemy session helpers
contract_agent/parser/           Contract file loading, conversion, Markdown parsing, chunks
contract_agent/review/           Local review facade, rule models, report rendering
contract_agent/rulesets/         Built-in contract review rule definitions
contract_agent/services/         Application services: review, chat, rule engine, gateway
contract_agent/schemas/          Pydantic request/response schemas
contract_agent/provider/         LLM, embedding, structured output, and tool-call providers
contract_agent/knowledge/        Legal knowledge persistence, RAG, vector store, reranking
contract_agent/agents/           Reviewer, editor, parser, risk checker, legal reference roles
contract_agent/orchestration/    Multi-agent protocol, supervisor, runtime, pipeline events
contract_agent/memory/           Hot/warm/cold memory stores for agent workflows
contract_agent/logger/           Structured component and audit logging
contract_agent/constants/        LLM and agent prompt constants
contract_agent/trace/            Token usage estimation and trace summaries
```

Supporting top-level directories:

```text
knowledge/          Bundled legal knowledge inputs and FAISS assets
proto/              Source protobuf contract
picture/            Architecture and package-view diagrams
tests/              Unit and integration-style test suite
```

## Review Flow

The service-backed review path is:

1. Input normalization accepts raw text, uploaded file bytes, or local file paths.
2. `contract_agent/parser/` converts supported files into Markdown and parsed document models.
3. `ContractClassifier` detects or normalizes the contract type.
4. `ContractExtractor` extracts basic contract fields.
5. `RuleEngine` runs local rules from `contract_agent/rulesets/`.
6. `contract_agent/knowledge/` retrieves relevant legal references from the vector store and optional reranker.
7. `LLMReviewer` enriches risk explanations and suggestions.
8. `ReviewService` returns summary, extracted fields, risks, report text, references, and token trace.

The CLI `review` command uses this same service path, so LLM and knowledge-base configuration must be available for full review execution.

## Parser Design

The parser package is intentionally layered:

```text
ParserSource
  -> converter backend
  -> MarkdownDocument
  -> MarkdownParsedService
  -> ParsedDocument
  -> clause chunks / tables / semantic graph / serializers
```

Supported file suffixes are configured under `parser.allowed_suffixes`; the default config enables `.txt`, `.docx`, `.pdf`, `.md`, `.html`, `.csv`, and `.xlsx` style inputs. Converter backends are routed by `ParserBackendRouter`, with `docling` and `builtin` enabled by default.

## Knowledge And RAG

The repository includes a small bundled legal knowledge base:

```text
knowledge/laws/民法典.txt
knowledge/ingested/laws_chunks.jsonl
knowledge/ingested/laws_faiss/index.faiss
knowledge/ingested/laws_faiss/index.pkl
knowledge/cases/retrieval_recall_gold_seed_50.jsonl
```

By default, retrieval uses the local FAISS assets in `knowledge/ingested/laws_faiss`. The config also contains Milvus connection settings for deployments that need an external vector store.

Retrieval behavior is controlled under:

- `retrieval.enable_hybrid`
- `retrieval.enable_rerank`
- `retrieval.fetch_k`
- `retrieval.final_k`
- `vector_store.backend`
- `vector_store.knowledge_vector_store_dir`

## Service Entrypoints

CLI:

```bash
contract-agent demo
contract-agent config
contract-agent review ./contract.txt --type purchase --side buyer
```

gRPC:

```bash
contract-agent-grpc
```

HTTP/FastAPI:

The minimal HTTP interface lives in `contract_agent/interfaces/http.py`. It is intended as a lightweight adapter around the same service layer.

## Tests And Quality Gates

Run the local checks before submitting changes:

```bash
python -m ruff format --check contract_agent tests
python -m ruff check contract_agent tests
python -m unittest discover -s tests -v
```

The test suite covers parser behavior, package boundaries, config loading, review rules, RAG retrieval/rerank behavior, gRPC service handling, runtime schema helpers, audit logging, and CLI flows.

## Audit Logs And Token Trace

Service-backed review flows write structured JSONL audit events to `.run/audit.jsonl`. These events include review start, parser activity, rule completion, LLM enrichment, review completion, and failures.

Review responses also include a `trace` object with estimated input, output, and total token usage. The current implementation uses local character-based estimates so usage remains visible even when providers do not return token accounting.
