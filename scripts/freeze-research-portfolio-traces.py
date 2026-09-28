#!/usr/bin/env python3
"""Bind portfolio baseline traces to independent decisions for Motif mining."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks/research_decision_portfolio_v1"
CONTRACTS = ROOT / "config/research-portfolio-tool-contracts.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_once(path: Path, value: dict) -> None:
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise ValueError(f"frozen identity changed: {path}")
    path.write_text(content, encoding="utf-8")
    path.chmod(0o600)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--train", nargs=2, required=True)
    parser.add_argument("--heldout", required=True)
    args = parser.parse_args()
    root = args.output_root.resolve(strict=True)
    if not root.is_relative_to((ROOT / ".local").resolve()):
        parser.error("trace identities must stay under .local")
    cases = [*args.train, args.heldout]
    if len(set(cases)) != 3:
        parser.error("training and held-out decisions must differ")
    rows = []
    for case in cases:
        task = BENCH / "cases" / case / "task.md"
        trial = root / case / "baseline"
        events = trial / "agent-events.jsonl"
        preview = trial / "PREVIEW.json"
        if not task.is_file() or not events.is_file() or not preview.is_file():
            parser.error(f"missing frozen baseline for {case}")
        frozen = json.loads(preview.read_text(encoding="utf-8"))
        if frozen.get("input_sha256", {}).get(str(task.relative_to(ROOT))) != digest(task):
            parser.error(f"task bytes changed after the baseline: {case}")
        question = task.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        save_once(trial / "manifest.json", {
            "task_id": frozen["task_id"], "question": question,
            "task_sha256": digest(task), "preview_sha256": digest(preview)})
        save_once(trial / "trace-identity.json", {
            "schema_version": 1, "research_decision_id": f"portfolio-v2-{case}",
            "manifest_sha256": digest(trial / "manifest.json"),
            "events_sha256": digest(events)})
        rows.append({"trace_id": f"portfolio-v2-{case}",
                     "events": str(events.relative_to(root)),
                     "identity": str((trial / "trace-identity.json").relative_to(root))})
    manifest = {"train": rows[:2], "heldout": rows[2:],
                "contracts": json.loads(CONTRACTS.read_text(encoding="utf-8"))}
    save_once(root / "compile-manifest.json", manifest)
    print(json.dumps({"train": args.train, "heldout": args.heldout,
                      "manifest": str(root / "compile-manifest.json")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
