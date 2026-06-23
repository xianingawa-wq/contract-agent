# Config YAML Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate all project-owned runtime configuration into `contract_agent/config/`, make YAML the single file-based configuration format, and inject config through `configure_runtime()`.

**Architecture:** Introduce an aggregate `AppConfig` and `AppContext` in the config package. Move model endpoint/profile config from `model_config` into `config`, replace JSON profile files with YAML, and update entrypoints/factories to use explicit context-derived config rather than direct environment/profile reads.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, unittest, existing `.venv`.

## Global Constraints

- All project-owned config modules must live under `contract_agent/config/`.
- All files in `contract_agent/config/` except `__init__.py` must use `config_*.py` naming.
- Do not keep compatibility shims for the old model configuration package, `contract_agent.runtime.config`, `contract_agent.orchestration.config`, or `contract_agent.knowledge.rag.config`.
- YAML is the only project-owned file format for runtime/profile config.
- Environment variables are deployment overrides and may only be read inside `contract_agent/config/`.
- Entry points must call `configure_runtime()` once and inject the resulting config/context.

---

### Task 1: Add AppConfig YAML Loader and Context

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`
- Create: `contract_agent/config/config_app.py`
- Create: `contract_agent/config/config_loader.py`
- Modify: `contract_agent/config/__init__.py`
- Modify: `tests/test_config_package.py`

**Interfaces:**
- Produces: `AppConfig`, `AppContext`, `load_app_config(path=None, environ=None)`, `configure_runtime(config=None, config_path=None, environ=None)`.
- Produces adapters: `AppConfig.to_settings()`, `AppConfig.to_model_runtime_config()`, `AppConfig.to_retrieval_config()`, `AppConfig.to_multiagent_config()`.

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
config = load_app_config(path)
self.assertEqual(config.models.chat.model, "yaml-chat")
self.assertEqual(config.to_settings().chat_model, "yaml-chat")
self.assertEqual(config.to_retrieval_config().fetch_k, 20)
self.assertEqual(config.to_multiagent_config().agent_timeout_seconds, 7)
context = configure_runtime(config)
self.assertEqual(context.settings.chat_model, "yaml-chat")
self.assertEqual(settings_snapshot().chat_model, "yaml-chat")
```

- [ ] **Step 1a: Add direct YAML dependency**

Add the same direct dependency to both project dependency files:

```toml
"PyYAML==6.0.3",
```

```text
PyYAML==6.0.3
```

- [ ] **Step 2: Verify red**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_config_package -v
```

Expected: import or attribute failures for missing `load_app_config` / `AppConfig`.

- [ ] **Step 3: Implement minimal loader**

Use `yaml.safe_load`, Pydantic models, and current defaults. Implement environment overlay only for existing env names currently handled by `load_settings_from_env()`.

- [ ] **Step 4: Verify green**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_config_package tests.test_runtime_config -v
```

Expected: PASS.

### Task 2: Move Model Config Into Config Package and YAML Profile Store

**Files:**
- Create: `contract_agent/config/config_model.py`
- Create: `contract_agent/config/config_model_store.py`
- Delete: `contract_agent/model_config/`
- Modify: all imports from `contract_agent.model_config.*`
- Modify: tests that reference `model_config`

**Interfaces:**
- `DEFAULT_MODEL_PROFILE_PATH = PROJECT_ROOT / ".run" / "cli_profile.yaml"`
- `YamlModelProfileStore(path: Path)`
- `YamlModelProfileCodec`
- `create_model_config_resolver(profile_path=None, app_config=None)`
- `create_model_profile_service(profile_path=None, app_config=None)`

- [ ] **Step 1: Write failing tests**

Update model config tests to import from `contract_agent.config`, use `profile.yaml`, and write YAML content. Add removed path assertions for `contract_agent.model_config`.

- [ ] **Step 2: Verify red**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_model_config tests.test_removed_legacy_paths -v
```

Expected: failures because YAML store and new imports are not implemented yet.

- [ ] **Step 3: Move implementation**

Move dataclasses/protocols/factory/service/store under `contract_agent/config/`. Replace JSON codec/store with YAML codec/store. Remove legacy profile decoder.

- [ ] **Step 4: Update callers**

Update CLI, console, provider factory/service tests, reranker tests, and package boundary tests to import from `contract_agent.config`.

- [ ] **Step 5: Verify green**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_model_config tests.test_cli tests.test_cli_demo tests.test_llm_provider tests.test_package_boundaries tests.test_removed_legacy_paths -v
```

Expected: PASS.

### Task 3: Close Runtime Injection Gaps

**Files:**
- Modify: `contract_agent/provider/client.py`
- Modify: `contract_agent/provider/factory.py`
- Modify: `contract_agent/provider/service.py`
- Modify: `contract_agent/knowledge/rag/rerank/factory.py`
- Modify: `contract_agent/knowledge/rag/vector_store.py`
- Modify: `contract_agent/knowledge/rag/retriever.py`
- Modify: `contract_agent/knowledge/rag/ingest.py`
- Modify: `contract_agent/knowledge/rag/eval_recall.py`
- Modify: `contract_agent/orchestration/supervisor.py`
- Modify: `contract_agent/agents/reviewer.py`
- Modify: `contract_agent/services/chat_service.py`
- Modify: `contract_agent/services/review_service.py`
- Modify: `contract_agent/agents/editor.py`
- Modify: `contract_agent/agents/workers.py`
- Modify: `contract_agent/provider/impl/openai/embeddings.py`
- Modify: related tests

