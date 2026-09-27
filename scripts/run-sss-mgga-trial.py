#!/usr/bin/env python3
"""Same frozen MGGA development task through compiled SSS read Motifs.

Preview is free. A paid run requires the plain budgeted DSH route, keeping
Distil out of this arm while both arms share the upstream cost gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / ".local" / "benchmarks" / "research-weekly-loop" / "native-dsh-baseline-preview"
FROZEN = ROOT / ".local" / "distil-sss" / "mgga-stage-a" / "sources"
POINTS = ROOT / ".local" / "distil-sss" / "mgga-stage-a" / "answer-points.json"
SOURCE_MOTIF = ROOT / ".local" / "motifs" / "research-source-read.json"
RETRIEVAL_MOTIF = ROOT / ".local" / "motifs" / "research-retrieval.json"
QUESTION = "MGGA / MotifAgent 终稿 TauBench Figure 7 的 ReAct 柱对应哪组原始运行，终稿基线表应如何标注和限定主张？"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(command: list[str], *, output: Path, name: str) -> tuple[int, Path | None]:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    (output / f"{name}-stdout.txt").write_text(result.stdout)
    (output / f"{name}-stderr.txt").write_text(result.stderr)
    found = re.search(r"report=(\S+)", result.stdout + "\n" + result.stderr)
    return result.returncode, Path(found.group(1)) if found else None


def plan_reuse_decision(candidates: dict, coverage: list[dict],
                        *, new_source: str) -> dict:
    """Reuse old queries only if they retrieve the newly added source where needed."""
    unresolved = [row["id"] for row in coverage if row["status"] != "cited_claim"]
    hits = sorted({row["point_id"] for row in candidates.values()
                   if row["evidence"]["source"] == new_source})
    allowed = bool(hits) and all(point_id in hits for point_id in unresolved)
    return {"reuse": allowed, "new_source": new_source,
            "unresolved_points": unresolved, "new_source_candidate_points": hits,
            "reason": "new source reached every unresolved point" if allowed else
                      "new source did not reach every unresolved point"}


def should_fallback_plan_reuse(status: dict) -> bool:
    """Only structural failures trigger a fresh query plan, not a weak answer."""
    return (status.get("status") == "stopped" and status.get("stage") in {
        "retrieval", "selection", "selection-state", "passage-packaging"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--answer-points", type=Path, default=POINTS,
                        help="frozen obligation file; record its hash for development iterations")
    parser.add_argument("--scenario-dir", type=Path,
                        help="private frozen two-stage MGGA scenario under .local")
    parser.add_argument("--reuse-stage-a-plan", action="store_true",
                        help="preview old queries against the new source and reuse only when guarded")
    args = parser.parse_args()
    scenario = None
    frozen = FROZEN
    if args.scenario_dir:
        scenario_dir = args.scenario_dir.resolve(strict=True)
        if not scenario_dir.is_relative_to(ROOT / ".local"):
            parser.error("scenario must stay under .local")
        scenario = json.loads((scenario_dir / "scenario.json").read_text())
        frozen = scenario_dir / "sources"
        answer_points = (scenario_dir / "answer-points.json").resolve(strict=True)
        if digest(answer_points) != scenario["answer_points_sha256"]:
            parser.error("scenario answer points changed")
        prior = scenario["stage_a_source_sha256"]
        review = Path(scenario["stage_b_release_path"]).resolve(strict=True)
        expected_review = scenario["stage_b_release_sha256"]
        question = scenario["question"]
    else:
        answer_points = args.answer_points.resolve(strict=True)
        prior = {row["name"]: row["sha256"] for row in
                 json.loads((BASE / "source-manifest.json").read_text())}
        review = BASE / "workspace" / "sources" / "review_2026-09-21.md"
        release = json.loads((BASE / "stage-b-release.json").read_text())
        expected_review = release["stage_b_event_sha256"]
        question = QUESTION
    if not answer_points.is_relative_to(ROOT / ".local"):
        parser.error("private trial obligations must stay under .local")
    if {path.name: digest(path) for path in frozen.iterdir() if path.is_file()} != prior:
        parser.error("stage A source snapshot does not match the native DSH baseline")
    if not SOURCE_MOTIF.is_file() or not RETRIEVAL_MOTIF.is_file():
        parser.error("compiled Motif artifacts are missing")
    if digest(review) != expected_review:
        parser.error("stage B event hash changed")
    if args.call_model and (os.environ.get("SSS_BUDGET_GATE_ACTIVE") != "1"
                            or os.environ.get("SSS_CONTEXT_MODE") != "plain"):
        parser.error("paid SSS arm requires run-distil-dsh.py --mode plain --budget-usd ...")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "distil-sss" / "sss-runs" / stamp
    sources = output / "sources"
    sources.mkdir(parents=True, exist_ok=False)
    for path in frozen.iterdir():
        shutil.copy2(path, sources / path.name)
    (output / "trial-input.json").write_text(json.dumps({
        "question": question, "answer_points": str(answer_points),
        "answer_points_sha256": digest(answer_points), "source_sha256": prior,
        "stage_b_sha256": digest(review),
        "scenario_sha256": digest(args.scenario_dir.resolve() / "scenario.json")
        if scenario is not None else None,
        "development_diagnostic": True,
    }, ensure_ascii=False, indent=2))
    command = [sys.executable, str(ROOT / "scripts" / "research-points.py"), question,
               "--source-dir", str(sources), "--answer-points", str(answer_points),
               "--source-motif-artifact", str(SOURCE_MOTIF),
               "--retrieval-motif-artifact", str(RETRIEVAL_MOTIF)]
    started = time.monotonic()
    preview_code, preview_dir = invoke(command, output=output, name="preview")
    if preview_code != 0 or preview_dir is None:
        print(f"SSS preview stopped: {output}", file=sys.stderr)
        return 2
    print(f"preview={preview_dir} source_hashes_match=True compiled_source_motif=True")
    if not args.call_model:
        return 0
    code_a, run_a = invoke(command + ["--call-model"], output=output, name="stage-a")
    if run_a is None or not (run_a / "status.json").is_file():
        print(f"stage A did not save a report: {output}", file=sys.stderr)
        return 2
    status_a = json.loads((run_a / "status.json").read_text()).get("status")
    if status_a not in {"point_links_present", "incomplete_answer"}:
        print(f"stage A stopped at {status_a}: {run_a}", file=sys.stderr)
        return 2
    shutil.copy2(review, sources / review.name)
    if digest(sources / review.name) != digest(review):
        raise RuntimeError("stage B release copy changed")
    extras = ["--previous-source-state", str(run_a / "motif-source-state.json"),
              "--previous-selection-state", str(run_a / "motif-selection-state.json"),
              "--previous-report-run", str(run_a)]
    retrieval = run_a / "motif-retrieval-state.json"
    if retrieval.is_file():
        extras += ["--previous-retrieval-state", str(retrieval)]
    plan_reuse = {"reuse": False, "reason": "not requested"}
    if args.reuse_stage_a_plan:
        plan_file = run_a / "plan.json"
        coverage_file = run_a / "question-coverage.json"
        if plan_file.is_file() and coverage_file.is_file():
            preview_code_b, preview_run_b = invoke(
                command + extras + ["--plan-file", str(plan_file)],
                output=output, name="stage-b-plan-reuse-preview")
            candidates_file = (preview_run_b / "selection-candidates.json"
                               if preview_run_b else None)
            if preview_code_b == 0 and candidates_file and candidates_file.is_file():
                plan_reuse = plan_reuse_decision(
                    json.loads(candidates_file.read_text()),
                    json.loads(coverage_file.read_text()), new_source=review.name)
                plan_reuse["preview_run"] = str(preview_run_b)
                if plan_reuse["reuse"]:
                    extras += ["--plan-file", str(plan_file)]
            else:
                plan_reuse = {"reuse": False, "reason": "plan reuse preview failed"}
        else:
            plan_reuse = {"reuse": False, "reason": "previous plan or coverage unavailable"}
    (output / "plan-reuse-decision.json").write_text(
        json.dumps(plan_reuse, ensure_ascii=False, indent=2))
    code_b, run_b = invoke(command + extras + ["--call-model"], output=output, name="stage-b")
    if plan_reuse["reuse"] and code_b != 0 and run_b and (run_b / "status.json").is_file():
        failed_status = json.loads((run_b / "status.json").read_text())
        if should_fallback_plan_reuse(failed_status):
            plan_reuse["fallback_from"] = str(run_b)
            plan_reuse["fallback_reason"] = failed_status
            if extras[-2:] != ["--plan-file", str(plan_file)]:
                raise RuntimeError("plan reuse arguments changed before fallback")
            fresh_extras = extras[:-2]
            code_b, run_b = invoke(command + fresh_extras + ["--call-model"],
                                   output=output, name="stage-b-plan-fallback")
    (output / "plan-reuse-decision.json").write_text(
        json.dumps(plan_reuse, ensure_ascii=False, indent=2))
    metrics = {
        "stage_a": str(run_a), "stage_a_status": status_a, "stage_a_exit_code": code_a,
        "stage_b": str(run_b) if run_b else None, "stage_b_exit_code": code_b,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "budget_cap_usd": os.environ.get("SSS_BUDGET_CAP_USD"),
        "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
        "context_mode": "plain", "quality": "pending researcher review",
        "stage_b_plan_reused": plan_reuse["reuse"],
    }
    if run_b and (run_b / "status.json").is_file():
        metrics["stage_b_status"] = json.loads((run_b / "status.json").read_text()).get("status")
    (output / "trial-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"stage_a={status_a} stage_b={metrics.get('stage_b_status', 'stopped')} output={output}")
    return 0 if code_b == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
