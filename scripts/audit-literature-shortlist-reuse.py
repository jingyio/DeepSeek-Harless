#!/usr/bin/env python3
"""Check a frozen Zotero read Motif against unseen natural shortlist traces.

Only source IDs, provenance, result metadata, and model-step boundaries are
checked. Raw source text and call arguments stay in ignored .local files.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / ".local").resolve()
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance  # noqa: E402
from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402
from src.motif_core.offline.edge_compiler import safe_edge_witnesses  # noqa: E402
from src.motif_core.offline.library_builder import validate_read_motif_library  # noqa: E402

PIN = "mcp__scoped_zotero_read__pin_scoped_zotero_source"
READ = "mcp__scoped_zotero_read__read_pinned_zotero_item"


def private_path(value: str, *, must_exist: bool = True) -> Path:
    path = (ROOT / value).resolve(strict=must_exist)
    if not path.is_relative_to(LOCAL):
        raise ValueError("library, traces, and report must stay under .local")
    return path


def events_at(path: Path) -> tuple[bytes, list[dict]]:
    raw = path.read_bytes()
    return raw, [json.loads(line) for line in raw.splitlines() if line.strip()]


def trace_for(events: list[dict], contracts: dict, trace_id: str):
    return extract_dsh_trace(
        events, contracts, trace_id=trace_id, task_fingerprint=trace_id,
        provenance_by_call_id=infer_dsh_provenance(events, contracts))


def candidate_for(artifact: dict) -> dict:
    binding = artifact["dependencies"]["operators"][READ]["bindings"][0]
    return {"status": "candidate_only", "from_tool": PIN,
            "from_field": binding["from_field"], "to_tool": READ,
            "to_param": binding["to_param"]}


def metadata_matches(source, target) -> bool:
    pin, read = source.observation, target.observation
    return (isinstance(pin, dict) and isinstance(read, dict)
            and pin.get("kind") == "item"
            and all(pin.get(key) == read.get(key) and pin.get(key) is not None
                    for key in ("source_id", "role", "key", "version", "data_sha256"))
            and target.arguments.get("source_id") == pin.get("source_id"))


def call_steps(events: list[dict]) -> dict[int, int]:
    return {event["seq"]: event["data"]["step"] for event in events
            if event.get("type") == "tool/call"
            and type(event.get("seq")) is int
            and type(event.get("data", {}).get("step")) is int}


def missing_id_probe(events: list[dict], contracts: dict, candidate: dict,
                     target_seq: int, original_count: int) -> int:
    altered = copy.deepcopy(events)
    for event in altered:
        data = event.get("data", {})
        if (event.get("type") == "tool/call" and data.get("name") == READ
                and event.get("seq") == target_seq):
            args = json.loads(data["arguments"])
            args["source_id"] = "source-" + "0" * 32
            data["arguments"] = json.dumps(args)
            break
    else:
        raise ValueError("read call missing from trace")
    count = len(safe_edge_witnesses(candidate,
                                    trace_for(altered, contracts, "negative-id"), contracts))
    if count >= original_count:
        raise ValueError("changed ID did not invalidate the witnessed edge")
    return count


def changed_version_probe(events: list[dict], contracts: dict, candidate: dict,
                          target_seq: int, original_count: int) -> int:
    altered = copy.deepcopy(events)
    call_id = next(event["data"]["callId"] for event in altered
                   if event.get("type") == "tool/call" and event.get("seq") == target_seq)
    for event in altered:
        if event.get("type") != "tool/result":
            continue
        message = event.get("data", {}).get("message", {})
        if message.get("source", {}).get("callId") != call_id:
            continue
        block = message["content"][0]["content"][0]
        payload = json.loads(block["text"])
        if type(payload.get("version")) is not int:
            raise ValueError("read result has no version")
        payload["version"] += 1
        block["text"] = json.dumps(payload, ensure_ascii=False)
        break
    else:
        raise ValueError("read result missing from trace")
    pairs = safe_edge_witnesses(candidate,
                                trace_for(altered, contracts, "negative-version"), contracts)
    count = sum(metadata_matches(source, target) for source, target in pairs)
    if count >= original_count:
        raise ValueError("changed result version passed metadata guard")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True)
    parser.add_argument("--training-event", action="append", default=[])
    parser.add_argument("--case", nargs=2, action="append", required=True,
                        metavar=("LABEL", "EVENTS_JSONL"))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    library_path = private_path(args.library)
    output_path = private_path(args.out, must_exist=False)
    library = json.loads(library_path.read_text(encoding="utf-8"))
    validate_read_motif_library(library)
    matches = [row for row in library["artifacts"] if row.get("tools") == [PIN, READ]]
    if len(matches) != 1:
        raise ValueError("expected exactly one certified Zotero item-read Motif")
    artifact = matches[0]
    contract_data = {}
    for filename in ("scoped-zotero-handle-contracts.json",
                     "scoped-research-handle-contracts.json"):
        incoming = json.loads((ROOT / "config" / filename).read_text(encoding="utf-8"))
        if contract_data.keys() & incoming.keys():
            raise ValueError("duplicate tool contract")
        contract_data.update(incoming)
    contracts = parse_tool_contracts(contract_data)
    candidate = candidate_for(artifact)

    training_ids = set()
    for filename in args.training_event:
        _raw, events = events_at(private_path(filename))
        training_ids.update(row.observation["source_id"]
                            for row in trace_for(events, contracts, filename).records
                            if row.name == PIN and row.eligible
                            and isinstance(row.observation, dict)
                            and isinstance(row.observation.get("source_id"), str))

    results = []
    labels = set()
    for label, filename in args.case:
        if label in labels:
            raise ValueError("duplicate case label")
        labels.add(label)
        raw, events = events_at(private_path(filename))
        trace = trace_for(events, contracts, label)
        pairs = safe_edge_witnesses(candidate, trace, contracts)
        steps = call_steps(events)
        source_steps = sorted({steps[source.event_seq] for source, _ in pairs})
        target_steps = sorted({steps[target.event_seq] for _, target in pairs})
        consistent = sum(metadata_matches(source, target) for source, target in pairs)
        handles = {source.observation["source_id"] for source, _ in pairs}
        negative_count = (missing_id_probe(events, contracts, candidate,
                                           pairs[0][1].event_seq, len(pairs))
                          if pairs else 0)
        stale_count = (changed_version_probe(events, contracts, candidate,
                                             pairs[0][1].event_seq, consistent)
                       if pairs else 0)
        results.append({
            "label": label, "events_sha256": hashlib.sha256(raw).hexdigest(),
            "safe_parameter_witnesses": len(pairs),
            "new_source_ids_vs_training": len(handles - training_ids)
            if args.training_event else None,
            "source_steps": source_steps, "target_steps": target_steps,
            "metadata_consistent_pairs": consistent,
            "changed_id_negative_witnesses": negative_count,
            "changed_version_metadata_consistent_pairs": stale_count,
            "structural_only": True,
        })
    report = {"status": "structural_reuse_only", "library_digest": library["library_digest"],
              "motif_id": artifact["motif_id"],
              "training_trace_ids": library["training_trace_ids"],
              "original_validation_trace_ids": library["heldout_trace_ids"],
              "cases": results,
              "limitations": "No model call or answer-quality and net-cost verdict."
              }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    output_path.chmod(0o600)
    print(json.dumps({"motif_id": artifact["motif_id"], "cases": [
        {"label": row["label"], "safe_witnesses": row["safe_parameter_witnesses"],
         "metadata_consistent": row["metadata_consistent_pairs"],
         "new_sources": row["new_source_ids_vs_training"],
         "source_steps": row["source_steps"], "target_steps": row["target_steps"]}
        for row in results]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
