"""Freeze a researcher-scoped Idea Delta trial without copying private content.

Only explicitly listed local snapshots are read. The manifest stores hashes and
source identities, not document text or future-event payloads. This is a task
boundary for fair baseline comparison, not a research-quality score.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


SOURCE_KINDS = {
    "idea_state", "idea_decision", "zotero_item", "zotero_annotation",
    "obsidian_note", "gmail_message", "local_data", "calendar_snapshot",
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _timestamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("source observation time is required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("source observation time must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("source observation time must include a timezone")
    return value


def _time_value(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _source(row: dict[str, Any], *, local_root: Path) -> dict[str, Any]:
    if (not isinstance(row, dict)
            or set(row) != {"kind", "source_id", "revision_id", "snapshot_file",
                            "observed_at", "external_model_excerpt_allowed"}
            or row.get("kind") not in SOURCE_KINDS
            or not isinstance(row.get("source_id"), str) or not row["source_id"].strip()
            or not isinstance(row.get("revision_id"), str) or not row["revision_id"].strip()
            or not isinstance(row.get("snapshot_file"), str)
            or not row["snapshot_file"].strip()
            or type(row.get("external_model_excerpt_allowed")) is not bool):
        raise ValueError("source needs a scoped identity, revision and model boundary")
    raw_path = Path(row["snapshot_file"])
    if not raw_path.is_absolute():
        raw_path = local_root / raw_path
    # Resolve the parent only, then reject the final component if it is a link.
    parent = raw_path.parent.resolve(strict=True)
    path = parent / raw_path.name
    if (not _inside(path, local_root) or path.is_symlink() or not path.is_file()
            or path.stat().st_size > 10_000_000):
        raise ValueError("source snapshot must be a bounded file under .local")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"kind": row["kind"], "source_id": row["source_id"],
            "revision_id": row["revision_id"], "snapshot_file": str(path),
            "observed_at": _timestamp(row["observed_at"]),
            "external_model_excerpt_allowed": row["external_model_excerpt_allowed"],
            "sha256": digest}


def freeze_initial_trial(intake: dict[str, Any], *, local_root: Path) -> dict[str, Any]:
    """Freeze only phase-A inputs; later events require a separate release."""
    local_root = local_root.resolve(strict=True)
    if (not isinstance(intake, dict)
            or set(intake) != {"schema_version", "task_id", "decision", "deadline", "as_of",
                               "reader", "idea_origin", "sources"}
            or intake["schema_version"] != 1
            or any(not isinstance(intake.get(key), str) or not intake[key].strip()
                   for key in ("task_id", "decision", "deadline", "as_of", "reader", "idea_origin"))
            or not isinstance(intake["sources"], list) or not intake["sources"]):
        raise ValueError("intake lacks a concrete research decision or scoped sources")
    _timestamp(intake["deadline"])
    _timestamp(intake["as_of"])
    sources = [_source(row, local_root=local_root) for row in intake["sources"]]
    if any(_time_value(row["observed_at"]) > _time_value(intake["as_of"])
           for row in sources):
        raise ValueError("phase-A source was observed after the snapshot cutoff")
    identities = [(row["kind"], row["source_id"]) for row in sources]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate source identity in one initial snapshot")
    if "idea_state" not in {row["kind"] for row in sources}:
        raise ValueError("an authoritative Idea State snapshot is required")
    frozen = {"schema_version": 1, "phase": "initial", "task_id": intake["task_id"],
              "decision": intake["decision"], "deadline": intake["deadline"],
              "as_of": intake["as_of"],
              "reader": intake["reader"], "idea_origin": intake["idea_origin"],
              "sources": sorted(sources, key=lambda row: (row["kind"], row["source_id"]))}
    frozen["task_digest"] = _digest(frozen)
    return frozen


def verify_frozen_trial(manifest: dict[str, Any], *, local_root: Path) -> None:
    """Reject a changed input before any baseline or SSS run consumes it."""
    local_root = local_root.resolve(strict=True)
    if (manifest.get("phase") != "initial"
            or manifest.get("task_digest") != _digest({
                key: value for key, value in manifest.items() if key != "task_digest"})):
        raise ValueError("trial manifest changed after freezing")
    for row in manifest["sources"]:
        path = Path(row["snapshot_file"])
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or not _inside(path.resolve(strict=True), local_root)
                or path.stat().st_size > 10_000_000
                or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]):
            raise ValueError("frozen research source changed")
