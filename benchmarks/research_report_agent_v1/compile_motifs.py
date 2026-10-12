"""Learn narrow, witnessed receipt-transfer motifs from normal DSH trajectories.

This benchmark-local compiler extends the repository's read-only experiment to
workspace-confined idempotent artifacts. It does not claim that the existing
Motif core already supports writes. No workflow/edge list is hand-authored here.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_trajectory import _observation_digest
from src.adapters.dsh_event_projection import is_original_tool_result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def field(value, path):
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def paired_records(events):
    """Keep original event order; failed/unpaired actions are hard barriers."""
    records, calls = [], {}
    for seq, event in enumerate(events):
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            try:
                args = data.get("arguments")
                args = json.loads(args) if isinstance(args, str) else args
            except ValueError:
                args = None
            row = {"name": data.get("name"), "call_id": data.get("callId"),
                   "arguments": args, "seq": seq, "ok": False, "output": None}
            calls[data.get("callId")] = row
            records.append(row)
        elif is_original_tool_result(event):
            call_id = data.get("message", {}).get("source", {}).get("callId")
            row = calls.get(call_id)
            if row is not None:
                ok, _, output = _observation_digest(event, row["name"])
                successful = (ok and output is not None and output.get("ok") is not False
                              and output.get("passed") is not False and output.get("quality_passed") is not False)
                row.update(ok=successful, output=output,
                           result_seq=seq)
    return records


def witnessed_edges(records, contracts):
    """Mine adjacent successful calls; accept only unique exact opaque transfers."""
    edges = defaultdict(list)
    for before, after in zip(records, records[1:]):
        if not before["ok"] or not after["ok"]:
            continue
        if before.get("result_seq", 10**20) >= after["seq"]:
            continue  # Parallel calls do not establish an observed dependency.
        source = contracts.get(before["name"], {})
        target = contracts.get(after["name"], {})
        params = target.get("required_params", [])
        if (target.get("execution") != "workspace_idempotent" or len(params) != 1
                or set(after.get("arguments") or {}) != set(params)):
            continue
        provenance = before["output"].get("_provenance", {})
        authorized = {name if name.startswith("mcp__") else "mcp__research_report__" + name
                      for name in provenance.get("authorized_tools", [])}
        if after["name"] not in authorized:
            continue
        value = after["arguments"][params[0]]
        if not isinstance(value, str) or len(value) < 16:
            continue
        matches = [key for key in source.get("output_fields", [])
                   if field(before["output"], key) == value]
        if len(matches) != 1:
            continue
        key = (before["name"], matches[0], after["name"], params[0])
        edges[key].append({"from_call_id": before["call_id"],
                           "to_call_id": after["call_id"],
                           "from_output_sha256": digest(before["output"]),
                           "to_arguments_sha256": digest(after["arguments"])})
    return edges


def load_run(path, contracts):
    path = Path(path)
    manifest = read(path / "manifest.json")
    metrics = read(path / "metrics.json")
    if (manifest.get("mode") != "baseline" or manifest.get("model") != "deepseek-flash"
            or manifest.get("real_upstream") is not True):
        raise ValueError("Only ordinary real Flash baseline trajectories may train/certify")
    if (metrics.get("status") != "done" or metrics.get("upstream_requests", 0) < 1
            or metrics.get("report_quality_passed") is not True):
        raise ValueError("Training/certification must be a completed real model run")
    if manifest.get("contracts_digest") != digest(contracts):
        raise ValueError("Trace tool contracts differ from the compilation input")
    events_path = path / "agent-events.jsonl"
    events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    schemas = None
    for request_path in sorted((path / "model-requests").glob("*.request.json")):
        request = read(request_path)
        current = {row["function"]["name"]: row["function"]["parameters"] for row in request.get("tools", [])}
        if set(current) != set(contracts):
            raise ValueError("Actual model-facing tool surface differs from the approved contracts")
        if schemas is not None and digest(schemas) != digest(current):
            raise ValueError("Tool schema changed within a training/certification run")
        schemas = current
    if not schemas:
        raise ValueError("Missing actual model request schemas")
    case = manifest["case_id"]
    return {"case_id": case, "run_id": manifest["run_id"],
            "events_sha256": hashlib.sha256(events_path.read_bytes()).hexdigest(),
            "source_sha256": manifest.get("input_sha256"),
            "tool_schemas": schemas,
            "edges": witnessed_edges(paired_records(events), contracts)}


def compile_library(training, certification, contracts):
    """Independently certify only edges witnessed in >=2 independent tasks."""
    case_ids = [run["case_id"] for run in training] + [certification["case_id"]]
    if len(training) < 2 or len(case_ids) != len(set(case_ids)):
        raise ValueError("Need >=2 distinct training tasks and one different certification task")
    schemas = training[0]["tool_schemas"]
    if any(digest(run["tool_schemas"]) != digest(schemas) for run in [*training, certification]):
        raise ValueError("Tool schema differs across training/certification runs")
    artifacts = []
    all_edges = set().union(*(set(run["edges"]) for run in training))
    for edge in sorted(all_edges):
        witnesses = [run for run in training if edge in run["edges"]]
        if len(witnesses) < 2 or edge not in certification["edges"]:
            continue
        artifact = dict(zip(("from_tool", "from_field", "to_tool", "to_param"), edge))
        artifact.update(
            policy="closed_receipt_transfer_after_explicit_llm_authorization",
            training_evidence=[{"case_id": run["case_id"], "run_id": run["run_id"],
                                "events_sha256": run["events_sha256"],
                                "witnesses": run["edges"][edge]} for run in witnesses],
            certification_evidence={"case_id": certification["case_id"],
                                    "run_id": certification["run_id"],
                                    "events_sha256": certification["events_sha256"],
                                    "witnesses": certification["edges"][edge]})
        artifact["certified_digest"] = digest(artifact)
        artifact["motif_id"] = "receipt-" + artifact["certified_digest"][:16]
        artifacts.append(artifact)
    if not artifacts:
        raise ValueError("No independently certified repeated receipt transfers found")
    library = {"schema_version": 1, "kind": "benchmark_workspace_receipt_motifs",
               "scope": "benchmark-local extension; not arbitrary workflow recognition",
               "selection": "exact binding + explicit plan permission; no semantic embedding",
               "contracts": contracts, "contracts_digest": digest(contracts),
               "tool_schemas": schemas, "tool_schemas_digest": digest(schemas),
               "training_cases": case_ids[:-1], "certification_case": case_ids[-1],
               "artifacts": artifacts}
    library["library_digest"] = digest(library)
    return library


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", nargs="+", required=True, type=Path)
    parser.add_argument("--certify", required=True, type=Path)
    parser.add_argument("--contracts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contracts = read(args.contracts)
    result = compile_library([load_run(path, contracts) for path in args.train],
                             load_run(args.certify, contracts), contracts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"motifs": len(result["artifacts"]), "library_digest": result["library_digest"],
                      "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
