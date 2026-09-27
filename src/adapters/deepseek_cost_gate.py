"""Conservative local spending gate for isolated DeepSeek research trials.

Reserves a peak-price upper bound before *every* upstream request, including
requests issued internally by Distil. A successful response with complete
provider usage settles that reservation at the peak-price token estimate;
otherwise the full reservation remains charged against the cap. It never logs
prompt bodies or credentials. Reconcile the provider bill afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


PEAK_USD_PER_MILLION = {
    "deepseek-flash": (0.30, 1.20),
    "deepseek-v4-pro": (1.32, 3.96),
}
CACHE_HIT_PEAK_USD_PER_MILLION = {
    "deepseek-flash": 0.006,
    "deepseek-v4-pro": 0.044,
}
HOP_HEADERS = {"host", "connection", "content-length", "transfer-encoding",
               "accept-encoding", "keep-alive", "proxy-connection"}
FILE_PATH = re.compile(r"^/v1/files(?:/[A-Za-z0-9_-]+)?$")


def _image_count(value: Any) -> int:
    if isinstance(value, dict):
        return int(value.get("type") in {"image_url", "input_image", "file", "image"}) + sum(
            _image_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_image_count(item) for item in value)
    return 0


def reservation(body: bytes, *, max_output: int) -> tuple[str, float, int]:
    request = json.loads(body)
    if not isinstance(request, dict):
        raise ValueError("request body must be an object")
    model = request.get("model")
    if model not in PEAK_USD_PER_MILLION:
        raise ValueError("model is not in the approved peak-price table")
    output = request.get("max_tokens")
    if not isinstance(output, int) or isinstance(output, bool) or not 1 <= output <= max_output:
        raise ValueError("max_tokens is missing or exceeds the per-request cap")
    # Every text token consumes at least one UTF-8 byte on the wire. Reserve an
    # additional 2,000 tokens for protocol/accounting differences and 1,024 for
    # each image reference; inline base64 is already covered by body bytes.
    input_ceiling = len(body) + 2_000 + 1_024 * _image_count(request)
    input_rate, output_rate = PEAK_USD_PER_MILLION[model]
    dollars = (input_ceiling * input_rate + output * output_rate) / 1_000_000
    return model, dollars, input_ceiling


def response_usage(content_type: str, answer: bytes) -> dict[str, int]:
    """Extract only billable counters, including Distil's hidden requests."""
    payloads: list[dict[str, Any]] = []
    try:
        if "text/event-stream" in content_type:
            for line in answer.splitlines():
                if line.startswith(b"data:"):
                    data = line[5:].strip()
                    if data and data != b"[DONE]":
                        item = json.loads(data)
                        if isinstance(item, dict) and isinstance(item.get("usage"), dict):
                            payloads.append(item)
        else:
            item = json.loads(answer)
            if isinstance(item, dict) and isinstance(item.get("usage"), dict):
                payloads.append(item)
    except (ValueError, TypeError):
        return {}
    if not payloads:
        return {}
    usage = payloads[-1]["usage"]
    fields = ("prompt_tokens", "prompt_cache_hit_tokens",
              "prompt_cache_miss_tokens", "completion_tokens", "total_tokens")
    values = {field: usage.get(field) for field in fields}
    if any(type(value) is not int or value < 0 for value in values.values()):
        return {}
    if (values["prompt_tokens"] != values["prompt_cache_hit_tokens"]
            + values["prompt_cache_miss_tokens"]):
        return {}
    return values


def observed_peak_cost(model: str, usage: dict[str, int]) -> float:
    """Price a complete provider usage record without reading response content."""
    if model not in PEAK_USD_PER_MILLION:
        raise ValueError("model is not in the approved peak-price table")
    required = ("prompt_tokens", "prompt_cache_hit_tokens",
                "prompt_cache_miss_tokens", "completion_tokens", "total_tokens")
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in required):
        raise ValueError("incomplete provider usage")
    if (usage["prompt_tokens"] != usage["prompt_cache_hit_tokens"]
            + usage["prompt_cache_miss_tokens"]
            or usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]):
        raise ValueError("inconsistent provider usage")
    input_rate, output_rate = PEAK_USD_PER_MILLION[model]
    return (usage["prompt_cache_miss_tokens"] * input_rate
            + usage["prompt_cache_hit_tokens"] * CACHE_HIT_PEAK_USD_PER_MILLION[model]
            + usage["completion_tokens"] * output_rate) / 1_000_000


