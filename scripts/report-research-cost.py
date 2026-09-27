#!/usr/bin/env python3
"""Report the token-priced API cost range of one saved research run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


OFFPEAK_USD_PER_MILLION = {"inputTokens": 0.15, "cacheReadTokens": 0.003,
                           "outputTokens": 0.6}


def estimate_cost(metrics: dict[str, int], *, peak: bool) -> float:
    values = {}
    for key in OFFPEAK_USD_PER_MILLION:
        value = metrics.get(key, 0)
        if type(value) is not int or value < 0:
            raise ValueError(f"invalid token usage: {key}")
        values[key] = value
    factor = 2 if peak else 1
    return sum(values[key] * rate * factor / 1_000_000
               for key, rate in OFFPEAK_USD_PER_MILLION.items())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="directory containing total-metrics.json")
    args = parser.parse_args()
    metrics = json.loads((args.run / "total-metrics.json").read_text(encoding="utf-8"))
    report = {
        "model": "deepseek-flash", "model_requests": metrics.get("model_requests", 0),
        "token_usage": {key: metrics.get(key, 0) for key in OFFPEAK_USD_PER_MILLION},
        "offpeak_usd_estimate": round(estimate_cost(metrics, peak=False), 8),
        "peak_usd_estimate": round(estimate_cost(metrics, peak=True), 8),
        "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing/",
        "pricing_checked": "2026-09-25",
        "scope": "API tokens visible in this run; excludes human, local compute, and unlogged requests",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
