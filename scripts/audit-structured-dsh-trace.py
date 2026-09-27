#!/usr/bin/env python3
"""Summarize real DSH tool provenance without copying research content."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import (  # noqa: E402
    extract_dsh_trace, infer_dsh_provenance,
)
from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402
from src.motif_core.offline.edge_compiler import count_safe_edge_witnesses  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--task-fingerprint", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--contracts", type=Path, action="append",
                        help="tool contract JSON; repeat to combine connector contracts")
    parser.add_argument("events", nargs="+", type=Path)
    args = parser.parse_args()
    events = []
    for path in args.events:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
    contract_paths = args.contracts or [
        ROOT / "config/structured-research-focused-contracts.json"]
    specs = {}
    for path in contract_paths:
        incoming = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
        duplicates = specs.keys() & incoming.keys()
        if duplicates:
            parser.error(f"duplicate tool contracts: {', '.join(sorted(duplicates))}")
        specs.update(incoming)
    contracts = parse_tool_contracts(specs)
    provenance = infer_dsh_provenance(events, contracts)
    trace = extract_dsh_trace(events, contracts, trace_id=args.trace_id,
                              task_fingerprint=args.task_fingerprint,
                              provenance_by_call_id=provenance)
    observed_edges = {
        (source["from_tool"], source["from_field"], record.name, param)
        for record in trace.records if record.eligible
        for param, source in (record.parameter_sources or {}).items()
    }
    safe_edges = []
    for source_tool, source_field, target_tool, target_param in sorted(observed_edges):
        candidate = {"status": "candidate_only", "from_tool": source_tool,
                     "from_field": source_field, "to_tool": target_tool,
                     "to_param": target_param}
        safe_edges.append({"from_tool": source_tool, "from_field": source_field,
                           "to_tool": target_tool, "to_param": target_param,
                           "safe_exact_argument_witnesses": count_safe_edge_witnesses(
                               candidate, trace, contracts)})
    summary = {
        "trace_id": args.trace_id,
        "task_fingerprint": args.task_fingerprint,
        "tool_calls": len(trace.records),
        "tool_names": dict(Counter(record.name for record in trace.records)),
        "eligibility": dict(Counter(record.reason for record in trace.records)),
        "eligible_segments": [list(segment) for segment in trace.segments],
        "longest_eligible_segment": max((len(segment) for segment in trace.segments), default=0),
        "witnessed_parameter_edges": [
            {"tool": record.name, "param": param,
             "from_tool": source["from_tool"], "from_field": source["from_field"]}
            for record in trace.records for param, source in (record.parameter_sources or {}).items()
        ],
        "safe_edge_opportunities": safe_edges,
        "note": "Safe witnesses are one-trace opportunities, not cross-task certified Motifs.",
    }
    output = args.out.resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        parser.error("summary must stay under .local")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({key: summary[key] for key in
                      ("trace_id", "tool_calls", "eligibility", "longest_eligible_segment")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
