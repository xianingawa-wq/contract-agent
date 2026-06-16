# Interface Entrypoints Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move CLI and minimal HTTP/FastAPI entrypoints into `contract_agent.interfaces` while preserving old root imports.

**Architecture:** Create `contract_agent/interfaces` for executable adapters. Keep `contract_agent.cli` and `contract_agent.main` as compatibility shims, and point the canonical console script at `contract_agent.interfaces.cli:main`.

**Tech Stack:** Python 3.11+, FastAPI, unittest, existing CLI review facade.

---

### Task 1: Add Interface Entrypoint Tests

**Files:**
- Modify: `tests/test_cli.py`
- Create: `tests/test_interfaces.py`

- [x] **Step 1: Update CLI tests to import the new canonical path**

Use:

```python
from contract_agent.interfaces.cli import main
```

- [x] **Step 2: Add compatibility tests**

Create tests that assert:

```python
old_cli.main is new_cli.main
old_http.app is new_http.app
old_http.root is new_http.root
```

- [x] **Step 3: Run focused tests and verify they fail**

Run: `python -m unittest tests.test_interfaces tests.test_cli -v`

Expected: ERROR because `contract_agent.interfaces` does not exist yet.

### Task 2: Move Entrypoint Implementations

**Files:**
- Create: `contract_agent/interfaces/__init__.py`
- Create: `contract_agent/interfaces/cli.py`
- Create: `contract_agent/interfaces/http.py`
- Modify: `contract_agent/cli.py`
- Modify: `contract_agent/main.py`
- Modify: `pyproject.toml`

- [x] **Step 1: Copy current CLI and FastAPI implementations**

Move implementation bodies:

```text
contract_agent/cli.py  -> contract_agent/interfaces/cli.py
contract_agent/main.py -> contract_agent/interfaces/http.py
```

- [x] **Step 2: Replace root files with shims**

Use:

```python
from contract_agent.interfaces.cli import main
```

and:

```python
from contract_agent.interfaces.http import app, root
```

- [x] **Step 3: Update console script**

Change:

```toml
contract-agent = "contract_agent.interfaces.cli:main"
```

- [x] **Step 4: Run focused tests and verify they pass**

Run: `python -m unittest tests.test_interfaces tests.test_cli -v`

Expected: PASS.

### Task 3: Update Documentation and Verify

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`

- [x] **Step 1: Document `contract_agent/interfaces`**

Add the new package to layout and architecture sections as CLI and minimal HTTP/FastAPI adapters.

- [x] **Step 2: Run final verification**

Run:

```powershell
python -m compileall -q contract_agent tests
python -m unittest discover -s tests -v
```

Expected: both commands exit with code 0.
