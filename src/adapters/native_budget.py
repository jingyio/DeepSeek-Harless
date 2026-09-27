"""Best-effort request and observed-token guard for tool-enabled DSH runs."""

from __future__ import annotations

from typing import Any


class NativeBudgetExceeded(RuntimeError):
    pass


class NativeBudgetGuard:
    def __init__(self, *, max_model_requests: int | None,
                 max_observed_input_tokens: int | None) -> None:
        if ((max_model_requests is not None and not 1 <= max_model_requests <= 100)
                or (max_observed_input_tokens is not None
                    and max_observed_input_tokens < 1)):
            raise ValueError("invalid native Agent budget")
        self.max_model_requests = max_model_requests
        self.max_observed_input_tokens = max_observed_input_tokens
        self.started_requests = 0
        self.observed_input_tokens = 0
        self.events: list[dict[str, Any]] = []

    def observe_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        kind = event.get("type")
        if (kind == "step/start" and self.max_model_requests is not None
                and self.started_requests >= self.max_model_requests):
            raise NativeBudgetExceeded("model request limit reached before the next agent step")
        self.events.append(event)
        if kind == "step/start":
            self.started_requests += 1
        elif kind == "assistant/message":
            usage = (event.get("data") or {}).get("usage")
            if isinstance(usage, dict):
                self.observed_input_tokens += int(usage.get("inputTokens") or 0)
                self.observed_input_tokens += int(usage.get("cacheReadTokens") or 0)
                if (self.max_observed_input_tokens is not None
                        and self.observed_input_tokens > self.max_observed_input_tokens):
                    raise NativeBudgetExceeded("observed input token limit reached")

    def on_notification(self, notification: Any) -> None:
        if getattr(notification, "method", None) != "session.event":
            return
        event = getattr(notification, "payload", {}).get("event")
        if isinstance(event, dict):
            self.observe_event(event)
