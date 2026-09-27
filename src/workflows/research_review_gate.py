"""Bind a human review verdict to the exact research draft it assessed.

This is a local integrity gate, not authentication of the reviewer or a
substitute for checking whether cited passages entail the claims.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


REVIEWED_FILES = (
    "status.json", "question.txt", "answer-points.json", "answer.md",
    "claims.json", "selected-evidence.json", "question-coverage.json",
    "motif-source-state.json", "motif-selection-state.json",
)


def _hashes(run: Path) -> dict[str, str]:
    digests = {}
    for name in REVIEWED_FILES:
        path = run / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"reviewed run is missing a regular {name}")
        digests[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def build_review_record(run: Path, assessment: dict[str, Any]) -> dict[str, Any]:
    """Validate a filled human form and freeze the draft files it reviewed."""
    file_hashes = _hashes(run)
    if (not isinstance(assessment, dict)
            or set(assessment) != {"reviewer", "reviewed_at", "verdict",
                                    "point_scores", "serious_error",
                                    "review_minutes", "notes"}):
        raise ValueError("review form fields are incomplete")
    reviewer, timestamp, verdict = (assessment[key] for key in
                                    ("reviewer", "reviewed_at", "verdict"))
    if (not isinstance(reviewer, str) or not reviewer.strip()
            or not isinstance(timestamp, str) or not timestamp
            or verdict not in {"approved", "rejected"}
            or type(assessment["serious_error"]) is not bool
            or type(assessment["review_minutes"]) not in {int, float}
            or not math.isfinite(assessment["review_minutes"])
            or assessment["review_minutes"] < 0
            or not isinstance(assessment["notes"], str)):
        raise ValueError("invalid human review verdict")
    try:
        reviewed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("reviewed_at must be ISO 8601") from exc
    if reviewed_at.tzinfo is None:
        raise ValueError("reviewed_at must include a timezone")
    points = json.loads((run / "answer-points.json").read_text(encoding="utf-8"))
    ids = [point["id"] for point in points]
    scores = assessment["point_scores"]
    if (not isinstance(scores, dict) or set(scores) != set(ids)
            or len(ids) != len(set(ids))
            or any(not isinstance(score, dict) or set(score) != {"support", "coverage"}
                   or any(type(score[key]) is not int or score[key] not in {0, 1, 2}
                          for key in ("support", "coverage"))
                   for score in scores.values())):
        raise ValueError("review scores must cover each answer point")
    if verdict == "approved" and (assessment["serious_error"]
            or any(score != {"support": 2, "coverage": 2}
                   for score in scores.values())):
        raise ValueError("approved draft must pass every quality point")
    return {"schema_version": 1, "assessment": assessment,
            "file_sha256": file_hashes}


def require_approved_review(run: Path) -> dict[str, Any]:
    """Reject unreviewed or changed drafts before another incremental round."""
    path = run / "human-review.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("prior incremental draft requires human review")
    record = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(record, dict) or record.get("schema_version") != 1
            or not isinstance(record.get("assessment"), dict)
            or record["assessment"].get("verdict") != "approved"
            or record.get("file_sha256") != _hashes(run)):
        raise ValueError("prior incremental draft lacks an approved review of current files")
    # Revalidate the form too: an edited verdict alone is not an approval.
    if build_review_record(run, record["assessment"]) != record:
        raise ValueError("prior incremental draft review is invalid")
    return record
