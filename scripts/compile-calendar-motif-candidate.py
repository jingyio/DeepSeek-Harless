#!/usr/bin/env python3
"""Compile, but do not certify, witnessed Calendar find→validate edges."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import ToolContract, extract_dsh_trace  # noqa: E402
from src.motif_core.offline.edge_compiler import compile_witnessed_edge_motif  # noqa: E402

BASE = ROOT / ".local/benchmarks/mcp-app-internal-v2/calendar/availability-v1"
FIND = "mcp__calendar_fixture__find-available-slots"
VALIDATE = "mcp__calendar_fixture__validate-slot"
SHARED = ("calendarId", "timeZone", "timeWindows", "durationMinutes")
EDGES = (("earliest.start", "candidateStart"), ("earliest.end", "candidateEnd"))


def contracts() -> dict[str, ToolContract]:
    prefix = "mcp__calendar_fixture__"
    return {
        FIND: ToolContract(SHARED, True,
            ("earliest.start", "earliest.end", "sourceSha256"),
            description="Find the earliest free Calendar slot from live busy intervals",
            parameter_shapes=(("timeWindows", "time_window_list"),),
            default_params=(("maxCandidates", 5),)),
        VALIDATE: ToolContract((*SHARED, "candidateStart", "candidateEnd"), True,
            ("sourceSha256", "valid", "isEarliest"),
            description="Recheck one proposed Calendar slot against live busy intervals",
            provenance_params=("candidateStart", "candidateEnd"),
            parameter_shapes=(("timeWindows", "time_window_list"),)),
        prefix + "list-calendars": ToolContract((), True, ()),
        prefix + "list-events": ToolContract(
            ("calendarId", "timeMin", "timeMax", "timeZone"), True, ()),
    }


def load_trace(case: str):
    path = BASE / f"agent-{case}" / "agent-events.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    calls = [event["data"] for event in events if event.get("type") == "tool/call"]
    find = [row for row in calls if row["name"] == FIND]
    validate = [row for row in calls if row["name"] == VALIDATE]
    if (len(find) != 1 or len(validate) != 1 or
            find[0]["step"] >= validate[0]["step"]):
        raise ValueError(f"Case {case} lacks a natural later validation step")
    declared = {validate[0]["callId"]: {
        target: {"from_call_id": find[0]["callId"], "from_field": field}
        for field, target in EDGES}}
    trace = extract_dsh_trace(events, contracts(), trace_id=f"calendar-{case}",
                              task_fingerprint=f"calendar-independent-{case}",
                              provenance_by_call_id=declared)
    return trace, hashlib.sha256(path.read_bytes()).hexdigest()


def compile_candidate() -> dict:
    traces = [load_trace(case) for case in "bc"]
    extracted = [trace for trace, _ in traces]
    signatures = {f"calendar-{case}": digest for case, (_, digest) in zip("bc", traces)}
    edge_artifacts = []
    for field, param in EDGES:
        candidate = {"status": "candidate_only", "from_tool": FIND,
                     "from_field": field, "to_tool": VALIDATE, "to_param": param,
                     "source_trace_ids": [trace.trace_id for trace in extracted]}
        edge_artifacts.append(compile_witnessed_edge_motif(candidate, extracted, contracts()))
    carryover = []
    for param in SHARED:
        observed = []
        for trace in extracted:
            find = next(row for row in trace.records if row.name == FIND)
            validate = next(row for row in trace.records if row.name == VALIDATE)
            if (not find.eligible or not validate.eligible or
                    type(find.arguments[param]) is not type(validate.arguments[param]) or
                    find.arguments[param] != validate.arguments[param]):
                raise ValueError(f"Case {trace.trace_id} does not witness {param} carryover")
            observed.append(find.arguments[param])
        carryover.append({"from_param": param, "to_param": param,
                          "training_value_changes": len({json.dumps(value, sort_keys=True)
                                                           for value in observed}) > 1})
    return {"status": "candidate_only_requires_independent_heldout",
            "tools": [FIND, VALIDATE],
            "source_trace_sha256": signatures,
            "output_edges": [{"from_field": field, "to_param": param,
                              "witness_counts": artifact["witness_counts"]}
                             for (field, param), artifact in zip(EDGES, edge_artifacts)],
            "argument_carryover": carryover,
            "same_source_guard": "find.sourceSha256 == validate.sourceSha256",
            "heldout_passed": False,
            "online_execution_allowed": False}


def main() -> None:
    candidate = compile_candidate()
    target = BASE / "calendar-find-validate-candidate.json"
    target.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n")
    target.chmod(0o600)
    print(json.dumps({"status": candidate["status"],
                      "output_edges": len(candidate["output_edges"]),
                      "argument_carryover": len(candidate["argument_carryover"]),
                      "online_execution_allowed": False}))


if __name__ == "__main__":
    main()
