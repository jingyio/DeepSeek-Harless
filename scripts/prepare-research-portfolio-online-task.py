#!/usr/bin/env python3
"""Freeze approved object versions for a held-out research portfolio case."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks/research_decision_portfolio_v1/cases"
PREFIX = "mcp__research_portfolio_fixture__"


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def prepare(case: str) -> dict:
    base = BENCH / case
    if not base.is_dir() or not (base / "task.md").is_file():
        raise ValueError("unknown frozen portfolio case")
    sources = json.loads((base / "sources.json").read_text(encoding="utf-8"))
    event = sources["event"]
    objects = sources["objects"]
    if event["event_id"] != f"event:{case}:01" or not objects or len(objects) > 32:
        raise ValueError("event identity or approved object count changed")
    versions = {object_id: digest(value) for object_id, value in objects.items()}
    event_version = digest(event)
    material = {"case": case, "event": event_version, "objects": versions,
                "task": hashlib.sha256((base / "task.md").read_bytes()).hexdigest()}
    return {"schema_version": 1, "task_id": f"research-portfolio-{case}",
            "session_id": f"sss-portfolio-{case}-{uuid4().hex}",
            "intent": " ".join((base / "task.md").read_text(encoding="utf-8").split()),
            "input_version": digest(material), "bindings": {},
            "source_versions": {
                PREFIX + "read_event": event_version,
                PREFIX + "pin_resource": sorted(versions.values()),
                PREFIX + "read_pinned": sorted(versions.values()),
            }, "object_versions": versions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        parser.error("frozen task must stay under .local")
    task = prepare(args.case)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.exists():
        raise ValueError("refusing to replace a frozen online task")
    output.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"output": str(output), "task_id": task["task_id"],
                      "approved_object_count": len(task["object_versions"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
