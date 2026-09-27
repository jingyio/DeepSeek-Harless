"""Build an executable read Motif library from independent tool traces.

The frozen MotifAgent pipeline mines sequences, adds sequential DAG edges and
records inter-motif connectors. This adaptation keeps those distinct from the
parameter-flow edges certified by ``trace_compiler``. A mined pattern is never
made executable merely because it is frequent.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping

from src.adapters.dsh_trajectory import DshTrace, mine_dsh_traces

from .motif_miner import normalize_repeated_tools
from .trace_compiler import certify_read_motif, compile_read_motif
from .repeat_compiler import certify_repeat_read_motif, compile_repeat_read_motif
from .link_compiler import compile_read_links
from .local_programs import compile_local_programs


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()).hexdigest()


def _eligible_sequences(traces: Iterable[DshTrace]) -> list[list[str]]:
    return [normalize_repeated_tools(list(segment))
            for trace in traces for segment in trace.segments
            if segment]


def _segment(sequence: list[str], motifs: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    """Longest-match segmentation from the frozen connector-table builder."""
    ordered = sorted(motifs, key=lambda row: (-len(row["tools"]), row["motif_id"]))
    result: list[tuple[str, Any]] = []
    index = 0
    while index < len(sequence):
        hit = next((row for row in ordered
                    if sequence[index:index + len(row["tools"])] == row["tools"]), None)
        if hit:
            result.append(("motif", hit["motif_id"]))
            index += len(hit["tools"])
        else:
            if result and result[-1][0] == "gap":
                result[-1][1].append(sequence[index])
            else:
                result.append(("gap", [sequence[index]]))
            index += 1
    return result


def _connectors(traces: list[DshTrace], motifs: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    for sequence in _eligible_sequences(traces):
        segments = _segment(sequence, motifs)
        for index, (kind, first) in enumerate(segments[:-1]):
            if kind != "motif":
                continue
            next_kind, second = segments[index + 1]
            if next_kind == "motif":
                counts[f"{first}|{second}"][()] += 1
            elif index + 2 < len(segments) and segments[index + 2][0] == "motif":
                counts[f"{first}|{segments[index + 2][1]}"][tuple(second)] += 1
    return {pair: {"total": sum(options.values()),
                   "options": [{"tools": list(gap), "count": count}
                               for gap, count in sorted(options.items(),
                                                        key=lambda row: (-row[1], row[0]))],
                   "deterministic": len(options) == 1}
            for pair, options in sorted(counts.items())}


def build_read_motif_library(
    training: list[DshTrace], heldout: list[DshTrace],
    contracts: Mapping[str, Any], *, min_trace_support: int = 2,
    task_identity_evidence: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Certify every eligible mined motif on an unseen task and record rejects.

    A candidate absent from heldout data remains a candidate, never an
    executable skill. Rejected traces contain identifiers and reasons only.
    """
    if (len(training) < 2 or not heldout
            or len({row.trace_id for row in training + heldout}) != len(training + heldout)
            or len({row.task_fingerprint for row in training + heldout})
            != len(training + heldout)
            or any(not row.task_fingerprint for row in training + heldout)):
        raise ValueError("independent identified training and held-out tasks are required")
    if task_identity_evidence is not None:
        rows = training + heldout
        if (set(task_identity_evidence) != {row.trace_id for row in rows}
                or any(task_identity_evidence[row.trace_id].get("research_decision_id")
                       != row.task_fingerprint for row in rows)
                or len({task_identity_evidence[row.trace_id].get("question_sha256")
                        for row in rows}) != len(rows)
                or any(not all(isinstance(task_identity_evidence[row.trace_id].get(key), str)
                                   and re.fullmatch(r"[0-9a-f]{64}",
                                                    task_identity_evidence[row.trace_id][key])
                                   for key in ("manifest_sha256", "events_sha256",
                                               "identity_sha256", "question_sha256"))
                       for row in rows)):
            raise ValueError("identity evidence must match every frozen trace")
    candidates = mine_dsh_traces(training, min_trace_support=min_trace_support)
    artifacts: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for candidate in candidates:
        try:
            repeated = any(name.endswith("+") for name in candidate["tools"])
            compiler = compile_repeat_read_motif if repeated else compile_read_motif
            certify = certify_repeat_read_motif if repeated else certify_read_motif
            compiled = compiler(candidate, training, contracts)
            validated = []
            for trace in heldout:
                try:
                    validated.append(certify(compiled, trace, contracts))
                except ValueError:
                    continue
            if not validated:
                raise ValueError("no independent held-out occurrence validates parameter flow")
            artifact = validated[0]
            tools = artifact["tools"]
            artifact["local_programs"] = compile_local_programs(artifact)
            artifact["dag"] = {
                "nodes": tools,
                "order_edges": [[tools[i], tools[i + 1]] for i in range(len(tools) - 1)],
                "parameter_edges": [[edge["from_tool"], edge["to_tool"]]
                                    for edge in (artifact["transfer_evidence"]
                                                 + artifact.get("selection_evidence", []))],
                "parallel_groups": [[name] for name in tools],
            }
            # DAG annotation is part of the immutable executable artifact.
            from .trace_compiler import artifact_signature
            artifact["certified_digest"] = artifact_signature(artifact)
            artifacts.append(artifact)
        except ValueError as exc:
            rejected.append({"motif_id": str(candidate["motif_id"]),
                             "reason": str(exc)})
    library = {"schema_version": 1, "status": "certified_read_library",
               "artifacts": artifacts, "connectors": _connectors(training, artifacts),
               "links": compile_read_links(training, heldout, artifacts, contracts),
               "rejected": rejected,
               "training_trace_ids": sorted(row.trace_id for row in training),
               "heldout_trace_ids": sorted(row.trace_id for row in heldout)}
    if task_identity_evidence is not None:
        library["task_identity_evidence"] = {
            trace_id: dict(task_identity_evidence[trace_id])
            for trace_id in sorted(task_identity_evidence)}
    library["library_digest"] = _digest(library)
    return library


def validate_read_motif_library(library: dict[str, Any]) -> None:
    if (library.get("schema_version") != 1
            or library.get("status") != "certified_read_library"
            or library.get("library_digest") != _digest({key: value for key, value in library.items()
                                                          if key != "library_digest"})
            or not isinstance(library.get("artifacts"), list)
            or len({row.get("motif_id") for row in library["artifacts"]})
            != len(library["artifacts"])):
        raise ValueError("Motif library is stale or invalid")


def library_from_certified(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    """Load already certified artifacts without silently promoting candidates."""
    from .trace_compiler import artifact_signature
    if (not artifacts or any(
        row.get("status") != "trace_validated_read_only"
        or row.get("certified_digest") != artifact_signature(row)
        for row in artifacts)):
        raise ValueError("library requires certified, unchanged artifacts")
    library = {"schema_version": 1, "status": "certified_read_library",
               "artifacts": list(artifacts), "connectors": {}, "links": [], "rejected": [],
               "training_trace_ids": sorted({trace_id for row in artifacts
                                             for trace_id in row["source_trace_ids"]}),
               "heldout_trace_ids": sorted({row["validation_trace_id"]
                                            for row in artifacts})}
    library["library_digest"] = _digest(library)
    validate_read_motif_library(library)
    return library
