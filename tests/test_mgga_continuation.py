"""A truncated research answer resumes in the same bounded conversation."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run-distil-mgga-trial.py"
loader = SourceFileLoader("mgga_trial_continuation", str(SCRIPT))
spec = spec_from_loader(loader.name, loader)
trial = module_from_spec(spec)
loader.exec_module(trial)


class FakeConversation:
    def __init__(self, responses):
        self.responses = responses
        self.prompts = []

    def run(self, prompt, on_notification):
        self.prompts.append(prompt)
        return self.responses.pop(0)


class MGGATrialContinuationTests(unittest.TestCase):
    def test_resumes_max_tokens_once_and_saves_attempts(self):
        responses = [
            SimpleNamespace(finish_reason="max-tokens", final_response="partial", events=[]),
            SimpleNamespace(finish_reason="completed", final_response="final", events=[]),
        ]
        conversation = FakeConversation(responses)
        with tempfile.TemporaryDirectory() as directory:
            result, attempts = trial.run_stage_with_continuation(
                conversation, "initial", observe=lambda _: None,
                output=Path(directory), stage="a", max_continuations=2)
            self.assertEqual(result.final_response, "final")
            self.assertEqual(len(attempts), 2)
            self.assertEqual(conversation.prompts, ["initial", trial.CONTINUE_PROMPT])
            self.assertEqual((Path(directory) / "stage-a-attempt-1.md").read_text(), "partial")
            record = json.loads((Path(directory) / "stage-a-continuations.json").read_text())
            self.assertEqual(record["finish_reasons"], ["max-tokens", "completed"])
            self.assertTrue(record["completed"])

    def test_does_not_continue_other_failure_or_exceed_cap(self):
        for reason, cap in (("error", 2), ("max-tokens", 0)):
            conversation = FakeConversation([
                SimpleNamespace(finish_reason=reason, final_response="", events=[]),
            ])
            with tempfile.TemporaryDirectory() as directory:
                _, attempts = trial.run_stage_with_continuation(
                    conversation, "initial", observe=lambda _: None,
                    output=Path(directory), stage="b", max_continuations=cap)
                self.assertEqual(len(attempts), 1)
                self.assertEqual(conversation.prompts, ["initial"])


if __name__ == "__main__":
    unittest.main()
