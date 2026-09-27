#!/usr/bin/env python3
"""Run two-step bounded research: plan searches, verify evidence, synthesize."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.deep_research_semantic import (  # noqa: E402
    parse_evidence_selection, parse_research_plan, prepare_deep_synthesis,
    prepare_evidence_selection, prepare_research_plan,
)
from src.adapters.harness_semantic import (  # noqa: E402
    SemanticValidationError, answer_bounded_evidence_prompt, call_bounded_prompt,
)
from src.graph.runtime import Evidence, execute  # noqa: E402
from src.workflows.research import (  # noqa: E402
    ANSWER_COVERAGE_MOTIF, ANSWER_POINT_PREFLIGHT_MOTIF, EVIDENCE_CONTRACT_MOTIF,
    QUESTION_COVERAGE_MOTIF, RETRIEVE_MOTIF, SOURCE_MOTIF,
    ground_query_terms,
)


def _save(directory: Path, name: str, value: object) -> None:
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _source_scope(question: str, sources: list[str]) -> list[str]:
    folded = question.casefold()
    compact = re.sub(r"[^a-z0-9]", "", folded)
    selected: list[str] = []
    for source in sources:
        stem = Path(source).stem
        normalized_name = re.sub(r"[^a-z0-9]", "", stem.casefold())
        acronyms = re.findall(r"[A-Z]{2,}", stem)
        if (4 <= len(normalized_name) <= 30 and normalized_name in compact) or any(
            re.search(r"\b" + re.escape(acronym.casefold()) + r"\b", folded) for acronym in acronyms
        ):
            selected.append(source)
    return selected or sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "reference")
    parser.add_argument("--plan-file", type=Path, help="reuse a saved, validated plan JSON without a planning model call")
    parser.add_argument("--selection-file", type=Path, help="reuse a saved evidence selection JSON without a selection model call")
    parser.add_argument("--evidence-contract", type=Path,
                        help="JSON answer points with exact source/page anchors that must reach synthesis")
    parser.add_argument("--answer-points", type=Path,
                        help="predeclared JSON obligations [{id, requirement}] without known source pages")
    parser.add_argument("--plan-only", action="store_true", help="stop after saving the validated search plan")
    parser.add_argument("--call-model", action="store_true", help="allow at most three paid model turns")
    args = parser.parse_args()
    source_dir = args.source_dir.resolve(strict=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "deep-research-runs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    sources = execute(SOURCE_MOTIF, {"source_dir": Evidence(str(source_dir), "user_input")})
    _save(output, "source-trace.json", sources.report())
    if sources.status != "completed":
        print(f"source collection stopped: {sources.gap.kind if sources.gap else sources.status}; report={output}")
        return 2
    pages = sources.state["unique_pages"].value
    answer_points = None
    if args.answer_points:
        try:
            raw_points = json.loads(args.answer_points.resolve(strict=True).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"answer points unreadable: {exc}; report={output}", file=sys.stderr)
            return 2
        preflight = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
            "answer_points": Evidence(raw_points, "user_supplied_question_obligations"),
        })
        _save(output, "answer-points-preflight.json", preflight.report())
        if preflight.status != "completed":
            print(f"answer points rejected: {preflight.gap.kind if preflight.gap else preflight.status}; "
                  f"report={output}", file=sys.stderr)
            return 2
        answer_points = preflight.state["validated_answer_points"].value
        _save(output, "answer-points.json", answer_points)
    contract = None
    if args.evidence_contract:
        try:
            contract = json.loads(args.evidence_contract.resolve(strict=True).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"evidence contract unreadable: {exc}; report={output}", file=sys.stderr)
            return 2
        preflight = execute(EVIDENCE_CONTRACT_MOTIF, {
            "unique_pages": sources.state["unique_pages"],
            "selected_evidence": Evidence([
                {"source": row["source"], "page": row["page"], "snippet": row["text"][:750]}
                for row in pages
            ], "preflight_source_pages"),
            "contract": Evidence(contract, "user_supplied_contract"),
        })
        _save(output, "contract-preflight.json", preflight.report())
        if preflight.status != "completed":
            print(f"evidence contract rejected: {preflight.gap.kind if preflight.gap else preflight.status}; "
                  f"report={output}", file=sys.stderr)
            return 2
    plan_prompt = prepare_research_plan(args.question, pages)
    (output / "plan-prompt.txt").write_text(plan_prompt, encoding="utf-8")
    print(f"sources={len({page['source'] for page in pages})} pages={len(pages)} "
          f"plan_prompt_characters={len(plan_prompt)} model_cap="
          f"{'0' if args.plan_file else '500'}+{'0' if args.selection_file else '500'}+"
          f"{1800 if contract is not None or answer_points is not None else 1200} output tokens")
    if not args.call_model and not args.plan_file:
        print(f"preview only; add --call-model for three bounded turns; report={output}")
        return 0
    if args.plan_file:
        saved = json.loads(args.plan_file.resolve(strict=True).read_text(encoding="utf-8"))
        plan = parse_research_plan(json.dumps({"subquestions": saved}, ensure_ascii=False))
        plan_metrics = {key: 0 for key in ("model_requests", "inputTokens", "cacheReadTokens", "outputTokens", "totalTokens")}
        _save(output, "plan-metrics.json", plan_metrics)
    else:
        try:
            raw_plan, plan_metrics = call_bounded_prompt(plan_prompt, root=ROOT, max_output_tokens=500)
            _save(output, "plan-metrics.json", plan_metrics)
            (output / "plan-response.txt").write_text(raw_plan, encoding="utf-8")
            plan = parse_research_plan(raw_plan)
        except SemanticValidationError as exc:
            _save(output, "plan-metrics.json", exc.metrics)
            (output / "plan-response.txt").write_text(exc.raw_response, encoding="utf-8")
            print(f"plan rejected: {exc}; report={output}", file=sys.stderr)
            return 2
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"plan rejected: {exc}; report={output}", file=sys.stderr)
            return 2
        except Exception as exc:
            (output / "plan-error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
            print(f"planning call failed: {type(exc).__name__}; report={output}", file=sys.stderr)
            return 2
    _save(output, "plan.json", plan)
    if args.plan_only:
        print(f"plan ready subquestions={len(plan)} model_requests={plan_metrics['model_requests']}; "
              f"plan={output / 'plan.json'}")
        return 0

    subresults: list[dict[str, object]] = []
    available_sources = sorted({page["source"] for page in pages})
    for item in plan:
        scope = _source_scope(item["question"], available_sources)
        try:
            grounded_terms, grounding_changes = ground_query_terms(item["terms"], pages, scope)
        except Exception as exc:
            _save(output, "failed-subquestion.json", {"item": item, "source_scope": scope,
                                                     "error": f"{type(exc).__name__}: {exc}"})
            print(f"query grounding stopped: {type(exc).__name__}; report={output}")
            return 2
        run = execute(RETRIEVE_MOTIF, {
            "unique_pages": sources.state["unique_pages"],
            "source_dir": sources.state["source_dir"],
            "question": Evidence(item["question"], "validated_plan"),
            "terms": Evidence(grounded_terms, "verified_source_terms"),
            "source_allowlist": Evidence(scope, "named_source_scope"),
            "per_source_limit": Evidence(12, "deep_research_candidate_pool"),
        })
        if run.gap is not None and run.gap.kind == "semantic_synthesis":
            status = "evidence_verified"
            evidence = run.state["verified_evidence"].value
        elif run.gap is not None and run.gap.kind == "no_matching_evidence":
            status = "no_matching_evidence"
            evidence = []
        else:
            _save(output, "failed-subquestion.json", {"item": item, "trace": run.report()})
            print(f"retrieval stopped: {run.gap.kind if run.gap else run.status}; report={output}")
            return 2
        subresults.append({"question": item["question"], "terms": item["terms"],
                           "grounded_terms": grounded_terms, "grounding_changes": grounding_changes,
                           "source_scope": scope,
                           "status": status, "evidence": evidence, "trace": run.report()})
    _save(output, "subquestions.json", subresults)
    if not any(row["evidence"] for row in subresults):
        print(f"no verified evidence for any subquestion; report={output}")
        return 2
    selection_prompt, selection_candidates = prepare_evidence_selection(args.question, subresults)
    (output / "evidence-selection-prompt.txt").write_text(selection_prompt, encoding="utf-8")
    if args.selection_file:
        selection_raw = args.selection_file.resolve(strict=True).read_text(encoding="utf-8")
        selection_metrics = {key: 0 for key in ("model_requests", "inputTokens", "cacheReadTokens", "outputTokens", "totalTokens")}
    elif not args.call_model:
        print(f"verified subquestions={len(plan)} candidate_pages={len(selection_candidates)} "
              f"selection_prompt_characters={len(selection_prompt)}")
        print(f"preview only; add --call-model for page selection and synthesis; report={output}")
        return 0
    else:
        try:
            selection_raw, selection_metrics = call_bounded_prompt(selection_prompt, root=ROOT,
                                                                   max_output_tokens=500)
        except SemanticValidationError as exc:
            _save(output, "evidence-selection-metrics.json", exc.metrics)
            (output / "evidence-selection-response.txt").write_text(exc.raw_response, encoding="utf-8")
            print(f"evidence selection rejected: {exc}; report={output}", file=sys.stderr)
            return 2
        except Exception as exc:
            (output / "evidence-selection-error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
            print(f"evidence selection failed: {type(exc).__name__}; report={output}", file=sys.stderr)
            return 2
    _save(output, "evidence-selection-metrics.json", selection_metrics)
    (output / "evidence-selection-response.txt").write_text(selection_raw, encoding="utf-8")
    try:
        selected_ids = parse_evidence_selection(selection_raw, selection_candidates, len(subresults))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"evidence selection invalid: {exc}; report={output}", file=sys.stderr)
        return 2
    _save(output, "evidence-selection.json", {"selections": [
        {"question_id": f"Q{index}", "evidence_ids": ids}
        for index, ids in enumerate(selected_ids, 1)
    ]})
    for result, ids in zip(subresults, selected_ids):
        result["evidence"] = [selection_candidates[key]["evidence"] for key in ids]
    _save(output, "selected-subquestions.json", subresults)
    if contract is not None:
        coverage = execute(EVIDENCE_CONTRACT_MOTIF, {
            "unique_pages": sources.state["unique_pages"],
            "selected_evidence": Evidence([row for result in subresults for row in result["evidence"]],
                                          "verified_selection"),
            "contract": Evidence(contract, "preflighted_contract"),
        })
        _save(output, "coverage-gate.json", coverage.report())
        if coverage.status != "completed":
            print(f"evidence coverage stopped: {coverage.gap.kind if coverage.gap else coverage.status}; "
                  f"report={output}", file=sys.stderr)
            return 2
        _save(output, "coverage-checks.json", coverage.state["coverage_checks"].value)
        grounded = {(row["source"], row["page"]): row
                    for row in coverage.state["grounded_evidence"].value}
        for result in subresults:
            result["evidence"] = [grounded[(row["source"], row["page"])] for row in result["evidence"]]
        _save(output, "grounded-subquestions.json", subresults)
    synthesis_prompt, citations = prepare_deep_synthesis(args.question, subresults, contract, answer_points)
    (output / "synthesis-prompt.txt").write_text(synthesis_prompt, encoding="utf-8")
    _save(output, "selected-evidence.json", citations)
    if not args.call_model:
        print(f"verified subquestions={len(plan)} citations={len(citations)} synthesis_prompt_characters={len(synthesis_prompt)}")
        print(f"preview only; add --call-model for synthesis; report={output}")
        return 0
    try:
        answer = answer_bounded_evidence_prompt(synthesis_prompt, citations, root=ROOT,
                                                max_output_tokens=1800 if contract is not None or answer_points else 1200,
                                                point_ids={point["id"] for point in answer_points} if answer_points else None)
    except SemanticValidationError as exc:
        _save(output, "synthesis-metrics.json", exc.metrics)
        (output / "synthesis-response.txt").write_text(exc.raw_response, encoding="utf-8")
        _save(output, "failed-total-metrics.json", {
            key: plan_metrics.get(key, 0) + selection_metrics.get(key, 0) + exc.metrics.get(key, 0)
            for key in ("model_requests", "inputTokens", "cacheReadTokens", "outputTokens", "totalTokens")
        })
        print(f"synthesis rejected: {exc}; report={output}", file=sys.stderr)
        return 2
    except Exception as exc:
        (output / "synthesis-error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        print(f"synthesis failed: {type(exc).__name__}; report={output}", file=sys.stderr)
        return 2
    (output / "answer.md").write_text(answer.markdown, encoding="utf-8")
    _save(output, "claims.json", answer.claims)
    _save(output, "rejected-claims.json", answer.rejected_claims)
    _save(output, "synthesis-metrics.json", answer.metrics)
    totals = {key: plan_metrics.get(key, 0) + selection_metrics.get(key, 0) + answer.metrics.get(key, 0)
              for key in ("model_requests", "inputTokens", "cacheReadTokens", "outputTokens", "totalTokens")}
    _save(output, "total-metrics.json", totals)
    if contract is not None and answer_points is not None:
        answer_status = "contract_and_point_links_present"
    elif contract is not None:
        answer_status = "contract_covered"
    elif answer_points is not None:
        answer_status = "point_links_present"
    else:
        answer_status = "answered"
    if contract is not None:
        coverage = execute(ANSWER_COVERAGE_MOTIF, {
            "contract": Evidence(contract, "preflighted_contract"),
            "citations": Evidence(citations, "verified_source_excerpts"),
            "claims": Evidence(answer.claims, "validated_model_claims"),
        })
        _save(output, "answer-coverage-gate.json", coverage.report())
        checks = coverage.state.get("answer_coverage")
        if checks is not None:
            _save(output, "answer-coverage.json", checks.value)
        if coverage.status != "completed":
            answer_status = "incomplete_answer"
            missing = [item["id"] for item in checks.value if item["status"] != "cited_in_claim"] if checks else []
            with (output / "answer.md").open("a", encoding="utf-8") as stream:
                stream.write("\n## 必答点尚未覆盖\n\n")
                stream.write("- " + ", ".join(missing) + "\n")
    if answer_points is not None:
        point_run = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": Evidence(answer_points, "preflighted_question_obligations"),
            "citations": Evidence(citations, "verified_source_excerpts"),
            "claims": Evidence(answer.claims, "validated_model_claims"),
            "uncertainties": Evidence(answer.uncertainties, "validated_model_uncertainties"),
        })
        _save(output, "question-coverage-gate.json", point_run.report())
        checks = point_run.state.get("point_coverage")
        if checks is not None:
            _save(output, "question-coverage.json", checks.value)
        if point_run.status != "completed":
            answer_status = "incomplete_answer"
            missing_points = [item for item in checks.value if item["status"] != "cited_claim"] if checks else []
            with (output / "answer.md").open("a", encoding="utf-8") as stream:
                stream.write("\n## 题目必答点尚未覆盖\n\n")
                for point in missing_points:
                    stream.write(f"- {point['id']}: {point['requirement']}\n")
    print(f"status={answer_status} subquestions={len(plan)} claims={len(answer.claims)} "
          f"rejected={len(answer.rejected_claims)} model_requests={totals['model_requests']} "
          f"input={totals['inputTokens']} cache_read={totals['cacheReadTokens']} output={totals['outputTokens']}")
    print(f"answer={output / 'answer.md'}")
    print(f"report={output}")
    return 0 if answer.claims and answer_status in {
        "answered", "contract_covered", "point_links_present", "contract_and_point_links_present"
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
