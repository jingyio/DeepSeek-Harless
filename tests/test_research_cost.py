"""Token classes must use their separate official DeepSeek prices."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE = Path(__file__).resolve().parents[1] / "scripts" / "report-research-cost.py"
SPEC = importlib.util.spec_from_file_location("report_research_cost", MODULE)
assert SPEC and SPEC.loader
cost = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cost)


class ResearchCostTests(unittest.TestCase):
    def test_counts_miss_cache_and_output_separately(self) -> None:
        metrics = {"inputTokens": 1_000_000, "cacheReadTokens": 1_000_000,
                   "outputTokens": 1_000_000}
        self.assertAlmostEqual(cost.estimate_cost(metrics, peak=False), 0.753)
        self.assertAlmostEqual(cost.estimate_cost(metrics, peak=True), 1.506)


if __name__ == "__main__":
    unittest.main()
