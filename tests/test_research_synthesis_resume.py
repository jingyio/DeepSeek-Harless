"""A failed semantic reply can resume only against the same verified state."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.workflows.motif_research_sources import collect
from src.workflows.research_synthesis_resume import prepare_synthesis_resume


class ResearchSynthesisResumeTests(unittest.TestCase):
    def test_reuses_validated_inputs_and_discards_failed_response(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary) / ".local"
            source = local / "sources"
            source.mkdir(parents=True)
            (source / "paper.md").write_text("An unchanged source", encoding="utf-8")
            _, state, _ = collect(source)
            parent = local / "point-research-runs" / "failed"
            parent.mkdir(parents=True)
            points = [{"id": "answer", "requirement": "Answer using the source"}]
            files = {
                "status.json": {"status": "stopped", "stage": "synthesis", "reason": "truncated"},
                "answer-points.json": points,
                "motif-source-state.json": state,
                "plan.json": [{"point_id": "answer", "terms": ["source"]}],
                "selection.json": {"answer": ["answer-C1"]},
                "selection-bundle-template.json": {
                    "candidate_sha256": "a" * 64, "selections": []},
                "motif-selection-state.json": {
                    "motif_id": "research_point_selection", "source_dir": str(source.resolve()),
                    "candidate_sha256": "a" * 64,
                    "decisions": {"select_answer.choice": {
                        "resolution_status": "VALIDATED",
                        "values": {"evidence_ids": ["answer-C1"]}}}},
            }
            for name, value in files.items():
                (parent / name).write_text(json.dumps(value), encoding="utf-8")
            (parent / "question.txt").write_text("A question\n", encoding="utf-8")
            (parent / "synthesis-response.txt").write_text('{"claims": [', encoding="utf-8")
            output = local / "next"
            output.mkdir()
            prepared = prepare_synthesis_resume(parent, local_root=local, output=output,
                                                question="A question", answer_points=points)
            bundle = json.loads(prepared["selection_file"].read_text())
            self.assertEqual(bundle["selections"], [
                {"point_id": "answer", "evidence_ids": ["answer-C1"]}])
            self.assertIsNotNone(prepared["lineage"]["discarded_synthesis_sha256"])
            self.assertIsNotNone(prepared["lineage"]["motif_selection_state_sha256"])
            self.assertEqual(prepared["source_dir"], source.resolve())
            (parent / "selection.json").write_text('{"answer":["answer-C2"]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "saved choice differs"):
                prepare_synthesis_resume(parent, local_root=local, output=output,
                                         question="A question", answer_points=points)
            (parent / "selection.json").write_text('{"answer":["answer-C1"]}', encoding="utf-8")
            (source / "paper.md").write_text("Changed source", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                prepare_synthesis_resume(parent, local_root=local, output=output,
                                         question="A question", answer_points=points)

    def test_rejects_non_failure_or_changed_obligation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            local = Path(temporary) / ".local"
            parent = local / "point-research-runs" / "not_failed"
            parent.mkdir(parents=True)
            (parent / "status.json").write_text('{"status":"point_links_present"}')
            with self.assertRaisesRegex(ValueError, "stopped synthesis"):
                prepare_synthesis_resume(parent, local_root=local, output=local,
                                         question="A question", answer_points=[])


if __name__ == "__main__":
    unittest.main()
