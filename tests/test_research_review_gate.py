"""A human verdict is sealed to the exact local draft before reuse."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.workflows.research_review_gate import REVIEWED_FILES, require_approved_review


ROOT = Path(__file__).resolve().parents[1]


class ResearchReviewGateTests(unittest.TestCase):
    def test_recorded_review_is_private_immutable_and_content_bound(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT / ".local") as directory:
            run = Path(directory) / "run"
            run.mkdir()
            for name in REVIEWED_FILES:
                (run / name).write_text("{}\n", encoding="utf-8")
            (run / "answer-points.json").write_text(
                json.dumps([{"id": "p1", "requirement": "Explain result"}]),
                encoding="utf-8")
            (run / "status.json").write_text('{"status":"incremental_draft"}\n',
                                              encoding="utf-8")
            form = Path(directory) / "filled-review.json"
            form.write_text(json.dumps({
                "reviewer": "researcher-1", "reviewed_at": "2026-09-26T17:00:00+08:00",
                "verdict": "approved", "point_scores": {"p1": {"support": 2, "coverage": 2}},
                "serious_error": False, "review_minutes": 10,
                "notes": "Checked the cited source.",
            }), encoding="utf-8")
            command = [sys.executable, str(ROOT / "scripts/record-research-review.py"),
                       str(run), "--form", str(form)]
            first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                   timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            record = run / "human-review.json"
            self.assertEqual(record.stat().st_mode & 0o777, 0o600)
            self.assertEqual(require_approved_review(run)["assessment"]["verdict"],
                             "approved")
            duplicate = subprocess.run(command, cwd=ROOT, capture_output=True,
                                       text=True, timeout=10)
            self.assertNotEqual(duplicate.returncode, 0)
            (run / "claims.json").write_text('{"changed":true}\n', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "current files"):
                require_approved_review(run)


if __name__ == "__main__":
    unittest.main()
