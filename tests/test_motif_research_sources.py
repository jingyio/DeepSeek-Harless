"""Incremental source evidence must follow the current files, not old state."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.adapters.dsh_trajectory import mine_dsh_traces
from src.graph.runtime import Evidence, execute
from src.motif_core.offline.trace_compiler import certify_read_motif, compile_read_motif
from src.workflows.motif_research_sources import collect, verify_source_snapshot
from src.workflows.research_source_tools import SOURCE_TOOL_CONTRACTS, capture_source_read_trace
from src.workflows.research_retrieval_tools import ResearchRetrievalToolClient
from src.workflows.research import POINT_PAGE_PASSAGES_MOTIF


class MotifResearchSourceTests(unittest.TestCase):
    def test_numeric_profile_survives_neighborhood_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "runs.json").write_text(json.dumps([
                {"metric": {f"field_{i}": i + row for i in range(20)}, "reward": row}
                for row in (0, 1)]), encoding="utf-8")
            (root / "paper.md").write_text("a " * 6000 + "Figure evidence " + "b " * 6000,
                                           encoding="utf-8")
            pages, _, _ = collect(root)
            derived = next(page for page in pages if page.get("evidence_kind") == "derived_numeric_summary")
            paper = next(page for page in pages if page["source"] == "paper.md")
            chosen = {
                "numeric": [{**derived, "snippet": "metric.field_0: count=2"}],
                "figure": [{**paper, "snippet": "Figure evidence"}],
            }
            run = execute(POINT_PAGE_PASSAGES_MOTIF, {
                "validated_answer_points": Evidence([
                    {"id": "numeric", "requirement": "Check every metric and the reward"},
                    {"id": "figure", "requirement": "Check the Figure evidence"},
                ], "test_points"),
                "selected_evidence_by_point": Evidence(chosen, "test_selection"),
                "unique_pages": Evidence(pages, "hash_bound_pages"),
                "source_dir": Evidence(str(root.resolve()), "test_root"),
            })
            self.assertEqual(run.status, "completed")
            self.assertEqual(run.state["passage_packaging"].value["mode"],
                             "selected_page_neighborhoods")
            text = "".join(row["snippet"] for row in run.state["point_passages"].value["numeric"])
            self.assertIn("metric.field_19: count=2, sum=39", text)
            self.assertIn("reward: count=2, sum=1", text)

    def test_three_numeric_sources_keep_derived_summaries_visible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, base in (("alpha.json", 10), ("beta.json", 20), ("gamma.json", 30)):
                rows = [{"metrics": {"calls": base + index, "tokens": 100 + index}}
                        for index in range(5)]
                (root / name).write_text(json.dumps(rows), encoding="utf-8")
            pages, state, _ = collect(root)
            client = ResearchRetrievalToolClient(root, pages, state)
            result = client.execute("retrieve_point", {
                "source_dir": str(client.root), "snapshot_sha256": client.snapshot_digest,
                "point_id": "three_groups", "question": "Aggregate calls and tokens in three groups",
                "terms": ["metrics.calls", "metrics.tokens"],
                "source_allowlist": ["alpha.json", "beta.json", "gamma.json"],
                "min_sources": 3,
            })
            first = result["evidence"][:3]
            self.assertEqual({row["source"] for row in first},
                             {"alpha.json", "beta.json", "gamma.json"})
            self.assertTrue(all(row.get("evidence_kind") == "derived_numeric_summary"
                                for row in first))

    def test_json_numeric_summaries_are_derived_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "runs.json"
            source.write_text('[{"reward": 1, "metrics": {"tokens": 10}, "flag": true}, '
                              '{"reward": 0, "metrics": {"tokens": 20}, "flag": false}]',
                              encoding="utf-8")
            pages, state, _ = collect(root)
            self.assertEqual([row["page"] for row in pages], [1, 2, 3])
            summary = pages[-1]
            self.assertEqual(summary["evidence_kind"], "derived_numeric_summary")
            self.assertEqual(summary["derived_from_pages"], [1, 2])
            self.assertEqual(summary["numeric_fields"]["metrics.tokens"],
                             {"count": 2, "sum": "30", "mean": "15"})
            self.assertIn("metrics.tokens: count=2, sum=30, mean=15", summary["text"])
            self.assertIn("reward: count=2, sum=1, mean=0.5", summary["text"])
            self.assertNotIn("flag:", summary["text"])
            client = ResearchRetrievalToolClient(root, pages, state)
            result = client.execute("retrieve_point", {
                "source_dir": str(client.root), "snapshot_sha256": client.snapshot_digest,
                "point_id": "numeric", "question": "What are the reward and token totals?",
                "terms": ["reward", "metrics.tokens"], "source_allowlist": ["runs.json"],
                "min_sources": 1,
            })
            self.assertTrue(any(row.get("evidence_kind") == "derived_numeric_summary"
                                for row in result["evidence"]))
            verify_source_snapshot(root, state)
            source.write_text(source.read_text().replace('"tokens": 20', '"tokens": 21'))
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                verify_source_snapshot(root, state)
            changed, _, events = collect(root, state)
            self.assertIn("metrics.tokens: count=2, sum=31, mean=15.5", changed[-1]["text"])
            self.assertTrue(any(row["event"] == "source_invalidated" for row in events))

    def test_large_integer_sum_is_not_rounded_by_decimal_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            large = 1234567890123456789012345678901234567890
            (root / "runs.json").write_text(json.dumps([{"tokens": large},
                                                       {"tokens": large}]), encoding="utf-8")
            pages, _, _ = collect(root)
            summary = next(row for row in pages
                           if row.get("evidence_kind") == "derived_numeric_summary")
            self.assertEqual(summary["numeric_fields"]["tokens"]["sum"], str(large * 2))

    def test_json_array_records_are_individually_citable_and_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "runs.json"
            source.write_text('[{"passed": true}, {"passed": false}]', encoding="utf-8")
            pages, state, _ = collect(root)
            self.assertEqual([(row["source"], row["page"]) for row in pages],
                             [("runs.json", 1), ("runs.json", 2)])
            self.assertIn('"passed": true', pages[0]["text"])
            verify_source_snapshot(root, state)
            source.write_text('[{"passed": false}, {"passed": false}]', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                verify_source_snapshot(root, state)
            updated, _, events = collect(root, state)
            self.assertIn('"passed": false', updated[0]["text"])
            self.assertTrue(any(row["event"] == "source_invalidated" for row in events))

    def test_reuse_change_and_removal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.md").write_text("A result is 12 of 20.", encoding="utf-8")
            (root / "b.txt").write_text("B result is 15 of 20.", encoding="utf-8")
            pages_a, state_a, events_a = collect(root)
            self.assertEqual(len(pages_a), 2)
            self.assertEqual(sum(row["event"] == "source_read" for row in events_a), 2)

            pages_same, state_same, events_same = collect(root, state_a)
            self.assertEqual(pages_same, pages_a)
            self.assertEqual(state_same["resume_count"], 1)
            self.assertEqual(sum(row["event"] == "source_reused" for row in events_same), 2)

            (root / "a.md").write_text("A corrected result is 11 of 20.", encoding="utf-8")
            (root / "b.txt").unlink()
            pages_changed, state_changed, events_changed = collect(root, state_same)
            self.assertEqual([row["source"] for row in pages_changed], ["a.md"])
            self.assertIn("11 of 20", pages_changed[0]["text"])
            self.assertFalse(any("12 of 20" in str(row) for row in state_changed["evidence"]))
            self.assertEqual([row["source"] for row in events_changed if row["event"] == "source_invalidated"],
                             ["a.md", "b.txt"])
            self.assertEqual([row["source"] for row in events_changed if row["event"] == "source_read"],
                             ["a.md"])

    def test_state_cannot_cross_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            first.mkdir()
            second.mkdir()
            (first / "same.md").write_text("Same text", encoding="utf-8")
            (second / "same.md").write_text("Same text", encoding="utf-8")
            _, state, _ = collect(first)
            with self.assertRaisesRegex(ValueError, "different directory"):
                collect(second, state)

    def test_parser_revision_invalidates_previous_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "paper.md").write_text("A source passage", encoding="utf-8")
            _, state, _ = collect(root)
            state["parser_version"] += 1
            with self.assertRaisesRegex(ValueError, "unsupported Motif research source state"):
                collect(root, state)

    def test_source_snapshot_detects_change_before_semantic_reentry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "paper.md"
            source.write_text("Original evidence", encoding="utf-8")
            _, state, _ = collect(root)
            verify_source_snapshot(root, state)
            source.write_text("Revised evidence", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                verify_source_snapshot(root, state)
            source.write_text("Original evidence", encoding="utf-8")
            (root / "new.md").write_text("New evidence", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                verify_source_snapshot(root, state)

    def test_trace_compiled_motif_reads_and_incrementally_reuses_new_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            training = []
            for name, text in (("a.md", "Alpha source"), ("b.md", "Beta source"),
                               ("c.md", "Gamma source")):
                path = root / name
                path.write_text(text, encoding="utf-8")
                training.append(capture_source_read_trace(path))
            candidate = mine_dsh_traces(training[:2])[0]
            compiled = compile_read_motif(candidate, training[:2], SOURCE_TOOL_CONTRACTS)
            artifact = certify_read_motif(compiled, training[2], SOURCE_TOOL_CONTRACTS)
            task = root / "new_task"
            task.mkdir()
            (task / "d.md").write_text("Delta source", encoding="utf-8")
            pages, state, events = collect(task, read_motif_artifact=artifact)
            self.assertEqual(pages[0]["text"], "Delta source")
            self.assertEqual(sum(row["event"] == "compiled_motif_execution" for row in events), 1)
            (task / "e.md").write_text("Epsilon source", encoding="utf-8")
            updated, _, updated_events = collect(task, state, read_motif_artifact=artifact)
            baseline, _, _ = collect(task)
            self.assertEqual(updated, baseline)
            with self.assertRaisesRegex(ValueError, "different Motif artifact"):
                collect(task, state)
            self.assertEqual([row["source"] for row in updated_events
                              if row["event"] == "source_reused"], ["d.md"])
            self.assertEqual([row["source"] for row in updated_events
                              if row["event"] == "source_read"], ["e.md"])


if __name__ == "__main__":
    unittest.main()
