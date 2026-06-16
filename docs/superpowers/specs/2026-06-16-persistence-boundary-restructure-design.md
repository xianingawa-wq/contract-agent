# Persistence Boundary Restructure Design

## Context

`contract_agent.db` currently mixes unrelated responsibilities:

- SQLAlchemy engine/session lifecycle.
- Database schema initialization.
- Knowledge chunk ORM records.
- Multi-agent memory ORM records.

This makes ownership unclear. Knowledge persistence belongs with knowledge ingestion metadata, memory persistence belongs with agent memory, and database connection/session lifecycle is a runtime resource.

## Goal

Split the current `db` package by responsibility:

```text
contract_agent/
  runtime/
    database.py
    schema.py
  knowledge/
    models.py
    repository.py
  memory/
    models.py
    warm_store.py
    hot_store.py
    cold_store.py
    manager.py
```

Keep `contract_agent.db.*` and `contract_agent.multi_agent.memory` as compatibility paths during this migration.

## Non-Goals

- Do not change public gRPC, CLI, review, RAG retrieval, or multi-agent behavior.
- Do not change table names.
- Do not change Redis key names.
- Do not change vector store behavior.
- Do not repair unrelated mojibake text.

## Target Ownership

### Runtime

`contract_agent.runtime.database` owns database engine/session creation:

- `get_engine`
- `get_session_factory`
- `SessionLocal`
- `session_scope`

`contract_agent.runtime.schema` owns schema initialization:

- `ensure_runtime_schema`

### Knowledge

`contract_agent.knowledge.models` owns `KnowledgeChunkModel`.

`contract_agent.knowledge.repository` owns `KnowledgeChunkRepository`.

RAG ingestion and gRPC embedding should import the repository from `contract_agent.knowledge.repository`.

### Memory

`contract_agent.memory.models` owns `AgentOutputRecord`.

`contract_agent.memory.warm_store` owns PostgreSQL-backed warm memory.

`contract_agent.memory.hot_store` owns Redis-backed hot memory.

`contract_agent.memory.cold_store` owns RAG-backed cold memory.

`contract_agent.memory.manager` owns `MemoryManager`.

`contract_agent.multi_agent.memory` remains a compatibility shim.

## Compatibility

Keep these old imports working:

```python
from contract_agent.db.session import SessionLocal, get_engine, get_session_factory, session_scope
from contract_agent.db.init_db import ensure_postgres_schema
from contract_agent.db.models import Base, KnowledgeChunkModel
from contract_agent.db.multi_agent_models import AgentOutputRecord
from contract_agent.multi_agent.memory import MemoryManager, HotLayer, WarmLayer, ColdLayer
```

## Known Bug Fixed By This Design

`contract_agent.multi_agent.memory.WarmLayer` currently imports `SessionLocal` from `contract_agent.db.session`, but `SessionLocal` does not exist. The new runtime database module must expose it.

The current `db.models.Base` and `db.multi_agent_models.Base` are separate metadata roots. Unified schema initialization should create both knowledge and memory tables.

## Acceptance Criteria

- Database connection/session lifecycle lives in `runtime.database`.
- Runtime schema initialization creates both knowledge and memory tables.
- Knowledge ORM and repository live under `contract_agent.knowledge`.
- Memory stores and manager live under `contract_agent.memory`.
- Old `db` and `multi_agent.memory` imports remain compatible.
- Tests cover new canonical paths and old compatibility paths.
- Full compile and unittest verification pass after every step.
