#!/usr/bin/env python3
"""Preview the first evidence-guarded migration; never writes target files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graph.runtime import Evidence, execute  # noqa: E402
from src.workflows.migration import MIGRATION_MOTIF  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="repository or subdirectory to inspect")
    parser.add_argument("--include", action="append", default=[], help="relative package, directory or file to scan; repeatable")
    args = parser.parse_args()
    target = args.target.resolve(strict=True)
    run = execute(MIGRATION_MOTIF, {"root": Evidence(str(target), source="user_input"),
                                    "includes": Evidence(args.include, source="user_input")})
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "migration" / stamp
    output.mkdir(parents=True, exist_ok=False)
    (output / "preview.diff").write_text(run.state.get("diff", Evidence("", "none")).value, encoding="utf-8")
    report = run.report()
    report["task"] = {"target": str(target), "includes": args.include, "recipe": MIGRATION_MOTIF.id}
    report["proposals"] = [
        {key: value for key, value in proposal.items() if key not in {"before", "after"}}
        for proposal in run.state.get("proposals", Evidence([], "none")).value
    ]
    report["gaps"] = run.state.get("gaps", Evidence([], "none")).value
    report["site_runs"] = run.state.get("site_runs", Evidence([], "none")).value
    report["changed_files"] = sorted(run.state.get("updated", Evidence({}, "none")).value)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"status={run.status} proposals={len(report['proposals'])} gaps={len(report['gaps'])}")
    print(f"preview={output / 'preview.diff'}")
    print(f"report={output / 'report.json'}")
    return 0 if run.status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
