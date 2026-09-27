"""A semantic request must never reach DSH outside the measured cost route."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.adapters.dsh_client import call_bounded_prompt, require_budget_gate


class ResearchBudgetGateTests(unittest.TestCase):
    def test_rejects_direct_provider_even_with_active_flag(self) -> None:
        with patch.dict("os.environ", {
            "SSS_BUDGET_GATE_ACTIVE": "1", "SSS_BUDGET_CAP_USD": "2",
            "SSS_BUDGET_LEDGER": "/tmp/ledger.jsonl",
            "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
        }, clear=True):
            with tempfile.TemporaryDirectory() as temporary:
                with self.assertRaisesRegex(ValueError, "local budget gate"):
                    call_bounded_prompt("A question", root=Path(temporary))

    def test_accepts_only_positive_local_cap(self) -> None:
        base = {"SSS_BUDGET_GATE_ACTIVE": "1", "SSS_BUDGET_LEDGER": "/tmp/ledger.jsonl",
                "DEEPSEEK_BASE_URL": "http://127.0.0.1:8765/v1"}
        with patch.dict("os.environ", {**base, "SSS_BUDGET_CAP_USD": "0"}, clear=True):
            with self.assertRaisesRegex(ValueError, "positive cap"):
                require_budget_gate()
        with patch.dict("os.environ", {**base, "SSS_BUDGET_CAP_USD": "2"}, clear=True):
            require_budget_gate()


if __name__ == "__main__":
    unittest.main()
