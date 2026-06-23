# Runtime and Rulesets Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move runtime settings and built-in rule data into clearer packages while preserving old imports.

> Superseded: runtime settings now live in `contract_agent/config/config_runtime.py`; internal imports should use `contract_agent.config`.

**Architecture:** Create `contract_agent.config` for settings and `contract_agent.rulesets` for built-in rules.

**Tech Stack:** Python 3.11+, unittest, existing settings and rule engine.

---

### Task 1: Add Import Compatibility Tests

**Files:**
- Create: `tests/test_runtime_rulesets_compatibility.py`

- [x] **Step 1: Add new-path and old-path identity tests**

Create a test that imports both old and new modules and asserts object identity for `settings`, `PROJECT_ROOT`, `_bool_env`, and `RULES`.

- [x] **Step 2: Run focused test and verify it fails**

Run: `python -m unittest tests.test_runtime_rulesets_compatibility -v`

Expected: ERROR because `contract_agent.runtime` and `contract_agent.rulesets` do not exist yet.

### Task 2: Move Implementations

**Files:**
- Create: `contract_agent/runtime/__init__.py`
- Create: `contract_agent/config/config_runtime.py`
- Create: `contract_agent/rulesets/__init__.py`
- Create: `contract_agent/rulesets/built_in.py`
- Modify: `contract_agent/core/config.py`
- Modify: `contract_agent/data/rules.py`

- [x] **Step 1: Copy current implementation into new packages**

Copy:

```text
contract_agent/core/config.py -> contract_agent/config/config_runtime.py
contract_agent/data/rules.py  -> contract_agent/rulesets/built_in.py
```

- [x] **Step 2: Replace old files with compatibility shims**

`contract_agent/core/config.py` should re-export `PROJECT_ROOT`, `Settings`, `_bool_env`, and `settings`.

`contract_agent/data/rules.py` should re-export `RULES`.

- [x] **Step 3: Run focused test and verify it passes**

Run: `python -m unittest tests.test_runtime_rulesets_compatibility -v`

Expected: PASS.

### Task 3: Update Canonical Imports

**Files:**
- Modify files importing `contract_agent.core.config`
- Modify: `contract_agent/services/rule_engine.py`

- [x] **Step 1: Replace settings imports**

Change internal imports to:

```python
from contract_agent.config import settings
```

- [x] **Step 2: Replace rule data import**

Change `RuleEngine` import to:

```python
from contract_agent.rulesets.built_in import RULES
```

### Task 4: Document and Verify

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`

- [x] **Step 1: Update layout documentation**

Document `runtime` and `rulesets`, and leave `db` unchanged.

- [x] **Step 2: Run final verification**

Run:

```powershell
python -m compileall -q contract_agent tests
python -m unittest discover -s tests -v
```

Expected: both commands exit with code 0.
