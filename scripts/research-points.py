#!/usr/bin/env python3
"""Research local sources one required answer point at a time, with bounded semantic calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.harness_semantic import (  # noqa: E402
    SemanticValidationError, call_bounded_prompt,
)
from src.adapters.dsh_client import require_budget_gate  # noqa: E402
from src.adapters.point_research_semantic import (  # noqa: E402
    prepare_point_queries, prepare_point_selection,
    prepare_point_synthesis,
)
from src.adapters.motif_research_handoff import (  # noqa: E402
    reenter_point_query_handoff, reenter_point_selection_handoff,
    reenter_point_synthesis_handoff, resolve_point_query_handoff,
    resolve_point_selection_handoff, resolve_point_synthesis_handoff,
)
from src.graph.runtime import Evidence, execute  # noqa: E402
from src.motif_core import StructureHandoffRequest  # noqa: E402
from src.motif_core.controller import MotifController  # noqa: E402
from src.motif_core.offline.library_builder import library_from_certified  # noqa: E402
from src.workflows.motif_point_selection import resolve_selection as resolve_motif_selection  # noqa: E402
from src.workflows.motif_research_incremental import (  # noqa: E402
    plan_incremental, remap_new_claims, render_change_log,
)
from src.workflows.motif_skill_evolution import (  # noqa: E402
    load_registry as load_motif_skill_registry, record_use as record_motif_skill_use,
    save_registry as save_motif_skill_registry, version as motif_skill_version,
)
from src.workflows.motif_research_sources import (  # noqa: E402
    SourceReadBlocked, collect as collect_motif_sources, verify_source_snapshot,
)
from src.workflows.research_numeric_ledger import (  # noqa: E402
    collect_numeric_ledger, render_numeric_ledger,
)
from src.workflows.research_cross_point import cross_point_dependencies  # noqa: E402
from src.workflows.research_synthesis_resume import prepare_synthesis_resume  # noqa: E402

from src.workflows.research_retrieval_tools import (  # noqa: E402
    RETRIEVAL_TOOL_CONTRACTS, ResearchRetrievalToolClient,
    export_retrieval_state, restore_retrieval_state,
)
from src.workflows.point_candidate_pool import candidate_fingerprint, candidate_pool  # noqa: E402
from src.workflows.research_brief import render_brief  # noqa: E402
from src.workflows.research import (  # noqa: E402
    ANSWER_POINT_PREFLIGHT_MOTIF, POINT_PAGE_PASSAGES_MOTIF,
    QUESTION_COVERAGE_MOTIF, RETRIEVE_MOTIF, ground_repair_terms,
)

USAGE_KEYS = ("model_requests", "inputTokens", "cacheReadTokens", "outputTokens", "totalTokens", "reasoningTokens")
SYNTHESIS_OUTPUT_CAP = 3000


def _save(directory: Path, name: str, value: object) -> None:
    (directory / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _totals(rows: list[dict[str, object]]) -> dict[str, int]:
    return {key: sum(int(row.get(key, 0) or 0) for row in rows) for key in USAGE_KEYS}


def _hash_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_scope(question: str, sources: list[str]) -> list[str]:
    folded = question.casefold()
    compact = re.sub(r"[^a-z0-9]", "", folded)
    chosen = []
    for source in sources:
        stem = Path(source).stem
        normalized = re.sub(r"[^a-z0-9]", "", stem.casefold())
        acronyms = re.findall(r"[A-Z]{2,}", stem)
        if (4 <= len(normalized) <= 30 and normalized in compact) or any(
            re.search(r"\b" + re.escape(acronym.casefold()) + r"\b", folded) for acronym in acronyms
        ):
            chosen.append(source)
    return chosen or sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--source-dir", type=Path, default=ROOT / "reference")
    parser.add_argument("--answer-points", type=Path, required=True,
                        help="JSON list of 1-8 obligations [{id, requirement}]")
    parser.add_argument("--plan-file", type=Path,
                        help="reuse a saved validated point query plan and skip the planning model call")
    parser.add_argument("--selection-file", type=Path,
                        help="offline selection bundle bound to this run's candidate fingerprint")
    parser.add_argument("--previous-source-state", type=Path,
                        help="reuse a previous Motif source state from this directory")
    parser.add_argument("--source-motif-artifact", type=Path,
                        help="run a trace-validated read-only Motif for source collection")
    parser.add_argument("--retrieval-motif-artifact", type=Path,
                        help="run a trace-validated cross-source retrieval Motif per answer point")
    parser.add_argument("--previous-retrieval-state", type=Path,
                        help="reuse exact-bound retrieval results from a prior Motif run")
    parser.add_argument("--previous-selection-state", type=Path,
                        help="reuse a Motif selection only when point and candidate signatures still match")
    parser.add_argument("--selection-skill-registry", type=Path,
                        help="use and record the active version of a local Motif selection skill registry")
    parser.add_argument("--previous-report-run", type=Path,
                        help="carry quote-checked prior claims into an incremental draft for human review")
    parser.add_argument("--synthesis-response-file", type=Path,
                        help="replay a saved raw synthesis response without a model call")
    parser.add_argument("--resume-synthesis-from", type=Path,
                        help="reuse validated source, plan and selection state after synthesis failure")
    parser.add_argument("--call-model", action="store_true", help="allow at most three paid model requests")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "point-research-runs" / stamp
    output.mkdir(parents=True, exist_ok=False)
    (output / "question.txt").write_text(args.question.strip() + "\n", encoding="utf-8")
    metrics: list[dict[str, object]] = []
    skill_registry = None
    signature_scope = "per_point"
    skill_version_id = None
    if args.selection_skill_registry:
        try:
            skill_registry = load_motif_skill_registry(args.selection_skill_registry.resolve(strict=True))
            active_skill = motif_skill_version(skill_registry)
            signature_scope = active_skill["signature_scope"]
            skill_version_id = active_skill["id"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(f"skill registry stopped: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

    def stop(stage: str, reason: str) -> int:
        _save(output, "total-metrics.json", _totals(metrics))
        _save(output, "status.json", {"status": "stopped", "stage": stage, "reason": reason})
        print(f"{stage} stopped: {reason}; report={output}", file=sys.stderr)
        return 2

    if args.call_model:
        try:
            require_budget_gate()
        except ValueError as exc:
            return stop("budget", str(exc))

    if args.resume_synthesis_from:
        if (args.plan_file or args.selection_file or args.previous_source_state
                or args.previous_retrieval_state or args.previous_selection_state
                or args.previous_report_run or args.synthesis_response_file):
            return stop("resume", "resume cannot be combined with other replay or incremental inputs")
        try:
            point_input = json.loads(args.answer_points.resolve(strict=True).read_text(encoding="utf-8"))
            replay = prepare_synthesis_resume(
                args.resume_synthesis_from, local_root=ROOT / ".local",
                output=output, question=args.question, answer_points=point_input)
            args.source_dir = replay["source_dir"]
            args.previous_source_state = replay["previous_source_state"]
            args.previous_retrieval_state = replay["previous_retrieval_state"]
            args.plan_file = replay["plan_file"]
            args.selection_file = replay["selection_file"]
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            return stop("resume", f"{type(exc).__name__}: {exc}")

    try:
        source_dir = args.source_dir.resolve(strict=True)
        point_data = json.loads(args.answer_points.resolve(strict=True).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return stop("input", f"{type(exc).__name__}: {exc}")
    try:
        previous_source = (json.loads(args.previous_source_state.resolve(strict=True).read_text(encoding="utf-8"))
                           if args.previous_source_state else None)
        source_motif_artifact = (
            json.loads(args.source_motif_artifact.resolve(strict=True).read_text(encoding="utf-8"))
            if args.source_motif_artifact else None)
        pages, source_state, source_events = collect_motif_sources(
            source_dir, previous_source, read_motif_artifact=source_motif_artifact)
    except SourceReadBlocked as exc:
        _save(output, "motif-failure-witness.json", exc.witness)
        return stop("source", str(exc))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return stop("source", f"{type(exc).__name__}: {exc}")
    _save(output, "motif-source-state.json", source_state)
    try:
        numeric_ledger = collect_numeric_ledger(pages)
        verify_source_snapshot(source_dir, source_state)
        _save(output, "verified-numeric-ledger.json", numeric_ledger)
        (output / "verified-numeric-ledger.md").write_text(
            render_numeric_ledger(numeric_ledger), encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return stop("source", f"numeric ledger: {type(exc).__name__}: {exc}")
    _save(output, "sources.json", [
        {"filename": row["binding"]["source"],
         "sha256": row["binding"]["sha256"]}
        for row in source_state["evidence"]
    ])
    _save(output, "source-trace.json", {"runtime": "migrated_motif_source_core",
                                        "revision": source_state["revision"],
                                        "resume_count": source_state["resume_count"],
                                        "events": source_events, "unique_pages": len(pages)})

    def invoke_harness(prompt: str, *, max_output_tokens: int,
                       max_prompt_characters: int) -> tuple[str, dict[str, object]]:
        verify_source_snapshot(source_dir, source_state)
        return call_bounded_prompt(prompt, root=ROOT,
                                   max_output_tokens=max_output_tokens,
                                   max_prompt_characters=max_prompt_characters)

    unique_pages = Evidence(pages, "motif_hash_bound_source_snapshot")
    source_dir_evidence = Evidence(str(source_dir), "user_input")
    point_run = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
        "answer_points": Evidence(point_data, "user_supplied_question_obligations"),
    })
    _save(output, "answer-points-preflight.json", point_run.report())
    if point_run.status != "completed":
        return stop("answer-points", point_run.gap.kind if point_run.gap else point_run.status)
    points = point_run.state["validated_answer_points"].value
    _save(output, "answer-points.json", points)
    scope = _source_scope(args.question, sorted({page["source"] for page in pages}))
    _save(output, "source-scope.json", scope)
    try:
        plan_prompt = prepare_point_queries(args.question, points, pages)
    except ValueError as exc:
        return stop("planning", str(exc))
    (output / "plan-prompt.txt").write_text(plan_prompt, encoding="utf-8")
    handoff_sources = [{"source": row["binding"]["source"], "sha256": row["binding"]["sha256"]}
                       for row in source_state["evidence"]]
    point_ids = [point["id"] for point in points]
    handoff = StructureHandoffRequest(
        handoff_type="need_semantic_resolution", source="point_query_planning",
        motif_id="research_point_planning", missing_slots=["queries_by_point"],
        available_state={
            "source_revision": source_state["revision"],
            "sources": handoff_sources,
            "point_ids": point_ids,
        },
        allowed_reentry={"mode": "same_motif", "candidates": point_ids},
        reason="literal source search terms for each required point need semantic planning",
        metadata={"prompt_sha256": hashlib.sha256(plan_prompt.encode("utf-8")).hexdigest(),
                  "max_output_tokens": 900, "max_model_requests": 3},
    )
    _save(output, "planning-handoff.json", handoff.to_dict())
    print(f"sources={len(scope)} pages={sum(p['source'] in scope for p in pages)} "
          f"points={len(points)} max_model_requests={3 - int(bool(args.plan_file)) - int(bool(args.selection_file)) - int(bool(args.synthesis_response_file))} "
          f"output_caps={'0' if args.plan_file else '900'}+{'0' if args.selection_file else '900'}+{'0' if args.synthesis_response_file else SYNTHESIS_OUTPUT_CAP} "
          f"plan_prompt_characters={len(plan_prompt)} "
          "selection_prompt_cap=14000 synthesis_prompt_cap=16000")
    if not args.call_model and not args.plan_file:
        _save(output, "status.json", {"status": "preview", "model_requests": 0})
        _save(output, "total-metrics.json", _totals(metrics))
        print(f"preview only; add --call-model to run; report={output}")
        return 0

    try:
        if args.plan_file:
            verify_source_snapshot(source_dir, source_state)
            saved = json.loads(args.plan_file.resolve(strict=True).read_text(encoding="utf-8"))
            replay = json.dumps({"queries": saved}, ensure_ascii=False)
            raw_plan, plan_metrics, resolution = resolve_point_query_handoff(
                handoff, prompt=plan_prompt, point_ids=point_ids, sources=handoff_sources,
                replay_response=replay)
            plan_metrics = _totals([])
        else:
            raw_plan, plan_metrics, resolution = resolve_point_query_handoff(
                handoff, prompt=plan_prompt, point_ids=point_ids, sources=handoff_sources,
                call_harness=lambda prompt: invoke_harness(
                    prompt, max_output_tokens=900, max_prompt_characters=12_000))
            metrics.append(plan_metrics)
        _save(output, "plan-metrics.json", plan_metrics)
        (output / "plan-response.txt").write_text(raw_plan, encoding="utf-8")
        _save(output, "planning-resolution.json", resolution.to_dict())
        verify_source_snapshot(source_dir, source_state)
        queries = reenter_point_query_handoff(
            handoff, resolution, prompt=plan_prompt,
            point_ids=point_ids, sources=handoff_sources)
        if resolution.metadata.get("query_normalization"):
            _save(output, "query-normalization.json",
                  resolution.metadata["query_normalization"])
    except SemanticValidationError as exc:
        metrics.append(exc.metrics)
        _save(output, "plan-metrics.json", exc.metrics)
        (output / "plan-response.txt").write_text(exc.raw_response, encoding="utf-8")
        return stop("planning", str(exc))
    except Exception as exc:
        return stop("planning", f"{type(exc).__name__}: {exc}")
    _save(output, "plan.json", queries)

    candidates: dict[str, dict[str, object]] = {}
    retrievals = []
    try:
        retrieval_artifact = (
            json.loads(args.retrieval_motif_artifact.resolve(strict=True).read_text(encoding="utf-8"))
            if args.retrieval_motif_artifact else None)
        retrieval_client = (ResearchRetrievalToolClient(source_dir, pages, source_state)
                            if retrieval_artifact is not None else None)
        if args.previous_retrieval_state and retrieval_artifact is None:
            raise ValueError("previous retrieval state needs a retrieval Motif artifact")
        previous_retrieval = (json.loads(args.previous_retrieval_state.resolve(strict=True).read_text(
            encoding="utf-8")) if args.previous_retrieval_state else None)
        retrieval_manager, retrieval_state_events = (
            restore_retrieval_state(previous_retrieval, client=retrieval_client,
                                    artifact=retrieval_artifact)
            if retrieval_artifact is not None else (None, []))
        if retrieval_artifact is not None:
            retrieval_controller = MotifController(
                library_from_certified([retrieval_artifact]),
                contracts=RETRIEVAL_TOOL_CONTRACTS,
                execute_tool=retrieval_client.execute,
                verify_current=retrieval_client.verify_current,
                is_read_only=lambda tool: tool in RETRIEVAL_TOOL_CONTRACTS,
                manager=retrieval_manager)
            _save(output, "retrieval-state-events.json", retrieval_state_events)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return stop("retrieval", f"{type(exc).__name__}: {exc}")
    for item in queries:
        point = next(point for point in points if point["id"] == item["point_id"])
        try:
            if retrieval_artifact is None:
                terms, changes = ground_repair_terms(item["terms"], pages, scope)
                run = execute(RETRIEVE_MOTIF, {
                    "unique_pages": unique_pages,
                    "source_dir": source_dir_evidence,
                    "question": Evidence(point["requirement"], "preflighted_answer_point"),
                    "terms": Evidence(terms, "source_grounded_point_terms"),
                    "source_allowlist": Evidence(scope, "named_source_scope"),
                    "per_source_limit": Evidence(12, "candidate_pool"),
                })
                evidence = run.state["verified_evidence"].value if run.gap and run.gap.kind == "semantic_synthesis" else []
                trace = run.report()
                if run.gap is None or run.gap.kind not in {"semantic_synthesis", "no_matching_evidence"}:
                    raise ValueError(f"retrieval stopped at {run.gap.kind if run.gap else run.status}")
                point_candidates = candidate_pool(evidence, min_sources=point.get("min_sources", 1))
            else:
                binding = {"source_dir": str(source_dir),
                           "point_id": point["id"], "question": point["requirement"],
                           "terms": item["terms"], "source_allowlist": scope,
                           "min_sources": point.get("min_sources", 1)}
                decision = retrieval_controller.execute_goal(
                    required_output="retrieve_point",
                    bindings={"snapshot_sources": {"source_dir": str(source_dir),
                                                   "input_version": retrieval_client.snapshot_digest},
                              "retrieve_point": binding},
                    input_version=retrieval_client.snapshot_digest)
                motif_run = decision.run
                if motif_run is None:
                    raise ValueError(f"retrieval Motif selection stopped: {decision.status}")
                if motif_run.status != "completed":
                    if motif_run.failure_witness is not None:
                        _save(output, f"retrieval-failure-{point['id']}.json",
                              motif_run.failure_witness)
                    if motif_run.handoff is not None:
                        _save(output, f"retrieval-handoff-{point['id']}.json",
                              motif_run.handoff.to_dict())
                    raise ValueError(f"compiled retrieval Motif {motif_run.status}")
                result = motif_run.outputs["retrieve_point"]
                terms, changes = result["grounded_terms"], result["grounding_changes"]
                evidence = result["evidence"]
                point_candidates = evidence
                trace = result["trace"]
                trace["compiled_motif"] = {
                    "motif_id": motif_run.motif_id,
                    "artifact_digest": retrieval_artifact["certified_digest"],
                    "input_version": motif_run.input_version,
                    "events": motif_run.events,
                }
        except Exception as exc:
            return stop("retrieval", f"{item['point_id']}: {type(exc).__name__}: {exc}")
        retrievals.append({"point_id": item["point_id"], "planned_terms": item["terms"],
                           "grounded_terms": terms, "grounding_changes": changes,
                           "trace": trace, "evidence": evidence})
        for index, row in enumerate(point_candidates, 1):
            candidates[f"{item['point_id']}-C{index}"] = {"point_id": item["point_id"], "evidence": row}
    _save(output, "point-retrievals.json", retrievals)
    if retrieval_artifact is not None:
        _save(output, "motif-retrieval-state.json", export_retrieval_state(
            retrieval_manager, client=retrieval_client,
            artifact=retrieval_artifact))
    _save(output, "selection-candidates.json", candidates)
    fingerprint = candidate_fingerprint(candidates)
    _save(output, "selection-bundle-template.json", {
        "candidate_sha256": fingerprint,
        "selections": [{"point_id": point["id"], "evidence_ids": []} for point in points],
    })
    if any(not any(row["point_id"] == point["id"] for row in candidates.values()) for point in points):
        return stop("retrieval", "one or more answer points have no verified candidate passage")

    previous_selection = None
    if args.previous_selection_state:
        try:
            previous_selection = json.loads(args.previous_selection_state.resolve(strict=True).read_text(encoding="utf-8"))
            reused_ids, _, reuse_events = resolve_motif_selection(
                source_dir, points, candidates, previous=previous_selection,
                signature_scope=signature_scope)
            _save(output, "selection-reuse-events.json", reuse_events)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return stop("selection", f"{type(exc).__name__}: {exc}")
    else:
        reused_ids = None
    reused_ids = reused_ids or {}
    missing_points = [point for point in points if point["id"] not in reused_ids]
    selection_scope_points = points if args.selection_file else missing_points
    try:
        selection_prompt = (prepare_point_selection(args.question, selection_scope_points, candidates)
                            if selection_scope_points else "")
    except ValueError as exc:
        return stop("selection", str(exc))
    (output / "selection-prompt.txt").write_text(selection_prompt, encoding="utf-8")
    selection_handoff = None
    if selection_scope_points:
        selection_point_ids = [point["id"] for point in selection_scope_points]
        allowed_candidate_ids = sorted(key for key, row in candidates.items()
                                       if row["point_id"] in set(selection_point_ids))
        selection_handoff = StructureHandoffRequest(
            handoff_type="need_semantic_resolution", source="point_evidence_selection",
            motif_id="research_point_selection", missing_slots=["selected_ids_by_point"],
            available_state={"point_ids": selection_point_ids, "sources": handoff_sources,
                             "candidate_sha256": fingerprint},
            allowed_reentry={"mode": "same_motif", "candidates": allowed_candidate_ids},
            reason="choose verified evidence for unresolved answer points",
            metadata={"prompt_sha256": hashlib.sha256(selection_prompt.encode()).hexdigest(),
                      "max_output_tokens": 900},
        )
        _save(output, "selection-handoff.json", selection_handoff.to_dict())
    if not args.call_model and not args.selection_file and missing_points:
        _save(output, "status.json", {"status": "preview", "model_requests": 0})
        _save(output, "total-metrics.json", _totals(metrics))
        print(f"candidate_passages={len(candidates)} reused_points={len(reused_ids)} "
              f"remaining_points={len(missing_points)} selection_prompt_characters={len(selection_prompt)}")
        print(f"preview only; add --call-model for selection and synthesis; report={output}")
        return 0
    try:
        if args.selection_file:
            verify_source_snapshot(source_dir, source_state)
            bundle = json.loads(args.selection_file.resolve(strict=True).read_text(encoding="utf-8"))
            if (not isinstance(bundle, dict) or set(bundle) != {"candidate_sha256", "selections"}
                    or bundle["candidate_sha256"] != fingerprint):
                raise ValueError("selection bundle does not match current candidate fingerprint")
            replay = json.dumps({"selections": bundle["selections"]}, ensure_ascii=False)
            raw_selection, _, resolution = resolve_point_selection_handoff(
                selection_handoff, prompt=selection_prompt, points=selection_scope_points,
                candidates=candidates, sources=handoff_sources, replay_response=replay)
            _save(output, "selection-metrics.json", _totals([]))
            _save(output, "selection-resolution.json", resolution.to_dict())
            verify_source_snapshot(source_dir, source_state)
            selected_ids = reenter_point_selection_handoff(
                selection_handoff, resolution, prompt=selection_prompt,
                points=selection_scope_points, candidates=candidates, sources=handoff_sources)
        elif not missing_points:
            selected_ids = reused_ids
            raw_selection = json.dumps({"selections": [
                {"point_id": point_id, "evidence_ids": keys} for point_id, keys in selected_ids.items()
            ]}, ensure_ascii=False)
            _save(output, "selection-metrics.json", _totals([]))
        else:
            raw_selection, selection_metrics, resolution = resolve_point_selection_handoff(
                selection_handoff, prompt=selection_prompt, points=selection_scope_points,
                candidates=candidates, sources=handoff_sources,
                call_harness=lambda prompt: invoke_harness(
                    prompt, max_output_tokens=900, max_prompt_characters=14_000))
            metrics.append(selection_metrics)
            _save(output, "selection-metrics.json", selection_metrics)
            _save(output, "selection-resolution.json", resolution.to_dict())
            verify_source_snapshot(source_dir, source_state)
            new_ids = reenter_point_selection_handoff(
                selection_handoff, resolution, prompt=selection_prompt,
                points=selection_scope_points, candidates=candidates, sources=handoff_sources)
            selected_ids = {**reused_ids, **new_ids}
            if resolution.metadata["alias_normalization"]:
                _save(output, "selection-alias-normalization.json",
                      resolution.metadata["alias_normalization"])
        (output / "selection-response.txt").write_text(raw_selection, encoding="utf-8")
    except SemanticValidationError as exc:
        metrics.append(exc.metrics)
        _save(output, "selection-metrics.json", exc.metrics)
        (output / "selection-response.txt").write_text(exc.raw_response, encoding="utf-8")
        return stop("selection", str(exc))
    except Exception as exc:
        return stop("selection", f"{type(exc).__name__}: {exc}")
    try:
        selected_ids, selection_state, selection_events = resolve_motif_selection(
            source_dir, points, candidates, selected_ids=selected_ids, previous=previous_selection,
            signature_scope=signature_scope)
    except (ValueError, KeyError, TypeError) as exc:
        return stop("selection-state", f"{type(exc).__name__}: {exc}")
    _save(output, "motif-selection-state.json", selection_state)
    _save(output, "motif-selection-events.json", selection_events)
    if skill_registry is not None and skill_version_id is not None:
        try:
            skill_use = record_motif_skill_use(skill_registry, run_id=stamp,
                                               version_id=skill_version_id,
                                               executed_point_ids=list(selected_ids))
            save_motif_skill_registry(args.selection_skill_registry, skill_registry)
            _save(output, "motif-skill-use.json", skill_use)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return stop("skill-use", f"{type(exc).__name__}: {exc}")
    _save(output, "selection.json", selected_ids)
    try:
        verify_source_snapshot(source_dir, source_state)
    except (OSError, ValueError) as exc:
        return stop("source-revalidation", str(exc))
    selected = {point_id: [candidates[key]["evidence"] for key in keys]
                for point_id, keys in selected_ids.items()}
    _save(output, "selected-evidence-by-point.json", selected)
    passages_run = execute(POINT_PAGE_PASSAGES_MOTIF, {
        "validated_answer_points": point_run.state["validated_answer_points"],
        "selected_evidence_by_point": Evidence(selected, "model_selected_verified_pages"),
        "unique_pages": unique_pages,
        "source_dir": source_dir_evidence,
    })
    _save(output, "point-passages-trace.json", passages_run.report())
    if passages_run.status != "completed":
        return stop("passage-packaging", passages_run.gap.kind if passages_run.gap else passages_run.status)
    point_passages = passages_run.state["point_passages"].value
    _save(output, "point-passages.json", point_passages)
    _save(output, "passage-packaging.json", passages_run.state["passage_packaging"].value)
    try:
        full_synthesis_prompt, citations, point_citations = prepare_point_synthesis(
            args.question, points, point_passages,
            max_prompt_characters=None if args.previous_report_run else 16_000,
            allow_verified_cross_point_reuse=True)
    except ValueError as exc:
        return stop("synthesis", str(exc))
    _save(output, "selected-evidence.json", citations)
    incremental = None
    dirty_points = points
    local_citations = citations
    local_point_citations = point_citations
    if args.previous_report_run:
        try:
            incremental = plan_incremental(
                args.previous_report_run, question=args.question, points=points,
                current_selection_state=selection_state, current_source_state=source_state,
                current_citations=citations,
                point_citations=point_citations)
            _save(output, "incremental-plan.json", incremental)
            (output / "change-log.md").write_text(render_change_log(incremental), encoding="utf-8")
            dirty_points = [point for point in points if point["id"] in incremental["dirty_points"]]
            if dirty_points:
                synthesis_prompt, local_citations, local_point_citations = prepare_point_synthesis(
                    args.question, dirty_points,
                    {point["id"]: point_passages[point["id"]] for point in dirty_points},
                    allow_verified_cross_point_reuse=True)
            else:
                synthesis_prompt = ""
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return stop("incremental-plan", f"{type(exc).__name__}: {exc}")
    else:
        synthesis_prompt = full_synthesis_prompt
    (output / "synthesis-prompt.txt").write_text(synthesis_prompt, encoding="utf-8")
    synthesis_handoff = None
    if dirty_points:
        synthesis_point_ids = [point["id"] for point in dirty_points]
        synthesis_handoff = StructureHandoffRequest(
            handoff_type="need_semantic_resolution", source="point_evidence_synthesis",
            motif_id="research_point_synthesis", missing_slots=["claims_by_point"],
            available_state={
                "point_ids": synthesis_point_ids, "sources": handoff_sources,
                "citations_sha256": _hash_json(local_citations),
                "point_citations_sha256": _hash_json(
                    {key: sorted(value) for key, value in local_point_citations.items()}),
            },
            allowed_reentry={"mode": "same_motif", "candidates": synthesis_point_ids},
            reason="synthesize bounded claims from verified current evidence",
            metadata={"prompt_sha256": hashlib.sha256(synthesis_prompt.encode()).hexdigest(),
                      "max_output_tokens": SYNTHESIS_OUTPUT_CAP,
                      "allow_cross_point_reuse": True},
        )
        _save(output, "synthesis-handoff.json", synthesis_handoff.to_dict())
    if not args.call_model and not args.synthesis_response_file and dirty_points:
        _save(output, "status.json", {"status": "preview", "model_requests": 0})
        _save(output, "total-metrics.json", _totals(metrics))
        if incremental is not None:
            preview = render_brief(args.question, points, incremental["carried_claims"], [], citations)
            preview += "\n> 增量草稿：沿用结论尚待人工复核；未覆盖问题需重新综合。\n"
            (output / "incremental-preview.md").write_text(preview, encoding="utf-8")
        print(f"verified_passages={len(citations)} carried_points={len(points) - len(dirty_points)} "
              f"remaining_points={len(dirty_points)} synthesis_prompt_characters={len(synthesis_prompt)}")
        print(f"preview only; add --call-model for synthesis; report={output}")
        return 0
    if dirty_points:
        try:
            if args.synthesis_response_file:
                verify_source_snapshot(source_dir, source_state)
                replay = args.synthesis_response_file.resolve(strict=True).read_text(encoding="utf-8")
                raw_synthesis, synthesis_metrics, synthesis_resolution = resolve_point_synthesis_handoff(
                    synthesis_handoff, prompt=synthesis_prompt,
                    point_ids=synthesis_point_ids, citations=local_citations,
                    point_citations=local_point_citations, sources=handoff_sources,
                    replay_response=replay)
                synthesis_metrics = _totals([])
            else:
                raw_synthesis, synthesis_metrics, synthesis_resolution = resolve_point_synthesis_handoff(
                    synthesis_handoff, prompt=synthesis_prompt,
                    point_ids=synthesis_point_ids, citations=local_citations,
                    point_citations=local_point_citations, sources=handoff_sources,
                    call_harness=lambda prompt: invoke_harness(
                        prompt, max_output_tokens=SYNTHESIS_OUTPUT_CAP,
                        max_prompt_characters=16_000))
                metrics.append(synthesis_metrics)
            (output / "synthesis-response.txt").write_text(raw_synthesis, encoding="utf-8")
            _save(output, "synthesis-metrics.json", synthesis_metrics)
            _save(output, "synthesis-resolution.json", synthesis_resolution.to_dict())
            verify_source_snapshot(source_dir, source_state)
            new_claims, uncertainties, rejected_claims = reenter_point_synthesis_handoff(
                synthesis_handoff, synthesis_resolution, raw_response=raw_synthesis,
                prompt=synthesis_prompt, point_ids=synthesis_point_ids,
                citations=local_citations, point_citations=local_point_citations,
                sources=handoff_sources)
            new_claims = (remap_new_claims(new_claims, local_citations, citations, point_citations)
                          if incremental is not None else new_claims)
        except SemanticValidationError as exc:
            metrics.append(exc.metrics)
            _save(output, "synthesis-metrics.json", exc.metrics)
            (output / "synthesis-response.txt").write_text(exc.raw_response, encoding="utf-8")
            return stop("synthesis", str(exc))
        except Exception as exc:
            return stop("synthesis", f"{type(exc).__name__}: {exc}")
        claims = (incremental["carried_claims"] if incremental else []) + new_claims
    else:
        _save(output, "synthesis-metrics.json", _totals([]))
        _save(output, "synthesis-reuse.json", {"model_requests": 0,
                                               "parent_run": incremental["parent_run"]})
        claims = incremental["carried_claims"]
        uncertainties = []
        rejected_claims = []
    if len(claims) > 12:
        return stop("synthesis", "combined incremental report exceeds 12-claim limit")
    try:
        _save(output, "cross-point-dependencies.json",
              cross_point_dependencies(claims, citations, point_citations))
    except (ValueError, KeyError, TypeError) as exc:
        return stop("synthesis-dependencies", str(exc))
    _save(output, "claims.json", claims)
    _save(output, "uncertainties.json", uncertainties)
    _save(output, "rejected-claims.json", rejected_claims)

    coverage = execute(QUESTION_COVERAGE_MOTIF, {
        "validated_answer_points": Evidence(points, "preflighted_question_obligations"),
        "citations": Evidence(citations, "verified_point_evidence"),
        "claims": Evidence(claims, "quote_checked_current_and_reused_claims"),
        "uncertainties": Evidence(uncertainties, "validated_model_uncertainties"),
    })
    _save(output, "question-coverage-gate.json", coverage.report())
    checks = coverage.state.get("point_coverage")
    if checks is not None:
        _save(output, "question-coverage.json", checks.value)
    status = ("incremental_draft" if incremental and incremental["review_required"] else
              "point_links_present") if coverage.status == "completed" and claims else "incomplete_answer"
    markdown = render_brief(args.question, points, claims, uncertainties, citations)
    if numeric_ledger["sources"]:
        markdown += ("\n> 可复算的原始数值见同目录 `verified-numeric-ledger.md`。"
                     "该账本不替模型结论背书。\n")
    if incremental and incremental["review_required"]:
        markdown += "\n> 增量更新：沿用的结论已重新核对引文与来源哈希；新资料可能提出冲突，仍需人工复核。\n"
    if status == "incomplete_answer" and checks is not None:
        markdown += "\n## 题目必答点尚未覆盖\n\n"
        markdown += "\n".join(f"- {row['id']}: {row['requirement']}" for row in checks.value
                              if row["status"] not in {"cited_claim", "abstention_pending_review"}) + "\n"
    (output / "answer.md").write_text(markdown, encoding="utf-8")
    _save(output, "total-metrics.json", _totals(metrics))
    _save(output, "status.json", {"status": status,
                                  "note": "Structural links only; human entailment review required"})
    print(f"status={status} points={len(points)} claims={len(claims)} "
          f"rejected={len(rejected_claims)} model_requests={_totals(metrics)['model_requests']}")
    print(f"answer={output / 'answer.md'}")
    print(f"report={output}")
    return 0 if status in {"point_links_present", "incremental_draft"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
