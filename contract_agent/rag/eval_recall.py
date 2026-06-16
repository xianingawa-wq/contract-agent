from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from contract_agent.runtime.config import settings
from contract_agent.rag.retriever import ContractKnowledgeRetriever
from contract_agent.rag.vector_store import load_vector_store


@dataclass(frozen=True)
class RecallSample:
    risk_id: str
    contract_id: str
    contract_type: str
    query: str
    gold_article_labels: list[str]
    severity: str | None = None
    note: str | None = None


def load_recall_dataset(dataset_path: str) -> list[RecallSample]:
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"Recall dataset file not found: {path}")

    samples: list[RecallSample] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            payload = json.loads(line)
            sample = _parse_sample(payload=payload, line_no=line_no)
            samples.append(sample)
    return samples


def filter_samples(
    samples: list[RecallSample],
    contract_types: set[str] | None = None,
    severities: set[str] | None = None,
) -> list[RecallSample]:
    filtered: list[RecallSample] = []
    for sample in samples:
        if contract_types and sample.contract_type not in contract_types:
            continue
        if severities and (sample.severity or "") not in severities:
            continue
        filtered.append(sample)
    return filtered


def evaluate_samples(
    samples: list[RecallSample],
    retriever: ContractKnowledgeRetriever,
    k_values: list[int],
    *,
    use_rerank: bool,
    fetch_k: int,
    final_k: int,
) -> list[dict[str, Any]]:
    if not samples:
        return []

    max_k = max(k_values)
    rerank_final_k = max(max_k, final_k)
    results: list[dict[str, Any]] = []
    for sample in samples:
        rerank_order_changed: bool | None = None
        rerank_meta: dict[str, Any] | None = None
        if use_rerank:
            baseline_docs = retriever.retrieve_documents(query=sample.query, k=fetch_k)
            docs = retriever.retrieve_documents_with_rerank(
                query=sample.query,
                fetch_k=fetch_k,
                final_k=rerank_final_k,
                use_rerank=True,
            )
            rerank_order_changed = _docs_signature(baseline_docs[:rerank_final_k]) != _docs_signature(docs)
            rerank_meta = dict(getattr(retriever, "last_rerank_meta", {}) or {})
        else:
            docs = retriever.retrieve_documents(query=sample.query, k=max_k)

        results.append(
            _evaluate_single_sample(
                sample=sample,
                docs=docs,
                k_values=k_values,
                rerank_order_changed=rerank_order_changed,
                rerank_meta=rerank_meta,
            )
        )
    return results


def build_summary(
    *,
    details: list[dict[str, Any]],
    k_values: list[int],
    dataset_path: str,
    filters: dict[str, list[str]] | None = None,
    retrieval_config: dict[str, Any] | None = None,
    timing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(Path(dataset_path).resolve()),
        "sample_count": len(details),
        "k_values": k_values,
        "filters": filters or {},
        "retrieval_config": retrieval_config or {},
        "timing": timing or {},
        "overall": _recall_stats(details=details, k_values=k_values),
        "by_contract_type": _grouped_recall_stats(details=details, k_values=k_values, key_name="contract_type"),
        "by_severity": _grouped_recall_stats(details=details, k_values=k_values, key_name="severity"),
        "rerank_diagnostics": _rerank_diagnostics(details),
    }
    return summary


def compare_with_baseline(current_summary: dict[str, Any], baseline_summary: dict[str, Any]) -> dict[str, Any]:
    k_values = [int(k) for k in current_summary.get("k_values", [])]
    comparison: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "k_values": k_values,
        "overall": _delta_stats(
            current=current_summary.get("overall", {}),
            baseline=baseline_summary.get("overall", {}),
            k_values=k_values,
        ),
        "by_contract_type": _delta_group_stats(
            current=current_summary.get("by_contract_type", {}),
            baseline=baseline_summary.get("by_contract_type", {}),
            k_values=k_values,
        ),
        "by_severity": _delta_group_stats(
            current=current_summary.get("by_severity", {}),
            baseline=baseline_summary.get("by_severity", {}),
            k_values=k_values,
        ),
    }
    return comparison


