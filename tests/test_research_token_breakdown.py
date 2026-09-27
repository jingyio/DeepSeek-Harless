"""Token breakdown must reconcile provider usage before reporting savings."""

import json
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "research-token-breakdown.py"
loader = SourceFileLoader("research_token_breakdown", str(SCRIPT))
spec = spec_from_loader(loader.name, loader)
breakdown = module_from_spec(spec)
loader.exec_module(breakdown)


class TokenBreakdownTests(unittest.TestCase):
    def test_counts_cache_separately_and_rejects_missing_usage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row = {"response_status": 200, "response_usage": {
                "prompt_cache_miss_tokens": 1000, "prompt_cache_hit_tokens": 2000,
                "completion_tokens": 500, "prompt_tokens": 3000, "total_tokens": 3500}}
            (root / "ledger.jsonl").write_text(json.dumps(row) + "\n")
            manifest = {"runs": [{"name": "test", "ledger": "ledger.jsonl",
                                  "stages": [{"name": "A", "requests": 1}]}]}
            report = breakdown.analyze(manifest, root=root)
            total = report["runs"][0]["total"]
            self.assertEqual(total["total"], 3500)
            self.assertAlmostEqual(total["offpeak_usd"], 0.000456)
            row["response_usage"]["total_tokens"] = 3499
            (root / "ledger.jsonl").write_text(json.dumps(row) + "\n")
            with self.assertRaisesRegex(ValueError, "do not reconcile"):
                breakdown.analyze(manifest, root=root)


if __name__ == "__main__":
    unittest.main()
