"""SSS-owned projection and recovery for the newest certified tool-result batch.

The original and its restore handle belong to SSS. Distil may be used downstream,
but neither this module nor ``sss_expand`` depends on Distil's implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from src.motif_core.offline.trace_compiler import artifact_signature
from src.motif_core.output_view_codecs import CODECS


_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_HOP_HEADERS = {"connection", "host", "content-length", "transfer-encoding", "keep-alive",
                "proxy-authenticate", "proxy-authorization", "te", "trailers", "upgrade"}
_EXPAND_TOOL = {"type": "function", "function": {
    "name": "sss_expand",
    "description": "Recover the complete original tool result for an SSS projection marker. "
                   "Call this when omitted fields may affect the answer or citation. "
                   "Use the eight-character handle shown as handle=XXXXXXXX.",
    "parameters": {"type": "object", "properties": {"handle": {"type": "string"}},
                   "required": ["handle"]}}}


def load_certified_projection(path: Path) -> tuple[str, dict[str, tuple[str, ...]]]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(artifact, dict) and artifact.get("status") == "certified_read_library":
        from src.motif_core.offline.library_builder import validate_read_motif_library

        validate_read_motif_library(artifact)
        rows = artifact["artifacts"]
        if len(rows) != 1:
            raise ValueError("projection requires exactly one selected certified Motif")
        artifact = rows[0]
    if (not isinstance(artifact, dict)
            or artifact.get("status") != "trace_validated_read_only"
            or artifact.get("certified_digest") != artifact_signature(artifact)):
        raise ValueError("projection requires an unchanged, certified read Motif")
    tools = artifact.get("tools")
    if not isinstance(tools, list) or not tools or not all(isinstance(t, str) for t in tools):
        raise ValueError("certified Motif has no valid tools")
    fields: dict[str, set[str]] = {name: set() for name in tools}
    for edge in [*(artifact.get("transfer_evidence") or []),
                 *(artifact.get("selection_evidence") or [])]:
        if not isinstance(edge, dict):
            raise ValueError("invalid compiled field edge")
        tool, field = edge.get("from_tool"), edge.get("from_field")
        if tool not in fields or not isinstance(field, str) or not _PATH.fullmatch(field):
            raise ValueError("compiled field edge is outside the certified Motif")
        fields[tool].add(field)
    return artifact["certified_digest"], {name: tuple(sorted(paths)) for name, paths in fields.items()}


def load_certified_evidence_views(path: Path) -> dict[str, str]:
    """Accept only codec plans sealed into the selected certified Motif."""
    load_certified_projection(path)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    if artifact.get("status") == "certified_read_library":
        artifact = artifact["artifacts"][0]
    rules = artifact.get("output_projections", {})
    if not isinstance(rules, dict) or set(rules) - set(artifact["tools"]):
        raise ValueError("invalid compiled output projection tools")
    views = {}
    for tool, rule in rules.items():
        if (not isinstance(rule, dict) or rule.get("codec") not in CODECS
                or rule.get("training_trace_ids") != artifact["source_trace_ids"]
                or rule.get("validation_trace_id") != artifact["validation_trace_id"]
                or rule.get("evidence_retention") != "all_visible_text_and_headers"
                or rule.get("restore") != "exact_original"
                or not isinstance(rule.get("proofs"), list)
                or len(rule["proofs"]) != len(artifact["source_trace_ids"]) + 1
                or any(not isinstance(row, dict) for row in rule["proofs"])
                or [row.get("trace_id") for row in rule["proofs"]]
                != [*artifact["source_trace_ids"], artifact["validation_trace_id"]]):
            raise ValueError("compiled output projection lacks independent evidence")
        proofs = rule["proofs"]
        if (len({row.get("original_sha256") for row in proofs}) != len(proofs)
                or any(not all(isinstance(row.get(key), str)
                                   and re.fullmatch(r"[0-9a-f]{64}", row[key])
                                   for key in ("original_sha256", "view_sha256",
                                               "observation_sha256"))
                       or not isinstance(row.get("visible_fragments"), int)
                       or row["visible_fragments"] < 2
                       or not isinstance(row.get("original_bytes"), int)
                       or not isinstance(row.get("view_bytes"), int)
                       or row["view_bytes"] >= row["original_bytes"] * 0.75
                       for row in proofs)):
            raise ValueError("compiled output projection proof is invalid")
        views[tool] = rule["codec"]
    return views


def _get_path(value: dict[str, Any], path: str) -> Any:
    node: Any = value
    for segment in path.split("."):
        if not isinstance(node, dict) or segment not in node:
            raise KeyError(path)
        node = node[segment]
    return node


def _put_path(value: dict[str, Any], path: str, item: Any) -> None:
    node = value
    parts = path.split(".")
    for segment in parts[:-1]:
        node = node.setdefault(segment, {})
    node[parts[-1]] = item


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class LatestToolProjector:
    def __init__(self, artifact: Path, local_dir: Path) -> None:
        self.signature, self.fields = load_certified_projection(artifact)
        self.evidence_views = load_certified_evidence_views(artifact)
        self.local_dir = local_dir
        self.local_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _store_original(self, key: str, tool: str, call_id: str, raw: str) -> str:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        record = {"tool": tool, "tool_call_id": call_id, "sha256": digest,
                  "certified_digest": self.signature, "content": raw}
        path = self.local_dir / "originals" / f"{key}.json"
        if not path.exists():
            _write_private(path, json.dumps(record, ensure_ascii=False).encode("utf-8"))
        return digest

    def _register_handle(self, handle: str, raw: str) -> bool:
        path = self.local_dir / "restore" / handle
        if path.exists():
            return path.read_bytes() == raw.encode("utf-8")
        _write_private(path, raw.encode("utf-8"))
        return path.read_bytes() == raw.encode("utf-8")

    def expand(self, handle: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{8}", handle):
            raise KeyError("invalid SSS handle")
        path = self.local_dir / "restore" / handle
        original = path.read_bytes()
        if hashlib.sha256(original).hexdigest()[:8] != handle:
            raise ValueError("SSS restore content does not match handle")
        _write_private(self.local_dir / "expansions" / uuid4().hex, b"restored\n")
        return original.decode("utf-8")

    def _project_tool(self, tool: str, call_id: str, raw: str, *, latest: bool) -> str:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key = hashlib.sha256(f"{self.signature}\0{tool}\0{call_id}\0{digest}".encode()).hexdigest()
        seen = (self.local_dir / "originals" / f"{key}.json").exists()
        self._store_original(key, tool, call_id, raw)
        saved = self.local_dir / "views" / f"{key}.txt"
        if saved.exists():
            view = saved.read_text(encoding="utf-8")
            return view if self._register_handle(digest[:8], raw) else raw
        if seen or not latest or (not self.fields.get(tool)
                                   and tool not in self.evidence_views):
            return raw
        codec_id = self.evidence_views.get(tool)
        if codec_id:
            try:
                evidence, _ = CODECS[codec_id](raw)
            except (ValueError, TypeError, KeyError):
                return raw
            handle = digest[:8]
            view = json.dumps({"sss_projection": {
                "tool": tool, "codec": codec_id,
                "evidence": evidence,
                "omitted": "presentation HTML and link URLs",
                "restore": f"<<sss_expand full tool result, handle={handle}>>"}},
                ensure_ascii=False, separators=(",", ":"))
            if len(view.encode("utf-8")) >= len(raw.encode("utf-8")):
                return raw
            if not self._register_handle(handle, raw):
                return raw
            _write_private(saved, view.encode("utf-8"))
            return view
        try:
            value = json.loads(raw)
            if not isinstance(value, dict):
                return raw
            status = value.get("status")
            if value.get("isError") is True or (
                    isinstance(status, str) and status in {"error", "failed", "unavailable"}):
                return raw
            kept: dict[str, Any] = {}
            for path in self.fields[tool]:
                _put_path(kept, path, _get_path(value, path))
        except (ValueError, TypeError, KeyError):
            return raw
        handle = digest[:8]
        view = json.dumps({"sss_projection": {"tool": tool, "kept": kept,
                           "omitted_top_level_fields": sorted(set(value) - set(kept)),
                           "restore": f"<<sss_expand full tool result, handle={handle}>>"}},
                          ensure_ascii=False, separators=(",", ":"))
        if len(view.encode("utf-8")) >= len(raw.encode("utf-8")):
            return raw
        if not self._register_handle(handle, raw):
            return raw
        _write_private(saved, view.encode("utf-8"))
        return view

    def project(self, body: dict[str, Any]) -> dict[str, Any]:
        messages = body.get("messages")
        if not isinstance(messages, list):
            return body
        newest_call = -1
        for index, message in enumerate(messages):
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list) or not tool_calls:
                continue
            newest_call = index
        if newest_call >= 0 and any(
                isinstance(message, dict) and message.get("role") in {"assistant", "user"}
                for message in messages[newest_call + 1:]):
            newest_call = -1
        changed = False
        projected = []
        active_calls: dict[str, tuple[str, int]] = {}
        with self._lock:
            for index, message in enumerate(messages):
                if not isinstance(message, dict):
                    projected.append(message)
                    continue
                if message.get("role") in {"assistant", "user"}:
                    active_calls = {}
                    tool_calls = message.get("tool_calls")
                    for row in tool_calls if isinstance(tool_calls, list) else []:
                        if isinstance(row, dict) and isinstance(row.get("function"), dict):
                            call_id, name = row.get("id"), row["function"].get("name")
                            if isinstance(call_id, str) and isinstance(name, str):
                                active_calls[call_id] = (name, index)
                    projected.append(message)
                    continue
                if message.get("role") != "tool":
                    projected.append(message)
                    continue
                call_id, raw = message.get("tool_call_id"), message.get("content")
                if not isinstance(call_id, str) or not isinstance(raw, str):
                    projected.append(message)
                    continue
                entry = active_calls.get(call_id)
                if entry is None or entry[1] >= index:
                    projected.append(message)
                    continue
                tool, call_index = entry
                view = self._project_tool(tool, call_id, raw, latest=call_index == newest_call)
                changed |= view != raw
                projected.append({**message, "content": view} if view != raw else message)
        return {**body, "messages": projected} if changed else body


class CompactJsonProjector(LatestToolProjector):
    """Losslessly compact the newest JSON tool results, preserving every value."""

    def __init__(self, local_dir: Path) -> None:
        self.local_dir = local_dir
        self.local_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _project_tool(self, tool: str, call_id: str, raw: str, *, latest: bool) -> str:
        if not latest:
            return raw
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return raw
        if not isinstance(value, (dict, list)):
            return raw
        view = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        original_bytes, view_bytes = len(raw.encode("utf-8")), len(view.encode("utf-8"))
        if view_bytes >= original_bytes or json.loads(view) != value:
            return raw
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        key = hashlib.sha256(f"json-compact-v1\0{tool}\0{call_id}\0{digest}".encode()).hexdigest()
        original_path = self.local_dir / "originals" / f"{key}.txt"
        view_path = self.local_dir / "views" / f"{key}.txt"
        audit_path = self.local_dir / "audit" / f"{key}.json"
        if not original_path.exists():
            _write_private(original_path, raw.encode("utf-8"))
            _write_private(view_path, view.encode("utf-8"))
            _write_private(audit_path, json.dumps({
                "tool": tool, "tool_call_id": call_id,
                "original_sha256": digest,
                "view_sha256": hashlib.sha256(view.encode("utf-8")).hexdigest(),
                "original_bytes": original_bytes, "view_bytes": view_bytes,
                "all_fields_preserved": True,
            }, ensure_ascii=False).encode("utf-8"))
        elif original_path.read_bytes() != raw.encode("utf-8") or view_path.read_bytes() != view.encode("utf-8"):
            raise ValueError("JSON compaction changed for an existing tool result")
        return view


def with_expand_tool(body: dict[str, Any]) -> dict[str, Any]:
    tools = body.get("tools")
    if tools is None:
        tools = []
    if not isinstance(tools, list):
        raise ValueError("chat tools must be a list")
    if any(isinstance(tool, dict) and isinstance(tool.get("function"), dict)
           and tool["function"].get("name") == "sss_expand" for tool in tools):
        raise ValueError("sss_expand is reserved for the SSS projection proxy")
    return {**body, "tools": [*tools, _EXPAND_TOOL]}


def resolve_sss_calls(body: dict[str, Any], response: dict[str, Any],
                      projector: LatestToolProjector) -> dict[str, Any] | None:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return None
    calls = message.get("tool_calls")
    if not isinstance(calls, list) or not calls:
        return None
    names = [row["function"].get("name") for row in calls
             if isinstance(row, dict) and isinstance(row.get("function"), dict)]
    if "sss_expand" not in names:
        return None
    if len(names) != len(calls) or any(name != "sss_expand" for name in names):
        raise ValueError("sss_expand cannot be mixed with client tool calls")
    messages = list(body.get("messages") or [])
    messages.append(message)
    for call in calls:
        args = json.loads(call["function"].get("arguments") or "{}")
        handle = args.get("handle")
        if not isinstance(handle, str):
            raise ValueError("sss_expand needs a handle")
        content = projector.expand(handle)
        messages.append({"role": "tool", "tool_call_id": call["id"], "content": content})
    return {**body, "messages": messages}


def _as_sse(response: dict[str, Any]) -> bytes:
    choice = response["choices"][0]
    message = choice.get("message") or {}
    delta = {key: value for key, value in message.items() if key in {"role", "content", "tool_calls"}}
    frame = {key: response[key] for key in ("id", "created", "model") if key in response}
    frame.update({"object": "chat.completion.chunk", "choices": [
        {"index": 0, "delta": delta, "finish_reason": choice.get("finish_reason")}]})
    usage = response.get("usage")
    if usage is not None:
        frame["usage"] = usage
    return ("data: " + json.dumps(frame, ensure_ascii=False) + "\n\n"
            + "data: [DONE]\n\n").encode("utf-8")


def _merge_usage(responses: list[dict[str, Any]]) -> dict[str, Any] | None:
    usages = [row.get("usage") for row in responses if isinstance(row.get("usage"), dict)]
    if not usages:
        return None
    result: dict[str, Any] = {}
    for usage in usages:
        for key, value in usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                result[key] = result.get(key, 0) + value
    return result


def serve(upstream: str, artifact: Path | None, local_dir: Path, port: int,
          *, compact_json_only: bool = False) -> None:
    target = urlsplit(upstream)
    if target.scheme != "http" or target.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("projection proxy only forwards to a local HTTP proxy")
    if compact_json_only == (artifact is not None):
        raise ValueError("choose exactly one projection mode")
    projector = CompactJsonProjector(local_dir) if compact_json_only else LatestToolProjector(artifact, local_dir)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/projection/health":
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")
                return
            self._forward(None)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            self._forward(self.rfile.read(length))

        def _forward(self, raw: bytes | None) -> None:
            if raw is not None and self.path.endswith("/chat/completions"):
                try:
                    body = json.loads(raw)
                    if not isinstance(body, dict):
                        raise ValueError("chat request must be a JSON object")
                    self._chat(body)
                except (ValueError, TypeError, KeyError, OSError,
                        http.client.HTTPException) as exc:
                    self._error_json(502, str(exc))
                return
            self._passthrough(raw)

        def _upstream(self, raw: bytes) -> tuple[int, bytes, str]:
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=300)
            try:
                headers = {name: value for name, value in self.headers.items()
                           if name.lower() not in _HOP_HEADERS}
                headers["Content-Length"] = str(len(raw))
                conn.request("POST", self.path, body=raw, headers=headers)
                response = conn.getresponse()
                return response.status, response.read(), response.getheader("Content-Type", "application/json")
            finally:
                conn.close()

        def _send(self, status: int, content: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _error_json(self, status: int, detail: str) -> None:
            payload = json.dumps({"error": {"message": detail, "type": "sss_projection_error"}}).encode()
            self._send(status, payload, "application/json")

        def _chat(self, body: dict[str, Any]) -> None:
            client_stream = body.get("stream") is True
            prepared = projector.project(body)
            if compact_json_only:
                status, raw, content_type = self._upstream(json.dumps(
                    prepared, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                self._send(status, raw, content_type)
                return
            prepared = with_expand_tool(prepared)
            prepared = {**prepared, "stream": False}
            prepared.pop("stream_options", None)
            responses: list[dict[str, Any]] = []
            for _ in range(5):
                status, raw, content_type = self._upstream(json.dumps(
                    prepared, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                if status >= 400:
                    self._send(status, raw, content_type)
                    return
                response = json.loads(raw)
                if not isinstance(response, dict):
                    raise ValueError("upstream response is not a JSON object")
                responses.append(response)
                continuation = None if compact_json_only else resolve_sss_calls(prepared, response, projector)
                if continuation is None:
                    merged = _merge_usage(responses)
                    if merged is not None:
                        response["usage"] = merged
                    output = _as_sse(response) if client_stream else json.dumps(
                        response, ensure_ascii=False).encode("utf-8")
                    self._send(200, output, "text/event-stream" if client_stream
                               else "application/json")
                    return
                prepared = continuation
            raise ValueError("sss_expand exceeded four continuation requests")

        def _passthrough(self, raw: bytes | None) -> None:
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=300)
            try:
                headers = {name: value for name, value in self.headers.items()
                           if name.lower() not in _HOP_HEADERS}
                conn.request(self.command, self.path, body=raw, headers=headers)
                response = conn.getresponse()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in _HOP_HEADERS:
                        self.send_header(name, value)
                self.end_headers()
                while chunk := response.read(65536):
                    self.wfile.write(chunk)
                    self.wfile.flush()
            except (OSError, http.client.HTTPException):
                self.send_error(502)
            finally:
                conn.close()

        def log_message(self, *_args: Any) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--compact-json-only", action="store_true")
    parser.add_argument("--local-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    serve(args.upstream, args.artifact, args.local_dir, args.port,
          compact_json_only=args.compact_json_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
