from __future__ import annotations

import math
import re
import time
from collections import Counter
from typing import Any, Protocol

from langchain_core.documents import Document

from contract_agent.config import RetrievalConfig
from contract_agent.knowledge.rag.rerank.interface import Reranker
from contract_agent.knowledge.rag.rerank.factory import create_reranker_service
from contract_agent.logger.audit import AuditLogger, get_audit_logger
from contract_agent.config import Settings


class SimilaritySearchStore(Protocol):
    def similarity_search(self, query: str, k: int = 3) -> list[Document]:
        ...


class ContractKnowledgeRetriever:
    def __init__(
        self,
        vector_store: SimilaritySearchStore,
        reranker: Reranker | None = None,
        retrieval_config: RetrievalConfig | None = None,
        runtime_settings: Settings | None = None,
        audit_logger: AuditLogger | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.retrieval_config = retrieval_config or RetrievalConfig.from_settings(runtime_settings)
        self.reranker = reranker or create_reranker_service().create_reranker()
        self.audit_logger = (audit_logger or get_audit_logger()).with_prefix("[Knowledge][RAG]", scope="rag")
        self.last_rerank_meta: dict[str, object] = {
            "attempted": False,
            "success": False,
            "fallback": False,
            "reason": None,
            "order_changed": None,
        }

    def retrieve_documents(self, query: str, k: int = 3) -> list[Document]:
        with self.audit_logger.span("rag.retrieve", mode="dense", query_length=len(query), k=k):
            target_k = max(1, int(k))
            candidates, _, _ = self._retrieve_candidates(query=query, target_k=target_k)
            return candidates

    def retrieve_documents_with_rerank(
        self,
        query: str,
        *,
        fetch_k: int | None = None,
        final_k: int | None = None,
        use_rerank: bool | None = None,
    ) -> list[Document]:
        with self.audit_logger.span("rag.retrieve", mode="rerank", query_length=len(query), fetch_k=fetch_k, final_k=final_k):
            candidate_k = max(1, int(fetch_k or self.retrieval_config.fetch_k))
            output_k = max(1, int(final_k or self.retrieval_config.final_k))
            candidates, top1_agree, candidate_profile = self._retrieve_candidates(query=query, target_k=candidate_k)

        base_profile = {
            "dense_retrieval_seconds": candidate_profile.get("dense_retrieval_seconds", 0.0),
            "bm25_retrieval_seconds": candidate_profile.get("bm25_retrieval_seconds", 0.0),
            "merge_dedup_seconds": candidate_profile.get("merge_dedup_seconds", 0.0),
            "rerank_request_seconds": 0.0,
            "rerank_model_inference_seconds": None,
            "json_serialize_seconds": 0.0,
            "network_seconds": 0.0,
        }

        rerank_enabled = self.retrieval_config.enable_rerank if use_rerank is None else bool(use_rerank)
        if not rerank_enabled:
            self.last_rerank_meta = {
                "attempted": False,
                "success": False,
                "fallback": False,
                "reason": "disabled",
                "order_changed": None,
                "hybrid_applied": bool(self.retrieval_config.enable_hybrid),
                "candidate_pool_size": len(candidates),
                "profile": base_profile,
            }
            return candidates[:output_k]

        if top1_agree:
            self.last_rerank_meta = {
                "attempted": False,
                "success": False,
                "fallback": False,
                "reason": "short_circuit_dense_bm25_top1_agree",
                "order_changed": None,
                "hybrid_applied": bool(self.retrieval_config.enable_hybrid),
                "candidate_pool_size": len(candidates),
                "profile": base_profile,
            }
            return candidates[:output_k]

        try:
            with self.audit_logger.span("rag.rerank", candidate_count=len(candidates), top_k=output_k):
                ranked = self.reranker.rerank(query=query, documents=candidates, top_k=output_k)
            rerank_profile = _extract_rerank_profile(self.reranker)
            order_changed = _docs_signature(candidates[: len(ranked)]) != _docs_signature(ranked)
            self.last_rerank_meta = {
                "attempted": True,
                "success": True,
                "fallback": False,
                "reason": None,
                "order_changed": order_changed,
                "hybrid_applied": bool(self.retrieval_config.enable_hybrid),
                "candidate_pool_size": len(candidates),
                "profile": _merge_profiles(base_profile, rerank_profile),
            }
            return ranked
        except Exception as exc:
            rerank_profile = _extract_rerank_profile(self.reranker)
            self.last_rerank_meta = {
                "attempted": True,
                "success": False,
                "fallback": True,
                "reason": _classify_rerank_error(exc),
                "order_changed": False,
                "hybrid_applied": bool(self.retrieval_config.enable_hybrid),
                "candidate_pool_size": len(candidates),
                "profile": _merge_profiles(base_profile, rerank_profile),
            }
            return candidates[:output_k]

    def retrieve(self, query: str, k: int = 3) -> list[str]:
        docs = self.retrieve_documents(query, k=k)
        return [doc.page_content for doc in docs]

    def _retrieve_candidates(self, query: str, target_k: int) -> tuple[list[Document], bool, dict[str, Any]]:
        dense_pool_k = max(target_k, int(self.retrieval_config.dense_pool_k))

        dense_started = time.perf_counter()
        dense_docs = self.vector_store.similarity_search(query, k=dense_pool_k)
        dense_elapsed = time.perf_counter() - dense_started

        if not self.retrieval_config.enable_hybrid:
            return dense_docs[:target_k], False, {
                "dense_retrieval_seconds": dense_elapsed,
                "bm25_retrieval_seconds": 0.0,
                "merge_dedup_seconds": 0.0,
            }

        bm25_started = time.perf_counter()
        query_tokens = _tokenize_for_bm25(query)
        bm25_scores = _bm25_scores(query_tokens=query_tokens, docs=dense_docs) if query_tokens else []
        bm25_elapsed = time.perf_counter() - bm25_started

        merge_started = time.perf_counter()
        top1_agree = _dense_and_bm25_top1_agree_from_scores(query_tokens=query_tokens, bm25_scores=bm25_scores)
        candidates = _hybrid_rank_documents_from_scores(
            dense_docs=dense_docs,
            bm25_scores=bm25_scores,
            top_k=target_k,
        )
        merge_elapsed = time.perf_counter() - merge_started

        return candidates, top1_agree, {
            "dense_retrieval_seconds": dense_elapsed,
            "bm25_retrieval_seconds": bm25_elapsed,
            "merge_dedup_seconds": merge_elapsed,
        }


def _extract_rerank_profile(reranker: Reranker) -> dict[str, Any]:
    profile = getattr(reranker, "last_profile", None)
    if not isinstance(profile, dict):
        return {}
    return dict(profile)


def _merge_profiles(base: dict[str, Any], rerank: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    out["rerank_request_seconds"] = float(rerank.get("request_seconds", 0.0) or 0.0)
    out["rerank_model_inference_seconds"] = rerank.get("model_inference_seconds")
    out["json_serialize_seconds"] = float(rerank.get("json_serialize_seconds", 0.0) or 0.0)
    out["network_seconds"] = float(rerank.get("network_seconds", 0.0) or 0.0)
    return out


def _classify_rerank_error(exc: Exception) -> str:
    message = str(exc).lower()
    if "404" in message:
        return "http_404"
    if "401" in message or "403" in message:
        return "auth_error"
    if "timed out" in message or "timeout" in message:
        return "timeout"
    if "json" in message and "parse" in message:
        return "bad_response_json"
    if "connection" in message or "name or service not known" in message:
        return "connection_error"
    return "other_error"


def _docs_signature(docs: list[Document]) -> list[tuple[str | None, str]]:
    signature: list[tuple[str | None, str]] = []
    for doc in docs:
        metadata = doc.metadata or {}
        label = metadata.get("article_label")
        signature.append((str(label).strip() if label is not None else None, doc.page_content[:80]))
    return signature


def _hybrid_rank_documents_from_scores(*, dense_docs: list[Document], bm25_scores: list[float], top_k: int) -> list[Document]:
    if len(dense_docs) <= top_k:
        return dense_docs[:top_k]

    max_bm25 = max(bm25_scores) if bm25_scores else 0.0
    if max_bm25 <= 0:
        return dense_docs[:top_k]

    dense_weight = 0.35
    bm25_weight = 0.65

    fused: list[tuple[float, int, Document]] = []
    for dense_rank, (doc, bm25_score) in enumerate(zip(dense_docs, bm25_scores), start=1):
        dense_prior = 1.0 / dense_rank
        bm25_norm = bm25_score / max_bm25
        hybrid_score = (dense_weight * dense_prior) + (bm25_weight * bm25_norm)
        fused.append((hybrid_score, dense_rank, doc))

    fused.sort(key=lambda item: (-item[0], item[1]))

    deduped: list[Document] = []
    seen: set[tuple[str | None, str]] = set()
    for _, _, doc in fused:
        key = _doc_key(doc)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(doc)
        if len(deduped) >= top_k:
            break
    return deduped


def _dense_and_bm25_top1_agree_from_scores(*, query_tokens: list[str], bm25_scores: list[float]) -> bool:
    if not query_tokens or not bm25_scores:
        return False
    max_bm25 = max(bm25_scores)
    if max_bm25 <= 0:
        return False
    bm25_top_idx = max(range(len(bm25_scores)), key=lambda idx: (bm25_scores[idx], -idx))
    return bm25_top_idx == 0


def _doc_key(doc: Document) -> tuple[str | None, str]:
    metadata = doc.metadata or {}
    label = metadata.get("article_label")
    normalized_label = str(label).strip() if label is not None else None
    return normalized_label, doc.page_content[:160]


def _bm25_scores(*, query_tokens: list[str], docs: list[Document], k1: float = 1.5, b: float = 0.5) -> list[float]:
    tokenized_docs = [_tokenize_for_bm25(doc.page_content) for doc in docs]
    doc_lengths = [len(tokens) for tokens in tokenized_docs]
    avg_doc_len = (sum(doc_lengths) / len(doc_lengths)) if doc_lengths else 1.0

    doc_freq: Counter[str] = Counter()
    per_doc_tf: list[Counter[str]] = []
    for tokens in tokenized_docs:
        tf = Counter(tokens)
        per_doc_tf.append(tf)
        doc_freq.update(tf.keys())

    total_docs = len(docs)
    scores: list[float] = []
    for idx, tf in enumerate(per_doc_tf):
        doc_len = max(1, doc_lengths[idx])
        score = 0.0
        for token in query_tokens:
            term_freq = tf.get(token, 0)
            if term_freq <= 0:
                continue
            df = doc_freq.get(token, 0)
            idf = math.log(1 + ((total_docs - df + 0.5) / (df + 0.5)))
            numerator = term_freq * (k1 + 1)
            denominator = term_freq + k1 * (1 - b + b * (doc_len / avg_doc_len))
            score += idf * (numerator / denominator)
        scores.append(score)

    return scores


def _tokenize_for_bm25(text: str) -> list[str]:
    normalized = (text or "").lower()
    english_tokens = re.findall(r"[a-z0-9_]+", normalized)
    cjk_tokens = re.findall(r"[\u4e00-\u9fff]", normalized)
    return english_tokens + cjk_tokens
