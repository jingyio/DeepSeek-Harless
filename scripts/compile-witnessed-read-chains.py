#!/usr/bin/env python3
"""Rebuild structural read edges and chains from independent DSH traces.

This does not apply the research-answer quality or cost gate and never installs
an artifact into the product Motif library.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import (  # noqa: E402
    ToolContract, extract_dsh_trace, infer_dsh_provenance,
    mine_witnessed_parameter_edges,
)
from src.adapters.task_identity import (  # noqa: E402
    load_trace_identity, require_distinct_decisions,
)
from src.motif_core.offline.chain_compiler import (  # noqa: E402
    certify_witnessed_chain_motif, compile_witnessed_chain_motif,
)
from src.motif_core.offline.edge_compiler import (  # noqa: E402
    certify_witnessed_edge_motif, compile_witnessed_edge_motif,
)


def _contracts(paths: list[Path]) -> dict[str, ToolContract]:
    specs = {}
    for path in paths:
        incoming = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
        if not isinstance(incoming, dict):
            raise ValueError("tool contracts must be a JSON object")
        if specs.keys() & incoming.keys():
            raise ValueError("tool contracts contain duplicate tool names")
        specs.update(incoming)
    # Use the same validated loader as the full library compiler so optional
    # page/line ranges and structured measure shapes are not silently lost.
    from src.adapters.tool_contract_loader import parse_tool_contracts
    return parse_tool_contracts(specs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", action="append", nargs=3, required=True,
                        metavar=("TRACE_ID", "IDENTITY_LOCK", "EVENTS_JSONL"))
    parser.add_argument("--heldout", nargs=3, required=True,
                        metavar=("TRACE_ID", "IDENTITY_LOCK", "EVENTS_JSONL"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, action="append", required=True,
                        help="approved tool contract JSON; repeat to combine connectors")
    args = parser.parse_args()
    if len(args.train) < 2:
        parser.error("at least two independent training traces are required")
    specs = [*args.train, args.heldout]
    if (len({row[0] for row in specs}) != len(specs)
            or any(not row[0].strip() for row in specs)):
        parser.error("trace IDs must be distinct and nonempty")
    contracts = _contracts(args.contracts)
    traces = []
    inputs = []
    identities = []
    local_root = (ROOT / ".local").resolve()
    for trace_id, identity_filename, filename in specs:
        path = Path(filename).resolve(strict=True)
        if not path.is_relative_to(local_root):
            parser.error("event traces must stay under .local")
        identity = load_trace_identity(Path(identity_filename), path, local_root)
        identities.append(identity)
        raw = path.read_bytes()
        events = [json.loads(line) for line in raw.decode("utf-8").splitlines()
                  if line.strip()]
        provenance = infer_dsh_provenance(events, contracts)
        traces.append(extract_dsh_trace(
            events, contracts, trace_id=trace_id,
            task_fingerprint=identity["research_decision_id"],
            provenance_by_call_id=provenance))
        inputs.append({"trace_id": trace_id,
                       "research_decision_id": identity["research_decision_id"],
                       "task_id": identity["task_id"],
                       "identity_sha256": identity["identity_sha256"],
                       "manifest_sha256": identity["manifest_sha256"],
                       "events_path": str(path.relative_to(ROOT)),
                       "events_sha256": hashlib.sha256(raw).hexdigest()})
    require_distinct_decisions(identities)
    training, heldout = traces[:-1], traces[-1]
    edges = mine_witnessed_parameter_edges(training, min_task_support=2)
    edge_artifacts = []
    chain_artifacts = []
    rejected = []
    for edge in edges:
        try:
            compiled = compile_witnessed_edge_motif(edge, training, contracts)
            edge_artifacts.append(certify_witnessed_edge_motif(
                compiled, heldout, contracts))
        except ValueError as exc:
            rejected.append({"tools": [edge["from_tool"], edge["to_tool"]],
                             "reason": str(exc)})
    for first in edges:
        for second in edges:
            if first["to_tool"] != second["from_tool"]:
                continue
            try:
                compiled = compile_witnessed_chain_motif(
                    first, second, training, contracts)
                artifact = certify_witnessed_chain_motif(
                    compiled, heldout, contracts)
                chain_artifacts.append(artifact)
            except ValueError as exc:
                rejected.append({"tools": [first["from_tool"], first["to_tool"],
                                           second["to_tool"]], "reason": str(exc)})
    artifacts = edge_artifacts + chain_artifacts
    if len({row["motif_id"] for row in artifacts}) != len(artifacts):
        raise ValueError("duplicate candidate identity from mined edges")
    output = args.out.resolve()
    if not output.is_relative_to(local_root):
        parser.error("output must stay under .local")
    report = {"status": "structural_only_not_product_registered",
              "inputs": inputs, "witnessed_edges": edges,
              "artifacts": artifacts, "edge_artifacts": edge_artifacts,
              "chain_artifacts": chain_artifacts, "rejected": rejected,
              "notice": "Held-out parameter flow is verified; answer quality and total-cost gates remain open."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"training_traces": len(training),
                      "heldout_trace": heldout.trace_id,
                      "witnessed_edges": len(edges),
                      "structural_edges": len(edge_artifacts),
                      "structural_chains": len(chain_artifacts),
                      "structural_artifacts": len(artifacts),
                      "rejected": len(rejected)}, ensure_ascii=False))
    return 0 if artifacts else 2


if __name__ == "__main__":
    raise SystemExit(main())