**Interfaces:**
- `get_chat_model(model_config: ModelRuntimeConfig | None = None, runtime_settings: Settings | None = None)`
- `get_embeddings(model_config: ModelRuntimeConfig | None = None, runtime_settings: Settings | None = None)`
- `create_reranker_service(endpoint: ModelEndpointConfig | None = None, runtime_settings: Settings | None = None)`
- `SupervisorAgent(config=None, llm=None, audit_logger=None, app_context=None, model_config=None)`
- `LLMReviewer(runtime_settings=None, model_config=None, llm=None)`
- `ContractEditor(runtime_settings=None, model_config=None, llm=None)`

- [ ] **Step 1: Write failing tests**

Add or update tests proving constructor-injected settings/config are used by chat, review, workers, RAG, embedding, reranker, supervisor, reviewer, editor, ingest, and recall evaluation paths without reading a different global snapshot. Include a worker task context case where `runtime_settings` and `model_config` are present, and assert it does not call `settings_snapshot()`.

- [ ] **Step 2: Verify red**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_service_config_injection tests.test_rag_eval_config_injection tests.test_rag_retriever_e2e tests.test_reranker -v
```

Expected: at least one failure showing global fallback still wins.

- [ ] **Step 3: Implement explicit config threading**

Propagate `Settings` / `ModelRuntimeConfig` from services, supervisor, reviewer, editor, and workers into provider and reranker factory calls. Runtime constants must also move to `AppConfig` and be consumed at their use sites:

- `ChatService.STREAM_MAX_SECONDS` -> `AppConfig.limits.stream_max_seconds`
- `ChatService.STREAM_MAX_CHARS` -> `AppConfig.limits.stream_max_chars`
- `OpenAIEmbeddings(chunk_size=10)` -> `AppConfig.provider.embedding_batch_size`
- `KnowledgeIngestor.ingest_laws(default directory)` -> `AppConfig.vector_store.knowledge_vector_store_dir`
- `run_evaluation()` default settings/retrieval config -> `AppContext`
- `milvus_retry_max` -> `AppConfig.vector_store.milvus_retry_max`

- [ ] **Step 4: Verify green**

Run the same command. Expected: PASS.

### Task 4: Entry Point YAML Injection and Direct Env Removal

**Files:**
- Modify: `contract_agent/interfaces/cli.py`
- Modify: `contract_agent/interfaces/console.py`
- Modify: `contract_agent/interfaces/console_paths.py`
- Modify: `contract_agent/agent_rpc/server.py`
- Modify: `contract_agent/agent_rpc/Dockerfile`
- Modify: `contract_agent/orchestration/events.py`
- Modify: `contract_agent/orchestration/supervisor.py`
- Modify: `contract_agent/orchestration/runtime.py`
- Modify: `contract_agent/knowledge/rag/ingest.py`
- Modify: `contract_agent/knowledge/rag/eval_recall.py`
- Modify: tests for CLI, console, RPC, orchestration events

**Interfaces:**
- CLI accepts `--config`, defaulting to `.run/config.yaml`.
- Demo profile path defaults to `.run/cli_profile.yaml`.
- gRPC `serve()` uses `configure_runtime()` for port/workers/message limits.
- `EventPublisher` takes explicit `redis_url`.
- `AgentRpcServicer` stores one `AppContext` and creates `MultiAgentConfig`, `EventPublisher`, `SupervisorAgent`, and worker contexts from that same object.
- RAG ingest/eval command entrypoints call `configure_runtime()` once and pass explicit config into `KnowledgeIngestor` and recall evaluation.
- Dockerfile healthcheck uses the configured default port literal or an entrypoint-provided variable without `os.getenv` in inline Python.

- [ ] **Step 1: Write failing tests**

Test YAML config path changes CLI config output, profile YAML is written/read, gRPC port/workers/message limits come from `AppConfig`, `EventPublisher` no longer needs `REDIS_URL`, RAG ingest/eval entrypoints use `configure_runtime()`, and multiagent RPC paths do not call `MultiAgentConfig()` without context.

- [ ] **Step 2: Verify red**

Run:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_cli tests.test_cli_demo tests.test_agent_rpc_servicer tests.test_orchestration_runtime -v
```

- [ ] **Step 3: Implement entrypoint injection**

Update entrypoints to call `configure_runtime()` once and pass explicit config into services, publishers, and runtime objects.

- [ ] **Step 4: Verify green**

Run the same command. Expected: PASS.

### Task 5: Docs, Search Gates, Full Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/architecture.md`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/plans/2026-06-18-model-provider-factory-refactor.md`
- Modify: `docs/superpowers/plans/2026-06-16-runtime-rulesets-restructure.md`
- Modify: `docs/superpowers/specs/2026-06-16-runtime-rulesets-restructure-design.md`
- Modify: `docs/config-yaml-unification-design.md`
- Modify: `docs/superpowers/plans/2026-06-23-config-yaml-unification.md`
- Modify: package boundary/architecture tests

- [ ] **Step 1: Update docs**

Replace old JSON profile references with `.run/cli_profile.yaml`, describe `.run/config.yaml`, update the package tree to remove the old model config package, mark historical plans/specs that mention old config paths as superseded with new path examples, and keep the final search command from self-matching this active design/plan.

- [ ] **Step 2: Add search-gate test**

Add a test asserting no runtime config `os.getenv` remains outside `contract_agent/config/` and no imports reference removed config packages.

- [ ] **Step 3: Full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m compileall -q contract_agent tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
rg "os\.getenv|os\.environ|contract_agent\.model_config|cli_profile\.json|json_profile|runtime\.config|orchestration\.config|knowledge\.rag\.config" contract_agent tests docs README.md AGENTS.md --glob "!docs/config-yaml-unification-design.md" --glob "!docs/superpowers/plans/2026-06-23-config-yaml-unification.md"
```

Expected: compile and unittest PASS; search output contains only removed path assertions or historical superseded docs marked as such.
