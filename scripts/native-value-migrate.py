#!/usr/bin/env python3
"""Preview and verify a guarded legacy native_concat Python 3.12 fix."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.runtime import Evidence, execute  # noqa: E402
from src.workflows.migration import VERIFY_MOTIF  # noqa: E402
from src.workflows.native_value_migration import NATIVE_VALUE_MOTIF  # noqa: E402


def _save(directory: Path, name: str, value: object) -> None:
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _verify(preview, argv: list[str], *, updated: dict[str, str]):
    return execute(VERIFY_MOTIF, {
        "root": preview.state["root"],
        "files": preview.state["files"],
        "updated": Evidence(updated, "guarded_recipe"),
        "ready": Evidence(True, "preview_verified"),
        "sandbox_root": Evidence(str(ROOT / ".local" / "migration-sandboxes"), "workspace_config"),
        "test_argv": Evidence(argv, "user_input"),
    })


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--file", required=True, help="relative package Python file; tests may not be edited")
    parser.add_argument("--test-command", required=True, help="quoted command and arguments; no shell")
    args = parser.parse_args()
    target = args.target.resolve(strict=True)
    argv = shlex.split(args.test_command)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "native-value-runs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    preview = execute(NATIVE_VALUE_MOTIF, {
        "root": Evidence(str(target), "user_input"), "file": Evidence(args.file, "user_input")
    })
    _save(output, "preview.json", preview.report())
    if "diff" in preview.state:
        (output / "preview.diff").write_text(preview.state["diff"].value, encoding="utf-8")
    if preview.status != "completed":
        print(f"preview stopped: {preview.gap.kind if preview.gap else preview.status}; report={output}")
        return 2
    baseline = _verify(preview, argv, updated={})
    _save(output, "baseline-verification.json", baseline.report())
    if "staged_path" in baseline.state:
        _save(output, "baseline-staged-path.json", {"path": baseline.state["staged_path"].value})
    if "test_result" in baseline.state:
        _save(output, "baseline-test-result.json", baseline.state["test_result"].value)
    if baseline.status == "completed":
        print(f"status=already_passed; no migration needed; report={output}")
        return 0
    if baseline.gap is None or baseline.gap.kind != "tests_failed":
        print(f"baseline stopped: {baseline.gap.kind if baseline.gap else baseline.status}; report={output}")
        return 2
    repaired = _verify(preview, argv, updated=preview.state["updated"].value)
    _save(output, "repaired-verification.json", repaired.report())
    if "staged_path" in repaired.state:
        _save(output, "repaired-staged-path.json", {"path": repaired.state["staged_path"].value})
    if "test_result" in repaired.state:
        _save(output, "repaired-test-result.json", repaired.state["test_result"].value)
    print(f"status={repaired.status} baseline_exit={baseline.state['test_result'].value['exit_code']} "
          f"repaired_exit={repaired.state.get('test_result', Evidence({}, 'none')).value.get('exit_code')} "
          f"model_requests=0; report={output}")
    return 0 if repaired.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
