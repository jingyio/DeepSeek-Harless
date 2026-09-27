"""Versioned cross-source retrieval tools for a trace-compiled read Motif.

The existing retrieval algorithm remains a read-only tool implementation; the
Motif owns the source-snapshot dependency and decides when the tool may run.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from src.adapters.dsh_trajectory import DshTrace, ToolContract, ToolRecord
from src.graph.runtime import Evidence, execute
from src.motif_core.context_manager import MotifContextManager
from src.motif_core.offline.trace_compiler import artifact_signature
from src.workflows.motif_research_sources import verify_source_snapshot
from src.workflows.point_candidate_pool import candidate_pool
from src.workflows.research import RETRIEVE_MOTIF, ground_repair_terms


RETRIEVAL_TOOL_CONTRACTS = {
    "snapshot_sources": ToolContract(("source_dir", "input_version"), True, ("sha256",)),
    "retrieve_point": ToolContract(
        ("source_dir", "snapshot_sha256", "point_id", "question", "terms",
         "source_allowlist", "min_sources"), True,
        collection_params=("terms", "source_allowlist")),
}
RETRIEVAL_POLICY_VERSION = 1


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


class ResearchRetrievalToolClient:
    def __init__(self, root: Path, pages: list[dict[str, Any]],
                 source_state: dict[str, Any]):
        self.root = root.resolve(strict=True)
        self.pages = pages
        self.source_state = source_state
        rows = sorted((row["binding"]["source"], row["binding"]["sha256"])
                      for row in source_state["evidence"])
        if (not rows or len(rows) != len({name for name, _ in rows})
                or {page["source"] for page in pages} - {name for name, _ in rows}
                or any(page["source_sha256"] != dict(rows)[page["source"]]
                       for page in pages)):
            raise ValueError("retrieval pages do not match the bound source state")
        self.snapshot_digest = _digest({
            "sources": rows, "parser_version": source_state["parser_version"],
            "source_motif_digest": source_state.get("read_motif_digest"),
            "retrieval_policy_version": RETRIEVAL_POLICY_VERSION,
        })
        self.verify_current()

    def verify_current(self) -> None:
        verify_source_snapshot(self.root, self.source_state)

    def execute(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        self.verify_current()
        if params.get("source_dir") != str(self.root):
            raise ValueError("retrieval tool has a different source directory")
        if tool == "snapshot_sources":
            if (set(params) != {"source_dir", "input_version"}
                    or params["input_version"] != self.snapshot_digest):
                raise ValueError("snapshot tool parameter schema changed")
            return {"sha256": self.snapshot_digest}
        if tool != "retrieve_point" or set(params) != set(
            RETRIEVAL_TOOL_CONTRACTS["retrieve_point"].required_params
        ) or params["snapshot_sha256"] != self.snapshot_digest:
            raise ValueError("retrieval needs the current source snapshot")
        terms, scope = params["terms"], params["source_allowlist"]
        known = {page["source"] for page in self.pages}
        if (not isinstance(params["point_id"], str) or not params["point_id"]
                or not isinstance(params["question"], str) or not params["question"]
                or not isinstance(terms, list) or not terms
                or any(not isinstance(term, str) or not term.strip() for term in terms)
                or not isinstance(scope, list) or not scope
                or any(not isinstance(name, str) or name not in known for name in scope)
                or type(params["min_sources"]) is not int
                or not 1 <= params["min_sources"] <= 4):
            raise ValueError("retrieval parameter scope is invalid")
        grounded, changes = ground_repair_terms(terms, self.pages, scope)
        run = execute(RETRIEVE_MOTIF, {
            "unique_pages": Evidence(self.pages, "motif_hash_bound_source_snapshot"),
            "source_dir": Evidence(str(self.root), "bound_source_dir"),
            "question": Evidence(params["question"], "preflighted_answer_point"),
            "terms": Evidence(grounded, "source_grounded_point_terms"),
            "source_allowlist": Evidence(scope, "named_source_scope"),
            "per_source_limit": Evidence(12, "candidate_pool"),
        })
        if run.gap is None or run.gap.kind not in {
            "semantic_synthesis", "no_matching_evidence"
        }:
            raise ValueError(f"retrieval stopped at {run.gap.kind if run.gap else run.status}")
        evidence = (run.state["verified_evidence"].value
                    if run.gap.kind == "semantic_synthesis" else [])
        selected = candidate_pool(evidence, min_sources=params["min_sources"])
        self.verify_current()
        return {"point_id": params["point_id"], "grounded_terms": grounded,
                "grounding_changes": changes, "evidence": selected,
                "trace": run.report()}


def capture_retrieval_trace(
    client: ResearchRetrievalToolClient, *, point_id: str, question: str,
    terms: list[str], source_allowlist: list[str], min_sources: int = 1,
) -> DshTrace:
    """Record actual calls and the explicit snapshot-to-retrieval parameter edge."""
    first_params = {"source_dir": str(client.root),
                    "input_version": client.snapshot_digest}
    first = client.execute("snapshot_sources", first_params)
    second_params = {"source_dir": str(client.root),
                     "snapshot_sha256": first["sha256"], "point_id": point_id,
                     "question": question, "terms": terms,
                     "source_allowlist": source_allowlist,
                     "min_sources": min_sources}
    second = client.execute("retrieve_point", second_params)
    summary = {"point_id": point_id, "candidate_count": len(second["evidence"])}
    rows = (
        ToolRecord("snapshot_sources", first_params, _digest(first), True,
                   "eligible_read", 1, first),
        ToolRecord("retrieve_point", second_params, _digest(summary), True,
                   "eligible_read", 2, summary,
                   {"snapshot_sha256": {"from_tool": "snapshot_sources",
                                           "from_field": "sha256"}}),
    )
    task = _digest({"source_snapshot": client.snapshot_digest, "point_id": point_id,
                    "question": question, "terms": terms,
                    "source_allowlist": source_allowlist})
    return DshTrace(f"retrieval-{task[:16]}", rows,
                    (("snapshot_sources", "retrieve_point"),), task)


def _state_digest(state: dict[str, Any]) -> str:
    return _digest({key: value for key, value in state.items()
                    if key != "state_digest"})


def restore_retrieval_state(
    previous: dict[str, Any] | None, *, client: ResearchRetrievalToolClient,
    artifact: dict[str, Any],
) -> tuple[MotifContextManager, list[dict[str, Any]]]:
    """Restore only evidence bound to this exact source and tool version."""
    manager = MotifContextManager()
    if previous is None:
        return manager, []
    if (previous.get("schema_version") != 1
            or previous.get("artifact_digest") != artifact.get("certified_digest")
            or artifact.get("certified_digest") != artifact_signature(artifact)
            or previous.get("source_dir") != str(client.root)
            or previous.get("state_digest") != _state_digest(previous)):
        raise ValueError("previous retrieval state has a different or invalid contract")
    records = previous.get("evidence")
    if not isinstance(records, list):
        raise ValueError("previous retrieval evidence is invalid")
    if previous.get("snapshot_digest") != client.snapshot_digest:
        return manager, [{"event": "retrieval_snapshot_invalidated",
                          "prior_records": len(records)}]
    page_lookup = {(row["source"], row["page"]): row for row in client.pages}
    for record in records:
        if (not isinstance(record, dict)
                or set(record) not in ({"type", "binding", "value"},
                                       {"type", "binding", "value", "version"})
                or ("version" in record and record["version"] is not None
                    and not isinstance(record["version"], str))
                or record["type"] not in RETRIEVAL_TOOL_CONTRACTS
                or not isinstance(record["binding"], dict)
                or not isinstance(record["value"], dict)):
            raise ValueError("previous retrieval evidence has an unknown tool result")
        binding = record["binding"]
        if record["type"] == "snapshot_sources":
            if (binding != {"source_dir": str(client.root),
                            "input_version": client.snapshot_digest}
                    or record["value"] != {"sha256": client.snapshot_digest}):
                raise ValueError("previous snapshot evidence is inconsistent")
        else:
            value = record["value"]
            if (set(binding) != set(RETRIEVAL_TOOL_CONTRACTS["retrieve_point"].required_params)
                    or binding["source_dir"] != str(client.root)
                    or binding["snapshot_sha256"] != client.snapshot_digest
                    or value.get("point_id") != binding["point_id"]
                    or not isinstance(value.get("evidence"), list)):
                raise ValueError("previous retrieval result is inconsistent")
            for row in value["evidence"]:
                if not isinstance(row, dict):
                    raise ValueError("previous evidence row is invalid")
                page = page_lookup.get((row.get("source"), row.get("page")))
                if (page is None or row.get("source_sha256") != page["source_sha256"]
                        or row.get("page_sha256") != page["page_sha256"]
                        or not isinstance(row.get("snippet"), str)
                        or row["snippet"] not in re.sub(r"\s+", " ", page["text"])):
                    raise ValueError("previous evidence quote cannot be rechecked")
        if not manager.evidence.record(record["type"], binding, record["value"],
                                       version=record.get("version")):
            raise ValueError("previous retrieval contains a failed tool result")
    return manager, [{"event": "retrieval_state_restored", "records": len(records)}]


def export_retrieval_state(
    manager: MotifContextManager, *, client: ResearchRetrievalToolClient,
    artifact: dict[str, Any],
) -> dict[str, Any]:
    """Store bounded evidence for later exact-binding reuse in ignored .local/."""
    records = [record for record in manager.evidence.records.values()
               if record["type"] in RETRIEVAL_TOOL_CONTRACTS and
               record["binding"].get(
                   "input_version" if record["type"] == "snapshot_sources"
                   else "snapshot_sha256") == client.snapshot_digest]
    state = {"schema_version": 1, "artifact_digest": artifact["certified_digest"],
             "source_dir": str(client.root), "snapshot_digest": client.snapshot_digest,
             "evidence": records}
    state["state_digest"] = _state_digest(state)
    return state
