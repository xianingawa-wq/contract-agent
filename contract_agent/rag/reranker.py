from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from langchain_core.documents import Document

from contract_agent.core.config import settings


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


class Reranker:
    def rerank(self, query: str, documents: list[Document], top_k: int) -> list[Document]:
        raise NotImplementedError


class QwenReranker(Reranker):
    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_retries: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.model = model or settings.rerank_model
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else settings.rerank_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.rerank_max_retries
        self.endpoint = endpoint or settings.rerank_endpoint or self._build_default_endpoint()
        self.last_profile: dict[str, Any] = {}
        self._last_request_profile: dict[str, Any] = {}

    def rerank(self, query: str, documents: list[Document], top_k: int) -> list[Document]:
        self.last_profile = {}
        if not documents or top_k <= 0:
            return []

        top_n = min(top_k, len(documents))
        payload = {
            "model": self.model,
            "query": query,
            "documents": [doc.page_content for doc in documents],
            "top_n": top_n,
        }

        request_started = time.perf_counter()
        response = self._request_with_retry(payload)
        request_elapsed = time.perf_counter() - request_started

        request_profile = dict(self._last_request_profile or {})
        request_profile.setdefault("request_seconds", request_elapsed)
        request_profile.setdefault("model_inference_seconds", _extract_model_inference_seconds(response))
        self.last_profile = request_profile

        ranked = self._parse_results(response)
        if not ranked:
            raise RuntimeError("Rerank response did not include valid ranked indices.")

        output: list[Document] = []
        used_indexes: set[int] = set()
        for item in ranked:
            if item.index < 0 or item.index >= len(documents) or item.index in used_indexes:
                continue
            output.append(documents[item.index])
            used_indexes.add(item.index)
            if len(output) >= top_n:
                break

        if len(output) < top_n:
            for idx, doc in enumerate(documents):
                if idx in used_indexes:
                    continue
                output.append(doc)
                if len(output) >= top_n:
                    break
        return output

    def _request_with_retry(self, payload: dict[str, Any]) -> dict[str, Any]:
        attempts = max(0, int(self.max_retries)) + 1
        last_error: Exception | None = None
        profile: dict[str, Any] = {
            "attempts": 0,
            "json_serialize_seconds": 0.0,
            "network_seconds": 0.0,
            "response_json_parse_seconds": 0.0,
            "request_seconds": 0.0,
            "model_inference_seconds": None,
        }

        started = time.perf_counter()
        for i in range(attempts):
            try:
                response = self._request(payload)
                profile["attempts"] = i + 1
                profile["json_serialize_seconds"] += float(self._last_request_profile.get("json_serialize_seconds", 0.0) or 0.0)
                profile["network_seconds"] += float(self._last_request_profile.get("network_seconds", 0.0) or 0.0)
                profile["response_json_parse_seconds"] += float(self._last_request_profile.get("response_json_parse_seconds", 0.0) or 0.0)
                profile["request_seconds"] = time.perf_counter() - started
                profile["model_inference_seconds"] = _extract_model_inference_seconds(response)
                self._last_request_profile = profile
                return response
            except Exception as exc:
                last_error = exc
                profile["attempts"] = i + 1
                profile["json_serialize_seconds"] += float(self._last_request_profile.get("json_serialize_seconds", 0.0) or 0.0)
                profile["network_seconds"] += float(self._last_request_profile.get("network_seconds", 0.0) or 0.0)
                profile["response_json_parse_seconds"] += float(self._last_request_profile.get("response_json_parse_seconds", 0.0) or 0.0)

        profile["request_seconds"] = time.perf_counter() - started
        self._last_request_profile = profile
        raise RuntimeError(f"qwen rerank request failed after retries: {last_error}") from last_error

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not settings.qwen_api_key:
            raise RuntimeError("QWEN_API_KEY is not configured for rerank.")

        profile = {
            "json_serialize_seconds": 0.0,
            "network_seconds": 0.0,
            "response_json_parse_seconds": 0.0,
        }

        ser_started = time.perf_counter()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        profile["json_serialize_seconds"] = time.perf_counter() - ser_started

        headers = {
            "Authorization": f"Bearer {settings.qwen_api_key}",
            "Content-Type": "application/json",
        }
        req = request.Request(self.endpoint, data=body, headers=headers, method="POST")

        try:
            net_started = time.perf_counter()
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
                if resp.status != 200:
                    raise RuntimeError(f"rerank http status={resp.status}, body={raw[:300]}")
            profile["network_seconds"] = time.perf_counter() - net_started
        except error.HTTPError as exc:
            profile["network_seconds"] = time.perf_counter() - net_started
            self._last_request_profile = profile
            payload_text = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"rerank http error={exc.code}, body={payload_text[:300]}") from exc
        except error.URLError as exc:
            profile["network_seconds"] = time.perf_counter() - net_started
            self._last_request_profile = profile
            raise RuntimeError(f"rerank connection error: {exc}") from exc

        try:
            parse_started = time.perf_counter()
            data = json.loads(raw)
            profile["response_json_parse_seconds"] = time.perf_counter() - parse_started
        except Exception as exc:
            self._last_request_profile = profile
            raise RuntimeError(f"rerank response json parse failed: {raw[:300]}") from exc

        self._last_request_profile = profile
        return data

    def _parse_results(self, payload: dict[str, Any]) -> list[RerankResult]:
        rows = self._find_result_rows(payload)
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

    def _find_result_rows(self, payload: dict[str, Any]) -> list[Any]:
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

    def _build_default_endpoint(self) -> str:
        base = settings.qwen_base_url.rstrip("/")
        if "/compatible-mode/" in base:
            return base.replace("/compatible-mode/", "/compatible-api/") + "/reranks"
        if base.endswith("/v1"):
            return f"{base}/reranks"
        return f"{base}/reranks"


def _extract_model_inference_seconds(payload: dict[str, Any]) -> float | None:
    candidates = [
        (payload.get("usage") if isinstance(payload.get("usage"), dict) else None),
        (payload.get("output", {}).get("usage") if isinstance(payload.get("output"), dict) else None),
        (payload.get("meta") if isinstance(payload.get("meta"), dict) else None),
    ]

    keys = (
        "model_inference_seconds",
        "model_latency_seconds",
        "inference_seconds",
        "latency_seconds",
        "duration_seconds",
        "model_inference_ms",
        "model_latency_ms",
        "inference_ms",
        "latency_ms",
        "duration_ms",
    )

    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        for key in keys:
            if key not in obj:
                continue
            try:
                value = float(obj[key])
            except Exception:
                continue
            if key.endswith("_ms"):
                return value / 1000.0
            return value
    return None
