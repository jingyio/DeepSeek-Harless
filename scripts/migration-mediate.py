#!/usr/bin/env python3
"""Diagnose a failed ABC migration, then structurally retry selected sites."""

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

from src.adapters.harness_semantic import SemanticValidationError, call_bounded_prompt  # noqa: E402
from src.adapters.migration_semantic import parse_migration_selection, prepare_migration_selection  # noqa: E402
from src.graph.runtime import Evidence, SemanticGap, execute  # noqa: E402
from src.workflows.migration import MIGRATION_MOTIF, VERIFY_MOTIF, discover_extra_abc_candidates  # noqa: E402


def _save(directory: Path, name: str, value: object) -> None:
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _verify(preview, test_argv: list[str]):
    initial = {key: preview.state[key] for key in ("root", "files", "updated", "ready")}
    initial["sandbox_root"] = Evidence(str(ROOT / ".local" / "migration-sandboxes"), "workspace_config")
    initial["test_argv"] = Evidence(test_argv, "user_input")
    return execute(VERIFY_MOTIF, initial)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--include", action="append", default=[], help="relative package, directory or file to scan; repeatable")
    parser.add_argument("--test-command", required=True, help="quoted command and arguments; no shell")
    parser.add_argument("--call-model", action="store_true", help="allow one paid, tool-free model selection")
    args = parser.parse_args()
    test_argv = shlex.split(args.test_command)
    target = args.target.resolve(strict=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "migration-mediations" / stamp
    output.mkdir(parents=True, exist_ok=False)

    preview = execute(MIGRATION_MOTIF, {"root": Evidence(str(target), "user_input"),
                                        "includes": Evidence(args.include, "user_input")})
    _save(output, "initial-preview.json", preview.report())
    (output / "initial.diff").write_text(preview.state.get("diff", Evidence("", "none")).value, encoding="utf-8")
    if preview.status != "completed":
        print(f"initial preview stopped: {preview.gap.kind if preview.gap else preview.status}; report={output}")
        return 2

    verification = _verify(preview, test_argv)
    _save(output, "initial-verification.json", verification.report())
    if "test_result" in verification.state:
        _save(output, "initial-test-result.json", verification.state["test_result"].value)
    if verification.status == "completed":
        print(f"status=verified; no model needed; report={output}")
        return 0
    if verification.gap is None or verification.gap.kind != "tests_failed":
        print(f"verification stopped: {verification.gap.kind if verification.gap else verification.status}; report={output}")
        return 2

    checkout = Path(verification.state["staged_path"].value)
    try:
        candidates = discover_extra_abc_candidates(checkout)
    except SemanticGap as exc:
        print(f"candidate discovery stopped: {exc.kind}; report={output}")
        return 2
    _save(output, "candidates.json", candidates)
    if not candidates:
        print(f"tests failed; no safe additional ABC candidate; report={output}")
        return 2
    prompt = prepare_migration_selection(verification, candidates)
    (output / "model-prompt.txt").write_text(prompt, encoding="utf-8")
    print(f"test failure; safe candidates={len(candidates)}; prompt characters={len(prompt)}; output cap=500 tokens")
    if not args.call_model:
        print(f"preview only; add --call-model for one bounded selection; report={output}")
        return 0

    try:
        raw, metrics = call_bounded_prompt(prompt, root=ROOT, max_output_tokens=500)
        _save(output, "model-metrics.json", metrics)
        (output / "model-response.txt").write_text(raw, encoding="utf-8")
        selection = parse_migration_selection(raw, candidates)
    except SemanticValidationError as exc:
        _save(output, "model-metrics.json", exc.metrics)
        (output / "model-response.txt").write_text(exc.raw_response, encoding="utf-8")
        print(f"model response rejected: {exc}; report={output}", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"model selection rejected: {exc}; report={output}", file=sys.stderr)
        return 2
    except Exception as exc:
        (output / "model-error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        print(f"model call failed: {type(exc).__name__}; report={output}", file=sys.stderr)
        return 2
    _save(output, "selection.json", selection)
    if not selection["selected"]:
        print(f"model found no related safe candidate; report={output}")
        return 2

    chosen = selection["selected"]
    retry = execute(MIGRATION_MOTIF, {
        "root": Evidence(str(checkout), "failed_staged_checkout"),
        "includes": Evidence(args.include, "user_input"),
        "aliases": Evidence(sorted({item["alias"] for item in chosen}), "validated_model_selection"),
        "selected_sites": Evidence([{key: item[key] for key in ("file", "line", "alias")} for item in chosen],
                                   "validated_model_selection"),
    })
    _save(output, "retry-preview.json", retry.report())
    (output / "retry.diff").write_text(retry.state.get("diff", Evidence("", "none")).value, encoding="utf-8")
    if retry.status != "completed" or not retry.state["updated"].value:
        print(f"retry preview stopped: {retry.gap.kind if retry.gap else retry.status}; report={output}")
        return 2
    retried = _verify(retry, test_argv)
    _save(output, "retry-verification.json", retried.report())
    if "test_result" in retried.state:
        _save(output, "retry-test-result.json", retried.state["test_result"].value)
    print(f"status={retried.status} selected_sites={len(chosen)} test_exit="
          f"{retried.state.get('test_result', Evidence({}, 'none')).value.get('exit_code')}; report={output}")
    return 0 if retried.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
