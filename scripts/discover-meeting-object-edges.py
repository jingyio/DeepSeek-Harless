#!/usr/bin/env python3
"""Audit application-object parameter flow in independent meeting traces."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.task_identity import load_trace_identity, require_distinct_decisions  # noqa: E402
from src.motif_core.offline.object_reference_candidates import (  # noqa: E402
    repeated_object_edge_candidates,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    private_root = (ROOT / ".local").resolve()
    manifest_path, output = args.manifest.resolve(strict=True), args.output.resolve()
    if not manifest_path.is_relative_to(private_root) or not output.is_relative_to(private_root):
        parser.error("trace manifest and output must stay under .local")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest.get("train", [])) != 2 or len(manifest.get("heldout", [])) != 1:
        parser.error("two training and one validation trace are required")
    approved = {name for name, contract in manifest["contracts"].items()
                if contract.get("read_only") is True}
    traces, identities = [], []
    for row in [*manifest["train"], *manifest["heldout"]]:
        events_file = (manifest_path.parent / row["events"]).resolve(strict=True)
        identity_file = (manifest_path.parent / row["identity"]).resolve(strict=True)
        identity = load_trace_identity(identity_file, events_file, private_root)
        identities.append(identity)
        traces.append({"trace_id": row["trace_id"],
                       "decision_id": identity["research_decision_id"],
                       "events": [json.loads(line) for line in
                                  events_file.read_text(encoding="utf-8").splitlines()]})
    require_distinct_decisions(identities)
    candidates = repeated_object_edge_candidates(traces, approved)
    result = {"status": "candidate_only", "executable_motifs": 0,
              "trace_ids": [row["trace_id"] for row in traces],
              "candidates": candidates}
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"candidate_count": len(candidates),
                      "executable_motifs": 0, "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
