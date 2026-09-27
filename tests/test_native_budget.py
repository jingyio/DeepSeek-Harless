"""The native Agent guard stops before the next request and retains usage."""

from __future__ import annotations

import unittest

from src.adapters.native_budget import NativeBudgetExceeded, NativeBudgetGuard


class NativeBudgetTests(unittest.TestCase):
    def test_stops_before_fourth_step(self) -> None:
        guard = NativeBudgetGuard(max_model_requests=3, max_observed_input_tokens=50_000)
        for number in range(3):
            guard.observe_event({"type": "step/start", "data": {"step": number}})
            guard.observe_event({"type": "assistant/message", "data": {
                "usage": {"inputTokens": 100, "cacheReadTokens": 10, "outputTokens": 20}}})
        with self.assertRaisesRegex(NativeBudgetExceeded, "before the next"):
            guard.observe_event({"type": "step/start", "data": {"step": 3}})
        self.assertEqual(guard.started_requests, 3)
        self.assertEqual(len([row for row in guard.events if row["type"] == "assistant/message"]), 3)

    def test_stops_after_observed_token_limit(self) -> None:
        guard = NativeBudgetGuard(max_model_requests=5, max_observed_input_tokens=100)
        guard.observe_event({"type": "step/start"})
        with self.assertRaisesRegex(NativeBudgetExceeded, "input token"):
            guard.observe_event({"type": "assistant/message", "data": {
                "usage": {"inputTokens": 80, "cacheReadTokens": 30}}})
        self.assertEqual(guard.observed_input_tokens, 110)
        self.assertEqual(len(guard.events), 2)

    def test_provider_cost_gate_can_be_only_limit(self) -> None:
        guard = NativeBudgetGuard(max_model_requests=None,
                                  max_observed_input_tokens=None)
        for number in range(120):
            guard.observe_event({"type": "step/start", "data": {"step": number}})
            guard.observe_event({"type": "assistant/message", "data": {
                "usage": {"inputTokens": 100, "cacheReadTokens": 200}}})
        self.assertEqual(guard.started_requests, 120)
        self.assertEqual(guard.observed_input_tokens, 36_000)


if __name__ == "__main__":
    unittest.main()
