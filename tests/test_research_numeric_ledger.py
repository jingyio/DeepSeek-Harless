"""A report may expose verified arithmetic without trusting model prose."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.workflows.motif_research_sources import collect
from src.workflows.research_numeric_ledger import collect_numeric_ledger, render_numeric_ledger


class ResearchNumericLedgerTests(unittest.TestCase):
    def test_real_json_source_becomes_hash_bound_human_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runs.json").write_text(json.dumps([
                {"reward": 1, "metrics": {"tokens": 10}, "a|b": 0},
                {"reward": 0, "metrics": {"tokens": 20}, "a|b": 1},
            ]), encoding="utf-8")
            pages, state, _ = collect(root)
            ledger = collect_numeric_ledger(pages)
            self.assertEqual(ledger["sources"][0]["source_sha256"],
                             state["evidence"][0]["binding"]["sha256"])
            self.assertEqual(ledger["sources"][0]["fields"]["reward"],
                             {"count": 2, "sum": "1", "mean": "0.5"})
            text = render_numeric_ledger(ledger)
            self.assertIn("metrics.tokens | 2 | 30 | 15", text)
            self.assertIn("a\\|b | 2 | 1 | 0.5", text)
            self.assertIn(ledger["ledger_sha256"], text)
            self.assertIn("科学含义", text)

    def test_metadata_cannot_impersonate_a_derived_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid derived numeric evidence"):
            collect_numeric_ledger([{"evidence_kind": "derived_numeric_summary",
                                     "source": "fake", "source_sha256": "short",
                                     "derived_from_pages": [1, 2], "numeric_fields": {"reward": 1}}])


if __name__ == "__main__":
    unittest.main()
