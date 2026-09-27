#!/usr/bin/env python3
"""Run the migrated MotifAgent office motif on prepared benchmark inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflows.motif_office import OfficeHandoffError, load_json, run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("A", "B"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="output directory; must be empty/new")
    parser.add_argument("--resume-state", type=Path)
    args = parser.parse_args()
    input_dir = args.input.resolve(strict=True)
    previous = load_json(args.resume_state.resolve(strict=True)) if args.resume_state else None
    try:
        prediction, state, events = run(args.stage, input_dir, previous)
    except OfficeHandoffError as exc:
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "handoff.json").write_text(
            json.dumps(exc.request.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "needs_clarification", "handoff": str((args.out / "handoff.json").resolve())}, ensure_ascii=False))
        return 2
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "prediction.json").write_text(json.dumps(prediction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.out / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")
    print(json.dumps({"stage": args.stage, "out": str(args.out.resolve()),
                      "archive_rows": len(prediction["archive"]), "facts": len(prediction["facts"]),
                      "reused_sources": len(prediction["trace"]["reused_sources"]),
                      "invalidated_records": prediction["trace"]["invalidated_records"],
                      "model_requests": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
