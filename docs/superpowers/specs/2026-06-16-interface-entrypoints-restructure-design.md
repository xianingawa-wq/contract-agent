# Interface Entrypoints Restructure Design

## Context

After moving the local review facade into `contract_agent.review`, the package root still contains two real entrypoint implementations:

- `contract_agent/cli.py`
- `contract_agent/main.py`

The rest of the root facade modules are compatibility shims. Keeping real entrypoint implementation at the package root makes the root package a mixed layer: partly compatibility API, partly executable adapters.

## Goal

Move CLI and HTTP/FastAPI entrypoint implementations into a focused `contract_agent.interfaces` package while preserving current import paths and console script behavior.

## Non-Goals

- Do not change CLI behavior or command output.
- Do not change the FastAPI root endpoint payload.
- Do not move or modify gRPC implementation in `contract_agent.agent_rpc`.
- Do not merge or edit protobuf files.
- Do not change review, RAG, LLM, multi-agent, or database behavior.

## Architecture

Create:

```text
contract_agent/
  interfaces/
    __init__.py
    cli.py
    http.py
```

Responsibilities:

- `interfaces.cli` owns the `contract-agent` console command implementation.
- `interfaces.http` owns the minimal FastAPI app exposed by the Python runtime.
- `contract_agent.cli` remains a shim that re-exports `interfaces.cli.main`.
- `contract_agent.main` remains a shim that re-exports `interfaces.http.app` and `interfaces.http.root`.

Update `pyproject.toml` so the canonical console script points to `contract_agent.interfaces.cli:main`.

## Compatibility

Current imports must keep working:

```python
from contract_agent.cli import main
from contract_agent.main import app, root
```

New imports should also work:

```python
from contract_agent.interfaces.cli import main
from contract_agent.interfaces.http import app, root
```

## Testing

Use tests to prove both new and old entrypoints resolve to the same objects:

- CLI tests should import `main` from `contract_agent.interfaces.cli`.
- A compatibility test should assert `contract_agent.cli.main is contract_agent.interfaces.cli.main`.
- A compatibility test should assert `contract_agent.main.app is contract_agent.interfaces.http.app`.
- A small HTTP root test should call `contract_agent.interfaces.http.root()` directly and assert the current payload keys.

Run:

```powershell
python -m compileall -q contract_agent tests
python -m unittest discover -s tests -v
```

## Acceptance Criteria

- `contract_agent.interfaces` exists and owns CLI/FastAPI implementation.
- Root `cli.py` and `main.py` are compatibility shims only.
- Console script points at `contract_agent.interfaces.cli:main`.
- Old import paths continue to work.
- Existing CLI tests and new compatibility tests pass.
