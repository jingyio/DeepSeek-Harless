#!/usr/bin/env python3
"""Freeze a DSH task's human-reviewed decision ID against manifest and events."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.task_identity import DECISION_ID, load_trace_identity  # noqa: E402


def freeze(task_dir: Path, decision_id: str,
           events_name: str = "events.jsonl") -> Path:
    local = (ROOT / ".local").resolve()
    directory = task_dir.resolve(strict=True)
    if not directory.is_relative_to(local) or not DECISION_ID.fullmatch(decision_id):
        raise ValueError("task directory must be under .local and decision ID must be stable")
    if Path(events_name).name != events_name:
        raise ValueError("events name must be a file in the task directory")
    manifest = directory / "manifest.json"
    events = directory / events_name
    if manifest.is_symlink() or events.is_symlink():
        raise ValueError("task manifest and events must be regular task files")
    manifest_raw = manifest.read_bytes()
    manifest_data = json.loads(manifest_raw)
    if (not isinstance(manifest_data, dict)
            or not isinstance(manifest_data.get("task_id"), str)
            or not manifest_data["task_id"]
            or not isinstance(manifest_data.get("question"), str)
            or not manifest_data["question"].strip()):
        raise ValueError("task manifest needs a task_id and research question")
    payload = {
        "schema_version": 1,
        "research_decision_id": decision_id,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "events_sha256": hashlib.sha256(events.read_bytes()).hexdigest(),
    }
    output = directory / "task-identity.json"
    encoded = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if output.exists():
        if output.read_text(encoding="utf-8") != encoded:
            raise ValueError("existing task identity is immutable")
    else:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
        output.chmod(0o600)
    load_trace_identity(output, events, local)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, required=True)
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--events", default="events.jsonl")
    args = parser.parse_args()
    path = freeze(args.task_dir, args.decision_id, args.events)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
