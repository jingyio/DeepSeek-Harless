"""Native Harness SSS tools reuse the certified core and reject stale reads."""

import json
import tempfile
import unittest
from pathlib import Path

from src.adapters.dsh_trajectory import mine_dsh_traces
from src.mcp.sss_runtime_server import ROOT, ResearchRuntime
from src.motif_core.offline.trace_compiler import certify_read_motif, compile_read_motif
from src.workflows.research_source_tools import (
    SOURCE_TOOL_CONTRACTS, capture_source_read_trace,
)
from src.workflows.motif_research_sources import collect
from src.workflows.research_retrieval_tools import (
    RETRIEVAL_TOOL_CONTRACTS, ResearchRetrievalToolClient,
    capture_retrieval_trace,
)


class ResearchRuntimeTests(unittest.TestCase):
    def test_certified_native_entry_and_source_invalidation(self):
        local = ROOT / ".local"
        local.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local) as temporary:
            base = Path(temporary)
            training = base / "training"
            current = base / "current"
            training.mkdir()
            current.mkdir()
            paths = []
            for name, body in (("a.md", "Alpha method."),
                               ("b.md", "Beta method."),
                               ("c.md", "Gamma method.")):
                path = training / name
                path.write_text(body, encoding="utf-8")
                paths.append(path)
            traces = [capture_source_read_trace(path) for path in paths[:2]]
            candidate = next(row for row in mine_dsh_traces(traces)
                             if row["tools"] == ["hash_source", "read_source"])
            compiled = compile_read_motif(candidate, traces,
                                          SOURCE_TOOL_CONTRACTS)
            artifact = certify_read_motif(
                compiled, capture_source_read_trace(paths[2]),
                SOURCE_TOOL_CONTRACTS)
            artifact_path = base / "source-motif.json"
            artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
            retrieval_traces = []
            for index in range(3):
                corpus = base / f"retrieval-training-{index}"
                corpus.mkdir()
                (corpus / "paper.md").write_text(
                    f"Research idea and graph study {index}.", encoding="utf-8")
                training_pages, training_state, _ = collect(corpus)
                client = ResearchRetrievalToolClient(
                    corpus, training_pages, training_state)
                retrieval_traces.append(capture_retrieval_trace(
                    client, point_id=f"point-{index}", question="What is research?",
                    terms=["research", "idea"], source_allowlist=["paper.md"]))
            retrieval_candidate = next(row for row in mine_dsh_traces(
                retrieval_traces[:2]) if row["tools"] ==
                ["snapshot_sources", "retrieve_point"])
            retrieval_artifact = certify_read_motif(
                compile_read_motif(retrieval_candidate, retrieval_traces[:2],
                                   RETRIEVAL_TOOL_CONTRACTS),
                retrieval_traces[2], RETRIEVAL_TOOL_CONTRACTS)
            retrieval_path = base / "retrieval-motif.json"
            retrieval_path.write_text(json.dumps(retrieval_artifact),
                                      encoding="utf-8")
            (current / "new.md").write_text("A new research idea.", encoding="utf-8")
            runtime = ResearchRuntime(current, artifact_path, base / "runs",
                                      retrieval_path)
            result = runtime.collect_sources()
            self.assertEqual(result["model_requests"], 0)
            self.assertEqual(result["structural_events"], 1)
            self.assertEqual(result["source_reads"], 1)
            self.assertEqual(result["source_reuses"], 0)
            self.assertEqual(result["sources"], [{"name": "new.md", "pages": 1}])
            restarted = ResearchRuntime(current, artifact_path, base / "runs",
                                        retrieval_path)
            self.assertEqual(restarted.collect_sources()["run_id"], result["run_id"])
            page = runtime.read_page(result["run_id"], "new.md", 1, limit=8)
            self.assertEqual(page["text"], "A new re")
            self.assertEqual(page["next_offset"], 8)
            frontier = runtime.open_point(result["run_id"], "P1",
                                          "What does this idea say?", ["new.md"])
            self.assertEqual(frontier["status"], "needs_semantic_terms")
            self.assertEqual(frontier["handoff"]["missing_params"],
                             {"retrieve_point": ["terms"]})
            self.assertEqual(restarted.open_point(
                result["run_id"], "P1", "What does this idea say?", ["new.md"]
            )["frontier_id"], frontier["frontier_id"])
            frontier_path = (base / "runs" / result["run_id"] / "frontiers" /
                             f"{frontier['frontier_id']}.json")
            saved_frontier = frontier_path.read_text(encoding="utf-8")
            changed_frontier = json.loads(saved_frontier)
            changed_frontier["checkpoint"]["bindings"]["retrieve_point"]["question"] = "altered"
            frontier_path.write_text(json.dumps(changed_frontier), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "saved SSS frontier changed"):
                runtime.resolve_point(result["run_id"], frontier["frontier_id"], "P1",
                                      "What does this idea say?", ["new.md"],
                                      frontier["handoff_signature"], ["research", "idea"])
            frontier_path.write_text(saved_frontier, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no longer matches"):
                runtime.resolve_point(result["run_id"], frontier["frontier_id"], "P1",
                                      "What does this idea say?", ["new.md"],
                                      "bad-signature", ["research", "idea"])
            resumed_runtime = ResearchRuntime(current, artifact_path, base / "runs",
                                              retrieval_path)
            point = resumed_runtime.resolve_point(
                result["run_id"], frontier["frontier_id"], "P1", "What does this idea say?",
                ["new.md"], frontier["handoff_signature"], ["research", "idea"])
            self.assertEqual(point["status"], "retrieved")
            self.assertGreaterEqual(len(point["evidence"]), 1)
            self.assertEqual(point["sss_model_requests"], 0)
            refreshed = runtime.refresh_sources(result["run_id"])
            self.assertEqual(refreshed["source_reuses"], 1)
            self.assertEqual(refreshed["source_reads"], 0)
            self.assertEqual(restarted.refresh_sources(result["run_id"])["run_id"],
                             refreshed["run_id"])
            with self.assertRaisesRegex(ValueError, "invalid bounded"):
                runtime.read_page("../escape", "new.md", 1)
            (current / "new.md").write_text("Changed idea.", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "changed"):
                runtime.read_page(result["run_id"], "new.md", 1)
            with self.assertRaisesRegex(ValueError, "changed"):
                runtime.resolve_point(
                    result["run_id"], frontier["frontier_id"], "P1", "What does this idea say?",
                    ["new.md"], frontier["handoff_signature"], ["research", "idea"])
            updated = runtime.refresh_sources(refreshed["run_id"])
            self.assertNotEqual(updated["run_id"], refreshed["run_id"])
            self.assertEqual(updated["source_reads"], 1)
            self.assertEqual(updated["source_reuses"], 0)
            self.assertEqual(runtime.read_page(updated["run_id"], "new.md", 1)["text"],
                             "Changed idea.")
            stored = base / "runs" / updated["run_id"] / "evidence.json"
            record = json.loads(stored.read_text(encoding="utf-8"))
            record["pages"][0]["text"] = "altered evidence"
            stored.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "saved research evidence changed"):
                runtime.read_page(updated["run_id"], "new.md", 1)
            with self.assertRaisesRegex(ValueError, "saved research evidence changed"):
                runtime.refresh_sources(updated["run_id"])


if __name__ == "__main__":
    unittest.main()
