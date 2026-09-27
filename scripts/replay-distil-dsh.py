#!/usr/bin/env python3
"""Offline Distil eligibility audit on a saved DSH session; no model calls.

This one-pass audit cannot predict cache hits, agent decisions, restores, or
qualified-task cost. It keeps content and per-result hashes under .local only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.dsh_event_projection import is_original_tool_result  # noqa: E402

DISTIL = ROOT / ".local" / "distil-upstream"
PIN = "e836dc1540dd390823b26582ad137f73072d6871"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path, help="session.v3.jsonl.zstd")
    parser.add_argument("--out", type=Path,
                        default=ROOT / ".local" / "distil-sss" / "offline-replay.json")
    args = parser.parse_args()
    session = args.session.resolve(strict=True)
    if not session.is_relative_to(ROOT / ".local"):
        parser.error("private DSH session must stay under .local")
    revision = subprocess.check_output(["git", "-C", str(DISTIL), "rev-parse", "HEAD"],
                                       text=True).strip()
    if revision != PIN:
        parser.error("Distil source does not match pinned revision")
    out = args.out.resolve()
    if not out.is_relative_to(ROOT / ".local"):
        parser.error("private replay report must stay under .local")
    out.parent.mkdir(parents=True, exist_ok=True)
    offline_home = ROOT / ".local" / "distil-sss" / "offline-home"
    offline_home.mkdir(parents=True, exist_ok=True)
    os.environ["DISTIL_HOME"] = str(offline_home)
    sys.path.insert(0, str(DISTIL))
    from distil.adapters.openai import compress_chat_completions
    from distil.tokenizer import resolve

    tok = resolve("heuristic")
    items: list[dict] = []
    image_blocks = 0
    events = subprocess.Popen(["zstdcat", str(session)], stdout=subprocess.PIPE, text=True)
    assert events.stdout is not None
    try:
        for raw in events.stdout:
            event = json.loads(raw)
            if not is_original_tool_result(event):
                continue
            message = event.get("data", {}).get("message", {})
            for block in message.get("content", []):
                for part in block.get("content", []):
                    if part.get("type") == "image":
                        image_blocks += 1
                        continue
                    value = part.get("text") if part.get("type") == "text" else None
                    if not isinstance(value, str):
                        continue
                    msg = {"role": "tool", "tool_call_id": "replay", "content": value}
                    compressed, store = compress_chat_completions([msg])
                    new = compressed[0]["content"]
                    handles = sorted(store.handles)
                    if any(store.expand(handle) is None for handle in handles):
                        raise RuntimeError("Distil issued an unresolvable restore handle")
                    items.append({
                        "sha256": hashlib.sha256(value.encode()).hexdigest(),
                        "original_bytes": len(value.encode()),
                        "compressed_bytes": len(new.encode()),
                        "heuristic_tokens_before": tok.count(value),
                        "heuristic_tokens_after": tok.count(new),
                        "restore_handles": len(handles),
                    })
    finally:
        events.stdout.close()
        if events.wait() != 0:
            raise RuntimeError("failed to read compressed DSH session")
    report = {
        "kind": "offline_one_pass_tool_result_eligibility",
        "distil_revision": PIN,
        "session": str(session),
        "tool_text_blocks": len(items),
        "image_blocks_excluded": image_blocks,
        "changed_blocks": sum(x["compressed_bytes"] != x["original_bytes"] for x in items),
        "total_original_bytes": sum(x["original_bytes"] for x in items),
        "total_compressed_bytes": sum(x["compressed_bytes"] for x in items),
        "heuristic_tokens_before": sum(x["heuristic_tokens_before"] for x in items),
        "heuristic_tokens_after": sum(x["heuristic_tokens_after"] for x in items),
        "restore_handles": sum(x["restore_handles"] for x in items),
        "items": items,
        "limits": "Not a model run or task result; no cache, restore-call, billing, quality, or SSS comparison inference.",
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(out, 0o600)
    print(json.dumps({k: v for k, v in report.items() if k not in {"session", "items"}},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
