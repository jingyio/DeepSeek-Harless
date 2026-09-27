"""Mechanism tests for the migrated MotifAgent office runtime."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from src.workflows.motif_office import OfficeHandoffError, run


ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "benchmarks" / "office_research_v0" / "inputs"


class MotifOfficeTests(unittest.TestCase):
    def test_incremental_resume_reuses_evidence_and_invalidates_correction(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            work = Path(root)
            shutil.copytree(INPUTS / "stage_a", work / "papers")
            a, state, a_events = run("A", work / "papers")
            self.assertEqual(a["trace"]["resume_count"], 0)
            self.assertEqual(len([e for e in a_events if e["event"] == "source_read"]), 5)
            for path in (INPUTS / "stage_b_delta").glob("*.md"):
                shutil.copy2(path, work / "papers" / path.name)
            b, _, b_events = run("B", work / "papers", state)
            self.assertEqual(b["trace"]["resume_count"], 1)
            self.assertEqual(b["trace"]["invalidated_records"], ["MF-24"])
            self.assertEqual(len([e for e in b_events if e["event"] == "source_reused"]), 5)
            self.assertEqual(len([e for e in b_events if e["event"] == "source_read"]), 2)
            self.assertEqual([e["record_id"] for e in b_events if e["event"] == "record_invalidated"], ["MF-24"])
            self.assertEqual(next(f["value"] for f in b["facts"] if f["id"] == "mf_success"), "28/40")
            self.assertNotIn("32/40；", b["report"].split("可比记录：", 1)[1].split("。", 1)[0])

    def test_changed_source_cannot_reuse_bound_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            work = Path(root)
            shutil.copytree(INPUTS / "stage_a", work / "papers")
            _, state, _ = run("A", work / "papers")
            path = work / "papers" / "graph_plan_2025.md"
            path.write_text(path.read_text().replace("30 of 40 tasks", "29 of 40 tasks"))
            for source in (INPUTS / "stage_b_delta").glob("*.md"):
                shutil.copy2(source, work / "papers" / source.name)
            b, _, events = run("B", work / "papers", state)
            self.assertIn("GP-25", b["trace"]["invalidated_records"])
            self.assertIn("MF-24", b["trace"]["invalidated_records"])
            self.assertIn("graph_plan_2025.md", [e["file"] for e in events if e["event"] == "source_read"])
            self.assertEqual(next(f["value"] for f in b["facts"] if f["id"] == "gp_success"), "29/40")

    def test_conflicting_official_revision_produces_bounded_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            work = Path(root)
            shutil.copytree(INPUTS / "stage_a", work / "papers")
            original = (work / "papers" / "graph_plan_2025.md").read_text()
            (work / "papers" / "graph_conflict.md").write_text(original.replace("30 of 40 tasks", "29 of 40 tasks"))
            with self.assertRaises(OfficeHandoffError) as caught:
                run("A", work / "papers")
            handoff = caught.exception.request
            self.assertEqual(handoff.source, "official_revision_conflict")
            self.assertEqual(handoff.available_state["record_id"], "GP-25")
            self.assertEqual(set(handoff.allowed_reentry["candidates"]),
                             {"graph_plan_2025.md", "graph_conflict.md"})


if __name__ == "__main__":
    unittest.main()
