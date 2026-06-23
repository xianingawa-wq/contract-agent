# Config YAML Unification Design

## Goal

Move every project-owned runtime configuration concern into `contract_agent/config/`, make YAML the single file-based configuration format, and make all runtime entrypoints inject configuration through one shared method. No legacy config modules or compatibility import paths are kept.

## Current State

The first migration already created `contract_agent/config/` for:

- `config_runtime.py`: `Settings`, global settings helpers, environment parsing.
- `config_multiagent.py`: `MultiAgentConfig`.
- `config_retrieval.py`: `RetrievalConfig`.

Remaining config responsibilities are still scattered:

- `contract_agent/model_config/` owns model endpoint config, profile persistence, environment model sources, resolver, and model profile service.
- `.run/cli_profile.json` is still JSON and separate from the global runtime settings path.
- `apply_model_runtime_config()` mutates module-level `settings`, so CLI profile application can affect unrelated requests in the same process.
- `EventPublisher` reads `REDIS_URL` directly.
- `agent_rpc.server.serve()` reads `AGENT_GRPC_PORT` directly.
- `SupervisorAgent`, `LLMReviewer`, `ContractEditor`, chat service, workers, embeddings, and reranker can still create LLM/provider clients through global default factories.
- RAG command-style entrypoints for ingest and recall evaluation read defaults directly from package-level settings.
- Provider, embedding, and reranker factories can still fall back to global settings instead of using the request/entrypoint configuration.

## Target Package Layout

All configuration modules must live under `contract_agent/config/` and use the `config_*.py` naming rule.

```text
contract_agent/config/
  __init__.py
  config_app.py          # AppConfig aggregate schema and AppContext
  config_loader.py       # YAML load/save, env overlay, global injection
  config_model.py        # ModelRole, ModelEndpointConfig, ModelRuntimeConfig, provider options
  config_model_store.py  # YAML model profile codec/store/resolver/service
  config_multiagent.py
  config_retrieval.py
  config_runtime.py
```

The `contract_agent/model_config/` package is removed after callers are migrated. The removed legacy path test must assert that `contract_agent.model_config` and its old submodules no longer import.

## YAML Files

YAML becomes the only project-owned configuration file format.

Default paths:

- Runtime config: `.run/config.yaml`
- CLI profile: `.run/cli_profile.yaml`

Example shape:

```yaml
app:
  name: Contract Review Agent
  default_contract_type: purchase_contract

models:
  chat:
    provider: openai_compatible
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: null
    model: qwen-max
  embedding:
    provider: openai_compatible
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: null
    model: text-embedding-v4
  rerank:
    provider: qwen
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: null
    model: qwen3-rerank
    endpoint: null

provider:
  temperature: 0
  use_responses_api: true
  embedding_batch_size: 10

retrieval:
  enable_rerank: true
  enable_hybrid: true
  fetch_k: 12
  final_k: 4
  dense_pool_k: 36
  rerank_timeout_seconds: 8
  rerank_max_retries: 0

vector_store:
  backend: milvus
  knowledge_vector_store_dir: knowledge/ingested/laws_faiss
  milvus_uri: http://127.0.0.1:19530
  milvus_collection_name: legal_knowledge_chunks
  milvus_consistency_level: Session
  milvus_retry_max: 3

database:
  postgres_dsn: postgresql+psycopg://postgres:postgres@127.0.0.1:5432/contract_agent

multiagent:
  redis_url: redis://localhost:6379/0
  redis_ttl_seconds: 1800
  max_retries_per_agent: 1
  pipeline_timeout_seconds: 300
  agent_timeout_seconds: 120
  supervisor_max_rounds: 5
  max_parallel_agents: 4
  hot_layer_rounds: 3
  warm_layer_rounds: 10
  context_warn_threshold: 0.6
  context_compress_threshold: 0.75
  context_force_threshold: 0.9

grpc:
  port: 50051
  max_workers: 16
  max_message_bytes: 10485760

limits:
  react_max_steps: 3
  max_upload_size_bytes: 5242880
  max_redraft_chunk_chars: 12000
  stream_max_seconds: 24.0
  stream_max_chars: 900

profile:
  path: .run/cli_profile.yaml
```

## Unified Injection Method

`contract_agent.config` exposes one injection method:

```python
def configure_runtime(
    config: AppConfig | None = None,
    *,
    config_path: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> AppContext:
    ...
```

`AppContext` is the entrypoint-owned dependency object:

```python
@dataclass(frozen=True)
class AppContext:
    config: AppConfig
    settings: Settings
    model_config: ModelRuntimeConfig
    retrieval_config: RetrievalConfig
    multiagent_config: MultiAgentConfig
```

