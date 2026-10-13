"""v2 arbitrary CSV/request entrypoint using the existing real DSH loop.

BudgetGate/logging are imported unchanged from v1; no second agent loop, no
unmetered API client. Preview is default, paid execution requires --call-model.
"""
from __future__ import annotations
import argparse
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from uuid import uuid4

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v1.runner import (
    BudgetGate, digest, file_sha, save, append, redact_diagnostics,
    create_harness, prepare_scenario, NativeBudgetGuard,
    _observation_digest, is_original_tool_result)
from benchmarks.research_report_agent_v2.intake import materialize
from benchmarks.research_report_agent_v2.matched_protocol import fixed_decisions

def frozen_sources(data_root, case):
    root = data_root / "cases" / case
    return [{"path": str((root / name).resolve()), "sha256": file_sha(root / name)}
            for name in ("data.csv", "study.json", "task.txt")]


def prepare(args):
    out = args.out.resolve()
    if not (ROOT / ".local") in out.parents:
        raise ValueError("Raw trajectories must be stored under this repository's ignored .local directory")
    if (out / "metrics.json").exists() or (out / "agent-events.jsonl").exists():
        raise ValueError("Run directory already contains results; use a fresh output")
    if args.data is not None:
        if args.data_root or args.case or not args.request_file:
            raise ValueError("Use --data/--request-file or --data-root/--case, not both")
        incoming = dict(data=args.data, request_file=args.request_file,
                        study_json=args.study_json, outline_file=args.outline_file)
    else:
        if not args.data_root or not args.case or args.request_file or args.study_json or args.outline_file:
            raise ValueError("Provide --data CSV --request-file TXT [--study-json JSON] [--outline-file TXT], or --data-root DIR --case ID")
        source = (args.data_root / "cases" / args.case).resolve()
        if source.parent != (args.data_root / "cases").resolve():
            raise ValueError("Case must be a direct scoped child")
        incoming = dict(data=source / "data.csv", request_file=source / "task.txt",
                        study_json=source / "study.json", case_id=args.case)
    intake = materialize(destination=out / "sources", **incoming)
    data_root, args.case = Path(intake["data_root"]), intake["case_id"]
    scoped_study = json.loads((Path(intake["folder"]) / "study.json").read_text(encoding="utf-8"))
    controlled = fixed_decisions(scoped_study)
    save(out / "intake.json", intake)
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
        if library.get("benchmark_version") != 2:
            raise ValueError("v2 requires a library compiled from v2 business-accepted trajectories")
        if library["contracts_digest"] != digest(contracts):
            raise ValueError("library contracts changed")
        if args.case in library["training_cases"] or args.case == library["certification_case"]:
            raise ValueError("Motif evaluation must use a held-out case")
        if source_files[0]["sha256"] in [*library.get("training_csv_sha256", []), library.get("certification_csv_sha256")]:
            raise ValueError("Motif evaluation cannot alias a training/certification dataset")
        task = {"session_id": session_id, "workspace": str(workspace), "source_files": source_files,
                "workspace_id": "workspace-" + hashlib.sha256(str(workspace).encode()).hexdigest()[:24],
                "study_version": digest({Path(row["path"]).name: row["sha256"] for row in source_files}),
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
                "contracts_digest": digest(contracts), "source_files": source_files, "input_sha256": digest(source_files), "input_content_digest": digest(intake["source_sha256"]),
                "prompt_sha256": prepared["prompt_sha256"], "tool_order": list(contracts),
                "patch_sha256": prepared["patch_sha256"], "budget_cny": args.budget_cny,
                "budget_ledger": str(args.budget_ledger.resolve()), "max_requests": args.max_requests,
                "max_output": args.max_output, "compression": "compaction-basic, command-compact and tool-result-pruner explicitly disabled in runtime.patch.yml",
                "automatic_retries": "llm-retry explicitly disabled in runtime.patch.yml; every upstream attempt metered",
                "pricing": pricing, "commit": commit, "git_status": status, "python": sys.version,
                "node": node_version, "dsh": dsh_version, "python_sdk": sdk_version,
                "benchmark_code_sha256": {path.name: file_sha(path) for path in HERE.iterdir() if path.suffix in (".py", ".mjs", ".ts", ".json")},
                "library_digest": library["library_digest"] if library else None,
                "experiment_id": getattr(args, "experiment_id", "research-report-agent-v2-20261010"),
                "comparison_protocol": "frozen_semantic_decisions" if controlled else "natural_request",
                "frozen_decisions_sha256": controlled["decision_sha256"] if controlled else None,
                "budget_implementation": "v1.runner.BudgetGate, imported unchanged",
                "budget_implementation_sha256": file_sha(HERE.parent / "research_report_agent_v1" / "runner.py"),
                "intake": intake, "benchmark_version": 2,
                "benchmark_split": scoped_study.get("split"),
                "scope": "scoped user-provided CSV/request; synthetic only when input metadata says so; real tools/DSH/MCP/cloud"}
    save(out / "manifest.json", manifest)
    return out, env, patches, manifest, pricing


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--request-file", type=Path)
    parser.add_argument("--study-json", type=Path)
    parser.add_argument("--outline-file", type=Path)
    parser.add_argument("--case")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--contracts", type=Path, default=HERE / "tool_contracts.json")
    parser.add_argument("--pricing", type=Path, default=HERE.parent / "research_report_agent_v1" / "pricing.json")
    parser.add_argument("--mode", choices=("baseline", "shadow", "execute"), default="baseline")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--budget-cny", type=float, default=100)
    parser.add_argument("--budget-ledger", type=Path, required=True)
    parser.add_argument("--max-output", type=int, default=4096)
    parser.add_argument("--max-requests", type=int, default=30)
    parser.add_argument("--experiment-id", default="research-report-agent-v2-20261010")
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
    deliveries = []
    tool_failures = []
    for event in guard.events:
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            calls[data.get("callId")] = data.get("name")
        elif is_original_tool_result(event):
            call_id = data.get("message", {}).get("source", {}).get("callId")
            tool_name = calls.get(call_id)
            if tool_name:
                ok, _, output = _observation_digest(event, tool_name)
                if not ok or (output and any(output.get(key) is False for key in ("ok", "passed", "quality_passed"))):
                    tool_failures.append({"call_id": call_id, "tool": tool_name})
                if tool_name == "mcp__research_report__verify_report":
                    report_verifications.append(bool(ok and output and output.get("ok") is not False
                                                     and output.get("quality_passed") is True))
                if tool_name == "mcp__research_report__deliver_report":
                    deliveries.append(output if ok and output else {"ok": False})
    report_quality_passed = bool(report_verifications and report_verifications[-1])
    delivered = bool(deliveries and deliveries[-1].get("ok") is not False
                     and deliveries[-1].get("delivered") is True
                     and deliveries[-1].get("quality_passed") is True)
    if metrics["status"] == "done" and not (delivered and report_quality_passed):
        metrics["status"] = "incomplete"
        metrics["incomplete_reason"] = "deliver_report_business_acceptance_not_passed"
    metrics.update(elapsed_seconds=time.monotonic() - started, upstream_requests=gate.count,
                   report_quality_passed=report_quality_passed, delivered=delivered,
                   delivery=deliveries[-1] if deliveries else None,
                   delivery_attempts=len(deliveries), tool_failures=tool_failures,
                   tool_failure_count=len(tool_failures),
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
