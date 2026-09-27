#!/usr/bin/env python3
"""Run bounded local-source research and optionally resolve its synthesis gap."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.harness_semantic import SemanticValidationError, answer_with_harness, prepare_research_prompt  # noqa: E402
from src.graph.runtime import Evidence, execute  # noqa: E402
from src.workflows.research import RESEARCH_MOTIF  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "reference")
    parser.add_argument("--terms", required=True, help="comma-separated search terms")
    parser.add_argument("--call-model", action="store_true", help="spend one bounded Harness model turn")
    args = parser.parse_args()
    run = execute(RESEARCH_MOTIF, {
        "question": Evidence(args.question, "user_input"),
        "source_dir": Evidence(str(args.source_dir.resolve(strict=True)), "user_input"),
        "terms": Evidence(args.terms.split(","), "user_input"),
    })
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "research-runs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    (output / "trace.json").write_text(json.dumps(run.report(), ensure_ascii=False, indent=2), encoding="utf-8")
    if run.gap is None or run.gap.kind != "semantic_synthesis":
        print(f"status={run.status} gap={run.gap.kind if run.gap else 'none'} trace={output / 'trace.json'}")
        return 2
    prompt, citations = prepare_research_prompt(run)
    (output / "selected-evidence.json").write_text(json.dumps(citations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"verified evidence={len(citations)}; prompt characters={len(prompt)}; output cap=1200 tokens")
    if not args.call_model:
        print("preview only; add --call-model to resolve the semantic gap")
        print(f"evidence={output / 'selected-evidence.json'}")
        return 0
    try:
        answer = answer_with_harness(run, root=ROOT)
    except SemanticValidationError as exc:
        (output / "metrics.json").write_text(json.dumps(exc.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "raw-response.txt").write_text(exc.raw_response, encoding="utf-8")
        (output / "error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        print(f"semantic answer rejected: {exc}; metrics={output / 'metrics.json'}", file=sys.stderr)
        return 2
    except Exception as exc:
        (output / "error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        print(f"semantic step failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    (output / "answer.md").write_text(answer.markdown, encoding="utf-8")
    (output / "validated-claims.json").write_text(json.dumps(answer.claims, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "rejected-claims.json").write_text(json.dumps(answer.rejected_claims, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(answer.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"status=answered claims={len(answer.claims)} rejected={len(answer.rejected_claims)} model_requests={answer.metrics['model_requests']}")
    print(f"answer={output / 'answer.md'}")
    print(f"metrics={output / 'metrics.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
