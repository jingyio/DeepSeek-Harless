"""Scenario-independent bounded DeepSeek Harness SDK request."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


class SemanticValidationError(ValueError):
    def __init__(self, message: str, *, metrics: dict[str, Any], raw_response: str) -> None:
        super().__init__(message)
        self.metrics = metrics
        self.raw_response = raw_response


def require_budget_gate() -> None:
    """Refuse a paid DSH request unless it is routed through the local cost gate."""
    endpoint = urlparse(os.environ.get("DEEPSEEK_BASE_URL", ""))
    try:
        cap = float(os.environ.get("SSS_BUDGET_CAP_USD", ""))
    except ValueError:
        cap = 0
    if (os.environ.get("SSS_BUDGET_GATE_ACTIVE") != "1"
            or endpoint.scheme != "http"
            or endpoint.hostname not in {"127.0.0.1", "localhost", "::1"}
            or endpoint.port is None
            or not 0 < cap < float("inf")
            or not os.environ.get("SSS_BUDGET_LEDGER")):
        raise ValueError("paid semantic request requires a local budget gate with a positive cap")


def _usage(events: list[dict[str, Any]]) -> dict[str, int]:
    totals = {key: 0 for key in ("inputTokens", "cacheReadTokens", "outputTokens", "totalTokens", "reasoningTokens")}
    requests = 0
    for event in events:
        if event.get("type") != "assistant/message":
            continue
        usage = event.get("data", {}).get("usage")
        if not isinstance(usage, dict):
            continue
        requests += 1
        for key in totals:
            totals[key] += int(usage.get(key) or 0)
    return {"model_requests": requests, **totals}


def call_bounded_prompt(prompt: str, *, root: Path, model: str = "deepseek-flash",
                        max_output_tokens: int = 1200,
                        max_prompt_characters: int = 12_000) -> tuple[str, dict[str, Any]]:
    require_budget_gate()
    if len(prompt) > max_prompt_characters or max_output_tokens < 1:
        raise ValueError("semantic request exceeds its configured budget")
    from src.adapters.harness_runtime import create_harness

    workspace = root / ".local" / "semantic-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with create_harness(
        root=root,
        provider="deepseek-official",
        model=model,
        max_tokens=max_output_tokens,
        cwd=str(workspace),
        runtime_cwd=str(workspace),
        patches=(str(root / "config" / "semantic-sdk.patch.yml"),),
        request_timeout_seconds=120,
    ) as harness:
        result = harness.run(prompt, session_id=f"sss-semantic-{uuid4().hex}")
    metrics = {
        "provider": "deepseek-official", "model": model,
        "reasoning_effort": "off",
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "prompt_characters": len(prompt), "max_output_tokens_per_request": max_output_tokens,
        "finish_reason": result.finish_reason, **_usage(result.events),
        "note": "SDK 0.1.5rc1 client with local npm DSH 0.1.5-rc.3 runtime; assistant/message usage only",
    }
    if not result.final_response.strip():
        raise SemanticValidationError("Harness returned no visible answer", metrics=metrics,
                                      raw_response=result.final_response)
    return result.final_response, metrics
