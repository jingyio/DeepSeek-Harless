"""Loopback-only embedding port for bounded Motif candidate ranking."""

from __future__ import annotations

import json
import math
from urllib.parse import urlparse
from urllib.request import ProxyHandler, Request, build_opener


class LocalEmbeddingPort:
    """Use an OpenAI-compatible local embeddings endpoint; no remote fallback."""

    def __init__(self, endpoint: str, model: str, *, timeout_seconds: float = 20.0):
        parsed = urlparse(endpoint)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"127.0.0.1", "localhost", "::1"}
                or not parsed.path.endswith("/v1/embeddings")
                or not isinstance(model, str) or not model.strip()):
            raise ValueError("embedding endpoint must be loopback /v1/embeddings")
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, texts: list[str]) -> list[list[float]]:
        if (not isinstance(texts, list) or not 2 <= len(texts) <= 13
                or any(not isinstance(text, str) or not text.strip()
                       or len(text) > 2000 for text in texts)):
            raise ValueError("embedding inputs exceed the bounded candidate scope")
        request = Request(
            self.endpoint,
            data=json.dumps({"model": self.model, "input": texts},
                            ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with build_opener(ProxyHandler({})).open(
            request, timeout=self.timeout_seconds) as response:
            result = json.load(response)
        rows = result.get("data") if isinstance(result, dict) else None
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError("embedding response count changed")
        ordered = sorted(rows, key=lambda row: row.get("index", -1)
                         if isinstance(row, dict) else -1)
        if [row.get("index") for row in ordered] != list(range(len(texts))):
            raise ValueError("embedding response indices changed")
        vectors = [row.get("embedding") for row in ordered]
        if (any(not isinstance(vector, list) or not vector for vector in vectors)
                or len({len(vector) for vector in vectors}) != 1
                or any(isinstance(value, bool) or not isinstance(value, (int, float))
                       or not math.isfinite(value)
                       for vector in vectors for value in vector)):
            raise ValueError("embedding response has invalid vectors")
        return [[float(value) for value in vector] for vector in vectors]
