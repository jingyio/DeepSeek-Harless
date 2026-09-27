#!/usr/bin/env python3
"""Create or assess one evidence-backed Motif selection dependency revision."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflows.motif_skill_evolution import (  # noqa: E402
    assess, load_registry, new_registry, promote, propose_local_dependency, save_registry,
)


def read_json(path: Path):
    return json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True,
                        help="local version ledger, preferably under .local/")
    parser.add_argument("--init", action="store_true", help="create a global-dependency seed")
    parser.add_argument("--source-run", type=Path,
                        help="first research-points run with a validated selection")
    parser.add_argument("--changed-run", type=Path,
                        help="subsequent run with changed candidates and invalidation events")
    parser.add_argument("--train-cases", type=Path,
                        help="JSON array of frozen candidate-change cases")
    parser.add_argument("--validation-cases", type=Path,
                        help="disjoint JSON array of frozen candidate-change cases")
    args = parser.parse_args()
    try:
        if args.init:
            if args.registry.exists():
                raise ValueError("registry already exists")
            save_registry(args.registry, new_registry())
            print(f"initialized={args.registry}")
            return 0
        if not all((args.source_run, args.changed_run, args.train_cases, args.validation_cases)):
            raise ValueError("evolution needs both run directories and both frozen case sets")
        registry = load_registry(args.registry)
        source_run = args.source_run.resolve(strict=True)
        changed_run = args.changed_run.resolve(strict=True)
        source_state = read_json(source_run / "motif-selection-state.json")
        if source_state.get("signature_scope") != "global":
            raise ValueError("source run must use the global seed skill")
        changed_state = read_json(changed_run / "motif-source-state.json")
        if source_state["source_dir"] != changed_state["source_dir"]:
            raise ValueError("candidate change runs must use the same source directory")
        events = read_json(changed_run / "selection-reuse-events.json")
        child = propose_local_dependency(
            registry, source_run_id=source_run.name,
            points=read_json(source_run / "answer-points.json"),
            before_candidates=read_json(source_run / "selection-candidates.json"),
            after_candidates=read_json(changed_run / "selection-candidates.json"),
            invalidated_point_ids=[row["point_id"] for row in events
                                   if row["event"] == "selection_invalidated"],
        )
        train = assess(registry, version_id=child["id"], split="train",
                       cases=read_json(args.train_cases), source_dir=Path(source_state["source_dir"]))
        validation = assess(registry, version_id=child["id"], split="validation",
                            cases=read_json(args.validation_cases),
                            source_dir=Path(source_state["source_dir"]))
        promote(registry, child["id"])
        save_registry(args.registry, registry)
        print(json.dumps({"promoted": child["id"], "train": train, "validation": validation},
                         ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"evolution stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
