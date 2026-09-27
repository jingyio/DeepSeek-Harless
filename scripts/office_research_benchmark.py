#!/usr/bin/env python3
"""Prepare or grade the small synthetic office/research benchmark.

This is a structural regression check, not a judge of report quality.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


DEFAULT_BENCHMARK = Path(__file__).resolve().parents[1] / "benchmarks" / "office_research_v0"


def prepare(benchmark: Path, stage: str, output: Path) -> None:
    if output.exists():
        raise ValueError(f"output directory already exists: {output}")
    shutil.copytree(benchmark / "inputs" / "stage_a", output)
    if stage == "B":
        for path in (benchmark / "inputs" / "stage_b_delta").iterdir():
            if not path.is_file() or path.name.startswith("."):
                raise ValueError("invalid stage B input file")
            shutil.copy2(path, output / path.name)


def grade(benchmark: Path, prediction_path: Path, events_path: Path | None = None) -> dict[str, object]:
    payload = json.loads(prediction_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("stage") not in {"A", "B"}:
        raise ValueError("prediction must contain stage A or B")
    stage = payload["stage"]
    gold = json.loads((benchmark / "gold.json").read_text(encoding="utf-8"))[stage]
    source_dirs = [benchmark / "inputs" / "stage_a"]
    if stage == "B":
        source_dirs.append(benchmark / "inputs" / "stage_b_delta")
    sources = {path.name: path.read_text(encoding="utf-8")
               for directory in source_dirs for path in directory.iterdir() if path.is_file()}

    archive_rows = payload.get("archive", [])
    fact_rows = payload.get("facts", [])
    if not isinstance(archive_rows, list) or not isinstance(fact_rows, list):
        raise ValueError("archive and facts must be lists")
    archive: dict[str, dict[str, object]] = {}
    for row in archive_rows:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise ValueError("invalid archive row")
        if row["file"] in archive:
            raise ValueError(f"duplicate archive row: {row['file']}")
        archive[row["file"]] = row
    facts: dict[str, dict[str, object]] = {}
    for row in fact_rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("invalid fact row")
        if row["id"] in facts:
            raise ValueError(f"duplicate fact row: {row['id']}")
        facts[row["id"]] = row

    archive_checks = {}
    for filename, (record_id, status) in gold["archive"].items():
        row = archive.get(filename, {})
        archive_checks[filename] = row.get("record_id") == record_id and row.get("status") == status
    fact_checks = {}
    for fact_id, (value, source_file, required_anchor) in gold["facts"].items():
        row = facts.get(fact_id, {})
        quote = row.get("support_quote")
        fact_checks[fact_id] = (
            type(row.get("value")) is type(value)
            and row.get("value") == value
            and row.get("source_file") == source_file
            and isinstance(quote, str)
            and required_anchor in quote
            and quote in sources.get(source_file, "")
        )
    unexpected_archive = sorted(set(archive) - set(gold["archive"]))
    unexpected_facts = sorted(set(facts) - set(gold["facts"]))
    report_present = isinstance(payload.get("report"), str) and bool(payload["report"].strip())
    structural_gate = (all(archive_checks.values()) and all(fact_checks.values())
                       and not unexpected_archive and not unexpected_facts and report_present)
    result: dict[str, object] = {
        "stage": stage,
        "archive_checks": archive_checks,
        "fact_checks": fact_checks,
        "unexpected_archive": unexpected_archive,
        "unexpected_facts": unexpected_facts,
        "report_present": report_present,
        "structural_gate_pass": structural_gate,
        "quality_note": "Report content, claim entailment, and comparison quality require human review.",
    }
    if stage == "B" and isinstance(payload.get("trace"), dict):
        trace = payload["trace"]
        reused = trace.get("reused_sources")
        invalidated = trace.get("invalidated_records")
        result["mechanism_trace_check"] = {
            "unchanged_sources_reused": isinstance(reused, list) and
                set(gold["expected_reused_sources"]) <= set(map(str, reused)),
            "changed_record_invalidated": isinstance(invalidated, list) and
                gold["expected_invalidated_record"] in invalidated,
            "note": "Self-reported trace is diagnostic; verify against runtime events before using as evidence.",
        }
    if events_path is not None:
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        reads = {row["file"] for row in events if row.get("event") == "source_read"}
        reused = {row["file"] for row in events if row.get("event") == "source_reused"}
        invalidated = {row["record_id"] for row in events if row.get("event") == "record_invalidated"}
        expected_sources = set(sources)
        source_coverage = reads.isdisjoint(reused) and reads | reused == expected_sources
        trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
        event_consistency = set(trace.get("reused_sources", [])) == reused and set(trace.get("invalidated_records", [])) == invalidated
        expected_behavior = (stage == "A" and not reused and not invalidated) or (
            stage == "B" and set(gold["expected_reused_sources"]) <= reused
            and gold["expected_invalidated_record"] in invalidated
            and "GP-25" not in invalidated and "TR-25" not in invalidated
        )
        result["runtime_event_check"] = {
            "source_coverage": source_coverage,
            "trace_matches_events": event_consistency,
            "expected_reuse_and_invalidation": expected_behavior,
            "pass": source_coverage and event_consistency and expected_behavior,
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare", help="copy only task inputs to a new directory")
    prepare_parser.add_argument("--stage", choices=("A", "B"), required=True)
    prepare_parser.add_argument("--out", type=Path, required=True)
    grade_parser = subparsers.add_parser("grade", help="check structured output")
    grade_parser.add_argument("--prediction", type=Path, required=True)
    grade_parser.add_argument("--events", type=Path, help="runtime events for independent trace consistency checks")
    for item in (prepare_parser, grade_parser):
        item.add_argument("--benchmark", type=Path, default=DEFAULT_BENCHMARK)
    args = parser.parse_args()
    benchmark = args.benchmark.resolve(strict=True)
    if args.command == "prepare":
        output = args.out.resolve()
        prepare(benchmark, args.stage, output)
        print(json.dumps({"stage": args.stage, "inputs": str(output),
                          "files": sorted(path.name for path in output.iterdir())}, ensure_ascii=False))
        return 0
    result = grade(benchmark, args.prediction.resolve(strict=True),
                   args.events.resolve(strict=True) if args.events else None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["structural_gate_pass"] and result.get("runtime_event_check", {}).get("pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
