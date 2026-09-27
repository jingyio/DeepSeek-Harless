#!/usr/bin/env python3
"""Report model-token usage from a DeepSeek Harness session without printing prompts."""

import argparse
from collections import defaultdict
import glob
import json
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSION_ROOT = PROJECT_ROOT / ".local" / "dsh" / "sessions"
TOKEN_KEYS = ("inputTokens", "cacheReadTokens", "outputTokens", "totalTokens", "reasoningTokens")


def summarize(events):
    """Attribute each response to the durable request route active at that point."""
    totals = {key: 0 for key in TOKEN_KEYS}
    routes = defaultdict(lambda: {"model_requests": 0, "usage": {key: 0 for key in TOKEN_KEYS}})
    session_id = None
    provider = model = None
    unassigned = 0
    compactions = 0
    for event in events:
        data = event.get("data", {})
        kind = event.get("type")
        if kind == "session":
            session_id = event.get("id")
        elif kind == "request/header":
            config = data.get("header", {}).get("config", {})
            provider = config.get("provider", provider)
            model = config.get("model", model)
        elif kind == "request/context":
            provider = data.get("provider", provider)
            model = data.get("model", model)
        elif kind == "assistant/message":
            usage = data.get("usage")
            if not isinstance(usage, dict):
                continue
            route = f"{provider}/{model}" if provider and model else "unassigned"
            if route == "unassigned":
                unassigned += 1
            routes[route]["model_requests"] += 1
            for key in TOKEN_KEYS:
                amount = int(usage.get(key) or 0)
                totals[key] += amount
                routes[route]["usage"][key] += amount
        elif kind == "compaction/summary" and isinstance(data.get("usage"), dict):
            # Compaction invokes a model too, but is not an assistant/message.
            # Keep it distinct so the caller can reconcile all billed work.
            compactions += 1
            route = f"{data.get('provider')}/{data.get('model')}"
            routes[route]["model_requests"] += 1
            for key in TOKEN_KEYS:
                amount = int(data["usage"].get(key) or 0)
                totals[key] += amount
                routes[route]["usage"][key] += amount
    return {
        "session_id": session_id,
        "model_requests": sum(row["model_requests"] for row in routes.values()),
        "usage": totals,
        "by_route": dict(sorted(routes.items())),
        "unassigned_requests": unassigned,
        "compaction_requests": compactions,
        "scope": "Recorded assistant/message and compaction/summary usage; route follows request/header and request/context. Reconcile with provider billing for actual cost.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a Harness session's token usage")
    parser.add_argument("session", nargs="?", type=Path, help="session.v3.jsonl.zstd; defaults to newest local session")
    args = parser.parse_args()

    if args.session:
        path = args.session.expanduser().resolve(strict=True)
    else:
        candidates = [Path(p) for p in glob.glob(str(SESSION_ROOT / "**" / "session.v3.jsonl.zstd"), recursive=True)]
        if not candidates:
            parser.error("no Harness session files found")
        path = max(candidates, key=lambda item: item.stat().st_mtime)

    result = subprocess.run(["zstdcat", str(path)], capture_output=True, text=True, check=True)
    report = summarize(json.loads(line) for line in result.stdout.splitlines())
    report["session_file"] = str(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
