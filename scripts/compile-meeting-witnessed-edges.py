#!/usr/bin/env python3
"""Mine exact opaque-handle edges from two meeting traces; certify on a third."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import (  # noqa: E402
    extract_dsh_trace, infer_dsh_provenance,
)
from src.adapters.task_identity import (  # noqa: E402
    load_trace_identity, require_distinct_decisions,
)
from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402
from src.motif_core.offline.edge_compiler import (  # noqa: E402
    certify_witnessed_edge_motif, compile_witnessed_edge_motif,
    safe_edge_witnesses,
)
from src.motif_core.offline.library_builder import (  # noqa: E402
    _digest, library_from_certified,
)


def _load_trace(base: Path, row: dict, contracts: dict):
    events_file = (base / row["events"]).resolve(strict=True)
    identity_file = (base / row["identity"]).resolve(strict=True)
    identity = load_trace_identity(identity_file, events_file, ROOT / ".local")
    events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()
              if line.strip()]
    trace = extract_dsh_trace(
        events, contracts, trace_id=row["trace_id"],
        task_fingerprint=identity["research_decision_id"],
        provenance_by_call_id=infer_dsh_provenance(events, contracts))
    return trace, identity


def _witnessed_edges(trace) -> set[tuple[str, str, str, str]]:
    return {(source["from_tool"], source["from_field"], record.name, param)
            for record in trace.records if record.eligible
            for param, source in (record.parameter_sources or {}).items()}


def _field(value: dict, path: str):
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        elif isinstance(value, list) and part.isdecimal() and int(part) < len(value):
            value = value[int(part)]
        else:
            return None
    return value


def _witnessed_versions(artifact: dict, traces: list, contracts: dict,
                        source_field: str, target_field: str) -> bool:
    edge = artifact["transfer_evidence"][0]
    candidate = {"status": "candidate_only", "from_tool": edge["from_tool"],
                 "from_field": edge["from_field"], "to_tool": edge["to_tool"],
                 "to_param": edge["to_param"],
                 "version_relation": edge.get("version_relation", "same_source")}
    for trace in traces:
        pairs = safe_edge_witnesses(candidate, trace, contracts)
        if not pairs or not any(
            isinstance(_field(source.observation, source_field), str) and
            isinstance(_field(target.observation, target_field), str)
            for source, target in pairs
        ):
            return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--contracts", type=Path,
                        help="Explicit current read-only contract; omitted uses frozen manifest")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--online-out", type=Path,
                        help="Optional subset whose exact parameter edge can run online")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve(strict=True)
    output = args.out.resolve()
    private_root = (ROOT / ".local").resolve()
    online_output = args.online_out.resolve() if args.online_out else None
    if (not manifest_path.is_relative_to(private_root)
            or not output.is_relative_to(private_root)
            or (online_output and not online_output.is_relative_to(private_root))):
        parser.error("research traces and certified library must stay under .local")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest.get("train", [])) != 2 or len(manifest.get("heldout", [])) != 1:
        parser.error("exactly two training and one independent held-out trace are required")
    contract_rows = (json.loads(args.contracts.read_text(encoding="utf-8"))
                     if args.contracts else manifest["contracts"])
    contracts = parse_tool_contracts(contract_rows)
    loaded = [_load_trace(manifest_path.parent, row, contracts)
              for row in [*manifest["train"], *manifest["heldout"]]]
    traces = [pair[0] for pair in loaded]
    identities = [pair[1] for pair in loaded]
    require_distinct_decisions(identities)
    candidates = sorted(_witnessed_edges(traces[0]) & _witnessed_edges(traces[1]))
    certified = []
    rejected = []
    for source, field, target, param in candidates:
        candidate = {"status": "candidate_only", "from_tool": source,
                     "from_field": field, "to_tool": target, "to_param": param,
                     "source_trace_ids": [row.trace_id for row in traces[:2]]}
        if param == "object_id" and field.split(".")[-1].endswith("_id"):
            candidate["version_relation"] = (
                "lookup_index" if "index_version_sha256" in
                contracts[target].output_fields else "object_lookup")
        try:
            compiled = compile_witnessed_edge_motif(candidate, traces[:2], contracts)
            artifact = certify_witnessed_edge_motif(compiled, traces[2], contracts)
        except ValueError as exc:
            rejected.append({"edge": [source, field, target, param],
                             "reason": str(exc)})
            continue
        certified.append(artifact)
    if not certified:
        raise ValueError("no witnessed parameter edge passed held-out certification")
    library = library_from_certified(certified)
    library["task_identity_evidence"] = {
        trace.trace_id: identity for trace, identity in loaded}
    library["rejected"] = rejected
    library["library_digest"] = _digest({
        key: value for key, value in library.items() if key != "library_digest"})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    online_count = 0
    if online_output:
        eligible = []
        for artifact in certified:
            if len(artifact["tools"]) != 2:
                continue
            first, second = artifact["tools"]
            edge = artifact["transfer_evidence"]
            target_required = set(contracts[second].required_params)
            bound = {row["to_param"] for row in edge if row["to_tool"] == second}
            source_version_field = next((field for field in
                ("event_version", "index_version_sha256", "version_sha256")
                if field in contracts[first].output_fields), None)
            target_version_field = next((field for field in
                ("index_version_sha256", "version_sha256")
                if field in contracts[second].output_fields), None)
            if (target_required <= bound
                    and source_version_field and target_version_field and
                    _witnessed_versions(artifact, traces, contracts,
                                        source_version_field, target_version_field)):
                eligible.append(artifact)
        if not eligible:
            raise ValueError("no certified edge has complete parameter and version guards")
        online_count = len(eligible)
        online_output.parent.mkdir(parents=True, exist_ok=True)
        online_output.write_text(json.dumps(library_from_certified(eligible),
                                            ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        online_output.chmod(0o600)
    print(json.dumps({"library": str(output), "witnessed_candidate_edges": len(candidates),
                      "certified_parameter_edges": len(certified),
                      "online_eligible_edges": online_count,
                      "rejected": len(rejected),
                      "library_digest": library["library_digest"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
