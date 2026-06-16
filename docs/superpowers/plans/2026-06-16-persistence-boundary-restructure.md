# Persistence Boundary Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `contract_agent.db` into runtime database initialization, knowledge persistence, and memory persistence while preserving compatibility imports.

**Architecture:** Move database lifecycle to `runtime`, knowledge ORM/repository to `knowledge`, and multi-agent memory stores to `memory`. Leave `db` and `multi_agent.memory` as shim namespaces.

**Tech Stack:** Python 3.11+, SQLAlchemy, Redis client, unittest.

---

### Task 1: Runtime Database

**Files:**
- Create: `contract_agent/runtime/database.py`
- Modify: `contract_agent/db/session.py`
- Create: `tests/test_runtime_database.py`

- [ ] Add tests proving `runtime.database` exposes `get_engine`, `get_session_factory`, `SessionLocal`, and `session_scope`.
- [ ] Add tests proving `db.session` re-exports those same objects.
- [ ] Move session implementation into `runtime.database`.
- [ ] Convert `db.session` into a compatibility shim.
- [ ] Run compile and tests.
- [ ] Commit.

### Task 2: Knowledge Persistence

**Files:**
- Create: `contract_agent/knowledge/__init__.py`
- Create: `contract_agent/knowledge/models.py`
- Create: `contract_agent/knowledge/repository.py`
- Modify: `contract_agent/db/models.py`
- Modify knowledge repository import callers.
- Create: `tests/test_knowledge_persistence.py`

- [ ] Add tests proving knowledge canonical and compatibility imports resolve to the same objects.
- [ ] Move `KnowledgeChunkModel` into `knowledge.models`.
- [ ] Move `KnowledgeChunkRepository` into `knowledge.repository`.
- [ ] Convert old repository/model paths into shims.
- [ ] Run compile and tests.
- [ ] Commit.

### Task 3: Memory Persistence

**Files:**
- Create: `contract_agent/memory/__init__.py`
- Create: `contract_agent/memory/models.py`
- Create: `contract_agent/memory/hot_store.py`
- Create: `contract_agent/memory/warm_store.py`
- Create: `contract_agent/memory/cold_store.py`
- Create: `contract_agent/memory/manager.py`
- Modify: `contract_agent/multi_agent/memory.py`
- Modify memory manager import callers.
- Create: `tests/test_memory_persistence.py`

- [ ] Add tests proving memory canonical and compatibility imports resolve to the same objects.
- [ ] Move `AgentOutputRecord` into `memory.models`.
- [ ] Move `HotLayer`, `WarmLayer`, `ColdLayer`, and `MemoryManager` into `memory` modules.
- [ ] Convert `multi_agent.memory` and `db.multi_agent_models` into shims.
- [ ] Run compile and tests.
- [ ] Commit.

### Task 4: Runtime Schema Initialization

**Files:**
- Create: `contract_agent/runtime/schema.py`
- Modify: `contract_agent/db/init_db.py`
- Modify schema initialization callers.
- Create: `tests/test_runtime_schema.py`

- [ ] Add tests proving `ensure_runtime_schema` creates both knowledge and memory metadata.
- [ ] Add tests proving `ensure_postgres_schema` is a compatibility alias.
- [ ] Move schema initialization into `runtime.schema`.
- [ ] Update knowledge repository to call `ensure_runtime_schema`.
- [ ] Run compile and tests.
- [ ] Commit.

### Task 5: Documentation and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`

- [ ] Document `knowledge`, `memory`, and runtime database/schema ownership.
- [ ] Run `git diff --check`.
- [ ] Run `python -m compileall -q contract_agent tests`.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Commit if documentation changed after Task 4.
