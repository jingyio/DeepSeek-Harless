#!/usr/bin/env python3
"""Recheck a saved model answer against current citation rules without another API call."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.harness_semantic import _parse_response, prepare_full_context_prompt, prepare_research_prompt, render_answer  # noqa: E402
from src.graph.runtime import Evidence, Motif, Node, execute  # noqa: E402
from src.workflows.research import RESEARCH_MOTIF, _collect  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="saved session.v3.jsonl.zstd")
    parser.add_argument("--mode", choices=("full", "structured"), required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "reference")
    parser.add_argument("--terms", help="required for structured mode")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "structured" and not args.terms:
        parser.error("--terms is required for structured mode")
    initial = {
        "question": Evidence(args.question, "replay"),
        "source_dir": Evidence(str(args.source_dir.resolve(strict=True)), "replay"),
    }
    if args.mode == "full":
        motif = Motif("full-context-extraction-v1", (Node("collect", (), ("source_dir",), ("pages",), _collect),))
        run = execute(motif, initial)
        _, citations = prepare_full_context_prompt(run)
    else:
        initial["terms"] = Evidence(args.terms.split(","), "replay")
        run = execute(RESEARCH_MOTIF, initial)
        _, citations = prepare_research_prompt(run)
    lines = subprocess.check_output(["zstdcat", str(args.session.resolve(strict=True))], text=True).splitlines()
    events = [json.loads(line) for line in lines]
    messages = [event for event in events if event.get("type") == "assistant/message"]
    if not messages:
        raise ValueError("saved session has no assistant message")
    content = messages[-1].get("data", {}).get("message", {}).get("content", [])
    raw = "".join(block.get("text", "") for block in content if block.get("type") == "text")
    claims, uncertainties, rejected = _parse_response(raw, citations)
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "revalidated-answer.md").write_text(render_answer(claims, uncertainties, citations), encoding="utf-8")
    (output / "revalidation.json").write_text(json.dumps({
        "session": str(args.session.resolve()), "mode": args.mode,
        "accepted_claims": len(claims), "rejected_claims": rejected,
        "rule": "alphanumeric-sequence source match; removes PDF extraction whitespace and punctuation only",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"accepted={len(claims)} rejected={len(rejected)}")
    print(f"answer={output / 'revalidated-answer.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
