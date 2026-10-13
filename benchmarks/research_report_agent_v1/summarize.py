"""Summarize observed runs only; retain failures, unknown costs and comparability checks.

This is an offline report generator. It never calls an LLM, updates an experiment,
selects the best successful repeat, or treats provider estimates as invoices.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


TOKENS = ("prompt_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
          "completion_tokens", "total_tokens")
CRITICAL_CODE = ("common.py", "data_tools.py", "report_ops.py", "server.py", "runner.py", "tool_contracts.json")


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def lines(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    result = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL in {path.name}, line {index}") from error
    return result


def source_signature(manifest: dict) -> dict:
    return {row["path"].replace("\\", "/").rsplit("/", 1)[-1]: row["sha256"]
            for row in manifest.get("source_files", [])}


def selected_evidence_runs(library: dict) -> tuple[set[str], set[str]]:
    training, certification = set(), set()
    for motif in library.get("artifacts", []):
        training.update(item["run_id"] for item in motif.get("training_evidence", []) if item.get("run_id"))
        if motif.get("certification_evidence", {}).get("run_id"):
            certification.add(motif["certification_evidence"]["run_id"])
    return training, certification


def complete_usage(row: dict) -> bool:
    usage = row.get("usage", {})
    return (row.get("status") == 200 and row.get("peak_estimate_cny") is not None
            and all(type(usage.get(key)) is int and usage[key] >= 0 for key in TOKENS)
            and usage["prompt_tokens"] == usage["prompt_cache_hit_tokens"] + usage["prompt_cache_miss_tokens"]
            and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"])


def schema_snapshot(run: Path) -> dict:
    signatures, count, first = set(), 0, None
    for path in sorted((run / "model-requests").glob("*.request.json")):
        request = read(path)
        tools = request.get("tools", [])
        schema = {item["function"]["name"]: item["function"]["parameters"] for item in tools}
        signatures.add(digest(schema)); count += 1
        if first is None:
            first = schema
    return {"request_files": count, "stable": len(signatures) == 1,
            "schema_digests": sorted(signatures), "schema": first}


def tool_outputs(events: list[dict]) -> list[dict]:
    names, result = {}, []
    for event in events:
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            names[data.get("callId")] = data.get("name")
        elif event.get("type") == "tool/result":
            message = data.get("message", {})
            call_id = message.get("source", {}).get("callId")
            name = names.get(call_id)
            if not name:
                continue
            blocks = message.get("content", [])
            output = None
            for block in blocks:
                for item in block.get("content", []) if isinstance(block, dict) else []:
                    if isinstance(item, dict) and item.get("type") == "text":
                        try:
                            parsed = json.loads(item.get("text", ""))
                            if isinstance(parsed, dict):
                                output = parsed
                        except ValueError:
                            pass
            result.append({"tool": name, "call_id": call_id,
                           "error": bool(data.get("error") or any(block.get("isError") for block in blocks)),
                           "output": output})
    return result


def record_inventory(run: Path) -> tuple[dict, list[str]]:
    records, invalid = {}, []
    for path in sorted((run / "workspace" / "records").glob("*.json")):
        record = read(path)
        identifier, kind = record.get("id"), record.get("kind")
        body = {key: value for key, value in record.items() if key != "id"}
        expected = f"rra-{kind}-{digest(body)[:32]}"
        if identifier != expected or path.stem != identifier:
            invalid.append(path.name)
        records[identifier] = record
    return records, invalid


def artifact_check(run: Path, report: dict | None) -> dict:
    if report is None:
        return {"available": False, "reason": "final_report_record_missing"}
    payload = report["payload"]
    raw = payload.get("path", "").replace("\\", "/")
    # A copied run may preserve old absolute paths. Rebase only the known
    # workspace/artifacts subtree; never follow arbitrary paths from records.
    marker = "/artifacts/"
    if marker not in raw:
        return {"available": False, "reason": "report_path_not_in_artifacts"}
    path = (run / "workspace" / "artifacts" / raw.split(marker, 1)[1]).resolve()
    workspace = (run / "workspace").resolve()
    if not path.is_relative_to(workspace) or not path.is_file():
        return {"available": False, "reason": "report_file_missing"}
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"available": True, "path": str(path), "sha256": actual,
            "hash_matches": actual == payload.get("sha256"),
            "target_pages": payload.get("target_pages"), "metadata": payload.get("metadata", {})}


def run_summary(path: Path, library: dict) -> dict:
    manifest, metrics = read(path / "manifest.json"), read(path / "metrics.json", {})
    case, mode = manifest["case_id"], manifest["mode"]
    training_ids, certification_ids = selected_evidence_runs(library)
    if manifest["run_id"] in training_ids:
        phase = "training"
    elif manifest["run_id"] in certification_ids:
        phase = "certification"
    elif case in library.get("training_cases", []) or case == library.get("certification_case"):
        phase = "development_pilot"
    else:
        phase = "heldout"
    events, audits, costs = (lines(path / name) for name in
                            ("agent-events.jsonl", "motif-audit.jsonl", "cost-ledger.jsonl"))
    outputs = tool_outputs(events)
    verified_reports = [row for row in outputs if row["tool"] == "mcp__research_report__verify_report"]
    final_check = verified_reports[-1] if verified_reports else None
    final_output = (final_check or {}).get("output") or {}
    records, invalid_records = record_inventory(path)
    report_record = records.get(final_output.get("report_id"))
    artifact = artifact_check(path, report_record)
    observed_quality = bool(final_check and not final_check["error"] and final_output.get("quality_passed") is True)
    passed = bool(manifest.get("real_upstream") is True and metrics.get("status") == "done"
                  and metrics.get("report_quality_passed") is True and observed_quality
                  and not invalid_records and artifact.get("hash_matches") is True)
    schema = schema_snapshot(path)
    audit_counts = dict(Counter(row.get("kind", "unknown") for row in audits))
    known = [row for row in costs if complete_usage(row)]
    unknown = [row for row in costs if not complete_usage(row)]
    final_ids = {row.get("request_id") for row in costs}
    return {
        "run_id": manifest["run_id"], "directory": str(path), "case_id": case,
        "phase": phase, "mode": mode, "status": metrics.get("status", "metrics_missing"),
        "finish_reason": metrics.get("finish_reason"), "error_type": metrics.get("error_type"),
        "has_metrics": bool(metrics), "real_upstream_declared": manifest.get("real_upstream") is True,
        "automated_quality_eligible": passed, "human_scientific_review": "not assessed by this script",
        "report_quality_from_metrics": metrics.get("report_quality_passed"),
        "report_quality_from_final_tool_event": observed_quality,
        "report_verification_attempts": len(verified_reports), "report_artifact": artifact,
        "final_report_checks": final_output.get("checks", {}),
        "final_report_pages": final_output.get("pages", []), "invalid_record_files": invalid_records,
        "record_counts": dict(Counter(record.get("kind") for record in records.values())),
        "requests": metrics.get("upstream_requests"), "successful_requests": sum(row.get("status") == 200 for row in costs),
        "cost_rows": len(costs), "unique_cost_request_ids": len(final_ids),
        "tool_calls": metrics.get("tool_calls"),
        "observed_tool_calls": sum(row.get("type") == "tool/call" for row in events),
        "tool_error_results": sum(row["error"] for row in outputs),
        "logical_failed_results": sum((row["output"] or {}).get("passed") is False or
                                      (row["output"] or {}).get("quality_passed") is False or
                                      (row["output"] or {}).get("ok") is False for row in outputs),
        "elapsed_seconds": metrics.get("elapsed_seconds"),
        "known_usage": {name: sum(row.get("usage", {}).get(name, 0) for row in known) for name in TOKENS},
        "complete_usage_requests": len(known), "unknown_cost_requests": len(unknown),
        "confirmed_peak_estimate_cny": sum(row["peak_estimate_cny"] for row in known),
        "confirmed_offpeak_estimate_cny": sum(row.get("offpeak_estimate_cny", 0) or 0 for row in known),
        "unknown_reserved_upper_cny": sum(row.get("reserved_upper_cny", 0) for row in unknown),
        "runner_conservative_peak_cny": metrics.get("peak_estimate_cny"),
        "usage_complete_for_all_attempts": bool(costs) and not unknown and len(costs) == metrics.get("upstream_requests")
                                           and len(final_ids) == len(costs),
        "audit_counts": audit_counts,
        "verified_motif_bypasses": audit_counts.get("model_request_skipped_verified", 0),
        "consistency_checks": {
            "request_count_matches_cost_rows": metrics.get("upstream_requests") == len(costs),
            "tool_count_matches_events": metrics.get("tool_calls") == sum(row.get("type") == "tool/call" for row in events),
            "bypass_count_matches_audit": metrics.get("verified_motif_bypasses") == audit_counts.get("model_request_skipped_verified", 0),
            "quality_metric_matches_final_event": metrics.get("report_quality_passed") == observed_quality,
            "settled_usage_is_consistent": all(complete_usage(row) for row in costs if row.get("peak_estimate_cny") is not None),
        },
        "schema_snapshot": {key: value for key, value in schema.items() if key != "schema"},
        "_schemas": schema["schema"], "_manifest": manifest,
    }


def differences(before: dict, after: dict) -> dict:
    return {key: {"baseline": before.get(key), "execute": after.get(key)}
            for key in sorted(before.keys() | after.keys()) if before.get(key) != after.get(key)}


def compare(before: dict, after: dict, library: dict) -> dict:
    a, b = before["_manifest"], after["_manifest"]
    code_a, code_b = a.get("benchmark_code_sha256", {}), b.get("benchmark_code_sha256", {})
    critical_diffs = differences({key: code_a.get(key) for key in CRITICAL_CODE},
                                 {key: code_b.get(key) for key in CRITICAL_CODE})
    settings = ("model", "provider", "reasoning_effort", "thinking", "contracts_digest", "tool_order",
                "max_requests", "max_output", "compression", "automatic_retries", "python", "node", "dsh", "python_sdk")
    setting_diffs = differences({key: a.get(key) for key in settings}, {key: b.get(key) for key in settings})
    checks = {"same_prompt": a.get("prompt_sha256") is not None and a.get("prompt_sha256") == b.get("prompt_sha256"),
              "same_source_bytes": bool(source_signature(a)) and source_signature(a) == source_signature(b),
              "same_critical_execution_code": not critical_diffs and all(key in code_a and key in code_b for key in CRITICAL_CODE),
              "same_model_and_runtime_settings": not setting_diffs,
              "stable_matching_actual_tool_schemas": before["schema_snapshot"]["stable"] and after["schema_snapshot"]["stable"]
                  and before["_schemas"] == after["_schemas"],
              "schemas_match_certified_library": before["_schemas"] is not None and before["_schemas"] == library.get("tool_schemas"),
              "execute_uses_selected_library": b.get("library_digest") == library.get("library_digest"),
              "both_reports_automatically_qualified": before["automated_quality_eligible"] and after["automated_quality_eligible"],
              "both_logs_consistent": all(before["consistency_checks"].values()) and all(after["consistency_checks"].values()),
              "both_usage_complete": before["usage_complete_for_all_attempts"] and after["usage_complete_for_all_attempts"]}
    eligible = all(checks.values())
    result = {"case_id": before["case_id"], "baseline_run_id": before["run_id"], "execute_run_id": after["run_id"],
              "eligible_for_automatic_paired_comparison": eligible, "checks": checks,
              "critical_code_differences": critical_diffs, "all_code_differences": differences(code_a, code_b),
              "runtime_setting_differences": setting_diffs,
              "baseline_requests": before["requests"], "execute_requests": after["requests"],
              "baseline_confirmed_peak_cny": before["confirmed_peak_estimate_cny"],
              "execute_confirmed_peak_cny": after["confirmed_peak_estimate_cny"],
              "baseline_elapsed_seconds": before["elapsed_seconds"], "execute_elapsed_seconds": after["elapsed_seconds"],
              "human_review_required": True}
    if eligible:
        result["request_reduction"] = before["requests"] - after["requests"]
        result["request_reduction_fraction"] = result["request_reduction"] / before["requests"] if before["requests"] else None
        result["confirmed_peak_cost_difference_cny"] = before["confirmed_peak_estimate_cny"] - after["confirmed_peak_estimate_cny"]
        result["confirmed_peak_cost_reduction_fraction"] = (result["confirmed_peak_cost_difference_cny"] / before["confirmed_peak_estimate_cny"]
                                                           if before["confirmed_peak_estimate_cny"] else None)
    return result


def summarize(runs_root: Path, library: dict) -> dict:
    runs = []
    for path in sorted(runs_root.rglob("manifest.json")):
        manifest = read(path)
        if isinstance(manifest, dict) and {"run_id", "case_id", "mode"}.issubset(manifest):
            # Previews are not attempts. Crashed runs with evidence are retained.
            if any((path.parent / name).exists() for name in ("metrics.json", "agent-events.jsonl", "cost-ledger.jsonl", "error-diagnostics.json")):
                runs.append(run_summary(path.parent, library))
    seen = [run["run_id"] for run in runs]
    if len(seen) != len(set(seen)):
        raise ValueError("Duplicate run IDs discovered; do not aggregate copied runs twice")
    grouped = defaultdict(list)
    for run in runs:
        grouped[(run["phase"], run["mode"])].append(run)
    totals = []
    for (phase, mode), group in sorted(grouped.items()):
        totals.append({"phase": phase, "mode": mode, "attempts": len(group),
                       "automatically_qualified": sum(row["automated_quality_eligible"] for row in group),
                       "unsuccessful_or_unqualified": sum(not row["automated_quality_eligible"] for row in group),
                       "observed_requests": sum(row["requests"] or 0 for row in group),
                       "request_count_complete": all(row["requests"] is not None for row in group),
                       "confirmed_peak_estimate_cny": sum(row["confirmed_peak_estimate_cny"] for row in group),
                       "unknown_reserved_upper_cny": sum(row["unknown_reserved_upper_cny"] for row in group),
                       "unknown_cost_requests": sum(row["unknown_cost_requests"] for row in group),
                       "known_usage": {name: sum(row["known_usage"][name] for row in group) for name in TOKENS}})
    pairs, pending = [], []
    for case in sorted({row["case_id"] for row in runs if row["phase"] == "heldout"}):
        arms = {mode: [row for row in runs if row["case_id"] == case and row["mode"] == mode and row["automated_quality_eligible"]]
                for mode in ("baseline", "execute")}
        if all(len(arms[mode]) == 1 for mode in arms):
            pairs.append(compare(arms["baseline"][0], arms["execute"][0], library))
        else:
            pending.append({"case_id": case, "reason": "need exactly one qualified run per arm; no best-run selection",
                            "qualified_run_counts": {mode: len(rows) for mode, rows in arms.items()}})
    ledger_paths = sorted({row["_manifest"].get("budget_ledger") for row in runs if row["_manifest"].get("budget_ledger")})
    ledgers = []
    for raw in ledger_paths:
        path = Path(raw)
        # Avoid following arbitrary paths outside the selected experiment root.
        contained = path.resolve().is_relative_to(runs_root.resolve())
        if contained and path.is_file():
            rows = lines(path)
            reservations = {row["request_id"]: row for row in rows if row.get("kind") == "reserve"}
            settlements = {row["request_id"]: row for row in rows if row.get("kind") == "settle"}
            ledgers.append({"path": raw, "available": True, "budget_accounted_cny": sum(row.get("delta_cny", 0) for row in rows),
                            "reserved_requests": len(reservations), "settled_requests": len(settlements),
                            "unsettled_reservation_cny": sum(row["delta_cny"] for key, row in reservations.items() if key not in settlements),
                            "not_a_provider_invoice": True})
        else:
            ledgers.append({"path": raw, "available": False, "reason": "ledger not present inside selected runs root"})
    public_runs = [{key: value for key, value in run.items() if not key.startswith("_")} for run in runs]
    return {"schema_version": 1, "generated_utc": datetime.now(timezone.utc).isoformat(),
            "source": "observed run files; no model calls made by summarizer", "library_digest": library.get("library_digest"),
            "training_cases": library.get("training_cases", []), "certification_case": library.get("certification_case"),
            "selected_training_run_ids": sorted(selected_evidence_runs(library)[0]),
            "selected_certification_run_ids": sorted(selected_evidence_runs(library)[1]),
            "certified_motif_count": len(library.get("artifacts", [])), "runs": public_runs,
            "phase_totals_including_failed_attempts": totals, "paired_comparisons": pairs,
            "unpaired_or_ambiguous_cases": pending, "shared_budget_ledgers": ledgers,
            "limitations": ["Synthetic observations, real runtime/tools/cloud model.",
                "Automated qualification is not independent scientific/visual review.",
                "No uncertainty intervals for single-run runtime/cost comparisons; no repeat variance estimate.",
                "Cache hit/miss and run order can affect token costs.",
                "Training/certification/failures are reported separately, not free savings.",
                "No generic scripted-pipeline baseline has been compared.",
                "Cost values are tariff estimates or conservative reservations, not provider invoices."]}


def plot_results(summary: dict, directory: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10.5,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": "#17324d", "text.color": "#17324d", "pdf.fonttype": 42,
                         "savefig.facecolor": "white"})
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    pairs = [row for row in summary["paired_comparisons"] if row["eligible_for_automatic_paired_comparison"]]
    if pairs:
        fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.8), layout="constrained")
        x, width = np.arange(len(pairs)), 0.34
        for ax, key, ylabel, title in (
            (axes[0], "requests", "Actual cloud requests", "A  Model requests"),
            (axes[1], "confirmed_peak_cny", "Estimated CNY (peak tariff)", "B  Usage-based model cost")):
            for offset, arm, color, label in ((-width/2, "baseline", "#2377a4", "Ordinary DSH"),
                                              (width/2, "execute", "#d07835", "Certified motif")):
                values = [row[f"{arm}_{key}"] for row in pairs]
                bars = ax.bar(x + offset, values, width, label=label, color=color, alpha=0.93)
                ax.bar_label(bars, labels=[f"{value:g}" if key == "requests" else f"{value:.3f}" for value in values], padding=4, fontsize=9)
            ax.set_xticks(x, [row["case_id"].removeprefix("eval_").capitalize() for row in pairs])
            ax.set_ylabel(ylabel); ax.set_title(title, loc="left", fontweight="bold", pad=16)
            ax.set_ylim(0, ax.get_ylim()[1] * 1.15); ax.yaxis.grid(True, alpha=0.16); ax.set_axisbelow(True)
        axes[0].legend(frameon=False, loc="upper right")
        fig.suptitle("Held-out tasks with matched configuration and automated artifact checks", fontsize=13, fontweight="bold")
        fig.supxlabel("One observed run per arm / case; no replicate uncertainty. Cost is not a provider invoice.", fontsize=9)
        for extension in ("png", "pdf"):
            path = directory / f"heldout_comparison.{extension}"
            fig.savefig(path, dpi=300, metadata={"CreationDate": None, "ModDate": None} if extension == "pdf" else {})
            paths.append(str(path))
        plt.close(fig)
    totals = summary["phase_totals_including_failed_attempts"]
    if totals:
        fig, ax = plt.subplots(figsize=(9.2, 4.5), layout="constrained")
        x = np.arange(len(totals))
        known = [row["confirmed_peak_estimate_cny"] for row in totals]
        unknown = [row["unknown_reserved_upper_cny"] for row in totals]
        ax.bar(x, known, color="#2377a4", label="Complete usage: peak-tariff estimate")
        ax.bar(x, unknown, bottom=known, color="#d07835", hatch="///", label="Unknown usage: reserved upper bound")
        ax.set_xticks(x, [row["phase"].capitalize() + "\n" + row["mode"] for row in totals])
        ax.set_ylabel("CNY: estimate / conservative reservation")
        ax.set_title("All observed attempts, including training and failures", loc="left", fontweight="bold", pad=14)
        ax.yaxis.grid(True, alpha=0.16); ax.set_axisbelow(True); ax.legend(frameon=False, fontsize=9)
        ax.set_ylim(0, max(max([a + b for a, b in zip(known, unknown)], default=0) * 1.3, 0.01))
        fig.supxlabel("Reservations may exceed actual charges. Shared ledger separately retains crash-time unresolved reservations.", fontsize=8.7)
        for extension in ("png", "pdf"):
            path = directory / f"cost_by_phase.{extension}"
            fig.savefig(path, dpi=300, metadata={"CreationDate": None, "ModDate": None} if extension == "pdf" else {})
            paths.append(str(path))
        plt.close(fig)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="RESULTS.json path; plots are saved beside it")
    args = parser.parse_args()
    summary = summarize(args.runs_root.resolve(), read(args.library))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    summary["comparison_figures"] = plot_results(summary, args.output.parent / "comparison_figures")
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "observed_runs": len(summary["runs"]),
                      "eligible_pairs": sum(row["eligible_for_automatic_paired_comparison"] for row in summary["paired_comparisons"]),
                      "figures": summary["comparison_figures"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
