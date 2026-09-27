"""Real-trial snapshots must stay private and fail closed when inputs change."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.workflows.research_weekly_trial import freeze_initial_trial, verify_frozen_trial


class ResearchWeeklyTrialTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.local = self.root / ".local"
        self.local.mkdir()
        self.snapshot = self.local / "idea.md"
        self.snapshot.write_text("researcher's actual Idea State", encoding="utf-8")

    def intake(self) -> dict:
        return {"schema_version": 1, "task_id": "aidd-pilot", "decision": "Which task?",
                "deadline": "2026-09-30T17:00:00+08:00",
                "as_of": "2026-09-25T09:00:00+08:00", "reader": "researcher",
                "idea_origin": "research-workflow@commit", "sources": [{
                    "kind": "idea_state", "source_id": "current", "revision_id": "v1",
                    "snapshot_file": str(self.snapshot),
                    "observed_at": "2026-09-25T08:00:00+08:00",
                    "external_model_excerpt_allowed": False,
                }]}

    def test_freeze_replays_only_unchanged_private_input(self) -> None:
        frozen = freeze_initial_trial(self.intake(), local_root=self.local)
        self.assertEqual(frozen["phase"], "initial")
        self.assertNotIn("researcher's actual Idea State", str(frozen))
        verify_frozen_trial(frozen, local_root=self.local)
        self.snapshot.write_text("changed conclusion", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "source changed"):
            verify_frozen_trial(frozen, local_root=self.local)

    def test_outside_or_linked_source_is_rejected(self) -> None:
        outside = self.root / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        intake = self.intake()
        intake["sources"][0]["snapshot_file"] = str(outside)
        with self.assertRaisesRegex(ValueError, "under .local"):
            freeze_initial_trial(intake, local_root=self.local)
        link = self.local / "link.md"
        link.symlink_to(self.snapshot)
        intake["sources"][0]["snapshot_file"] = str(link)
        with self.assertRaisesRegex(ValueError, "under .local"):
            freeze_initial_trial(intake, local_root=self.local)

    def test_replay_rejects_parent_retargeted_outside_local(self) -> None:
        folder = self.local / "sources"
        folder.mkdir()
        source = folder / "idea.md"
        source.write_text("same content", encoding="utf-8")
        intake = self.intake()
        intake["sources"][0]["snapshot_file"] = str(source)
        frozen = freeze_initial_trial(intake, local_root=self.local)
        outside = self.root / "outside"
        folder.rename(outside)
        folder.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "source changed"):
            verify_frozen_trial(frozen, local_root=self.local)

    def test_future_observation_cannot_enter_initial_phase(self) -> None:
        intake = self.intake()
        intake["sources"][0]["observed_at"] = "2026-09-25T10:00:00+08:00"
        with self.assertRaisesRegex(ValueError, "after the snapshot cutoff"):
            freeze_initial_trial(intake, local_root=self.local)


if __name__ == "__main__":
    unittest.main()
