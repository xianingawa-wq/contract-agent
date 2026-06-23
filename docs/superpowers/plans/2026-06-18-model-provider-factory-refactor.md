# Model Provider Factory Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor model configuration and model creation into a clean `interface -> service -> impl -> factory` structure with role-specific chat, embedding, and rerank configuration.

**Architecture:** Add `model_config`, restructure `provider`, and add `knowledge.rag.rerank` packages. Each package exposes interfaces, service orchestration, concrete implementations, and factory creation points. Existing public imports remain available through compatibility shims while internal code moves to the new naming.

**Tech Stack:** Python 3.11+, dataclasses, Protocols, unittest, OpenAI-compatible client wrappers.

---

### Task 1: Model Configuration Package

**Files:**
- Create: `contract_agent/model_config/interface.py`
- Create: `contract_agent/model_config/service.py`
- Create: `contract_agent/model_config/impl/env_source.py`
- Create: `contract_agent/model_config/impl/json_profile_store.py`
- Create: `contract_agent/model_config/factory.py`
- Modify: `contract_agent/interfaces/console.py`
- Modify: `contract_agent/interfaces/cli.py`
- Test: `tests/test_model_config.py`

- [x] Write tests for role-based config resolution and profile persistence.
- [x] Implement model config interfaces and normalized names.
- [x] Implement env source and JSON profile store.
- [x] Implement resolver and profile service.
- [x] Update CLI and console to use the service instead of local config dataclasses.

### Task 2: Provider Package Factory

**Files:**
- Create: `contract_agent/provider/interface.py`
- Create: `contract_agent/provider/service.py`
- Create: `contract_agent/provider/impl/openai/provider.py`
- Create: `contract_agent/provider/impl/openai/embeddings.py`
- Create: `contract_agent/provider/impl/openai/message_codec.py`
- Create: `contract_agent/provider/impl/dashscope/provider.py`
- Create: `contract_agent/provider/impl/dashscope/embeddings.py`
- Create: `contract_agent/provider/factory.py`
- Modify: `contract_agent/provider/client.py`
- Modify: `contract_agent/provider/providers.py`
- Test: `tests/test_llm_provider.py`

- [x] Write tests for chat and embedding factory isolation.
- [x] Move provider protocols to `interface.py`.
- [x] Move OpenAI concrete implementation to `impl/openai/`.
- [x] Move DashScope/Qwen concrete implementation to `impl/dashscope/`.
- [x] Keep `impl/openai_compatible*.py` modules as legacy shims only.
- [x] Implement `ModelProviderFactory` and `ModelProviderService`.
- [x] Keep `provider.providers` as a compatibility export.

### Task 3: Rerank Package Factory

**Files:**
- Create: `contract_agent/knowledge/rag/rerank/interface.py`
- Create: `contract_agent/knowledge/rag/rerank/service.py`
- Create: `contract_agent/knowledge/rag/rerank/impl/qwen.py`
- Create: `contract_agent/knowledge/rag/rerank/factory.py`
- Modify: `contract_agent/knowledge/rag/reranker.py`
- Modify: `contract_agent/knowledge/rag/retriever.py`
- Test: `tests/test_reranker.py`

- [x] Write tests that rerank uses only rerank endpoint configuration.
- [x] Move reranker interface and Qwen implementation into the package.
- [x] Implement factory and service.
- [x] Keep `knowledge.rag.reranker` as a compatibility export.

### Task 4: Integration and Verification

**Files:**
- Modify: `README.md`
- Modify: affected service call sites that still read legacy model settings directly.

- [x] Update docs to mention the package structure and local profile behavior.
- [x] Run `python -m unittest discover -s tests -v`.
- [x] Fix any import regressions or naming leaks.
