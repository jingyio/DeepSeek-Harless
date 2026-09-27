#!/usr/bin/env python3
"""Prepare traceable local-source evidence before semantic synthesis."""

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
from src.workflows.research import RESEARCH_MOTIF  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="bounded research question")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "reference")
    parser.add_argument("--terms", required=True, help="comma-separated search terms")
    args = parser.parse_args()
    source_dir = args.source_dir.resolve(strict=True)
    run = execute(RESEARCH_MOTIF, {
        "question": Evidence(args.question, "user_input"),
        "source_dir": Evidence(str(source_dir), "user_input"),
        "terms": Evidence(args.terms.split(","), "user_input"),
    })
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "research-runs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    report = run.report()
    report["question"] = args.question
    report["terms"] = args.terms.split(",")
    evidence = run.state.get("verified_evidence", Evidence([], "none")).value
    (output / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"status={run.status} verified_pages={len(evidence)} gap={run.gap.kind if run.gap else 'none'}")
    print(f"evidence={output / 'evidence.json'}")
    print(f"report={output / 'report.json'}")
    return 0 if run.gap and run.gap.kind == "semantic_synthesis" else 2


if __name__ == "__main__":
    raise SystemExit(main())
