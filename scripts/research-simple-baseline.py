#!/usr/bin/env python3
"""Deterministic retrieval script baseline with one bounded synthesis call."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.harness_semantic import (  # noqa: E402
    SemanticValidationError, answer_bounded_evidence_prompt,
    prepare_research_prompt_from_evidence,
)
from src.adapters.point_research_semantic import prepare_simple_point_prompt  # noqa: E402
from src.graph.runtime import Evidence, SemanticGap, execute  # noqa: E402
from src.workflows.research_brief import render_brief  # noqa: E402
from src.workflows.research import (  # noqa: E402
    ANSWER_POINT_PREFLIGHT_MOTIF, QUESTION_COVERAGE_MOTIF,
    _collect, _dedupe, _select, _verify,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "reference")
    parser.add_argument("--terms", required=True, help="human supplied comma-separated English terms")
    parser.add_argument("--per-source-limit", type=int, default=4,
                        help="verified candidate pages per source (1-12; default 4)")
    parser.add_argument("--answer-points", type=Path, help="optional shared 1-8-point evaluation rubric")
    parser.add_argument("--call-model", action="store_true")
    args = parser.parse_args()
    source_dir = args.source_dir.resolve(strict=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "research-simple-baselines" / stamp
    output.mkdir(parents=True, exist_ok=False)
    (output / "question.txt").write_text(args.question.strip() + "\n", encoding="utf-8")
    points = None
    if args.answer_points:
        try:
            point_data = json.loads(args.answer_points.resolve(strict=True).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"answer points unreadable: {exc}; report={output}", file=sys.stderr)
            return 2
        preflight = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
            "answer_points": Evidence(point_data, "shared_question_obligations"),
        })
        (output / "answer-points-preflight.json").write_text(
            json.dumps(preflight.report(), ensure_ascii=False, indent=2), encoding="utf-8")
        if preflight.status != "completed":
            print(f"answer points rejected: {preflight.gap.kind if preflight.gap else preflight.status}; "
                  f"report={output}", file=sys.stderr)
            return 2
        points = preflight.state["validated_answer_points"].value
        (output / "answer-points.json").write_text(
            json.dumps(points, ensure_ascii=False, indent=2), encoding="utf-8")
    state: dict[str, Evidence] = {
        "source_dir": Evidence(str(source_dir), "user_input"),
        "terms": Evidence(args.terms.split(","), "human_supplied_baseline_terms"),
        "per_source_limit": Evidence(args.per_source_limit, "user_supplied_retrieval_limit"),
    }
    try:
        for action in (_collect, _dedupe, _select, _verify):
            for key, value in action(state).items():
                state[key] = Evidence(value, "ordinary_script")
    except SemanticGap as exc:
        print(f"baseline retrieval stopped: {exc.kind}; report={output}", file=sys.stderr)
        return 2
    sources = sorted(path for path in source_dir.iterdir()
                     if path.suffix.lower() in {".pdf", ".md", ".txt"})
    inventory = [
        {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
         "bytes": path.stat().st_size} for path in sources
    ]
    collected_hashes = {row["source"]: row["source_sha256"] for row in state["pages"].value}
    if any(row["filename"] in collected_hashes and
           row["sha256"] != collected_hashes[row["filename"]] for row in inventory):
        print(f"baseline source changed during inventory; report={output}", file=sys.stderr)
        return 2
    (output / "sources.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    evidence = state["verified_evidence"].value
    if points is None:
        prompt, citations = prepare_research_prompt_from_evidence(args.question, evidence)
    else:
        prompt, citations = prepare_simple_point_prompt(args.question, points, evidence)
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    (output / "evidence.json").write_text(json.dumps(citations, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"retrieved={len(evidence)} cited={len(citations)} prompt_characters={len(prompt)} "
          f"output_cap={1800 if points is not None else 1200}")
    if not args.call_model:
        (output / "status.json").write_text(json.dumps({"status": "preview"}), encoding="utf-8")
        print(f"preview only; report={output}")
        return 0
    try:
        answer = answer_bounded_evidence_prompt(
            prompt, citations, root=ROOT, max_output_tokens=1800 if points is not None else 1200,
            point_ids={point["id"] for point in points} if points is not None else None)
    except SemanticValidationError as exc:
        (output / "metrics.json").write_text(json.dumps(exc.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "raw-response.txt").write_text(exc.raw_response, encoding="utf-8")
        (output / "status.json").write_text(json.dumps({"status": "stopped", "stage": "synthesis",
                                                          "reason": str(exc)}, ensure_ascii=False),
                                                   encoding="utf-8")
        print(f"baseline answer rejected: {exc}; report={output}", file=sys.stderr)
        return 2
    markdown = (render_brief(args.question, points, answer.claims, answer.uncertainties, citations)
                if points is not None else answer.markdown)
    (output / "answer.md").write_text(markdown, encoding="utf-8")
    (output / "claims.json").write_text(json.dumps(answer.claims, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "uncertainties.json").write_text(json.dumps(answer.uncertainties, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "rejected-claims.json").write_text(json.dumps(answer.rejected_claims, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(answer.metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "raw-response.txt").write_text(answer.raw_response, encoding="utf-8")
    if points is not None:
        coverage = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": Evidence(points, "shared_question_obligations"),
            "citations": Evidence(citations, "verified_retrieval"),
            "claims": Evidence(answer.claims, "quote_checked_model_claims"),
            "uncertainties": Evidence(answer.uncertainties, "validated_model_uncertainties"),
        })
        (output / "question-coverage-gate.json").write_text(
            json.dumps(coverage.report(), ensure_ascii=False, indent=2), encoding="utf-8")
        checks = coverage.state.get("point_coverage")
        if checks is not None:
            (output / "question-coverage.json").write_text(
                json.dumps(checks.value, ensure_ascii=False, indent=2), encoding="utf-8")
        status = "point_links_present" if coverage.status == "completed" and answer.claims else "incomplete_answer"
    else:
        status = "answered" if answer.claims else "incomplete_answer"
    (output / "status.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    print(f"status={status} claims={len(answer.claims)} rejected={len(answer.rejected_claims)}; report={output}")
    return 0 if status in {"answered", "point_links_present"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
