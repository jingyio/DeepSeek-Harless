#!/usr/bin/env python3
"""Try one bounded, source-verified repair of a saved incomplete research run."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.harness_semantic import (  # noqa: E402
    SemanticValidationError, answer_bounded_evidence_prompt, call_bounded_prompt, render_answer,
)
from src.adapters.dsh_client import require_budget_gate  # noqa: E402
from src.adapters.research_repair_semantic import (  # noqa: E402
    parse_repair_queries, prepare_repair_answer, prepare_repair_queries,
)
from src.graph.runtime import Evidence, execute  # noqa: E402
from src.workflows.research_repair_snapshot import verify_repair_source_trace  # noqa: E402
from src.workflows.research_repair_reuse import rebind_accepted_evidence  # noqa: E402
from src.workflows.research import (  # noqa: E402
    ANSWER_POINT_PREFLIGHT_MOTIF, QUESTION_COVERAGE_MOTIF, RESEARCH_REPAIR_MERGE_MOTIF,
    RETRIEVE_MOTIF, SOURCE_MOTIF, ground_repair_terms,
)

USAGE_KEYS = ("model_requests", "inputTokens", "cacheReadTokens", "outputTokens", "totalTokens")


def _read(directory: Path, name: str):
    return json.loads((directory / name).read_text(encoding="utf-8"))


def _save(directory: Path, name: str, value: object) -> None:
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _question_from_run(directory: Path) -> str:
    prompt = (directory / "plan-prompt.txt").read_text(encoding="utf-8")
    marker = "Main question: "
    if prompt.count(marker) != 1:
        raise ValueError("original question cannot be recovered from planning prompt")
    tail = prompt.split(marker, 1)[1]
    for terminator in ("\nRequired points:", "\n\nSource catalog:"):
        if terminator in tail:
            return tail.split(terminator, 1)[0]
    raise ValueError("original question cannot be recovered from planning prompt")


def _sum_usage(*items: dict[str, object]) -> dict[str, int]:
    return {key: sum(int(item.get(key, 0) or 0) for item in items) for key in USAGE_KEYS}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path,
                        help="a saved incomplete deep-research-runs or point-research-runs run")
    parser.add_argument("--source-dir", required=True, type=Path, help="same local source directory used before")
    parser.add_argument("--call-model", action="store_true", help="allow at most two paid repair calls")
    parser.add_argument("--reuse-accepted-evidence", action="store_true",
                        help="compose only verified evidence from already accepted points; one paid call")
    args = parser.parse_args()
    if args.call_model:
        try:
            require_budget_gate()
        except ValueError as exc:
            parser.error(str(exc))
    prior = args.run_dir.resolve(strict=True)
    deep_parent = prior.is_relative_to((ROOT / ".local" / "deep-research-runs").resolve())
    point_parent = prior.is_relative_to((ROOT / ".local" / "point-research-runs").resolve())
    if not deep_parent and not point_parent:
        parser.error("repair parent must be a private research run")
    source_dir = args.source_dir.resolve(strict=True)
    try:
        question = _question_from_run(prior)
        points_raw = _read(prior, "answer-points.json")
        previous_checks = _read(prior, "question-coverage.json")
        old_claims = _read(prior, "claims.json")
        old_citations = _read(prior, "selected-evidence.json")
        old_source_trace = (_read(prior, "source-trace.json") if deep_parent else
                            _read(prior, "motif-source-state.json"))
        prior_metrics = _read(prior, "total-metrics.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(f"prior run is not a readable answer-point run: {exc}")
    preflight = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
        "answer_points": Evidence(points_raw, "saved_run"),
    })
    if preflight.status != "completed":
        parser.error("saved answer points failed validation")
    points = preflight.state["validated_answer_points"].value
    point_map = {point["id"]: point for point in points}
    missing_ids = {row["id"] for row in previous_checks if row["status"] != "cited_claim"}
    if not missing_ids or not missing_ids <= point_map.keys():
        parser.error("prior run has no valid missing question point")
    missing = [{**point_map[point_id], "prior_status": next(
        row["status"] for row in previous_checks if row["id"] == point_id
    )} for point_id in sorted(missing_ids)]
    if point_parent:
        from src.workflows.motif_research_sources import collect
        try:
            pages, _, _ = collect(source_dir)
        except (OSError, ValueError, TypeError) as exc:
            parser.error(f"source collection stopped: {exc}")
        pages_evidence = Evidence(pages, "current_source_pages")
        directory_evidence = Evidence(str(source_dir), "user_input")
    else:
        sources = execute(SOURCE_MOTIF, {"source_dir": Evidence(str(source_dir), "user_input")})
        if sources.status != "completed":
            parser.error(f"source collection stopped: {sources.gap.kind if sources.gap else sources.status}")
        pages_evidence = sources.state["unique_pages"]
        directory_evidence = sources.state["source_dir"]
        pages = pages_evidence.value
    try:
        if deep_parent:
            verify_repair_source_trace(old_source_trace, source_dir, pages)
        else:
            from src.workflows.motif_research_sources import verify_source_snapshot
            verify_source_snapshot(source_dir, old_source_trace)
    except ValueError as exc:
        parser.error(str(exc))
    lookup = {(row["source"], row["page"]): row for row in pages}
    for row in old_citations.values():
        page = lookup.get((row["source"], row["page"]))
        if (page is None or row["source_sha256"] != page["source_sha256"]
                or row["page_sha256"] != page["page_sha256"]):
            parser.error("source file or extracted page changed since the prior run")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "research-repairs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    _save(output, "parent.json", {"run": str(prior), "question": question,
                                  "missing_points": missing, "source_dir": str(source_dir)})
    accepted_context = None
    if args.reuse_accepted_evidence:
        try:
            citations, accepted_context, edges = rebind_accepted_evidence(
                old_claims, old_citations, missing_ids)
            prompt = prepare_repair_answer(question, missing, citations, accepted_context)
        except (ValueError, KeyError, TypeError) as exc:
            parser.error(f"bounded evidence reuse stopped: {exc}")
        query_metrics = {key: 0 for key in USAGE_KEYS}
        _save(output, "reuse-edges.json", edges)
        _save(output, "repair-evidence.json", citations)
        print(f"missing={','.join(sorted(missing_ids))} reused_claims={len(accepted_context)} "
              f"reused_citations={len(citations)} repair_cap=1200 output tokens")
        if not args.call_model:
            (output / "repair-prompt.txt").write_text(prompt, encoding="utf-8")
            print(f"preview only; add --call-model for one repair request; report={output}")
            return 0
    else:
        query_prompt = prepare_repair_queries(question, missing, sorted({row["source"] for row in pages}))
        (output / "query-prompt.txt").write_text(query_prompt, encoding="utf-8")
        print(f"missing={','.join(sorted(missing_ids))} query_prompt_characters={len(query_prompt)} "
              f"repair_cap=500+1200 output tokens")
        if not args.call_model:
            print(f"preview only; add --call-model for at most two repair requests; report={output}")
            return 0
        try:
            query_raw, query_metrics = call_bounded_prompt(query_prompt, root=ROOT, max_output_tokens=500)
            (output / "query-response.txt").write_text(query_raw, encoding="utf-8")
            _save(output, "query-metrics.json", query_metrics)
            queries = parse_repair_queries(query_raw, missing_ids)
        except SemanticValidationError as exc:
            _save(output, "query-metrics.json", exc.metrics)
            (output / "query-response.txt").write_text(exc.raw_response, encoding="utf-8")
            print(f"repair query rejected: {exc}; report={output}", file=sys.stderr)
            return 2
        except Exception as exc:
            (output / "query-error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
            print(f"repair query failed: {type(exc).__name__}; report={output}", file=sys.stderr)
            return 2
        _save(output, "queries.json", queries)
        all_sources = sorted({row["source"] for row in pages})
        citations: dict[str, dict[str, object]] = {}
        retrieval: list[dict[str, object]] = []
        for query in queries:
            try:
                terms, changes = ground_repair_terms(query["terms"], pages, all_sources)
            except Exception as exc:
                _save(output, "retrieval-error.json", {"query": query, "error": f"{type(exc).__name__}: {exc}"})
                print(f"repair query grounding stopped: {type(exc).__name__}; report={output}")
                return 2
            run = execute(RETRIEVE_MOTIF, {
                "unique_pages": pages_evidence,
                "source_dir": directory_evidence,
                "question": Evidence(point_map[query["point_id"]]["requirement"], "saved_task_obligation"),
                "terms": Evidence(terms, "grounded_repair_terms"),
                "source_allowlist": Evidence(all_sources, "same_source_scope"),
                "per_source_limit": Evidence(12, "repair_candidate_pool"),
            })
            if run.gap is None or run.gap.kind != "semantic_synthesis":
                _save(output, "retrieval-error.json", {"query": query, "trace": run.report()})
                print(f"repair retrieval stopped: {run.gap.kind if run.gap else run.status}; report={output}")
                return 2
            chosen = run.state["verified_evidence"].value[:3]
            if not chosen:
                print(f"repair has no verified evidence for {query['point_id']}; report={output}")
                return 2
            ids: list[str] = []
            for row in chosen:
                label = f"R{len(citations) + 1}"
                citations[label] = row
                ids.append(label)
            retrieval.append({"point_id": query["point_id"], "terms": terms,
                              "grounding_changes": changes, "evidence_ids": ids,
                              "trace": run.report()})
        _save(output, "retrieval.json", retrieval)
        _save(output, "repair-evidence.json", citations)
        prompt = prepare_repair_answer(question, missing, citations)
    (output / "repair-prompt.txt").write_text(prompt, encoding="utf-8")
    try:
        repaired = answer_bounded_evidence_prompt(prompt, citations, root=ROOT,
                                                   max_output_tokens=1200, point_ids=missing_ids)
    except SemanticValidationError as exc:
        _save(output, "repair-metrics.json", exc.metrics)
        (output / "repair-response.txt").write_text(exc.raw_response, encoding="utf-8")
        _save(output, "cumulative-metrics.json", _sum_usage(prior_metrics, query_metrics, exc.metrics))
        print(f"repair answer rejected: {exc}; report={output}", file=sys.stderr)
        return 2
    except Exception as exc:
        (output / "repair-error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        print(f"repair answer failed: {type(exc).__name__}; report={output}", file=sys.stderr)
        return 2
    (output / "repair-response.txt").write_text(repaired.raw_response, encoding="utf-8")
    _save(output, "repair-metrics.json", repaired.metrics)
    _save(output, "repair-claims.json", repaired.claims)
    _save(output, "repair-uncertainties.json", repaired.uncertainties)
    _save(output, "repair-rejected-claims.json", repaired.rejected_claims)
    merged = execute(RESEARCH_REPAIR_MERGE_MOTIF, {
        "validated_answer_points": Evidence(points, "saved_task_obligations"),
        "missing_ids": Evidence(sorted(missing_ids), "saved_coverage_gap"),
        "original_claims": Evidence(old_claims, "saved_validated_claims"),
        "original_citations": Evidence(old_citations, "same_hash_verified_sources"),
        "repair_claims": Evidence(repaired.claims, "validated_repair_claims"),
        "repair_citations": Evidence(citations, "verified_repair_excerpts"),
        "repair_uncertainties": Evidence(repaired.uncertainties, "validated_repair_uncertainties"),
    })
    _save(output, "merge-trace.json", merged.report())
    if merged.status != "completed":
        print(f"repair merge stopped: {merged.gap.kind if merged.gap else merged.status}; report={output}")
        return 2
    claims = merged.state["merged_claims"].value
    all_citations = merged.state["merged_citations"].value
    uncertainties = merged.state["merged_uncertainties"].value
    coverage = execute(QUESTION_COVERAGE_MOTIF, {
        "validated_answer_points": Evidence(points, "saved_task_obligations"),
        "claims": Evidence(claims, "merged_validated_claims"),
        "citations": Evidence(all_citations, "same_hash_verified_sources"),
        "uncertainties": Evidence(uncertainties, "validated_repair_uncertainties"),
    })
    _save(output, "coverage-gate.json", coverage.report())
    checks = coverage.state.get("point_coverage")
    if checks:
        _save(output, "coverage.json", checks.value)
    answer = render_answer(claims, uncertainties, all_citations)
    if coverage.status != "completed" and checks:
        answer += "\n## 修复后仍未覆盖\n\n"
        answer += "".join(f"- {row['id']}: {row['requirement']}\n" for row in checks.value
                          if row["status"] != "cited_claim")
    (output / "answer.md").write_text(answer, encoding="utf-8")
    _save(output, "merged-claims.json", claims)
    _save(output, "cumulative-metrics.json", _sum_usage(prior_metrics, query_metrics, repaired.metrics))
    status = "point_links_present" if coverage.status == "completed" else "incomplete_answer"
    print(f"status={status} repaired_claims={len(repaired.claims)} "
          f"remaining={sum(row['status'] != 'cited_claim' for row in checks.value) if checks else '?'} "
          f"added_requests={query_metrics['model_requests'] + repaired.metrics['model_requests']}; "
          f"answer={output / 'answer.md'} report={output}")
    return 0 if status == "point_links_present" else 2


if __name__ == "__main__":
    raise SystemExit(main())
