"""Real DSH + real MCP + bounded real DeepSeek Flash benchmark runner.

Default is preview. --call-model forwards requests through a persistent shared
CNY budget ledger; the real API key stays inside this parent process. All raw
traces and generated artifacts must be stored under ignored .local directories.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from importlib.metadata import version, PackageNotFoundError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from uuid import uuid4
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.harness_runtime import create_harness
from src.adapters.scenario import prepare_scenario
from src.adapters.native_budget import NativeBudgetGuard
from src.adapters.deepseek_cost_gate import response_usage
from src.adapters.dsh_trajectory import _observation_digest
from src.adapters.dsh_event_projection import is_original_tool_result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def append(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
    path.chmod(0o600)


def redact_diagnostics(text, secrets=()):
    """Preserve startup/transport evidence without serializing credentials."""
    value = str(text)
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED_API_KEY]", value)
    value = re.sub(r"(?i)(authorization\s*[:=]\s*['\"]?bearer\s+)[^\s,'\"}]+", r"\1[REDACTED]", value)
    return value[-100000:]


@contextmanager
def ledger_lock(path):
    """Process-wide ledger serialization; retain reservations across crashes."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0"); stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def estimated_cost(usage, rates):
    required = ("prompt_tokens", "prompt_cache_miss_tokens", "prompt_cache_hit_tokens", "completion_tokens", "total_tokens")
    if any(type(usage.get(key)) is not int or usage[key] < 0 for key in required):
        raise ValueError("incomplete_usage")
    if usage["prompt_cache_miss_tokens"] + usage["prompt_cache_hit_tokens"] != usage["prompt_tokens"]:
        raise ValueError("inconsistent_cache_usage")
    if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
        raise ValueError("inconsistent_total_usage")
    return (usage["prompt_cache_miss_tokens"] * rates["input_miss"] +
            usage["prompt_cache_hit_tokens"] * rates["input_hit"] +
            usage["completion_tokens"] * rates["output"]) / 1_000_000


