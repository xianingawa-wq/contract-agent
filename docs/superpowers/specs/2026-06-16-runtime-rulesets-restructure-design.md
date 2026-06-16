# Runtime and Rulesets Restructure Design

## Context

`contract_agent.core` currently contains only environment-backed runtime configuration. `contract_agent.data` currently contains only built-in rule definitions used by the rule engine.

The names are broader than their actual responsibilities:

- `core` implies domain core logic, but the package only owns runtime settings.
- `data` is ambiguous because the project also has knowledge base files, database persistence, and test data.

## Goal

Move these two narrow responsibilities into clearer packages:

```text
contract_agent/runtime/config.py
contract_agent/rulesets/built_in.py
```

Preserve existing imports through compatibility shims.

## Non-Goals

- Do not change settings behavior or environment variable names.
- Do not change built-in rule content.
- Do not change `db` or persistence structure in this step.
- Do not change review, RAG, LLM, multi-agent, or gRPC behavior.

## Architecture

Create:

- `contract_agent.runtime`: runtime configuration and process-level settings.
- `contract_agent.rulesets`: built-in rule definitions consumed by `RuleEngine`.

Compatibility shims:

- `contract_agent.core.config` re-exports `contract_agent.runtime.config`.
- `contract_agent.data.rules` re-exports `contract_agent.rulesets.built_in`.

Canonical imports should use the new packages:

```python
from contract_agent.runtime.config import settings
from contract_agent.rulesets.built_in import RULES
```

## Testing

Add tests proving old and new import paths resolve to the same objects:

- `contract_agent.core.config.settings is contract_agent.runtime.config.settings`
- `contract_agent.data.rules.RULES is contract_agent.rulesets.built_in.RULES`

Run:

```powershell
python -m compileall -q contract_agent tests
python -m unittest discover -s tests -v
```

## Acceptance Criteria

- `contract_agent.runtime.config` owns settings implementation.
- `contract_agent.rulesets.built_in` owns built-in rules.
- Old imports continue to work.
- Internal canonical imports use the new paths.
- All tests pass.