class State:
    def __init__(self, *, cap_usd: float, output_cap: int, record: Path):
        self.cap_usd = cap_usd
        self.output_cap = output_cap
        self.record = record
        self.reserved_usd = 0.0
        self.request_count = 0
        self.pending: dict[int, float] = {}
        self.lock = threading.Lock()

    def book(self, body: bytes) -> tuple[int, str, float, int] | None:
        model, dollars, ceiling = reservation(body, max_output=self.output_cap)
        with self.lock:
            if self.reserved_usd + dollars > self.cap_usd:
                return None
            self.reserved_usd += dollars
            self.request_count += 1
            self.pending[self.request_count] = dollars
            return self.request_count, model, dollars, ceiling

    def settle(self, request_id: int, model: str, status: int,
               usage: dict[str, int]) -> tuple[float | None, float]:
        """Release unused reservation only after a complete successful usage record."""
        with self.lock:
            reserved = self.pending.pop(request_id)
            if status != 200:
                return None, 0.0
            try:
                observed = observed_peak_cost(model, usage)
            except ValueError:
                return None, 0.0
            if observed > reserved:
                # The input ceiling was insufficient; account for the excess
                # and refuse future requests until the budget allows them.
                self.reserved_usd += observed - reserved
                return observed, 0.0
            released = reserved - observed
            self.reserved_usd -= released
            return observed, released

    def log(self, row: dict[str, Any]) -> None:
        self.record.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            with self.record.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
            os.chmod(self.record, 0o600)


def serve(host: str, port: int, upstream: str, state: State) -> None:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args: Any) -> None:
            pass

        def _reply(self, code: int, message: str) -> None:
            raw = json.dumps({"error": message}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/budget/health":
                self._reply(200, "ok")
            elif FILE_PATH.match(self.path):
                self._forward_file(None, "GET")
            else:
                self._reply(403, "budget gate only forwards model requests")

        def do_DELETE(self) -> None:  # noqa: N802
            if FILE_PATH.match(self.path):
                self._forward_file(None, "DELETE")
            else:
                self._reply(403, "unmetered endpoint refused")

        def _call_upstream(self, body: bytes | None, method: str) -> tuple[int, str, bytes]:
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in HOP_HEADERS}
            request = urllib.request.Request(upstream + self.path, data=body,
                                             headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=900) as response:
                    return (response.status,
                            response.headers.get("Content-Type", "application/json"),
                            response.read())
            except urllib.error.HTTPError as exc:
                return (exc.code, exc.headers.get("Content-Type", "application/json"),
                        exc.read())
            except Exception:
                return 502, "application/json", b'{"error":"upstream unavailable"}'

        def _send_upstream(self, status: int, content_type: str, answer: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(answer)))
            self.end_headers()
            self.wfile.write(answer)

        def _forward_file(self, body: bytes | None, method: str) -> None:
            # DeepSeek's Files API is free; image tokens are reserved when the
            # resulting file_id is used in a model request.
            started = time.monotonic()
            status, content_type, answer = self._call_upstream(body, method)
            state.log({"kind": "files_api", "method": method, "path": self.path,
                       "request_bytes": len(body or b""), "response_status": status,
                       "response_bytes": len(answer),
                       "elapsed_seconds": round(time.monotonic() - started, 3)})
            self._send_upstream(status, content_type, answer)

        def do_POST(self) -> None:  # noqa: N802
            file_upload = self.path == "/v1/files"
            if self.path != "/v1/chat/completions" and not file_upload:
                self._reply(403, "unmetered endpoint refused")
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._reply(400, "invalid request length")
                return
            maximum = 64 * 1024 * 1024 if file_upload else 8 * 1024 * 1024
            if not 0 < length <= maximum:
                self._reply(413, "request body exceeds budget gate limit")
                return
            body = self.rfile.read(length)
            if file_upload:
                self._forward_file(body, "POST")
                return
            try:
                booked = state.book(body)
            except (ValueError, TypeError, json.JSONDecodeError):
                self._reply(400, "unpriced or unbounded model request refused")
                return
            if booked is None:
                self._reply(429, "approved research budget exhausted")
                return
            request_id, model, dollars, ceiling = booked
            started = time.monotonic()
            status, content_type, answer = self._call_upstream(body, "POST")
            usage = response_usage(content_type, answer)
            observed, released = state.settle(request_id, model, status, usage)
            state.log({"request_id": request_id, "model": model,
                       "reserved_upper_usd": round(dollars, 8),
                       "observed_peak_usd": round(observed, 8) if observed is not None else None,
                       "reservation_released_usd": round(released, 8),
                       "input_token_ceiling": ceiling, "response_status": status,
                       "response_bytes": len(answer),
                       "response_usage": usage,
                       "request_utc_epoch": round(time.time(), 3),
                       "elapsed_seconds": round(time.monotonic() - started, 3)})
            self._send_upstream(status, content_type, answer)

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--upstream", default="https://api.deepseek.com")
    parser.add_argument("--cap-usd", type=float, required=True)
    parser.add_argument("--max-output", type=int, default=3000)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.cap_usd <= 100 or not 1 <= args.max_output <= 8000:
        parser.error("invalid research budget")
    root = Path(__file__).resolve().parents[2]
    record = args.record.resolve()
    if not record.is_relative_to(root / ".local"):
        parser.error("private request ledger must be under .local")
    serve("127.0.0.1", args.port, args.upstream.rstrip("/"),
          State(cap_usd=args.cap_usd, output_cap=args.max_output, record=record))


if __name__ == "__main__":
    main()