class BudgetGate:
    def __init__(self, *, ledger, output, run_id, pricing, cap=100, output_cap=4096,
                 max_requests=30, key="", upstream="https://api.deepseek.com"):
        self.ledger, self.output = Path(ledger), Path(output)
        self.run_id, self.pricing, self.cap = run_id, pricing, cap
        self.output_cap, self.max_requests, self.key = output_cap, max_requests, key
        self.upstream = upstream.rstrip("/")
        parsed = urlparse(self.upstream)
        if not ((parsed.scheme == "https" and parsed.netloc == "api.deepseek.com" and not parsed.path)
                or (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1"))):
            raise ValueError("upstream_must_be_official_DeepSeek_or_an_offline_loopback_test")
        self.local_token = "rra-local-" + uuid4().hex
        self.count = 0
        self.rows = []
        self.lock = threading.Lock()

    def current_total(self):
        if not self.ledger.exists():
            return 0.0
        return sum(json.loads(line)["delta_cny"] for line in self.ledger.read_text(encoding="utf-8").splitlines())

    def book(self, body):
        request = json.loads(body)
        if request.get("model") != "deepseek-flash":
            raise ValueError("unapproved_model")
        output = request.get("max_tokens")
        if type(output) is not int or not 1 <= output <= self.output_cap:
            raise ValueError("unbounded_output")
        # Only text tools are enabled in this scenario. Disallow unpriced images.
        if '"image_url"' in body.decode("utf-8") or '"input_image"' in body.decode("utf-8"):
            raise ValueError("image_billing_not_enabled")
        input_upper = len(body) + 4000
        reserved = (input_upper * self.pricing["peak"]["input_miss"] +
                    output * self.pricing["peak"]["output"]) / 1_000_000
        with self.lock, ledger_lock(self.ledger):
            if self.count >= self.max_requests:
                raise ValueError("request_limit_reached")
            if self.current_total() + reserved > self.cap:
                raise ValueError("approved_CNY_budget_exhausted")
            self.count += 1
            request_id = f"{self.run_id}-{self.count:03d}"
            append(self.ledger, {"kind": "reserve", "request_id": request_id, "run_id": self.run_id,
                                "delta_cny": reserved, "utc_epoch": time.time(),
                                "pricing_sha256": digest(self.pricing), "cap_cny": self.cap})
        return request_id, reserved, input_upper

    def settle(self, request_id, reserved, status, usage):
        peak = offpeak = None
        if status == 200:
            try:
                peak = estimated_cost(usage, self.pricing["peak"])
                offpeak = estimated_cost(usage, self.pricing["offpeak"])
            except ValueError:
                pass
        if peak is not None:
            with self.lock, ledger_lock(self.ledger):
                append(self.ledger, {"kind": "settle", "request_id": request_id, "run_id": self.run_id,
                                    "delta_cny": peak - reserved, "peak_estimate_cny": peak,
                                    "offpeak_estimate_cny": offpeak, "usage": usage, "utc_epoch": time.time()})
        return peak, offpeak

    def create_server(self):
        gate = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            def log_message(self, *_args):
                pass
            def reply(self, status, content_type, raw):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            def do_POST(self):
                if self.headers.get("Authorization") != "Bearer " + gate.local_token:
                    self.reply(401, "application/json", b'{"error":"local session token required"}')
                    return
                if self.path != "/v1/chat/completions":
                    self.reply(403, "application/json", b'{"error":"unmetered endpoint refused"}')
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 8 * 1024 * 1024:
                        raise ValueError("invalid_body_size")
                    request = json.loads(self.rfile.read(size))
                    request["thinking"] = {"type": "disabled"}
                    if request.get("stream"):
                        request["stream_options"] = {"include_usage": True}
                    body = json.dumps(request, ensure_ascii=False).encode("utf-8")
                    request_id, reserved, ceiling = gate.book(body)
                except (ValueError, TypeError) as exc:
                    self.reply(429, "application/json", json.dumps({"error": str(exc)}).encode())
                    return
                folder = gate.output / "model-requests"
                save(folder / f"{request_id}.request.json", request)
                started = time.monotonic()
                upstream_request = urllib.request.Request(gate.upstream + self.path, data=body, headers={
                    "Authorization": "Bearer " + gate.key, "Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(upstream_request, timeout=900) as response:
                        status, content_type, answer = response.status, response.headers.get("Content-Type", "application/json"), response.read()
                except urllib.error.HTTPError as exc:
                    status, content_type, answer = exc.code, exc.headers.get("Content-Type", "application/json"), exc.read()
                except Exception as exc:
                    status, content_type = 502, "application/json"
                    answer = json.dumps({"error": "upstream unavailable", "exception_type": type(exc).__name__}).encode()
                # Never save Authorization, response headers, or provider credentials.
                raw_path = folder / f"{request_id}.response.txt"
                raw_path.write_bytes(answer); raw_path.chmod(0o600)
                usage = response_usage(content_type, answer)
                peak, offpeak = gate.settle(request_id, reserved, status, usage)
                row = {"request_id": request_id, "status": status, "model": request["model"],
                       "request_sequence": int(request_id.rsplit("-", 1)[1]), "request_sha256": hashlib.sha256(body).hexdigest(),
                       "thinking": request["thinking"], "input_ceiling": ceiling, "reserved_upper_cny": reserved,
                       "peak_estimate_cny": peak, "offpeak_estimate_cny": offpeak, "usage": usage,
                       "elapsed_seconds": time.monotonic() - started, "utc_epoch": time.time()}
                gate.rows.append(row)
                append(gate.output / "cost-ledger.jsonl", row)
                self.reply(status, content_type, answer)
        return ThreadingHTTPServer(("127.0.0.1", 0), Handler)


def frozen_sources(data_root, case):
    root = data_root / "cases" / case
    return [{"path": str((root / name).resolve()), "sha256": file_sha(root / name)}
            for name in ("data.csv", "study.json", "task.txt")]


def prepare(args):
    data_root, out = args.data_root.resolve(), args.out.resolve()
    if not (ROOT / ".local") in out.parents:
        raise ValueError("Raw trajectories must be stored under this repository's ignored .local directory")
    workspace = (args.workspace or (out / "workspace")).resolve()
    if workspace != out / "workspace":
        raise ValueError("Workspace must be the fresh output directory's workspace child")
    contracts = json.loads(args.contracts.read_text(encoding="utf-8"))
    source_files = frozen_sources(data_root, args.case)
    prompt = (data_root / "cases" / args.case / "task.txt").read_text(encoding="utf-8")
    if not prompt.strip():
        raise ValueError("empty_prompt")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "metrics.json").exists() or (out / "agent-events.jsonl").exists():
        raise ValueError("Run directory already contains results; use a fresh output")
    workspace.mkdir(parents=True, exist_ok=True)
    run_id, session_id = out.name + "-" + uuid4().hex[:8], "rra-" + uuid4().hex
    scenario = {"schema_version": 1, "name": "research_report", "prompt": str(data_root / "cases" / args.case / "task.txt"),
                "servers": [{"server_name": "research_report", "transport": "stdio", "command": sys.executable,
                             "args": [str(HERE / "server.py")], "cwd": str(ROOT), "tool_call_timeout_ms": 300000,
                             "env": {"RRA_DATA_ROOT": str(data_root), "RRA_RUN_ROOT": str(workspace), "RRA_CASE": args.case}}],
                "allowed_tools": list(contracts)}
    save(out / "scenario.json", scenario)
    prepared = prepare_scenario(out / "scenario.json", case=args.case)
    patches = [prepared["patch"]]
    # Explicit public profile configuration, identically applied to both arms.
    # The shared semantic patch already disables llm-retry; repeat it here so
    # this benchmark's effective configuration is auditable in one saved file.
    runtime_patch = [{"id": name, "disabled": True} for name in
                     ("llm-retry", "compaction-basic", "command-compact", "tool-result-pruner")]
    save(out / "runtime.patch.yml", runtime_patch)
    patches.append(str(out / "runtime.patch.yml"))
    env = {"DSH_HOME": str(out / "dsh"), "DEEPSEEK_API_KEY": "benchmark-local-budget-gate",
           "SSS_SCENARIO_TOOLS": json.dumps(list(contracts)),
           "SSS_ONLINE_MOTIF_MANIFEST": "", "SSS_ONLINE_MOTIF_TASK": "",
           "RRA_DATA_ROOT": str(data_root), "RRA_RUN_ROOT": str(workspace), "RRA_CASE": args.case}
    library = None
    if args.mode != "baseline":
        if args.library is None:
            raise ValueError("Motif modes require a learned and independently certified library")
        library = json.loads(args.library.read_text(encoding="utf-8"))
        if library["contracts_digest"] != digest(contracts):
            raise ValueError("library contracts changed")
        if args.case in library["training_cases"] or args.case == library["certification_case"]:
            raise ValueError("Motif evaluation must use a held-out case")
        task = {"session_id": session_id, "workspace": str(workspace), "source_files": source_files,
                "workspace_id": "workspace-" + hashlib.sha256(str(workspace).encode()).hexdigest()[:24],
                "study_version": digest({Path(row["path"]).name: row["sha256"] for row in source_files[:2]}),
                "csv_sha256": source_files[0]["sha256"], "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "audit_path": str(out / "motif-audit.jsonl")}
        save(out / "motif-task.json", task)
        motif_patch = [{"insert": [{"id": "rra-receipt-motif", "name": (HERE / "motif_plugin.mjs").as_uri()}]}]
        save(out / "motif.patch.yml", motif_patch)
        patches.append(str(out / "motif.patch.yml"))
        env.update(RRA_MOTIF_TASK=str(out / "motif-task.json"), RRA_MOTIF_LIBRARY=str(args.library.resolve()), RRA_MOTIF_MODE=args.mode)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        status = subprocess.check_output(["git", "status", "--short"], cwd=ROOT, text=True).strip()
    except Exception:
        commit = status = "unavailable"
    try:
        node_version = subprocess.check_output(["node", "--version"], text=True).strip()
        dsh_version = json.loads((ROOT / "node_modules/@deepseek-ai/dsh/package.json").read_text(encoding="utf-8"))["version"]
    except Exception:
        node_version = dsh_version = "unavailable"
    try:
        sdk_version = version("deepseek-harness")
    except PackageNotFoundError:
        sdk_version = "unavailable"
    pricing = json.loads(args.pricing.read_text(encoding="utf-8"))
    manifest = {"run_id": run_id, "session_id": session_id, "case_id": args.case, "mode": args.mode,
                "model": "deepseek-flash", "provider": "deepseek-official", "real_upstream": True,
                "reasoning_effort": "off", "thinking": "disabled", "question": prompt,
                "contracts_digest": digest(contracts), "source_files": source_files, "input_sha256": digest(source_files),
                "prompt_sha256": prepared["prompt_sha256"], "tool_order": list(contracts),
                "patch_sha256": prepared["patch_sha256"], "budget_cny": args.budget_cny,
                "budget_ledger": str(args.budget_ledger.resolve()), "max_requests": args.max_requests,
                "max_output": args.max_output, "compression": "compaction-basic, command-compact and tool-result-pruner explicitly disabled in runtime.patch.yml",
                "automatic_retries": "llm-retry explicitly disabled in runtime.patch.yml; every upstream attempt metered",
                "pricing": pricing, "commit": commit, "git_status": status, "python": sys.version,
                "node": node_version, "dsh": dsh_version, "python_sdk": sdk_version,
                "benchmark_code_sha256": {path.name: file_sha(path) for path in HERE.iterdir() if path.suffix in (".py", ".mjs", ".ts", ".json")},
                "library_digest": library["library_digest"] if library else None,
                "scope": "synthetic measured data; real statistics/rendering/filesystem/MCP/DSH/cloud model"}
    save(out / "manifest.json", manifest)
    return out, env, patches, manifest, pricing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--contracts", type=Path, default=HERE / "tool_contracts.json")
    parser.add_argument("--pricing", type=Path, default=HERE / "pricing.json")
    parser.add_argument("--mode", choices=("baseline", "shadow", "execute"), default="baseline")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--budget-cny", type=float, default=100)
    parser.add_argument("--budget-ledger", type=Path, required=True)
    parser.add_argument("--max-output", type=int, default=4096)
    parser.add_argument("--max-requests", type=int, default=30)
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    if not 0 < args.budget_cny <= 100 or not 1 <= args.max_output <= 8192 or not 1 <= args.max_requests <= 60:
        parser.error("Budget/output/request bounds exceed the authorized experiment")
    out, env, patches, manifest, pricing = prepare(args)
    print(json.dumps({"output": str(out), "case": args.case, "mode": args.mode, "model": "deepseek-flash",
                      "budget_cap_cny": args.budget_cny, "call_model": args.call_model,
                      "tool_count": len(manifest["tool_order"])}, ensure_ascii=False), flush=True)
    if not args.call_model:
        return 0
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY must be supplied in the parent environment")
    gate = BudgetGate(ledger=args.budget_ledger, output=out, run_id=manifest["run_id"], pricing=pricing,
                      cap=args.budget_cny, output_cap=args.max_output, max_requests=args.max_requests, key=key)
    server = gate.create_server()
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    env["DEEPSEEK_BASE_URL"] = f"http://127.0.0.1:{server.server_port}/v1"
    env["DEEPSEEK_API_KEY"] = gate.local_token
    guard = NativeBudgetGuard(max_model_requests=100, max_observed_input_tokens=None)
    def observe(notification):
        if notification.method == "session.event":
            event = notification.payload.get("event")
            if isinstance(event, dict):
                append(out / "agent-events.jsonl", event)
        guard.on_notification(notification)
    started = time.monotonic()
    metrics = {"status": "error"}
    harness = None
    try:
        harness = create_harness(root=ROOT, patches=tuple(patches), env=env, provider="deepseek-official",
                                 model="deepseek-flash", max_tokens=args.max_output, cwd=str(out), runtime_cwd=str(out),
                                 request_timeout_seconds=900)
        with harness:
            result = harness.run(manifest["question"], session_id=manifest["session_id"], on_notification=observe)
        save(out / "answer.md", result.final_response)
        metrics.update(status="done" if result.finish_reason == "completed" and result.final_response.strip() else "incomplete",
                       finish_reason=result.finish_reason)
    except Exception as exc:
        metrics.update(error_type=type(exc).__name__)
        runtime = "unavailable"
        try:
            # Read the pinned SDK's bounded diagnostic buffer only on failure;
            # this does not change its launch seam or execution behavior.
            if harness is not None:
                runtime = harness.client._runtime_diagnostics()
        except Exception as diagnostic_error:
            runtime = "diagnostic_capture_failed:" + type(diagnostic_error).__name__
        secrets = (key, gate.local_token)
        save(out / "error-diagnostics.json", {
            "error_type": type(exc).__name__,
            "message": redact_diagnostics(str(exc), secrets),
            "traceback": redact_diagnostics(traceback.format_exc(), secrets),
            "runtime_stderr": redact_diagnostics(runtime, secrets),
            "source": "SDK exception plus pinned SDK stderr tail; credentials redacted"})
    finally:
        if harness is not None:
            try:
                harness.close()
            except Exception as close_error:
                metrics["runtime_cleanup_error_type"] = type(close_error).__name__
        server.shutdown(); server.server_close(); worker.join(timeout=5)
    audit_file = out / "motif-audit.jsonl"
    audits = [json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines()] if audit_file.exists() else []
    usage = {name: sum(row["usage"].get(name, 0) for row in gate.rows) for name in
             ("prompt_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens", "completion_tokens", "total_tokens")}
    calls = {}
    report_verifications = []
    for event in guard.events:
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            calls[data.get("callId")] = data.get("name")
        elif is_original_tool_result(event):
            call_id = data.get("message", {}).get("source", {}).get("callId")
            if calls.get(call_id) == "mcp__research_report__verify_report":
                ok, _, output = _observation_digest(event, calls[call_id])
                report_verifications.append(bool(ok and output and output.get("ok") is not False
                                                 and output.get("quality_passed") is True))
    report_quality_passed = bool(report_verifications and report_verifications[-1])
    metrics.update(elapsed_seconds=time.monotonic() - started, upstream_requests=gate.count,
                   report_quality_passed=report_quality_passed,
                   report_verification_attempts=len(report_verifications),
                   agent_steps=guard.started_requests, usage=usage,
                   peak_estimate_cny=sum(row["peak_estimate_cny"] if row["peak_estimate_cny"] is not None else row["reserved_upper_cny"] for row in gate.rows),
                   offpeak_estimate_cny=sum(row["offpeak_estimate_cny"] if row["offpeak_estimate_cny"] is not None else row["reserved_upper_cny"] for row in gate.rows),
                   complete_usage_requests=sum(row["peak_estimate_cny"] is not None for row in gate.rows),
                   unknown_cost_requests=sum(row["peak_estimate_cny"] is None for row in gate.rows),
                   successful_upstream_requests=sum(row["status"] == 200 for row in gate.rows),
                   shared_budget_accounted_cny=gate.current_total(),
                   tool_calls=sum(row.get("type") == "tool/call" for row in guard.events),
                   verified_motif_bypasses=sum(row["kind"] == "model_request_skipped_verified" for row in audits),
                   run_id=manifest["run_id"], case_id=args.case, mode=args.mode)
    save(out / "metrics.json", metrics)
    print(json.dumps({"output": str(out), **metrics}, ensure_ascii=False), flush=True)
    return 0 if metrics["status"] == "done" else 2


if __name__ == "__main__":
    raise SystemExit(main())
