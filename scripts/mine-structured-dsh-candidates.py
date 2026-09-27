#!/usr/bin/env python3
"""Mine candidate-only read patterns from distinct real DSH task traces.

No pattern emitted here is authorized for replay. A separate trace compiler,
held-out check, and quality gate are required before runtime execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import (  # noqa: E402
    ToolContract, extract_dsh_trace, infer_dsh_provenance,
    mine_dsh_traces, mine_witnessed_parameter_edges,
)
from src.adapters.task_identity import (  # noqa: E402
    load_trace_identity, require_distinct_decisions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", action="append", nargs=3,
                        metavar=("TRACE_ID", "IDENTITY_LOCK", "EVENTS_JSONL"),
                        required=True)
    parser.add_argument("--min-task-support", type=int, default=2)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.min_task_support < 2:
        parser.error("min-task-support must be at least 2")
    specs = json.loads((ROOT / "config/structured-research-focused-contracts.json").read_text())
    contracts = {name: ToolContract(
        tuple(spec["required_params"]), spec["read_only"],
        tuple(spec.get("output_fields", [])), description=spec.get("description", ""),
        provenance_params=tuple(spec.get("provenance_params", [])),
        parameter_shapes=tuple(tuple(item) for item in spec.get("parameter_shapes", [])),
        default_params=tuple(tuple(item) for item in spec.get("default_params", [])))
        for name, spec in specs.items()}
    traces = []
    identities = []
    for trace_id, identity_filename, filename in args.trace:
        path = Path(filename).resolve(strict=True)
        if not path.is_relative_to((ROOT / ".local").resolve()):
            parser.error("event traces must be under .local")
        identity = load_trace_identity(Path(identity_filename), path, ROOT / ".local")
        identities.append(identity)
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                  if line.strip()]
        provenance = infer_dsh_provenance(events, contracts)
        traces.append(extract_dsh_trace(events, contracts, trace_id=trace_id,
                                        task_fingerprint=identity["research_decision_id"],
                                        provenance_by_call_id=provenance))
    require_distinct_decisions(identities)
    if len(traces) < args.min_task_support:
        parser.error("not enough task traces")
    output = args.out.resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        parser.error("result must stay under .local")
    result = {
        "status": "candidate_only",
        "trace_ids": [trace.trace_id for trace in traces],
        "task_fingerprints": [trace.task_fingerprint for trace in traces],
        "identity_sha256": [row["identity_sha256"] for row in identities],
        "min_task_support": args.min_task_support,
        "contiguous_candidates": mine_dsh_traces(
            traces, min_trace_support=args.min_task_support),
        "witnessed_parameter_edges": mine_witnessed_parameter_edges(
            traces, min_task_support=args.min_task_support),
        "notice": "Neither candidate type is an executable or quality-certified Motif.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"traces": len(traces),
                      "contiguous_candidates": len(result["contiguous_candidates"]),
                      "witnessed_parameter_edges": len(result["witnessed_parameter_edges"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
