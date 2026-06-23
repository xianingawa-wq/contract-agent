from __future__ import annotations

import json
import time
from typing import Any
from urllib import error, request


class QwenRerankTransport:
    def __init__(self, *, api_key: str | None, endpoint: str, timeout_seconds: int) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.last_profile: dict[str, Any] = {}

    def request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("RERANK_API_KEY is not configured for rerank.")

        profile = {
            "json_serialize_seconds": 0.0,
            "network_seconds": 0.0,
            "response_json_parse_seconds": 0.0,
        }

        ser_started = time.perf_counter()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        profile["json_serialize_seconds"] = time.perf_counter() - ser_started

        headers = {
            "Authorization": f"Bearer {self.api_key}",
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
            self.last_profile = profile
            payload_text = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"rerank http error={exc.code}, body={payload_text[:300]}") from exc
        except error.URLError as exc:
            profile["network_seconds"] = time.perf_counter() - net_started
            self.last_profile = profile
            raise RuntimeError(f"rerank connection error: {exc}") from exc

        try:
            parse_started = time.perf_counter()
            data = json.loads(raw)
            profile["response_json_parse_seconds"] = time.perf_counter() - parse_started
        except Exception as exc:
            self.last_profile = profile
            raise RuntimeError(f"rerank response json parse failed: {raw[:300]}") from exc

        self.last_profile = profile
        return data
