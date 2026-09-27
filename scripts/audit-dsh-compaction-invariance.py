#!/usr/bin/env python3
"""Check that context-pruned DSH results cannot rewrite Motif trace evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_event_projection import is_original_tool_result  # noqa: E402
from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance  # noqa: E402
from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contracts", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("events", nargs="+", type=Path)
    args = parser.parse_args()
    local = (ROOT / ".local").resolve()
    events = []
    for path in args.events:
        source = path.resolve(strict=True)
        if not source.is_relative_to(local):
            parser.error("event logs must be under .local")
        events.extend(json.loads(line) for line in source.read_text(encoding="utf-8").splitlines()
                      if line.strip())

    specs = {}
    for path in args.contracts:
        incoming = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
        if specs.keys() & incoming.keys():
            parser.error("duplicate contract names")
        specs.update(incoming)
    contracts = parse_tool_contracts(specs)

    raw = [event for event in events
           if event.get("type") != "tool/result" or is_original_tool_result(event)]
    full_edges = infer_dsh_provenance(events, contracts)
    raw_edges = infer_dsh_provenance(raw, contracts)
    full = extract_dsh_trace(events, contracts, trace_id="with-compaction",
                             provenance_by_call_id=full_edges)
    original = extract_dsh_trace(raw, contracts, trace_id="original-results",
                                 provenance_by_call_id=raw_edges)
    def fingerprint(trace):
        return [(row.name, row.observation_sha256, row.eligible, row.reason,
                 row.event_seq, row.parameter_sources) for row in trace.records]
    records_equal = fingerprint(full) == fingerprint(original)
    equal = full_edges == raw_edges and records_equal
    result = {"status": "invariant" if equal else "mismatch",
              "tool_calls": len(full.records),
              "context_replacement_results": len(events) - len(raw),
              "eligible_witnessed_parameter_edges": sum(
                  len(row.parameter_sources or {}) for row in full.records),
              "observation_digests_equal": [row.observation_sha256 for row in full.records]
              == [row.observation_sha256 for row in original.records],
              "provenance_equal": full_edges == raw_edges,
              "trace_records_equal": records_equal,
              "eligibility_equal": full.segments == original.segments,
              "scope": "Context projection invariance only; not source freshness, scientific validity, or Motif reuse."}
    output = args.out.resolve()
    if not output.is_relative_to(local):
        parser.error("output must be under .local")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if equal else 2


if __name__ == "__main__":
    raise SystemExit(main())
