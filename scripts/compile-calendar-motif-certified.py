#!/usr/bin/env python3
"""Certify a two-output Calendar read Motif from B/C and independent D."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location(
    "calendar_candidate", ROOT / "scripts/compile-calendar-motif-candidate.py")
assert SPEC and SPEC.loader
CANDIDATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANDIDATE)

from src.motif_core.offline.edge_compiler import (  # noqa: E402
    certify_witnessed_edge_motif, compile_witnessed_edge_motif)
from src.motif_core.offline.local_programs import compile_local_programs  # noqa: E402
from src.motif_core.offline.trace_compiler import artifact_signature  # noqa: E402
from src.motif_core.read_executor import _validate_artifact  # noqa: E402

OUT = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/motif-continuation-v1"


def compile_certified() -> dict:
    training = [CANDIDATE.load_trace(case)[0] for case in "bc"]
    original_base = CANDIDATE.BASE
    try:
        CANDIDATE.BASE = OUT
        heldout, heldout_sha = CANDIDATE.load_trace("d")
    finally:
        CANDIDATE.BASE = original_base
    contracts = CANDIDATE.contracts()
    trained = CANDIDATE.compile_candidate()
    if trained["status"] != "candidate_only_requires_independent_heldout":
        raise ValueError("training candidate was not frozen")
    from importlib.util import spec_from_file_location, module_from_spec
    audit_spec = spec_from_file_location("calendar_audit", ROOT / "scripts/audit-calendar-motif-opportunities.py")
    assert audit_spec and audit_spec.loader
    audit = module_from_spec(audit_spec)
    audit_spec.loader.exec_module(audit)
    calls, results = audit.read_events(OUT / "agent-d/agent-events.jsonl")
    witness = audit.witnessed_continuation(calls, results)
    if not witness["witnessed"]:
        raise ValueError("independent D did not witness a safe continuation")

    certified_edges = []
    for source_field, target_param in CANDIDATE.EDGES:
        candidate = {"status": "candidate_only", "from_tool": CANDIDATE.FIND,
                     "from_field": source_field, "to_tool": CANDIDATE.VALIDATE,
                     "to_param": target_param,
                     "source_trace_ids": [row.trace_id for row in training]}
        compiled = compile_witnessed_edge_motif(candidate, training, contracts)
        certified_edges.append(certify_witnessed_edge_motif(compiled, heldout, contracts))
    first, second = certified_edges
    if any(first[key] != second[key] for key in (
            "tools", "source_trace_ids", "source_task_fingerprints",
            "validation_trace_id", "validation_task_fingerprint",
            "contract_signature")):
        raise ValueError("independently certified edges disagree")
    artifact = copy.deepcopy(first)
    artifact["motif_id"] = "calendar_pair_" + hashlib.sha256(
        (first["motif_id"] + second["motif_id"]).encode()).hexdigest()[:12]
    artifact["mining_basis"] = "two_witnessed_parameter_edges"
    artifact["dependencies"]["operators"][CANDIDATE.VALIDATE]["bindings"] = [
        row["dependencies"]["operators"][CANDIDATE.VALIDATE]["bindings"][0]
        for row in certified_edges]
    artifact["transfer_evidence"] = [row["transfer_evidence"][0]
                                     for row in certified_edges]
    artifact["argument_carryover"] = trained["argument_carryover"]
    for param in CANDIDATE.SHARED:
        if not all(next(row for row in trace.records if row.name == CANDIDATE.FIND)
                   .arguments[param] == next(row for row in trace.records
                   if row.name == CANDIDATE.VALIDATE).arguments[param]
                   for trace in (*training, heldout)):
            raise ValueError(f"{param} does not carry over in held-out D")
    artifact["source_trace_sha256"] = trained["source_trace_sha256"]
    artifact["heldout_trace_sha256"] = heldout_sha
    artifact["heldout_guard_checks"] = witness["checks"]
    artifact["source_guard"] = "sourceSha256_equal_after_live_validation"
    artifact["local_programs"] = compile_local_programs(artifact)
    tools = artifact["tools"]
    artifact["dag"] = {
        "nodes": tools, "order_edges": [[tools[0], tools[1]]],
        "parameter_edges": [[tools[0], tools[1]] for _ in artifact["transfer_evidence"]],
        "parallel_groups": [[name] for name in tools],
    }
    artifact["certified_digest"] = artifact_signature(artifact)
    _validate_artifact(artifact, contracts)
    return artifact


if __name__ == "__main__":
    artifact = compile_certified()
    target = OUT / "calendar-certified-motif.json"
    target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({"status": artifact["status"], "motif_id": artifact["motif_id"],
                      "certified_digest": artifact["certified_digest"],
                      "training": artifact["source_trace_ids"],
                      "heldout": artifact["validation_trace_id"]}))
