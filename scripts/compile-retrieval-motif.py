#!/usr/bin/env python3
"""Compile a cross-source read Motif from actual public retrieval tool calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import mine_dsh_traces  # noqa: E402
from src.motif_core.offline.trace_compiler import (  # noqa: E402
    certify_read_motif, compile_read_motif,
)
from src.workflows.motif_research_sources import collect  # noqa: E402
from src.workflows.research_retrieval_tools import (  # noqa: E402
    RETRIEVAL_TOOL_CONTRACTS, ResearchRetrievalToolClient,
    capture_retrieval_trace,
)


def _trace(case: dict):
    root = (ROOT / case["source_dir"]).resolve(strict=True)
    pages, state, _ = collect(root)
    client = ResearchRetrievalToolClient(root, pages, state)
    scope = sorted({page["source"] for page in pages})
    return capture_retrieval_trace(
        client, point_id=case["point_id"], question=case["question"],
        terms=case["terms"], source_allowlist=scope,
        min_sources=case.get("min_sources", 1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path,
                        default=ROOT / "benchmarks/retrieval_motif_cases.json")
    parser.add_argument("--out", type=Path,
                        default=ROOT / ".local/motifs/research-retrieval.json")
    args = parser.parse_args()
    cases = json.loads(args.cases.resolve(strict=True).read_text(encoding="utf-8"))
    if (not isinstance(cases, dict) or not isinstance(cases.get("train"), list)
            or len(cases["train"]) < 2 or not isinstance(cases.get("heldout"), dict)):
        raise ValueError("provide at least two training cases and one held-out case")
    traces = [_trace(case) for case in cases["train"]]
    heldout = _trace(cases["heldout"])
    candidates = mine_dsh_traces(traces)
    eligible = [row for row in candidates
                if row["tools"] == ["snapshot_sources", "retrieve_point"]]
    if len(eligible) != 1:
        raise ValueError("actual traces did not expose one safe retrieval motif")
    compiled = compile_read_motif(eligible[0], traces, RETRIEVAL_TOOL_CONTRACTS)
    artifact = certify_read_motif(compiled, heldout, RETRIEVAL_TOOL_CONTRACTS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps({"status": artifact["status"], "motif_id": artifact["motif_id"],
                      "train_tasks": len(traces), "heldout_task": heldout.trace_id,
                      "verified_transfers": len(artifact["transfer_evidence"]),
                      "artifact": str(args.out.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