def run_evaluation(
    *,
    dataset_path: str,
    output_dir: str,
    k_values: list[int],
    contract_types: set[str] | None = None,
    severities: set[str] | None = None,
    retriever: ContractKnowledgeRetriever | None = None,
    use_rerank: bool | None = None,
    fetch_k: int | None = None,
    final_k: int | None = None,
) -> dict[str, Any]:
    started_at_dt = datetime.now(timezone.utc)

    all_samples = load_recall_dataset(dataset_path)
    selected_samples = filter_samples(all_samples, contract_types=contract_types, severities=severities)
    if not selected_samples:
        raise ValueError("No samples left after applying filters.")

    active_retriever = retriever or _build_retriever()
    use_rerank_value = settings.retrieval_enable_rerank if use_rerank is None else bool(use_rerank)
    fetch_k_value = max(1, int(fetch_k or settings.retrieval_fetch_k))
    final_k_value = max(1, int(final_k or settings.retrieval_final_k))

    details = evaluate_samples(
        selected_samples,
        active_retriever,
        k_values,
        use_rerank=use_rerank_value,
        fetch_k=fetch_k_value,
        final_k=final_k_value,
    )

    filters = {
        "contract_types": sorted(contract_types) if contract_types else [],
        "severities": sorted(severities) if severities else [],
    }
    retrieval_config = {
        "use_rerank": use_rerank_value,
        "fetch_k": fetch_k_value,
        "final_k": final_k_value,
        "rerank_model": settings.rerank_model,
        "rerank_endpoint": settings.rerank_endpoint,
    }

    finished_at_dt = datetime.now(timezone.utc)
    timing = {
        "started_at": started_at_dt.isoformat(),
        "finished_at": finished_at_dt.isoformat(),
        "duration_seconds": round((finished_at_dt - started_at_dt).total_seconds(), 6),
    }

    summary = build_summary(
        details=details,
        k_values=k_values,
        dataset_path=dataset_path,
        filters=filters,
        retrieval_config=retrieval_config,
        timing=timing,
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = out_dir / "summary.json"
    details_path = out_dir / "details.jsonl"
    miss_cases_path = out_dir / "miss_cases.jsonl"
    baseline_path = out_dir / "baseline_summary.json"
    comparison_path = out_dir / "comparison.json"

    _write_json(summary_path, summary)
    _write_jsonl(details_path, details)

    max_k = max(k_values)
    misses = [item for item in details if not item["hits_by_k"].get(f"hit_at_{max_k}", False)]
    _write_jsonl(miss_cases_path, misses)

    comparison = None
    if baseline_path.exists():
        baseline_summary = json.loads(baseline_path.read_text(encoding="utf-8"))
        comparison = compare_with_baseline(summary, baseline_summary)
        _write_json(comparison_path, comparison)
    else:
        _write_json(baseline_path, summary)

    return {
        "summary_path": str(summary_path.resolve()),
        "details_path": str(details_path.resolve()),
        "miss_cases_path": str(miss_cases_path.resolve()),
        "baseline_path": str(baseline_path.resolve()),
        "comparison_path": str(comparison_path.resolve()) if comparison is not None else None,
        "sample_count": len(details),
    }


def _build_retriever() -> ContractKnowledgeRetriever:
    vector_store = load_vector_store(settings.knowledge_vector_store_dir)
    return ContractKnowledgeRetriever(vector_store)


def _parse_sample(payload: dict[str, Any], line_no: int) -> RecallSample:
    required = ("risk_id", "contract_id", "contract_type", "query", "gold_article_labels")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Dataset line {line_no} missing fields: {', '.join(missing)}")

    labels = payload.get("gold_article_labels")
    if not isinstance(labels, list):
        raise ValueError(f"Dataset line {line_no} field gold_article_labels must be an array.")
    normalized_labels = sorted({str(item).strip() for item in labels if str(item).strip()})
    if not normalized_labels:
        raise ValueError(f"Dataset line {line_no} has empty gold_article_labels.")

    query = str(payload.get("query", "")).strip()
    if not query:
        raise ValueError(f"Dataset line {line_no} has empty query.")

    return RecallSample(
        risk_id=str(payload["risk_id"]).strip(),
        contract_id=str(payload["contract_id"]).strip(),
        contract_type=str(payload["contract_type"]).strip(),
        query=query,
        gold_article_labels=normalized_labels,
        severity=str(payload["severity"]).strip() if payload.get("severity") else None,
        note=str(payload["note"]).strip() if payload.get("note") else None,
    )


def _evaluate_single_sample(
    *,
    sample: RecallSample,
    docs: list[Document],
    k_values: list[int],
    rerank_order_changed: bool | None = None,
    rerank_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    retrieved_items: list[dict[str, Any]] = []
    retrieved_labels: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        metadata = doc.metadata or {}
        article_label = _normalize_label(metadata.get("article_label"))
        if article_label:
            retrieved_labels.append(article_label)
        retrieved_items.append(
            {
                "rank": idx,
                "article_label": article_label,
                "source_title": metadata.get("title") or metadata.get("doc_name"),
                "source_path": metadata.get("source_path"),
                "snippet": doc.page_content[:240],
            }
        )

    gold_set = set(sample.gold_article_labels)
    first_hit_rank = _first_hit_rank(retrieved_labels, gold_set)
    reciprocal_rank = round(1.0 / first_hit_rank, 6) if first_hit_rank is not None else 0.0

    hits_by_k: dict[str, bool] = {}
    matched_labels_by_k: dict[str, list[str]] = {}
    ndcg_by_k: dict[str, float] = {}
    for k in k_values:
        top_labels = set(retrieved_labels[:k])
        matched = sorted(top_labels.intersection(gold_set))
        hits_by_k[f"hit_at_{k}"] = bool(matched)
        matched_labels_by_k[f"matched_labels_at_{k}"] = matched
        ndcg_by_k[f"ndcg_at_{k}"] = _ndcg_at_k(retrieved_labels=retrieved_labels, gold_set=gold_set, k=k)

    return {
        "risk_id": sample.risk_id,
        "contract_id": sample.contract_id,
        "contract_type": sample.contract_type,
        "severity": sample.severity,
        "query": sample.query,
        "gold_article_labels": sample.gold_article_labels,
        "retrieved": retrieved_items,
        "hits_by_k": hits_by_k,
        "matched_labels_by_k": matched_labels_by_k,
        "ndcg_by_k": ndcg_by_k,
        "first_hit_rank": first_hit_rank,
        "reciprocal_rank": reciprocal_rank,
        "rerank_order_changed": rerank_order_changed,
        "rerank_meta": rerank_meta or {},
        "note": sample.note,
    }


def _grouped_recall_stats(details: list[dict[str, Any]], *, k_values: list[int], key_name: str) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in details:
        key = (item.get(key_name) or "unknown").strip() if isinstance(item.get(key_name), str) else "unknown"
        groups.setdefault(key, []).append(item)

    grouped: dict[str, Any] = {}
    for key, rows in groups.items():
        grouped[key] = _recall_stats(details=rows, k_values=k_values)
    return grouped


def _recall_stats(details: list[dict[str, Any]], k_values: list[int]) -> dict[str, Any]:
    total = len(details)
    stats: dict[str, Any] = {"sample_count": total}
    for k in k_values:
        hit_key = f"hit_at_{k}"
        hits = sum(1 for row in details if row["hits_by_k"].get(hit_key))
        recall = round(hits / total, 6) if total else 0.0
        avg_ndcg = round(sum(float(row.get("ndcg_by_k", {}).get(f"ndcg_at_{k}", 0.0)) for row in details) / total, 6) if total else 0.0
        stats[f"hits_at_{k}"] = hits
        stats[f"recall_at_{k}"] = recall
        stats[f"ndcg_at_{k}"] = avg_ndcg

    reciprocal_sum = sum(float(row.get("reciprocal_rank", 0.0)) for row in details)
    stats["mrr"] = round(reciprocal_sum / total, 6) if total else 0.0

    hit_ranks = [int(row["first_hit_rank"]) for row in details if row.get("first_hit_rank") is not None]
    stats["avg_first_hit_rank"] = round(sum(hit_ranks) / len(hit_ranks), 6) if hit_ranks else None
    stats["hit_sample_count"] = len(hit_ranks)
    return stats


def _rerank_diagnostics(details: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in details if row.get("rerank_order_changed") is not None]
    if not rows:
        return {
            "order_changed_count": None,
            "order_changed_ratio": None,
            "success_count": None,
            "fallback_count": None,
            "fallback_reasons": {},
            "sample_count": 0,
        }

    changed = sum(1 for row in rows if row.get("rerank_order_changed") is True)
    success_count = 0
    fallback_count = 0
    reason_counts: dict[str, int] = {}
    for row in rows:
        meta = row.get("rerank_meta") or {}
        if meta.get("success") is True:
            success_count += 1
        if meta.get("fallback") is True:
            fallback_count += 1
            reason = str(meta.get("reason") or "unknown")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "order_changed_count": changed,
        "order_changed_ratio": round(changed / len(rows), 6) if rows else None,
        "success_count": success_count,
        "fallback_count": fallback_count,
        "fallback_reasons": reason_counts,
        "sample_count": len(rows),
    }


def _delta_group_stats(current: dict[str, Any], baseline: dict[str, Any], k_values: list[int]) -> dict[str, Any]:
    keys = sorted(set(current.keys()).union(set(baseline.keys())))
    return {
        key: _delta_stats(current=current.get(key, {}), baseline=baseline.get(key, {}), k_values=k_values) for key in keys
    }


def _delta_stats(current: dict[str, Any], baseline: dict[str, Any], k_values: list[int]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for k in k_values:
        for metric in ("recall", "ndcg"):
            key = f"{metric}_at_{k}"
            current_value = current.get(key)
            baseline_value = baseline.get(key)
            delta = None
            if current_value is not None and baseline_value is not None:
                delta = round(float(current_value) - float(baseline_value), 6)
            data[f"delta_{metric}_at_{k}"] = delta
            data[f"current_{metric}_at_{k}"] = current_value
            data[f"baseline_{metric}_at_{k}"] = baseline_value

    for metric in ("mrr", "avg_first_hit_rank"):
        current_value = current.get(metric)
        baseline_value = baseline.get(metric)
        delta = None
        if current_value is not None and baseline_value is not None:
            delta = round(float(current_value) - float(baseline_value), 6)
        data[f"delta_{metric}"] = delta
        data[f"current_{metric}"] = current_value
        data[f"baseline_{metric}"] = baseline_value
    return data


def _normalize_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_hit_rank(retrieved_labels: list[str], gold_set: set[str]) -> int | None:
    for idx, label in enumerate(retrieved_labels, start=1):
        if label in gold_set:
            return idx
    return None


def _ndcg_at_k(*, retrieved_labels: list[str], gold_set: set[str], k: int) -> float:
    if k <= 0:
        return 0.0

    dcg = 0.0
    for rank, label in enumerate(retrieved_labels[:k], start=1):
        if label in gold_set:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(len(gold_set), k)
    if ideal_hits == 0:
        return 0.0

    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    if idcg == 0:
        return 0.0
    return round(dcg / idcg, 6)


def _docs_signature(docs: list[Document]) -> list[tuple[str | None, str]]:
    signature: list[tuple[str | None, str]] = []
    for doc in docs:
        metadata = doc.metadata or {}
        label = _normalize_label(metadata.get("article_label"))
        signature.append((label, doc.page_content[:80]))
    return signature


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _parse_values(raw_values: list[str]) -> set[str] | None:
    merged: set[str] = set()
    for value in raw_values:
        for token in value.split(","):
            token = token.strip()
            if token:
                merged.add(token)
    return merged or None


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean value: {value}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval recall with gold-labeled legal article IDs.")
    parser.add_argument("--dataset", required=True, help="Path to recall evaluation dataset in JSONL format.")
    parser.add_argument("--k", nargs="*", type=int, default=[1, 3, 5], help="K values for Recall@k.")
    parser.add_argument("--output-dir", required=True, help="Directory for output reports.")
    parser.add_argument(
        "--filter-contract-type",
        action="append",
        default=[],
        help="Filter by contract_type, can be provided multiple times or comma-separated.",
    )
    parser.add_argument(
        "--filter-severity",
        action="append",
        default=[],
        help="Filter by severity, can be provided multiple times or comma-separated.",
    )
    parser.add_argument(
        "--use-rerank",
        type=_parse_bool,
        default=settings.retrieval_enable_rerank,
        help="Whether to use rerank in evaluation (true/false).",
    )
    parser.add_argument(
        "--fetch-k",
        type=int,
        default=settings.retrieval_fetch_k,
        help="Candidate size before rerank.",
    )
    parser.add_argument(
        "--final-k",
        type=int,
        default=settings.retrieval_final_k,
        help="Final output size after rerank.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    k_values = sorted({int(k) for k in args.k if int(k) > 0})
    if not k_values:
        raise ValueError("At least one positive K value is required.")

    result = run_evaluation(
        dataset_path=args.dataset,
        output_dir=args.output_dir,
        k_values=k_values,
        contract_types=_parse_values(args.filter_contract_type),
        severities=_parse_values(args.filter_severity),
        use_rerank=args.use_rerank,
        fetch_k=args.fetch_k,
        final_k=args.final_k,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
