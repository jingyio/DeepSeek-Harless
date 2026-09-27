#!/usr/bin/env python3
"""Freeze a private, version-scoped online task for one synthetic meeting case."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "benchmarks/meeting_decision_chain_v1/sources"
V2_CASE_IDS = frozenset(("model_rsi_state", "aidd_mutation",
                         "agent_tool_transfer"))
V3_CASE_IDS = frozenset(("rna_batch", "retrieval_language", "robot_protocol"))
V4_CASE_IDS = frozenset(("battery_cold", "corpus_shift", "remote_assay"))
V5_CASE_IDS = frozenset(("microscopy_vendor", "chemistry_substrate",
                         "materials_scaleup"))
PRIVATE = (ROOT / ".local").resolve()
PREFIX = "mcp__meeting_decision_fixture__"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(case: str, template: dict) -> dict:
    version = ("v5" if case in V5_CASE_IDS else
               "v4" if case in V4_CASE_IDS else
               "v3" if case in V3_CASE_IDS else "v2" if case in V2_CASE_IDS else "v1")
    bench = ROOT / f"benchmarks/meeting_decision_chain_{version}"
    base = bench / "sources" / case
    task_file = bench / "tasks" / f"{case}.md"
    if not base.is_dir() or not task_file.is_file():
        raise ValueError("unknown approved meeting case")
    event = json.loads((base / "event.json").read_text(encoding="utf-8"))
    note = json.loads((base / "note.json").read_text(encoding="utf-8"))
    current, previous = event["experiment_id"], event["previous_experiment_id"]
    if (event["event_id"] != f"event:{case}:w39" or
            note["depends_on"] != current or
            event["previous_version_sha256"] != sha(base / "previous_experiment.xlsx") or
            current != f"wps:{case}:run_2026w39" or
            previous != f"wps:{case}:run_2026w38"):
        raise ValueError("event, prior version, and claim index disagree")
    object_versions = {
        current: sha(base / "experiment.xlsx"),
        previous: sha(base / "previous_experiment.xlsx"),
        f"obsidian:{case}:claim": sha(base / "note.json"),
        f"zotero:{case}:annotation": sha(base / "annotation.json"),
    }
    index_version = hashlib.sha256(":".join((
        object_versions[current], object_versions[f"obsidian:{case}:claim"],
        object_versions[f"zotero:{case}:annotation"])).encode()).hexdigest()
    lookup_versions = {PREFIX + "find_dependent_claims": {current: index_version}}
    event_version = sha(base / "event.json")
    if (template.get("schema_version") != 1 or
            template.get("task_id") != f"meeting-decision-{case}" or
            not isinstance(template.get("intent"), str) or
            not template["intent"] or template.get("bindings") != {}):
        raise ValueError("template does not match this independent decision")
    source_versions = {
        PREFIX + "read_change": event_version,
        PREFIX + "pin_object": sorted(object_versions.values()),
        PREFIX + "read_pinned_object": sorted(object_versions.values()),
        PREFIX + "find_dependent_claims": index_version,
    }
    input_material = {"case": case, "event_version": event_version,
                      "object_versions": object_versions,
                      "lookup_versions": lookup_versions,
                      "task_sha256": sha(task_file)}
    input_version = hashlib.sha256(json.dumps(input_material, sort_keys=True)
                                   .encode("utf-8")).hexdigest()
    return {**template, "session_id": f"sss-meeting-{case}-object-{uuid4().hex}",
            "input_version": input_version, "source_versions": source_versions,
            "object_versions": object_versions,
            "lookup_versions": lookup_versions}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    parser.add_argument("--template", type=Path,
                        help="Private prior task template; omit for a new v2 case")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(PRIVATE):
        parser.error("task output must stay under .local")
    if args.template:
        template_path = args.template.resolve(strict=True)
        if not template_path.is_relative_to(PRIVATE):
            parser.error("task template must stay under .local")
        template = json.loads(template_path.read_text(encoding="utf-8"))
    elif args.case in V2_CASE_IDS | V3_CASE_IDS | V4_CASE_IDS | V5_CASE_IDS:
        version = ("v5" if args.case in V5_CASE_IDS else
                   "v4" if args.case in V4_CASE_IDS else
                   "v3" if args.case in V3_CASE_IDS else "v2")
        task_text = (ROOT / f"benchmarks/meeting_decision_chain_{version}/tasks"
                     / f"{args.case}.md").read_text(encoding="utf-8")
        template = {"schema_version": 1, "task_id": f"meeting-decision-{args.case}",
                    "intent": " ".join(task_text.split()), "bindings": {}}
    else:
        parser.error("old cases need a frozen private template")
    task = prepare(args.case, template)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.write_text(json.dumps(task, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"output": str(output), "task_id": task["task_id"],
                      "approved_object_count": len(task["object_versions"])},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
