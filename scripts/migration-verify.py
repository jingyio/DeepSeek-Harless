#!/usr/bin/env python3
"""Preview a narrow migration, then test it in a copied checkout."""

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
from src.workflows.migration import MIGRATION_MOTIF, VERIFY_MOTIF  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--include", action="append", default=[], help="relative package, directory or file to scan; repeatable")
    parser.add_argument("--test-command", required=True, help="quoted command and arguments; no shell expansion")
    args = parser.parse_args()
    root = args.target.resolve(strict=True)
    preview = execute(MIGRATION_MOTIF, {"root": Evidence(str(root), "user_input"),
                                        "includes": Evidence(args.include, "user_input")})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "migration-verifications" / stamp
    output.mkdir(parents=True, exist_ok=False)
    (output / "preview.diff").write_text(preview.state.get("diff", Evidence("", "none")).value, encoding="utf-8")
    preview_report = preview.report()
    preview_report["site_runs"] = preview.state.get("site_runs", Evidence([], "none")).value
    (output / "preview.json").write_text(json.dumps(preview_report, ensure_ascii=False, indent=2), encoding="utf-8")
    if preview.status != "completed":
        print(f"preview stopped: {preview.gap.kind if preview.gap else preview.status}; report={output / 'preview.json'}")
        return 2
    initial = {key: preview.state[key] for key in ("root", "files", "updated", "ready")}
    initial["sandbox_root"] = Evidence(str(ROOT / ".local" / "migration-sandboxes"), "workspace_config")
    initial["test_argv"] = Evidence(shlex.split(args.test_command), "user_input")
    verification = execute(VERIFY_MOTIF, initial)
    (output / "verification.json").write_text(json.dumps(verification.report(), ensure_ascii=False, indent=2), encoding="utf-8")
    if "test_result" in verification.state:
        (output / "test-result.json").write_text(json.dumps(verification.state["test_result"].value, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"status={verification.status} test_exit={verification.state.get('test_result', Evidence({}, 'none')).value.get('exit_code')}" )
    print(f"preview={output / 'preview.diff'}")
    print(f"report={output / 'verification.json'}")
    return 0 if verification.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
