from __future__ import annotations

from typing import Any

from contract_agent.knowledge.rag.rerank.interface import RerankResult


def parse_qwen_rerank_results(payload: dict[str, Any]) -> list[RerankResult]:
    rows = _find_result_rows(payload)
    parsed: list[RerankResult] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        index = row.get("index")
        if index is None:
            index = row.get("document_id")
        if index is None:
            continue
        score = row.get("relevance_score")
        if score is None:
            score = row.get("score", 0.0)
        try:
            parsed.append(RerankResult(index=int(index), score=float(score)))
        except Exception:
            continue
    parsed.sort(key=lambda item: item.score, reverse=True)
    return parsed


def _find_result_rows(payload: dict[str, Any]) -> list[Any]:
    if isinstance(payload.get("results"), list):
        return payload["results"]

    data = payload.get("data")
    if isinstance(data, list):
        return data

    output = payload.get("output")
    if isinstance(output, dict):
        if isinstance(output.get("results"), list):
            return output["results"]
        if isinstance(output.get("data"), list):
            return output["data"]
    return []
