"""The proxy-side budget includes calls invisible to DSH step counting."""

import json
import tempfile
import unittest
from pathlib import Path

from src.adapters.deepseek_cost_gate import State, observed_peak_cost, reservation, response_usage


class DeepSeekCostGateTests(unittest.TestCase):
    def test_peak_reservation_refuses_next_request_before_forwarding(self) -> None:
        body = json.dumps({"model": "deepseek-flash", "max_tokens": 3000,
                           "messages": [{"role": "user", "content": "x" * 20_000}]}).encode()
        _, cost, _ = reservation(body, max_output=3000)
        with tempfile.TemporaryDirectory() as temporary:
            state = State(cap_usd=cost * 1.5, output_cap=3000,
                          record=Path(temporary) / "gate.jsonl")
            self.assertIsNotNone(state.book(body))
            self.assertIsNone(state.book(body))
            self.assertEqual(state.request_count, 1)

    def test_unknown_model_and_missing_output_cap_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "approved peak-price"):
            reservation(b'{"model":"unknown","max_tokens":100}', max_output=3000)
        with self.assertRaisesRegex(ValueError, "max_tokens"):
            reservation(b'{"model":"deepseek-flash"}', max_output=3000)

    def test_complete_usage_releases_unused_reservation_without_exceeding_cap(self) -> None:
        body = json.dumps({"model": "deepseek-flash", "max_tokens": 3000,
                           "messages": [{"role": "user", "content": "x" * 20_000}]}).encode()
        _, reserved, _ = reservation(body, max_output=3000)
        usage = {"prompt_tokens": 120, "prompt_cache_hit_tokens": 100,
                 "prompt_cache_miss_tokens": 20, "completion_tokens": 30,
                 "total_tokens": 150}
        observed = observed_peak_cost("deepseek-flash", usage)
        with tempfile.TemporaryDirectory() as temporary:
            state = State(cap_usd=reserved * 1.5, output_cap=3000,
                          record=Path(temporary) / "gate.jsonl")
            first = state.book(body)
            self.assertIsNotNone(first)
            self.assertIsNone(state.book(body))
            charged, released = state.settle(first[0], first[1], 200, usage)
            self.assertAlmostEqual(charged, observed)
            self.assertAlmostEqual(released, reserved - observed)
            self.assertAlmostEqual(state.reserved_usd, observed)
            self.assertIsNotNone(state.book(body))

    def test_missing_usage_or_failed_request_keeps_full_reservation(self) -> None:
        body = b'{"model":"deepseek-flash","max_tokens":100,"messages":[]}'
        with tempfile.TemporaryDirectory() as temporary:
            state = State(cap_usd=1, output_cap=3000,
                          record=Path(temporary) / "gate.jsonl")
            first = state.book(body)
            self.assertEqual(state.settle(first[0], first[1], 200, {}), (None, 0.0))
            self.assertAlmostEqual(state.reserved_usd, first[2])
            second = state.book(body)
            self.assertEqual(state.settle(second[0], second[1], 502, {}), (None, 0.0))
            self.assertAlmostEqual(state.reserved_usd, first[2] + second[2])

    def test_inconsistent_usage_cannot_release_reservation(self) -> None:
        with self.assertRaisesRegex(ValueError, "inconsistent provider usage"):
            observed_peak_cost("deepseek-flash", {"prompt_tokens": 12,
                "prompt_cache_hit_tokens": 8, "prompt_cache_miss_tokens": 4,
                "completion_tokens": 3, "total_tokens": 14})

    def test_streamed_usage_is_recordable_without_response_content(self) -> None:
        event = {"choices": [{"delta": {"content": "private answer"}}],
                 "usage": {"prompt_tokens": 12, "prompt_cache_hit_tokens": 8,
                           "prompt_cache_miss_tokens": 4,
                           "completion_tokens": 3, "total_tokens": 15}}
        payload = (b'data: {"choices":[{"delta":{"content":"private"}}],"usage":null}\n\n'
                   + b"data: " + json.dumps(event).encode() + b"\n\ndata: [DONE]\n")
        self.assertEqual(response_usage("text/event-stream", payload), {
            "prompt_tokens": 12, "prompt_cache_hit_tokens": 8,
            "prompt_cache_miss_tokens": 4, "completion_tokens": 3,
            "total_tokens": 15,
        })
        self.assertEqual(response_usage("application/json", b'{"usage":{"prompt_tokens":1}}'), {})


if __name__ == "__main__":
    unittest.main()
