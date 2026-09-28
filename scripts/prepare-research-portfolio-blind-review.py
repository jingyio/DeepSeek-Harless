#!/usr/bin/env python3
"""Create private, arm-blinded answer packets for independent human review."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = (ROOT / ".local").resolve()


def write_private(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(data, encoding="utf-8")
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=("v1", "v2"), required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_root = args.run_root.resolve(strict=True)
    output = args.output.resolve()
    if not run_root.is_relative_to(PRIVATE) or not output.is_relative_to(PRIVATE):
        parser.error("run and review packets must stay under .local")
    bench = ROOT / f"benchmarks/research_decision_portfolio_{args.benchmark}"
    cases = sorted(path.name for path in (bench / "cases").iterdir()
                   if path.is_dir() and
                   all((run_root / path.name / arm / "agent-answer.md").is_file()
                       for arm in ("baseline", "motif")))
    if not cases:
        parser.error("no paired completed answers")
    index = []
    for case in cases:
        base = bench / "cases" / case
        packet = output / case
        answers = {arm: (run_root / case / arm / "agent-answer.md").read_text(
                   encoding="utf-8") for arm in ("baseline", "motif")}
        flip = int(hashlib.sha256((args.benchmark + ":" + case).encode()).hexdigest(), 16) % 2
        assignment = ({"A": "motif", "B": "baseline"} if flip
                      else {"A": "baseline", "B": "motif"})
        for label, arm in assignment.items():
            write_private(packet / f"answer-{label}.md", answers[arm])
        rubric = json.loads((base / "review.json").read_text(encoding="utf-8"))
        visible = {key: rubric[key] for key in ("case_id", "family", "must", "fatal",
                                               "numerical_reference")}
        write_private(packet / "rubric.json", json.dumps(visible, ensure_ascii=False,
                                                         indent=2) + "\n")
        write_private(packet / "task.md", (base / "task.md").read_text(encoding="utf-8"))
        write_private(output / "_sealed" / f"{case}.json",
                      json.dumps(assignment, indent=2) + "\n")
        index.append({"case": case, "family": rubric["family"],
                      "review_status": "pending_independent_review"})
    write_private(output / "INDEX.json", json.dumps(index, ensure_ascii=False,
                                                    indent=2) + "\n")
    print(json.dumps({"output": str(output), "paired_cases": len(index),
                      "status": "pending_independent_review"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
