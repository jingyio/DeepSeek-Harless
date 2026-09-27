#!/usr/bin/env python3
"""Two-stage native DSH MGGA diagnostic with optional Distil interception.

Preview is local and free. The paid path requires the isolated budget wrapper;
it never edits the original paper, experiments, Zotero or Obsidian.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_client import _usage  # noqa: E402
from src.adapters.native_budget import NativeBudgetGuard  # noqa: E402

BASE = ROOT / ".local" / "benchmarks" / "research-weekly-loop" / "native-dsh-baseline-preview"
FROZEN = ROOT / ".local" / "distil-sss" / "mgga-stage-a" / "sources"
QUESTION = "MGGA / MotifAgent 终稿 TauBench Figure 7 的 ReAct 柱对应哪组原始运行，终稿基线表应如何标注和限定主张？"
CONTINUE_PROMPT = (
    "上一轮在单次输出上限处截断。请继续完成当前研究任务，优先给出完整、可审阅的"
    "最终回答；沿用已核验的资料和计算。证据不足的地方请明确暂停主张。"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_stage_with_continuation(conversation, prompt: str, *, observe, output: Path,
                                stage: str, max_continuations: int) -> tuple[object, list[object]]:
    """Continue a truncated turn in the same conversation, with a fixed cap."""
    attempts = []
    next_prompt = prompt
    for index in range(max_continuations + 1):
        response = conversation.run(next_prompt, on_notification=observe)
        attempts.append(response)
        (output / f"stage-{stage}-attempt-{index + 1}.md").write_text(response.final_response)
        if response.finish_reason == "completed" and response.final_response.strip():
            break
        if response.finish_reason != "max-tokens" or index == max_continuations:
            break
        next_prompt = CONTINUE_PROMPT
    (output / f"stage-{stage}-metrics.json").write_text(json.dumps(
        _usage([event for response in attempts for event in response.events]), indent=2))
    (output / f"stage-{stage}-continuations.json").write_text(json.dumps({
        "attempts": len(attempts),
        "finish_reasons": [response.finish_reason for response in attempts],
        "completed": attempts[-1].finish_reason == "completed" and bool(attempts[-1].final_response.strip()),
    }, indent=2))
    return attempts[-1], attempts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--call-model", action="store_true")
    parser.add_argument("--max-model-requests", type=int, default=100)
    parser.add_argument("--max-observed-input-tokens", type=int, default=6_000_000)
    parser.add_argument("--max-output-tokens", type=int, default=3000)
    parser.add_argument("--max-continuations-per-stage", type=int, default=2)
    parser.add_argument("--scenario-dir", type=Path,
                        help="private frozen two-stage MGGA scenario under .local")
    args = parser.parse_args()
    if not 1 <= args.max_model_requests <= 100:
        parser.error("request limit must be in 1..100")
    if args.max_observed_input_tokens < 1:
        parser.error("invalid observed input cap")
    if not 1 <= args.max_output_tokens <= 8000:
        parser.error("output cap must be in 1..8000")
    if not 0 <= args.max_continuations_per_stage <= 3:
        parser.error("continuation cap must be in 0..3")
    scenario = None
    frozen = FROZEN
    if args.scenario_dir:
        scenario_dir = args.scenario_dir.resolve(strict=True)
        if not scenario_dir.is_relative_to(ROOT / ".local"):
            parser.error("scenario must stay under .local")
        scenario = json.loads((scenario_dir / "scenario.json").read_text())
        frozen = scenario_dir / "sources"
        prior = scenario["stage_a_source_sha256"]
        review = Path(scenario["stage_b_release_path"]).resolve(strict=True)
        expected_review = scenario["stage_b_release_sha256"]
        question = scenario["question"]
        prompt_a = f"研究问题：{question}\n\n" + scenario["stage_a_prompt"]
        prompt_b = scenario["stage_b_prompt"]
    else:
        prior = {row["name"]: row["sha256"] for row in
                 json.loads((BASE / "source-manifest.json").read_text())}
        review = BASE / "workspace" / "sources" / "review_2026-09-21.md"
        release = json.loads((BASE / "stage-b-release.json").read_text())
        expected_review = release["stage_b_event_sha256"]
        question = QUESTION
        prompt_a = (
            "你在协助终稿作者处理一个真实研究决定。阶段 A 的时间切点是 2026-09-20 23:59（上海），"
            "只能使用本工作区 sources/ 中现有的投稿 PDF 和三份原始 task_reports.json。"
            "不要读取工作区以外的资料，不浏览网络，不修改来源、论文或外部应用，不发送邮件或建立会议。"
            "你可自己决定何时使用本地工具；不要调用 SSS Motif 运行时。\n\n"
            f"问题：{QUESTION}\n"
            "交付一份可审阅的研究决定材料：给出三组运行的分母、成功率、token 与工具调用量的"
            "可复算聚合；检验 Figure 7 的柱与原始运行能否一一对应；提出终稿表格标签与限定后的主张。"
            "每项重要结论标明文件和具体记录或稿件位置，区分原始测量、稿件表述与推断。"
            "证据不足时暂停该主张，并列出最小补证。\n"
        )
        prompt_b = (
            "现在才释放 sources/review_2026-09-21.md。这是真实发生于阶段 A 之后的审查说明。"
            "请据此更新刚才的决定：逐项标记沿用、失效、修订或待补证，特别核对 Figure 7 的"
            "ReAct 与 ReAct-ACT 映射。不得把审查说明本身当成原始测量，也不要改原始资料。"
            "交付完整、可审阅的增量决定材料，给出每项新旧结论的证据位置。"
        )
    sources = {path.name: digest(path) for path in frozen.iterdir() if path.is_file()}
    if sources != prior:
        parser.error("stage A source hashes differ from the native DSH baseline")
    if digest(review) != expected_review:
        parser.error("stage B event differs from the historical release")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "distil-sss" / "runs" / stamp
    workspace = output / "workspace"
    target = workspace / "sources"
    target.mkdir(parents=True, exist_ok=False)
    for path in sorted(frozen.iterdir()):
        shutil.copy2(path, target / path.name)
    if {path.name: digest(path) for path in target.iterdir()} != prior:
        raise RuntimeError("source copy changed during trial preparation")
    preview = {
        "status": "preview", "question": question, "source_sha256": sources,
        "stage_b_sha256": digest(review), "model": "deepseek-flash",
        "reasoning_effort": "off", "max_output_tokens_per_request": args.max_output_tokens,
        "max_model_requests": args.max_model_requests,
        "max_observed_input_tokens": args.max_observed_input_tokens,
        "max_continuations_per_stage": args.max_continuations_per_stage,
        "context_mode": os.environ.get("SSS_CONTEXT_MODE", "unset"),
        "distil_profile": os.environ.get("SSS_DISTIL_PROFILE", "unset"),
        "budget_cap_usd": os.environ.get("SSS_BUDGET_CAP_USD"),
        "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
        "distil_home": os.environ.get("SSS_DISTIL_HOME"),
        "scenario_sha256": digest(args.scenario_dir.resolve() / "scenario.json")
        if scenario is not None else None,
        "note": "MGGA is a development diagnostic, not an independent held-out score.",
    }
    (output / "preview.json").write_text(json.dumps(preview, ensure_ascii=False, indent=2))
    (output / "stage-a-prompt.txt").write_text(prompt_a)
    (output / "stage-b-prompt.txt").write_text(prompt_b)
    print(f"preview={output / 'preview.json'} sources={len(sources)} model=deepseek-flash ",
          f"request_cap={args.max_model_requests} context={preview['context_mode']}")
    if not args.call_model:
        return 0
    if (os.environ.get("SSS_BUDGET_GATE_ACTIVE") != "1"
            or os.environ.get("SSS_CONTEXT_MODE") not in {"distil", "plain"}
            or not os.environ.get("DEEPSEEK_BASE_URL", "").startswith("http://127.0.0.1:")):
        parser.error("paid trial requires the isolated cost-gated DSH wrapper")
    from deepseek_harness import DeepSeekHarness

    guard = NativeBudgetGuard(max_model_requests=args.max_model_requests,
                              max_observed_input_tokens=args.max_observed_input_tokens)
    event_file = output / "events.jsonl"

    def observe(notification: object) -> None:
        if getattr(notification, "method", None) == "session.event":
            event = getattr(notification, "payload", {}).get("event")
            if isinstance(event, dict):
                with event_file.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        guard.on_notification(notification)

    started = time.monotonic()
    session_id = "sss-distil-mgga-" + uuid4().hex
    stage = "A"
    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash",
            reasoning_effort="off", max_tokens=args.max_output_tokens,
            cwd=str(workspace), runtime_cwd=str(workspace),
            dsh_bin=str(ROOT / "node_modules" / ".bin" / "dsh"), profile="sdk",
            patches=(str(ROOT / "config" / "native-baseline.patch.yml"),),
            dsh_home=str(ROOT / ".local" / "dsh"), request_timeout_seconds=900,
        ) as harness:
            conversation = harness.start_session(session_id)
            answer_a, _ = run_stage_with_continuation(
                conversation, prompt_a, observe=observe, output=output, stage="a",
                max_continuations=args.max_continuations_per_stage)
            (output / "stage-a-answer.md").write_text(answer_a.final_response)
            if answer_a.finish_reason != "completed" or not answer_a.final_response.strip():
                raise RuntimeError("stage A did not finish with a reviewable answer")
            stage = "B"
            shutil.copy2(review, target / review.name)
            if digest(target / review.name) != digest(review):
                raise RuntimeError("stage B event changed on release")
            answer_b, _ = run_stage_with_continuation(
                conversation, prompt_b, observe=observe, output=output, stage="b",
                max_continuations=args.max_continuations_per_stage)
            (output / "stage-b-answer.md").write_text(answer_b.final_response)
            if answer_b.finish_reason != "completed" or not answer_b.final_response.strip():
                raise RuntimeError("stage B did not finish with a reviewable answer")
        status = "completed"
    except Exception as exc:
        status = "stopped"
        (output / "error.txt").write_text(f"{stage}: {type(exc).__name__}: {str(exc)[:500]}")
    metrics = {"status": status, "stopped_at": stage, "session_id": session_id,
               "elapsed_seconds": round(time.monotonic() - started, 3),
               "started_requests": guard.started_requests,
               "observed_input_tokens": guard.observed_input_tokens,
               "budget_ledger": os.environ.get("SSS_BUDGET_LEDGER"),
               "distil_home": os.environ.get("SSS_DISTIL_HOME"),
               **_usage(guard.events)}
    (output / "trial-metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"status={status} stage={stage} model_requests={metrics['model_requests']} "
          f"elapsed={metrics['elapsed_seconds']} output={output}")
    return 0 if status == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
