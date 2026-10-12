"""Per-task budget routing over the existing conservative DeepSeek gate.

The control endpoint is loopback-only and token authenticated. Registration is
immutable and inactive until a confirmed task is activated. Every model call
reserves against both its task cap and the unchanged whole-launch cap. It logs
only counters/usage and identities, never prompt bodies or authentication keys.
"""
from __future__ import annotations

import hmac
import json
import math
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit

from src.adapters.deepseek_cost_gate import State, reservation

TASK_ID = re.compile(r"^[a-f0-9]{32}$")
USAGE_FIELDS = ("prompt_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
                "completion_tokens", "total_tokens")


def session_identity(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise ValueError("invalid session identity")
    return value


class RoutedState:
    """State-compatible book/settle/log facade for one registered task."""
    def __init__(self, registry: TaskBudgetRegistry, task_id: str, session_id: str,
                 state: State):
        self.registry = registry
        self.task_id = task_id
        self.session_id = session_id
        self.state = state
        self.active = False
        self.cancelled = False
        self.denials = 0
        self.unknown_usage_requests = 0
        self.observed_cost_usd = 0.0
        self.usage = {key: 0 for key in USAGE_FIELDS}
        self._global_ids: dict[int, int] = {}

    def book(self, body: bytes) -> tuple[int, str, float, int] | None:
        model, dollars, ceiling = reservation(body, max_output=self.state.output_cap)
        run = self.registry.run_state
        # All routed admissions/settlements share this lock. Holding both State
        # locks makes the two reservations atomic even against other readers.
        with self.registry.lock, run.lock, self.state.lock:
            if not self.active or self.cancelled:
                self.denials += 1
                return None
            for state in (run, self.state):
                if (state.reserved_usd + dollars > state.cap_usd or
                        (state.request_limit is not None and state.request_count >= state.request_limit)):
                    self.denials += 1
                    return None
            for state in (run, self.state):
                state.reserved_usd += dollars
                state.request_count += 1
                state.pending[state.request_count] = dollars
            request_id = self.state.request_count
            self._global_ids[request_id] = run.request_count
            return request_id, model, dollars, ceiling

    def settle(self, request_id: int, model: str, status: int,
               usage: dict[str, int]) -> tuple[float | None, float]:
        with self.registry.lock:
            if request_id not in self.state.pending:
                raise ValueError("request already settled or not booked")
            global_id = self._global_ids[request_id]
            self.registry.run_state.settle(global_id, model, status, usage)
            observed, released = self.state.settle(request_id, model, status, usage)
            if observed is None:
                self.unknown_usage_requests += 1
            else:
                self.observed_cost_usd += observed
                for key in USAGE_FIELDS:
                    self.usage[key] += usage[key]
            return observed, released

    def log(self, row: dict[str, Any]) -> None:
        with self.registry.lock:
            task_row = {**row, "task_id": self.task_id, "session_id": self.session_id}
            request_id = row.get("request_id")
            global_id = self._global_ids.get(request_id)
            if global_id is not None:
                task_row["global_request_id"] = global_id
            self.state.log(task_row)
            run_row = dict(task_row)
            if global_id is not None:
                run_row["task_request_id"] = request_id
                run_row["request_id"] = global_id
            self.registry.run_state.log(run_row)


class TaskBudgetRegistry:
    def __init__(self, *, run_state: State, tasks_root: Path,
                 max_task_budget_usd: float | None = None,
                 task_request_limit: int | None = None):
        if (not isinstance(run_state.cap_usd, (int, float)) or isinstance(run_state.cap_usd, bool)
                or not math.isfinite(run_state.cap_usd) or run_state.cap_usd < 0
                or type(run_state.output_cap) is not int or run_state.output_cap < 1):
            raise ValueError("invalid whole-launch budget state")
        maximum = run_state.cap_usd if max_task_budget_usd is None else max_task_budget_usd
        if (not isinstance(maximum, (int, float)) or isinstance(maximum, bool)
                or not math.isfinite(maximum) or not 0 <= maximum <= run_state.cap_usd):
            raise ValueError("task maximum must not exceed whole-launch cap")
        self.run_state = run_state
        self.max_task_budget_usd = float(maximum)
        if task_request_limit is not None and (type(task_request_limit) is not int or task_request_limit < 1):
            raise ValueError("task_request_limit must be a positive integer")
        self.task_request_limit = run_state.request_limit if task_request_limit is None else task_request_limit
        self.tasks_root = Path(tasks_root).resolve()
        if ".local" not in self.tasks_root.parts:
            raise ValueError("task ledgers must stay inside a private .local directory")
        self.tasks_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.by_session: dict[str, RoutedState] = {}
        self.by_task: dict[str, RoutedState] = {}
        self.route_denials = 0

    def register(self, task_id: str, session_id: str, budget_usd: float) -> dict[str, Any]:
        if not isinstance(task_id, str) or TASK_ID.fullmatch(task_id) is None:
            raise ValueError("task_id must be 32 lowercase hexadecimal characters")
        session_id = session_identity(session_id)
        if (not isinstance(budget_usd, (int, float)) or isinstance(budget_usd, bool)
                or not math.isfinite(budget_usd) or not 0 <= budget_usd <= self.max_task_budget_usd):
            raise ValueError("task budget exceeds the server maximum")
        with self.lock:
            existing = self.by_session.get(session_id) or self.by_task.get(task_id)
            if existing is not None:
                if (existing.task_id != task_id or existing.session_id != session_id
                        or existing.state.cap_usd != budget_usd):
                    raise ValueError("immutable task registration conflicts")
                return self.stats(session_id)
            directory = self.tasks_root / task_id
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.is_symlink() or directory.resolve().parent != self.tasks_root:
                raise ValueError("task ledger directory escapes its private root")
            ledger = directory / "ledger.jsonl"
            # A cold restart cannot silently reset a pre-existing task ledger.
            try:
                descriptor = os.open(ledger, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as error:
                raise ValueError("task ledger exists; register a new task identity") from error
            os.close(descriptor)
            state = State(cap_usd=float(budget_usd), output_cap=self.run_state.output_cap,
                          request_limit=self.task_request_limit, record=ledger)
            route = RoutedState(self, task_id, session_id, state)
            self.by_session[session_id] = route
            self.by_task[task_id] = route
            return self.stats(session_id)

    def _route(self, session_id: str) -> RoutedState:
        session_id = session_identity(session_id)
        route = self.by_session.get(session_id)
        if route is None:
            raise KeyError("session has no registered task budget")
        return route

    def activate(self, session_id: str) -> dict[str, Any]:
        with self.lock:
            route = self._route(session_id)
            if route.cancelled:
                raise ValueError("cancelled task cannot be reactivated")
            route.active = True
            return self.stats(session_id)

    def cancel(self, session_id: str) -> dict[str, Any]:
        with self.lock:
            route = self._route(session_id)
            route.cancelled = True
            route.active = False
            return self.stats(session_id)

    def state_for(self, headers: Mapping[str, str]) -> RoutedState:
        session_id = next((value for key, value in headers.items()
                           if key.lower() == "x-deepseek-harness-session-id"), None)
        with self.lock:
            try:
                route = self._route(session_id)
            except (KeyError, ValueError):
                self.route_denials += 1
                raise PermissionError("model request has no admitted task budget") from None
            if not route.active or route.cancelled:
                route.denials += 1
                self.route_denials += 1
                raise PermissionError("task budget is inactive or cancelled")
            return route

    def stats(self, session_id: str) -> dict[str, Any]:
        with self.lock:
            route = self._route(session_id)
            with route.state.lock, self.run_state.lock:
                return {"task_id": route.task_id, "session_id": route.session_id,
                        "active": route.active, "cancelled": route.cancelled,
                        "budget_usd": route.state.cap_usd,
                        "request_limit": route.state.request_limit,
                        "output_cap": route.state.output_cap,
                        "upstream_requests": route.state.request_count,
                        **route.usage,
                        "estimated_cost_usd": route.state.reserved_usd,
                        "observed_peak_cost_usd": route.observed_cost_usd,
                        "pending_requests": len(route.state.pending),
                        "unknown_usage_requests": route.unknown_usage_requests,
                        "usage_complete": not route.state.pending and route.unknown_usage_requests == 0,
                        "denials": route.denials,
                        "global_budget_usd": self.run_state.cap_usd,
                        "global_upstream_requests": self.run_state.request_count,
                        "global_estimated_cost_usd": self.run_state.reserved_usd,
                        "global_request_limit": self.run_state.request_limit,
                        "global_route_denials": self.route_denials,
                        "cost_basis": "conservative_peak_estimate_not_provider_bill"}


def create_control_server(host: str, port: int, registry: TaskBudgetRegistry, *,
                          control_token: str) -> ThreadingHTTPServer:
    """Bind private task control; token is never returned or logged."""
    if host != "127.0.0.1":
        raise ValueError("budget control must bind IPv4 loopback")
    if not isinstance(control_token, str) or len(control_token) < 32:
        raise ValueError("control token must be generated with at least 32 characters")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            pass

        def reply(self, code: int, value: dict[str, Any]) -> None:
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(raw)
            self.close_connection = True

        def authenticated(self) -> bool:
            supplied = self.headers.get("X-SSS-Control-Token", "")
            if not hmac.compare_digest(supplied.encode(), control_token.encode()):
                self.reply(401, {"error": "task budget control authentication required"})
                return False
            return True

        def do_GET(self) -> None:  # noqa: N802
            if not self.authenticated():
                return
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            if parsed.path != "/tasks/stats" or set(query) != {"session_id"} or len(query["session_id"]) != 1:
                self.reply(404, {"error": "unknown task budget control route"})
                return
            try:
                self.reply(200, registry.stats(query["session_id"][0]))
            except (KeyError, ValueError):
                self.reply(404, {"error": "registered task not found"})

        def do_POST(self) -> None:  # noqa: N802
            if not self.authenticated():
                return
            routes = {"/tasks/register": registry.register,
                      "/tasks/activate": registry.activate, "/tasks/cancel": registry.cancel}
            if self.path not in routes:
                self.reply(404, {"error": "unknown task budget control route"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
                if not 0 < length <= 8192:
                    self.reply(413, {"error": "control request body exceeds limit"})
                    return
                value = json.loads(self.rfile.read(length))
                expected = {"task_id", "session_id", "budget_usd"} if self.path == "/tasks/register" else {"session_id"}
                if not isinstance(value, dict) or set(value) != expected:
                    raise ValueError("invalid task budget control fields")
                self.reply(200, routes[self.path](**value))
            except KeyError:
                self.reply(404, {"error": "registered task not found"})
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                self.reply(400, {"error": str(error)})

    return ThreadingHTTPServer((host, port), Handler)