Entrypoints call `configure_runtime()` once, then pass the resulting context or its explicit pieces into services and factories. Library code must not read environment variables or profile files directly.

The following creation paths are mandatory injection targets:

- `SupervisorAgent` receives `AppContext` or `ModelRuntimeConfig` and passes it to `get_chat_model()`.
- `LLMReviewer` and `ContractEditor` receive `ModelRuntimeConfig` or an already constructed LLM; no no-arg provider creation is allowed in request paths.
- `parser_agent`, `risk_checker_agent`, `legal_ref_agent`, `redrafter_agent`, and `summarizer_agent` receive `runtime_settings` and model config through task context.
- `AgentRpcServicer` creates `MultiAgentConfig`, `EventPublisher`, `SupervisorAgent`, and `SingleAgentHandler` from one `AppContext`.
- `get_chat_model()`, `get_embeddings()`, and `create_reranker_service()` accept explicit config and only use package-level runtime state after `configure_runtime()` has installed that state.
- `ChatService` stream limits, `OpenAIEmbeddings` batch size, gRPC limits, Redis URL, and Milvus retry max are read from `AppConfig`.
- RAG ingest and recall evaluation entrypoints call `configure_runtime()` and pass `AppContext.settings`, `AppContext.retrieval_config`, and vector-store config explicitly.

`settings`, `settings_snapshot()`, and `temporary_settings()` can remain as current global helpers during the transition, but their source of truth becomes `configure_runtime()` and YAML. They are not compatibility for old modules; they are the package-level runtime injection state.

## Environment Overlay

Environment variables are still accepted as deployment overrides, but only inside `config_loader.py`.

Rules:

1. Built-in defaults create an `AppConfig`.
2. YAML config overrides defaults.
3. Environment variables override YAML for deploy-time secrets and ports.
4. CLI profile YAML overrides only `models.*`.

No module outside `contract_agent/config/` may call `os.getenv()` for runtime configuration.

## Migration Rules

- Rename all config modules under `contract_agent/config/` to `config_*.py`.
- Remove the old model configuration package; do not leave import shims.
- Replace JSON profile store with YAML profile store.
- Add `PyYAML` as a direct project dependency in both `pyproject.toml` and `requirements.txt`.
- Update tests to import model config classes from `contract_agent.config`.
- Update docs from the old JSON profile filename to `.run/cli_profile.yaml`.
- Update historical plans/specs that mention removed paths by marking them superseded or changing examples so the final search gate has no misleading old config paths.
- Update Docker/runtime support files that contain runtime environment reads, including `contract_agent/agent_rpc/Dockerfile`.
- Keep `.env.example` as a deployment overlay reference, not as the primary configuration format.

## P0 Requirements

- P0-1: The old model configuration package and all old config paths are removed.
- P0-2: A YAML loader can create `AppConfig` and derive `Settings`, `ModelRuntimeConfig`, `RetrievalConfig`, and `MultiAgentConfig` from the same source.
- P0-3: CLI/demo/gRPC entrypoints use `configure_runtime()` rather than direct profile/env mutation.
- P0-4: Provider, embedding, reranker, RAG, services, and multiagent runtime accept explicit configuration and do not silently fall back to a different global source inside one request.
- P0-5: Full test suite passes in `.venv`.

## P1 Requirements

- P1-1: No runtime config `os.getenv()` remains outside `contract_agent/config/`.
- P1-2: `.env.example`, README, and `docs/architecture.md` describe YAML as the primary format.
- P1-3: Old JSON profile tests and docs are replaced by `.run/cli_profile.yaml`.
- P1-4: Constants identified as runtime config are represented in `AppConfig`: stream limits, embedding batch size, gRPC limits, Redis URL, and Milvus retry max.
- P1-5: Removed legacy path tests cover old model config and config modules.
- P1-6: Historical docs that still mention removed config paths are either updated or explicitly marked superseded and excluded from runtime guidance.

## Verification

Use these commands after implementation. The search gate intentionally excludes this active design and implementation plan because they document the migration from the old names:

```powershell
.\.venv\Scripts\python.exe -m compileall -q contract_agent tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
rg "os\.getenv|os\.environ|contract_agent\.model_config|cli_profile\.json|json_profile|runtime\.config|orchestration\.config|knowledge\.rag\.config" contract_agent tests docs README.md AGENTS.md --glob "!docs/config-yaml-unification-design.md" --glob "!docs/superpowers/plans/2026-06-23-config-yaml-unification.md"
```

Expected:

- Compile and unittest exit 0.
- Search output contains only removed-path assertions or historical superseded docs where explicitly marked.
