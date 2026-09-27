#!/usr/bin/env python3
"""Compile a read-only source Motif from distinct observed document runs."""

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
from src.workflows.research_source_tools import (  # noqa: E402
    SOURCE_TOOL_CONTRACTS, capture_source_read_trace,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, action="append", required=True,
                        help="repeat for at least two different source documents")
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=ROOT / ".local" / "motifs" / "research-source-read.json")
    args = parser.parse_args()
    if len(args.train) < 2:
        parser.error("at least two training documents are required")
    traces = [capture_source_read_trace(path) for path in args.train]
    heldout = capture_source_read_trace(args.heldout)
    candidates = mine_dsh_traces(traces)
    selected = [row for row in candidates if row["tools"] == ["hash_source", "read_source"]]
    if len(selected) != 1:
        raise ValueError("source read Motif was not uniquely mined")
    compiled = compile_read_motif(selected[0], traces, SOURCE_TOOL_CONTRACTS)
    certified = certify_read_motif(compiled, heldout, SOURCE_TOOL_CONTRACTS)
    output = args.out.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(certified, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"status": certified["status"], "motif_id": certified["motif_id"],
                      "source_trace_count": len(traces),
                      "verified_transfers": len(certified["transfer_evidence"]),
                      "artifact": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
