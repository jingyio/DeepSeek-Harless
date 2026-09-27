"""SSS-owned research reading exposed as bounded Harness tools.

Harness supplies the conversation and local semantic choices. The migrated
Motif controller owns source reads, parameter flow, evidence versions and
freshness checks. The source directory and certified artifact are fixed by
the host at process startup; model arguments cannot choose either path.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from src.motif_core.offline.trace_compiler import artifact_signature
from src.motif_core.offline.library_builder import library_from_certified
from src.motif_core.controller import MotifController
from src.motif_core.handoff import SemanticResolution
from src.mcp.structured_research_tools import HandleStore
from src.workflows.motif_research_sources import collect, verify_source_snapshot
from src.workflows.research_retrieval_tools import (
    RETRIEVAL_TOOL_CONTRACTS, ResearchRetrievalToolClient,
)


ROOT = Path(__file__).resolve().parents[2]
RUN_ID = re.compile(r"^[0-9a-f]{32}$")
server = MCPServer(
    "sss-runtime",
    instructions="Use collect_sources to obtain a versioned research source index. "
    "Use read_page with its run_id for bounded text. Source changes invalidate "
    "the index; collect again before making claims. Pass open_point's frontier_id "
    "unchanged to resolve_point. These tools never write "
    "to the source directory or call a model.",
)


def _record_digest(record: dict[str, Any]) -> str:
    body = {key: value for key, value in record.items() if key != "record_sha256"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResearchRuntime:
    def __init__(self, source_root: Path, artifact_path: Path,
                 run_root: Path, retrieval_artifact_path: Path | None = None) -> None:
        self.source_root = source_root.resolve(strict=True)
        self.artifact_path = artifact_path.resolve(strict=True)
        self.run_root = run_root.resolve()
        self._handles = HandleStore(self.run_root / "handles.sqlite3")
        self.retrieval_artifact_path = (retrieval_artifact_path or
                                        ROOT / ".local" / "motifs" /
                                        "research-retrieval.json")
        if not self.source_root.is_dir():
            raise ValueError("SSS source root must be an existing directory")
        if not self.run_root.is_relative_to((ROOT / ".local").resolve()):
            raise ValueError("SSS runtime state must stay under .local")

    def _artifact(self) -> dict[str, Any]:
        artifact = json.loads(self.artifact_path.read_text(encoding="utf-8"))
        if (artifact.get("status") != "trace_validated_read_only"
                or artifact.get("tools") != ["hash_source", "read_source"]
                or artifact.get("certified_digest") != artifact_signature(artifact)):
            raise ValueError("source Motif artifact is missing or no longer certified")
        return artifact

    def _retrieval_artifact(self) -> dict[str, Any]:
        artifact = json.loads(self.retrieval_artifact_path.read_text(encoding="utf-8"))
        if (artifact.get("status") != "trace_validated_read_only"
                or artifact.get("tools") != ["snapshot_sources", "retrieve_point"]
                or artifact.get("certified_digest") != artifact_signature(artifact)):
            raise ValueError("retrieval Motif artifact is missing or no longer certified")
        return artifact

    def _point_frontier(self, run_id: str, point_id: str, question: str,
                        source_allowlist: list[str], min_sources: int):
        if (not isinstance(point_id, str) or not 1 <= len(point_id) <= 100
                or not isinstance(question, str) or not 1 <= len(question) <= 1000
                or not isinstance(source_allowlist, list)
                or not 1 <= len(source_allowlist) <= 20
                or any(not isinstance(name, str) for name in source_allowlist)
                or len(set(source_allowlist)) != len(source_allowlist)
                or type(min_sources) is not int or not 1 <= min_sources <= 4):
            raise ValueError("invalid bounded research point")
        record = self._load_run(run_id)
        known = {row["source"] for row in record["pages"]}
        if not set(source_allowlist) <= known or min_sources > len(source_allowlist):
            raise ValueError("point source scope exceeds current evidence")
        client = ResearchRetrievalToolClient(
            self.source_root, record["pages"], record["source_state"])
        artifact = self._retrieval_artifact()
        controller = MotifController(
            library_from_certified([artifact]),
            contracts=RETRIEVAL_TOOL_CONTRACTS,
            execute_tool=client.execute, verify_current=client.verify_current,
            is_read_only=lambda tool: tool in RETRIEVAL_TOOL_CONTRACTS)
        decision = controller.execute_goal(
            required_output="retrieve_point",
            bindings={
                "snapshot_sources": {"source_dir": str(self.source_root),
                                     "input_version": client.snapshot_digest},
                "retrieve_point": {"source_dir": str(self.source_root),
                                   "point_id": point_id, "question": question,
                                   "source_allowlist": source_allowlist,
                                   "min_sources": min_sources}},
            input_version=client.snapshot_digest)
        if (decision.status != "needs_mediation" or decision.handoff is None
                or decision.handoff.missing_params != {"retrieve_point": ["terms"]}):
            raise ValueError(f"retrieval Motif did not reach a terms frontier: {decision.status}")
        return controller, decision, client

    def open_point(self, run_id: str, point_id: str, question: str,
                   source_allowlist: list[str], min_sources: int = 1) -> dict[str, Any]:
        """Execute certified structure until the precise semantic terms gap."""
        controller, decision, client = self._point_frontier(
            run_id, point_id, question, source_allowlist, min_sources)
        handoff = decision.handoff.to_dict()
        checkpoint = controller.export_replay_checkpoint()
        frontier_id = self._handles.put("frontier", {
            "run_id": run_id, "checkpoint_digest": checkpoint["checkpoint_digest"]
        }).split("-", 1)[1]
        frontier_dir = self.run_root / run_id / "frontiers"
        frontier_dir.mkdir(mode=0o700, exist_ok=True)
        if (frontier_dir.is_symlink()
                or not frontier_dir.resolve().is_relative_to(self.run_root.resolve())):
            raise ValueError("SSS frontier state escaped the private run directory")
        record = {"schema_version": 1, "run_id": run_id,
                  "checkpoint": checkpoint}
        record["record_sha256"] = _record_digest(record)
        path = frontier_dir / f"{frontier_id}.json"
        if path.is_symlink():
            raise ValueError("saved SSS frontier changed")
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if (existing.get("record_sha256") != record["record_sha256"]
                    or _record_digest(existing) != record["record_sha256"]):
                raise ValueError("saved SSS frontier changed")
        else:
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)
        return {"status": "needs_semantic_terms", "run_id": run_id,
                "frontier_id": frontier_id,
                "point_id": point_id, "question": question,
                "min_sources": min_sources,
                "snapshot_digest": client.snapshot_digest,
                "handoff": handoff, "handoff_signature": _record_digest(handoff),
                "allowed_sources": source_allowlist,
                "sss_model_requests": 0}

    def resolve_point(self, run_id: str, frontier_id: str, point_id: str, question: str,
                      source_allowlist: list[str], handoff_signature: str,
                      terms: list[str], min_sources: int = 1) -> dict[str, Any]:
        """Replay the saved frontier, verify its signature, then resume execution."""
        if (not isinstance(terms, list) or not 1 <= len(terms) <= 8
                or any(not isinstance(term, str) or not 1 <= len(term.strip()) <= 100
                       for term in terms)):
            raise ValueError("semantic terms exceed the bounded handoff")
        if not isinstance(frontier_id, str) or not RUN_ID.fullmatch(frontier_id):
            raise ValueError("invalid SSS frontier id")
        record = self._load_run(run_id)
        frontier_dir = self.run_root / run_id / "frontiers"
        if (frontier_dir.is_symlink()
                or not frontier_dir.resolve().is_relative_to(self.run_root.resolve())):
            raise ValueError("SSS frontier state escaped the private run directory")
        path = frontier_dir / f"{frontier_id}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("unknown SSS frontier")
        saved = json.loads(path.read_text(encoding="utf-8"))
        if (saved.get("schema_version") != 1 or saved.get("run_id") != run_id
                or saved.get("record_sha256") != _record_digest(saved)):
            raise ValueError("saved SSS frontier changed")
        checkpoint = saved.get("checkpoint")
        if not isinstance(checkpoint, dict):
            raise ValueError("saved SSS frontier is invalid")
        expected_binding = {"source_dir": str(self.source_root),
                            "point_id": point_id, "question": question,
                            "source_allowlist": source_allowlist,
                            "min_sources": min_sources}
        if checkpoint.get("bindings", {}).get("retrieve_point") != expected_binding:
            raise ValueError("semantic answer no longer matches the Motif frontier")
        client = ResearchRetrievalToolClient(
            self.source_root, record["pages"], record["source_state"])
        artifact = self._retrieval_artifact()
        controller = MotifController(
            library_from_certified([artifact]), contracts=RETRIEVAL_TOOL_CONTRACTS,
            execute_tool=client.execute, verify_current=client.verify_current,
            is_read_only=lambda tool: tool in RETRIEVAL_TOOL_CONTRACTS)
        decision = controller.replay_checkpoint(
            checkpoint, current_input_version=client.snapshot_digest,
            current_node_versions=None)
        expected = _record_digest(decision.handoff.to_dict())
        if not isinstance(handoff_signature, str) or handoff_signature != expected:
            raise ValueError("semantic answer no longer matches the Motif frontier")
        resolution = SemanticResolution(
            resolution_type="slot_fill",
            slot_values={"retrieve_point": {"terms": [term.strip() for term in terms]}},
            metadata={"handoff_signature": expected})
        resumed = controller.resume_slots(resolution)
        if resumed.status != "completed" or resumed.run is None:
            raise ValueError(f"retrieval Motif did not complete: {resumed.status}")
        result = resumed.run.outputs["retrieve_point"]
        client.verify_current()
        return {"status": "retrieved", "run_id": run_id, "frontier_id": frontier_id,
                "point_id": point_id,
                "snapshot_digest": client.snapshot_digest,
                "motif_id": resumed.motif_id,
                "artifact_digest": self._retrieval_artifact()["certified_digest"],
                "grounded_terms": result["grounded_terms"],
                "grounding_changes": result["grounding_changes"],
                "evidence": result["evidence"],
                "structural_events": list(resumed.events),
                "sss_model_requests": 0}

    def _load_run(self, run_id: str) -> dict[str, Any]:
        if not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id):
            raise ValueError("invalid SSS research run id")
        path = self.run_root / run_id / "evidence.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("unknown SSS research run")
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("schema_version") != 1
                or record.get("artifact_digest") != self._artifact()["certified_digest"]):
            raise ValueError("source Motif artifact changed after collection")
        if record.get("record_sha256") != _record_digest(record):
            raise ValueError("saved research evidence changed after collection")
        return record

    def _save_run(self, pages: list[dict[str, Any]], state: dict[str, Any],
                  events: list[dict[str, Any]], artifact: dict[str, Any],
                  *, previous_run_id: str | None = None) -> dict[str, Any]:
        counts = Counter(page["source"] for page in pages)
        self.run_root.mkdir(parents=True, exist_ok=True)
        record = {"schema_version": 1, "artifact_digest": artifact["certified_digest"],
                  "source_state": state, "pages": pages}
        record["record_sha256"] = _record_digest(record)
        run_id = self._handles.put("run", {
            "record_sha256": record["record_sha256"],
            "previous_run_id": previous_run_id,
        }).split("-", 1)[1]
        directory = self.run_root / run_id
        directory.mkdir(mode=0o700, exist_ok=True)
        if (directory.is_symlink()
                or not directory.resolve().is_relative_to(self.run_root.resolve())):
            raise ValueError("SSS run directory escaped the private state root")
        path = directory / "evidence.json"
        if path.is_symlink():
            raise ValueError("saved research evidence changed after collection")
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if (existing.get("record_sha256") != record["record_sha256"]
                    or _record_digest(existing) != record["record_sha256"]):
                raise ValueError("saved research evidence changed after collection")
        else:
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        path.chmod(0o600)
        event_counts = Counter(row.get("event") for row in events)
        return {"status": "collected", "run_id": run_id,
                "previous_run_id": previous_run_id,
                "source_count": len(counts), "page_count": len(pages),
                "sources": [{"name": name, "pages": count}
                            for name, count in sorted(counts.items())],
                "motif_id": artifact["motif_id"],
                "structural_events": event_counts["compiled_motif_execution"],
                "source_reads": event_counts["source_read"],
                "source_reuses": event_counts["source_reused"],
                "source_invalidations": event_counts["source_invalidated"],
                "model_requests": 0}

    def collect_sources(self) -> dict[str, Any]:
        paths = [path for path in self.source_root.iterdir()
                 if path.suffix.lower() in {".pdf", ".md", ".txt"}]
        if not 1 <= len(paths) <= 20:
            raise ValueError("SSS source root must contain 1–20 supported files")
        artifact = self._artifact()
        pages, state, events = collect(self.source_root,
                                       read_motif_artifact=artifact)
        return self._save_run(pages, state, events, artifact)

    def refresh_sources(self, run_id: str) -> dict[str, Any]:
        """Apply a changed source collection to a prior Motif frame."""
        previous = self._load_run(run_id)
        artifact = self._artifact()
        pages, state, events = collect(
            self.source_root, previous=previous["source_state"],
            read_motif_artifact=artifact)
        return self._save_run(pages, state, events, artifact,
                              previous_run_id=run_id)

    def read_page(self, run_id: str, source: str, page: int,
                  offset: int = 0, limit: int = 1800) -> dict[str, Any]:
        if (not isinstance(run_id, str) or not RUN_ID.fullmatch(run_id)
                or not isinstance(source, str) or Path(source).name != source
                or not isinstance(page, int) or page < 1
                or not isinstance(offset, int) or offset < 0
                or not isinstance(limit, int) or not 1 <= limit <= 2000):
            raise ValueError("invalid bounded page request")
        record = self._load_run(run_id)
        verify_source_snapshot(self.source_root, record["source_state"])
        matches = [row for row in record["pages"]
                   if row["source"] == source and row["page"] == page]
        if len(matches) != 1:
            raise ValueError("page is outside the current SSS source index")
        row = matches[0]
        body = row["text"]
        normalized = re.sub(r"\s+", " ", body).strip()
        if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != row["page_sha256"]:
            raise ValueError("saved page evidence changed after collection")
        if offset > len(body):
            raise ValueError("offset is beyond the source page")
        excerpt = body[offset:offset + limit]
        return {"run_id": run_id, "source": source, "page": page,
                "source_sha256": row["source_sha256"],
                "page_sha256": row["page_sha256"],
                "offset": offset, "total_characters": len(body),
                "next_offset": offset + len(excerpt) if offset + len(excerpt) < len(body) else None,
                "text": excerpt}


def _runtime() -> ResearchRuntime:
    source_root = Path(os.environ.get("SSS_SOURCE_ROOT", ROOT / "reference"))
    artifact = Path(os.environ.get(
        "SSS_SOURCE_MOTIF", ROOT / ".local" / "motifs" / "research-source-read.json"))
    retrieval_artifact = Path(os.environ.get(
        "SSS_RETRIEVAL_MOTIF", ROOT / ".local" / "motifs" / "research-retrieval.json"))
    return ResearchRuntime(source_root, artifact,
                           ROOT / ".local" / "sss-runtime", retrieval_artifact)


def collect_sources() -> dict[str, Any]:
    """Read the configured research collection through a certified Motif graph."""
    return _runtime().collect_sources()


def read_page(run_id: str, source: str, page: int,
              offset: int = 0, limit: int = 1800) -> dict[str, Any]:
    """Return a bounded excerpt from current, hash-verified Motif evidence."""
    return _runtime().read_page(run_id, source, page, offset, limit)


def refresh_sources(run_id: str) -> dict[str, Any]:
    """Resume a prior Motif collection after source additions, edits or removal."""
    return _runtime().refresh_sources(run_id)


def open_point(run_id: str, point_id: str, question: str,
               source_allowlist: list[str], min_sources: int = 1) -> dict[str, Any]:
    """Stop a certified retrieval Motif at its semantic terms frontier."""
    return _runtime().open_point(run_id, point_id, question, source_allowlist,
                                 min_sources)


def resolve_point(run_id: str, frontier_id: str, point_id: str, question: str,
                  source_allowlist: list[str], handoff_signature: str,
                  terms: list[str], min_sources: int = 1) -> dict[str, Any]:
    """Resume the exact retrieval frontier with bounded Harness-chosen terms."""
    return _runtime().resolve_point(run_id, frontier_id, point_id, question, source_allowlist,
                                    handoff_signature, terms, min_sources)


for function in (collect_sources, read_page, refresh_sources, open_point,
                 resolve_point):
    server.add_tool(function, name=function.__name__,
                    annotations=ToolAnnotations(readOnlyHint=True,
                                                destructiveHint=False,
                                                openWorldHint=False))


if __name__ == "__main__":
    server.run(transport="stdio")
