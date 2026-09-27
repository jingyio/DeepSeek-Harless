#!/usr/bin/env python3
"""Compare plain calls, a simple versioned cache, and Motif on fixed read tasks.

All three receive the same explicit source, record path, and statistic slots.
This measures structural execution only: no model, discovery, or answer writing.
Inputs and output stay under .local so source paths and observations remain private.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_trajectory import ToolContract  # noqa: E402
from src.mcp import structured_research_tools as research  # noqa: E402
from src.motif_core.controller import MotifController  # noqa: E402
from src.motif_core.offline.library_builder import library_from_certified  # noqa: E402

FUNCTIONS = {"pin_source": research.pin_source,
             "inspect_records": research.inspect_records,
             "aggregate_records": research.aggregate_records}


def _local_file(path: str | Path) -> Path:
    target = Path(path).resolve(strict=True)
    if not target.is_file() or not target.is_relative_to((ROOT / ".local").resolve()):
        raise ValueError("comparison inputs must be files under .local")
    return target


def _contracts() -> dict[str, ToolContract]:
    specs = json.loads((ROOT / "config/structured-research-focused-contracts.json")
                       .read_text(encoding="utf-8"))
    return {name: ToolContract(
        tuple(spec["required_params"]), spec["read_only"],
        tuple(spec.get("output_fields", [])),
        description=spec.get("description", ""),
        provenance_params=tuple(spec.get("provenance_params", [])),
        parameter_shapes=tuple(tuple(item) for item in spec.get("parameter_shapes", [])),
        default_params=tuple(tuple(item) for item in spec.get("default_params", [])))
        for name, spec in specs.items()}


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    return {"matched_records": result["matched_records"],
            "group_count": result["group_count"], "groups": result["groups"]}


def _run_case(case: dict[str, Any], artifact: dict[str, Any],
              contracts: dict[str, ToolContract], stores: Path) -> dict[str, Any]:
    name = str(case["name"])
    source = _local_file(case["source"])
    record_path = case["records_path"]
    questions = case["questions"]
    expected_rows = case.get("expected")
    if (not name or not isinstance(record_path, str)
            or not isinstance(questions, list) or len(questions) < 2
            or any(not isinstance(query, dict)
                   or set(query) != {"group_by", "measures"}
                   for query in questions)
            or (expected_rows is not None
                and (not isinstance(expected_rows, list)
                     or len(expected_rows) != len(questions)
                     or any(not isinstance(row, dict) for row in expected_rows)))):
        raise ValueError("case needs a name, record path, and at least two explicit statistics")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    pin_tool, inspect_tool, aggregate_tool = artifact["tools"]
    if [item.rsplit("__", 1)[-1] for item in artifact["tools"]] != list(FUNCTIONS):
        raise ValueError("artifact must certify the three focused read operations")
    treatments = {}
    previous_store = research._STORE
    try:
        for mode in ("plain", "versioned_cache", "motif"):
            research._STORE = research.HandleStore(stores / f"{name}-{mode}.sqlite3")
            calls: list[str] = []
            checks = 0
            cache: dict[str, dict[str, Any]] = {}

            def verify() -> None:
                nonlocal checks
                checks += 1
                if hashlib.sha256(source.read_bytes()).hexdigest() != source_hash:
                    raise ValueError("source changed during structural comparison")

            def execute(tool: str, params: dict[str, Any]) -> dict[str, Any]:
                short = tool.rsplit("__", 1)[-1]
                if short not in FUNCTIONS:
                    raise ValueError("unapproved comparison tool")
                calls.append(short)
                return FUNCTIONS[short](**params)

            controller = (MotifController(
                library_from_certified([artifact]), contracts=contracts,
                execute_tool=execute, verify_current=verify,
                is_read_only=lambda tool: tool.rsplit("__", 1)[-1] in FUNCTIONS)
                if mode == "motif" else None)
            rounds = []
            for query in questions:
                before_calls, before_checks = len(calls), checks
                start = time.perf_counter_ns()
                if controller is not None:
                    decision = controller.execute_goal(
                        required_output=aggregate_tool,
                        bindings={pin_tool: {"path": str(source)},
                                  inspect_tool: {"records_path": record_path},
                                  aggregate_tool: query},
                        input_version=source_hash)
                    if decision.status != "completed" or decision.run is None:
                        raise ValueError("certified Motif did not complete the same statistic")
                    result = decision.run.outputs[aggregate_tool]
                else:
                    def call(short: str, params: dict[str, Any]) -> dict[str, Any]:
                        verify()
                        key = json.dumps([source_hash, short, params], sort_keys=True,
                                         ensure_ascii=False, separators=(",", ":"))
                        if mode == "versioned_cache" and key in cache:
                            return cache[key]
                        output = execute(short, params)
                        if mode == "versioned_cache":
                            cache[key] = output
                        return output

                    pinned = call("pin_source", {"path": str(source)})
                    inspected = call("inspect_records", {
                        "source_id": pinned["source_id"],
                        "records_path": record_path})
                    result = call("aggregate_records", {
                        "dataset_id": inspected["dataset_id"], **query})
                elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000
                rounds.append({"result": _summary(result),
                               "tool_calls": calls[before_calls:],
                               "source_checks": checks - before_checks,
                               "elapsed_ms": round(elapsed_ms, 3)})
            treatments[mode] = rounds
    finally:
        research._STORE = previous_store
    plain = treatments["plain"]
    for mode, rounds in treatments.items():
        for index, row in enumerate(rounds):
            if row["result"] != plain[index]["result"]:
                raise ValueError(f"{name}: {mode} result differs from plain tool calls")
            expected = (expected_rows or [None] * len(questions))[index]
            if expected is not None and any(row["result"].get(key) != value
                                            for key, value in expected.items()):
                raise ValueError(f"{name}: fixed expected data-stage result failed")
    return {"case": name, "source_sha256": source_hash,
            "question_count": len(questions), "model_requests": 0,
            "treatments": treatments,
            "notice": "Input slots are supplied identically; model and answer quality are out of scope."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    artifact_file, cases_file = _local_file(args.artifact), _local_file(args.cases)
    artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
    cases = json.loads(cases_file.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or len(cases) < 2:
        raise ValueError("at least two fixed data-stage cases are required")
    output = Path(args.out).resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        parser.error("output must stay under .local")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        result = [_run_case(case, artifact, _contracts(), Path(temporary))
                  for case in cases]
    report = {"status": "structural_execution_comparison_only",
              "artifact_motif_id": artifact["motif_id"],
              "artifact_certified_digest": artifact["certified_digest"],
              "artifact_file_sha256": hashlib.sha256(artifact_file.read_bytes()).hexdigest(),
              "cases_file_sha256": hashlib.sha256(cases_file.read_bytes()).hexdigest(),
              "cases": result,
              "limitations": ["no model decisions in any treatment",
                              "no complete research report or human quality review",
                              "small local latency measurements are descriptive only"]}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"cases": len(result),
                      "same_results": True,
                      "rounds_per_case": [row["question_count"] for row in result],
                      "tool_calls": {row["case"]: {
                          mode: [len(item["tool_calls"]) for item in rounds]
                          for mode, rounds in row["treatments"].items()}
                          for row in result}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
