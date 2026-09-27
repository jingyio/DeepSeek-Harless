"""Bind a DSH trace to a frozen research decision and exact event bytes."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


DECISION_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,99}$")


def load_trace_identity(identity_file: Path, events_file: Path,
                        local_root: Path) -> dict[str, str]:
    """Read an auditable identity lock; its decision ID is still human asserted."""
    identity_path = identity_file.resolve(strict=True)
    events_path = events_file.resolve(strict=True)
    local = local_root.resolve()
    if (not identity_path.is_relative_to(local)
            or not events_path.is_relative_to(local)
            or identity_path.parent != events_path.parent):
        raise ValueError("identity and events must share one task directory under .local")
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    if (not isinstance(identity, dict) or identity.get("schema_version") != 1
            or not isinstance(identity.get("research_decision_id"), str)
            or not DECISION_ID.fullmatch(identity["research_decision_id"])):
        raise ValueError("identity needs a stable research_decision_id")
    manifest_path = identity_path.parent / "manifest.json"
    if (manifest_path.is_symlink()
            or manifest_path.resolve(strict=True).parent != identity_path.parent):
        raise ValueError("task manifest must be a regular file in the task directory")
    manifest_raw = manifest_path.read_bytes()
    events_raw = events_path.read_bytes()
    if (identity.get("manifest_sha256") != hashlib.sha256(manifest_raw).hexdigest()
            or identity.get("events_sha256") != hashlib.sha256(events_raw).hexdigest()):
        raise ValueError("identity lock does not match frozen manifest and event bytes")
    manifest = json.loads(manifest_raw)
    if (not isinstance(manifest, dict)
            or not isinstance(manifest.get("task_id"), str) or not manifest["task_id"]
            or not isinstance(manifest.get("question"), str)
            or not manifest["question"].strip()):
        raise ValueError("task manifest needs a task_id and research question")
    question = " ".join(manifest["question"].split()).casefold()
    return {"research_decision_id": identity["research_decision_id"],
            "task_id": manifest["task_id"],
            "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
            "manifest_sha256": identity["manifest_sha256"],
            "events_sha256": identity["events_sha256"],
            "identity_sha256": hashlib.sha256(identity_path.read_bytes()).hexdigest()}


def require_distinct_decisions(identities: list[dict[str, str]]) -> None:
    decisions = [row["research_decision_id"] for row in identities]
    questions = [row["question_sha256"] for row in identities]
    if len(set(decisions)) != len(decisions):
        raise ValueError("training and held-out traces repeat one research decision")
    if len(set(questions)) != len(questions):
        raise ValueError("identical research questions cannot claim distinct decisions")
