#!/usr/bin/env python3
"""Compile a certified Motif library from local DeepSeek Harness event logs.

The manifest names approved read-only tool contracts, distinct training and
held-out event files, optional host-recorded call provenance sidecars, and an
optional tool_schema_file with the corresponding MCP tools list.
Optional code_candidate_files (or development-only inline code_candidates)
propose bounded local code nodes for gaps in otherwise certified Motifs.
All raw records stay local; only the compiled artifact is written under .local.
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
)
from src.adapters.tool_schema_contracts import bind_mcp_descriptions  # noqa: E402
from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402
from src.adapters.task_identity import (  # noqa: E402
    load_trace_identity, require_distinct_decisions,
)
from src.motif_core.offline.library_builder import (  # noqa: E402
    _digest as library_digest, build_read_motif_library,
)
from src.motif_core.offline.dynamic_code_nodes import (  # noqa: E402
    certify_dynamic_code_node,
)


def attach_code_candidates(library: dict, candidates: list[dict],
                           train: list, heldout: list,
                           contracts: dict[str, ToolContract]) -> dict:
    """Promote only code verified on this library's frozen independent tasks."""
    if not isinstance(candidates, list):
        raise ValueError("code_candidates must be a list")
    by_trace = {row.trace_id: row for row in train}
    heldout_by_id = {row.trace_id: row for row in heldout}
    by_motif = {row["motif_id"]: index
                for index, row in enumerate(library["artifacts"])}
    if len(by_motif) != len(library["artifacts"]):
        raise ValueError("library contains duplicate Motif IDs")
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("code candidate must be an object")
        motif_id = candidate.get("motif_id")
        if motif_id is None and isinstance(candidate.get("tools"), list):
            matches = [row["motif_id"] for row in library["artifacts"]
                       if row["tools"] == candidate["tools"]]
            motif_id = matches[0] if len(matches) == 1 else None
        if not isinstance(motif_id, str):
            raise ValueError("code candidate must identify one certified Motif")
        if motif_id not in by_motif:
            library["rejected"].append({"motif_id": motif_id,
                                        "reason": "code candidate has no certified Motif"})
            continue
        artifact = library["artifacts"][by_motif[motif_id]]
        try:
            if candidate.get("trace_id") not in artifact["source_trace_ids"]:
                raise ValueError("code proposal is not tied to a training trace")
            training = [by_trace[key] for key in artifact["source_trace_ids"]]
            validation = heldout_by_id[artifact["validation_trace_id"]]
            body = {key: value for key, value in candidate.items()
                    if key not in {"motif_id", "tools", "trace_id"}}
            upgraded = certify_dynamic_code_node(artifact, body, training,
                                                 validation, contracts)
        except (KeyError, TypeError, ValueError) as exc:
            library["rejected"].append({"motif_id": motif_id,
                                        "reason": "code candidate rejected: " + str(exc)})
            continue
        library["artifacts"][by_motif[motif_id]] = upgraded
    library["library_digest"] = library_digest({
        key: value for key, value in library.items() if key != "library_digest"})
    return library


def _load(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def _code_candidate_file(path: Path) -> dict:
    target = path.resolve(strict=True)
    if not target.is_relative_to((ROOT / ".local").resolve()):
        raise ValueError("code candidate must stay under SSS/.local")
    payload = _load(target)
    if not isinstance(payload, dict) or payload.get("status") != "candidate_only":
        raise ValueError("code proposal must remain a candidate")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    if hashlib.sha256(raw.encode("utf-8")).hexdigest() != target.stem:
        raise ValueError("code candidate file hash changed")
    return {key: value for key, value in payload.items() if key != "status"}


def _events(path: Path) -> list[dict]:
    target = path.resolve(strict=True)
    if not target.is_relative_to((ROOT / ".local").resolve()):
        raise ValueError("Harness event traces must stay under SSS/.local")
    raw = target.read_text(encoding="utf-8")
    if target.suffix == ".jsonl":
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    else:
        rows = json.loads(raw)
        if isinstance(rows, dict):
            rows = rows.get("events")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Harness event file must contain event objects")
    return rows


def _contracts(rows: dict) -> dict[str, ToolContract]:
    return parse_tool_contracts(rows)


def _trace(row: dict, base: Path, contracts: dict[str, ToolContract]):
    if (not isinstance(row, dict) or not row.get("trace_id")
            or not row.get("identity") or not row.get("events")):
        raise ValueError("trace requires ID, frozen identity and event file")
    events_path = base / row["events"]
    identity = load_trace_identity(base / row["identity"], events_path,
                                   ROOT / ".local")
    events = _events(events_path)
    provenance = (_load(base / row["provenance"]) if row.get("provenance")
                  else infer_dsh_provenance(events, contracts))
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError("call provenance sidecar must be a mapping")
    return extract_dsh_trace(
        events, contracts, trace_id=str(row["trace_id"]),
        task_fingerprint=identity["research_decision_id"],
        provenance_by_call_id=provenance)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=ROOT / ".local" / "motifs" / "dsh-library.json")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve(strict=True)
    manifest = _load(manifest_path)
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("train"), list)
            or not isinstance(manifest.get("heldout"), list)):
        raise ValueError("manifest requires train and heldout trace lists")
    output = args.out.resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        raise ValueError("compiled library must stay under SSS/.local")
    contracts = _contracts(manifest.get("contracts"))
    if manifest.get("tool_schema_file"):
        schemas = _load(manifest_path.parent / manifest["tool_schema_file"])
        contracts = bind_mcp_descriptions(contracts, schemas)
    train = [_trace(row, manifest_path.parent, contracts) for row in manifest["train"]]
    heldout = [_trace(row, manifest_path.parent, contracts) for row in manifest["heldout"]]
    # A repeated decision cannot be made independent by renaming its trace.
    all_rows = [*manifest["train"], *manifest["heldout"]]
    identities = [
        load_trace_identity(manifest_path.parent / row["identity"],
                            manifest_path.parent / row["events"], ROOT / ".local")
        for row in all_rows]
    require_distinct_decisions(identities)
    evidence = {str(row["trace_id"]): identity
                for row, identity in zip(all_rows, identities)}
    library = build_read_motif_library(
        train, heldout, contracts, task_identity_evidence=evidence)
    if not library["artifacts"]:
        raise ValueError("no candidate passed independent held-out certification")
    candidate_files = manifest.get("code_candidate_files", [])
    inline_candidates = manifest.get("code_candidates", [])
    if not isinstance(candidate_files, list) or not isinstance(inline_candidates, list):
        raise ValueError("code candidate entries must be lists")
    candidates = list(inline_candidates)
    candidates.extend(_code_candidate_file(manifest_path.parent / path)
                      for path in candidate_files)
    library = attach_code_candidates(library, candidates, train, heldout,
                                     contracts)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(library, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({"library": str(output),
                      "certified_motifs": len(library["artifacts"]),
                      "rejected_candidates": len(library["rejected"]),
                      "library_digest": library["library_digest"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
