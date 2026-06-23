from __future__ import annotations


def build_qwen_rerank_endpoint(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if "/compatible-mode/" in base:
        return base.replace("/compatible-mode/", "/compatible-api/") + "/reranks"
    return f"{base}/reranks"
