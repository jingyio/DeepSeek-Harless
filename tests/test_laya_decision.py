"""Boundary checks for the local typed-decision port."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from src.adapters.laya_decision import LayaDecisionPort


class _Response:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class _Opener:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def open(self, *_args, **_kwargs):
        return _Response(self.payload)


class LayaDecisionTests(unittest.TestCase):
    def test_nonlocal_endpoint_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LayaDecisionPort("https://example.com/v1/systemone")

    def test_out_of_set_answer_rejected(self) -> None:
        payload = {"answers": {"q": {"choice": "outside", "probabilities": {"A": 0.6, "B": 0.4}}}}
        with patch("src.adapters.laya_decision.build_opener", return_value=_Opener(payload)):
            with self.assertRaisesRegex(ValueError, "outside"):
                LayaDecisionPort().choose(state="text", question_id="q", instructions="choose",
                                          criteria={"A": "first", "B": "second"})

    def test_valid_choice_returns_selected_probability(self) -> None:
        payload = {"routing": {"model": "multilingual"}, "answers": {"q": {
            "choice": "A", "probabilities": {"A": 0.7, "B": 0.3}, "confidence": 0.2}}}
        with patch("src.adapters.laya_decision.build_opener", return_value=_Opener(payload)):
            result = LayaDecisionPort().choose(state="text", question_id="q", instructions="choose",
                                               criteria={"A": "first", "B": "second"})
        self.assertEqual(result.choice, "A")
        self.assertEqual(result.probability, 0.7)
        self.assertEqual(result.model, "multilingual")


if __name__ == "__main__":
    unittest.main()
