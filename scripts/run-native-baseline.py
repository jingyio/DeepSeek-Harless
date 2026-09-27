#!/usr/bin/env python3
"""Run one native, tool-enabled Harness answer in a copied local workspace."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.dsh_client import _usage  # noqa: E402
from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard  # noqa: E402
from src.graph.runtime import Evidence, execute  # noqa: E402
from src.workflows.research import ANSWER_POINT_PREFLIGHT_MOTIF  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", type=Path, help="one local PDF")
    source_group.add_argument("--source-dir", type=Path, help="directory of up to 20 local PDF/text sources")
    parser.add_argument("--answer-points", type=Path, help="shared answer-point obligations for comparison")
    parser.add_argument("--max-model-requests", type=int,
                        help="required with --call-model; stop before starting a later Agent step")
    parser.add_argument("--max-observed-input-tokens", type=int, default=200_000,
                        help="stop after observed total input exceeds this value (default 200000)")
    parser.add_argument("--call-model", action="store_true", help="allow this paid, tool-enabled Agent run")
    args = parser.parse_args()
    if args.call_model and args.max_model_requests is None:
        parser.error("--call-model requires --max-model-requests")
    if args.max_model_requests is not None and not 1 <= args.max_model_requests <= 30:
        parser.error("max model requests must be 1 to 30")
    if args.max_observed_input_tokens < 1:
        parser.error("max observed input tokens must be positive")
    if args.source is not None:
        if args.source.is_symlink():
            parser.error("source must not be a symlink")
        source = args.source.resolve(strict=True)
        if not source.is_file() or source.suffix.lower() != ".pdf" or source.stat().st_size > 10_000_000:
            parser.error("source must be one regular PDF of at most 10 MB")
        sources = [source]
    else:
        if args.source_dir.is_symlink():
            parser.error("source directory must not be a symlink")
        source_dir = args.source_dir.resolve(strict=True)
        if not source_dir.is_dir():
            parser.error("source directory is not a directory")
        sources = sorted(path for path in source_dir.iterdir()
                         if path.suffix.lower() in {".pdf", ".md", ".txt"})
        if not 1 <= len(sources) <= 20:
            parser.error("source directory needs 1 to 20 supported files")
        if any(path.is_symlink() or not path.is_file() or path.stat().st_size > 10_000_000
               for path in sources):
            parser.error("source directory contains a symlink, non-file, or oversized source")
    if sum(path.stat().st_size for path in sources) > 50_000_000:
        parser.error("source set exceeds 50 MB")
    points = None
    if args.answer_points:
        points = json.loads(args.answer_points.resolve(strict=True).read_text(encoding="utf-8"))
        point_run = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
            "answer_points": Evidence(points, "shared_question_obligations"),
        })
        if point_run.status != "completed":
            parser.error("answer points failed structural preflight")
        points = point_run.state["validated_answer_points"].value
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:6]
    output = ROOT / ".local" / "native-baselines" / stamp
    workspace = output / "workspace"
    references = workspace / "reference"
    references.mkdir(parents=True, exist_ok=False)
    (output / "question.txt").write_text(args.question.strip() + "\n", encoding="utf-8")
    if points is not None:
        (output / "answer-points.json").write_text(
            json.dumps(points, ensure_ascii=False, indent=2), encoding="utf-8")
    inventory = []
    for source in sources:
        target = references / source.name
        shutil.copy2(source, target)
        source_hash = sha256(source.read_bytes()).hexdigest()
        if sha256(target.read_bytes()).hexdigest() != source_hash:
            raise RuntimeError("copied source hash mismatch")
        inventory.append({"filename": source.name, "sha256": source_hash, "bytes": target.stat().st_size})
    prompt = (
        "Prepare a concise, reviewable research brief using only the files in reference/ in this "
        "workspace. You may inspect those files with local tools. Do not use web sources or files "
        "outside this workspace, and do not modify the source files. Cite source filenames and PDF "
        "page numbers or text file identifiers for each substantive claim. Explain uncertainty where "
        "evidence is insufficient. If comparing methods, state each method's inputs and steps, then "
        "their similarities and differences using evidence from at least two different sources.\n\n"
        "Question: " + args.question + "\nSource files: "
        + json.dumps([row["filename"] for row in inventory], ensure_ascii=False)
        + ("\nRequired answer points: " + json.dumps(points, ensure_ascii=False)
           if points is not None else "")
    )
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    (output / "sources.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.source is not None:
        (output / "source.json").write_text(json.dumps(inventory[0], ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    print(f"sources={len(inventory)} bytes={sum(row['bytes'] for row in inventory)} "
          f"prompt_characters={len(prompt)} model=deepseek-flash reasoning=off "
          f"output_cap_per_request=1800 max_model_requests={args.max_model_requests or 'unset'} "
          f"max_observed_input_tokens={args.max_observed_input_tokens}")
    if not args.call_model:
        (output / "status.json").write_text(json.dumps({"status": "preview"}), encoding="utf-8")
        print(f"preview only; add --call-model; report={output}")
        return 0
    from deepseek_harness import DeepSeekHarness

    started = time.monotonic()
    guard = NativeBudgetGuard(max_model_requests=args.max_model_requests,
                              max_observed_input_tokens=args.max_observed_input_tokens)
    try:
        with DeepSeekHarness(
            provider="deepseek-official", model="deepseek-flash", reasoning_effort="off",
            max_tokens=1800, cwd=str(workspace), runtime_cwd=str(workspace),
            dsh_bin=str(ROOT / "node_modules" / ".bin" / "dsh"), profile="sdk",
            patches=(str(ROOT / "config" / "native-baseline.patch.yml"),),
            dsh_home=str(ROOT / ".local" / "dsh"), request_timeout_seconds=120,
        ) as harness:
            result = harness.run(prompt, session_id=f"sss-native-baseline-{uuid4().hex}",
                                 on_notification=guard.on_notification)
    except Exception as exc:
        partial = {"provider": "deepseek-official", "model": "deepseek-flash",
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "status": "budget_stopped" if isinstance(exc, NativeBudgetExceeded) else "error",
                   "started_requests": guard.started_requests,
                   "observed_input_tokens": guard.observed_input_tokens,
                   **_usage(guard.events)}
        (output / "metrics.json").write_text(json.dumps(partial, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "events.json").write_text(json.dumps(guard.events, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / "error.txt").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        (output / "status.json").write_text(json.dumps({"status": partial["status"]}), encoding="utf-8")
        print(f"native baseline failed: {type(exc).__name__}; report={output}", file=sys.stderr)
        return 2
    metrics = {"provider": "deepseek-official", "model": "deepseek-flash",
               "reasoning_effort": "off", "elapsed_seconds": round(time.monotonic() - started, 3),
               "finish_reason": result.finish_reason, "session_id": result.session_id,
               "event_types": {kind: sum(item.get("type") == kind for item in result.events)
                               for kind in sorted({item.get("type", "") for item in result.events})},
               **_usage(result.events)}
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "events.json").write_text(json.dumps(result.events, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "answer.md").write_text(result.final_response, encoding="utf-8")
    (output / "status.json").write_text(json.dumps({"status": result.finish_reason}), encoding="utf-8")
    print(f"status={result.finish_reason} requests={metrics['model_requests']} "
          f"input={metrics['inputTokens']} cache_read={metrics['cacheReadTokens']} "
          f"output={metrics['outputTokens']}; report={output}")
    return 0 if result.finish_reason == "completed" and result.final_response.strip() else 2


if __name__ == "__main__":
    raise SystemExit(main())
