# Review Package Restructure Design

## Context

`contract-agent` is an extracted Python contract review agent runtime. The package already has clear subsystem boundaries for runtime configuration, LLM integration, RAG, multi-agent orchestration, gRPC integration, persistence, and Pydantic schemas.

The package root still contains an older local-review facade:

- `contract_agent/models.py`
- `contract_agent/rules.py`
- `contract_agent/report.py`
- `contract_agent/service.py`

These files support the local CLI and rule-only review tests, but their names make the package root look like the primary domain layer. That becomes less clear as the runtime grows around `services`, `schemas`, `rag`, `llm`, and `multi_agent`.

## Goal

Move the local review facade into a focused `contract_agent.review` package while preserving current imports, CLI behavior, tests, and runtime semantics.

## Non-Goals

- Do not change review behavior.
- Do not rewrite Chinese strings or repair mojibake text.
- Do not refactor large runtime modules such as `services/chat_service.py`, `agent_rpc/server.py`, or `rag/eval_recall.py`.
- Do not change gRPC, RAG, multi-agent, database, or LLM provider behavior.

## Architecture

Create a new package:

```text
contract_agent/
  review/
    __init__.py
    models.py
    reporting.py
    rules.py
    service.py
```

The new package owns the local rule-review facade used by the CLI:

- `review.models` contains dataclass report models and severity values.
- `review.rules` normalizes CLI aliases and adapts `RuleEngine` risks into local `Finding` objects.
- `review.reporting` renders local review reports as Markdown or JSON.
- `review.service` coordinates rule review and optional LLM enrichment.
- `review.__init__` exports the public local-review API.

The existing root modules remain as compatibility shims:

```text
contract_agent/models.py   -> re-export from contract_agent.review.models
contract_agent/rules.py    -> re-export from contract_agent.review.rules
contract_agent/report.py   -> re-export from contract_agent.review.reporting
contract_agent/service.py  -> re-export from contract_agent.review.service
```

This keeps external code and current tests that import the old paths working.

## Data Flow

The CLI review command should flow through the new package:

1. `contract_agent.cli` reads a UTF-8 text file.
2. It calls `contract_agent.review.service.review_text`.
3. `review.service` builds a `review.models.ReviewRequest`.
4. `review.rules` parses the contract and runs `services.rule_engine.RuleEngine`.
5. `review.service` optionally calls an injected LLM enricher.
6. `review.reporting` renders the returned `ReviewReport`.

The old root import paths should resolve to the same objects through shim modules.

## Compatibility

Current public imports must keep working:

```python
from contract_agent.service import review_text
from contract_agent.models import ReviewRequest, Severity
from contract_agent.rules import run_rules
from contract_agent.report import render_json, render_markdown
```

New imports should also work:

```python
from contract_agent.review.service import review_text
from contract_agent.review.models import ReviewRequest, Severity
from contract_agent.review.rules import run_rules
from contract_agent.review.reporting import render_json, render_markdown
```

## Testing

Use the existing unittest suite as the regression boundary:

```powershell
python -m unittest discover -s tests -v
```

Update local review tests to import the new paths where appropriate, and add a focused compatibility test proving the old root imports still point at the new implementation objects.

## Risks

- Import churn can break CLI or external callers if shims are incomplete.
- Dataclass and enum identity must remain stable across old and new imports.
- The existing mojibake strings are behaviorally significant in tests; moving files should preserve the strings byte-for-byte.

## Acceptance Criteria

- `contract_agent.review` exists and contains the local review facade.
- Root facade modules are compatibility shims only.
- `contract_agent.cli` uses the new review package.
- Old import paths continue to work.
- All existing tests pass.
- No behavior, configuration, or generated protobuf files are changed.
