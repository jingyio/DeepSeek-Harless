"""Cross-source retrieval uses a trace-compiled Motif with bounded reentry."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.adapters.dsh_trajectory import mine_dsh_traces
from src.motif_core.handoff import SemanticResolution
from src.motif_core.offline.trace_compiler import certify_read_motif, compile_read_motif
from src.motif_core.read_executor import resume_read_motif, run_read_motif
from src.workflows.motif_research_sources import collect
from src.workflows.research_retrieval_tools import (
    RETRIEVAL_TOOL_CONTRACTS, ResearchRetrievalToolClient, capture_retrieval_trace,
    export_retrieval_state, restore_retrieval_state,
)


class RetrievalMotifTests(unittest.TestCase):
    def test_real_files_compile_reenter_and_reject_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            clients = []
            for index in range(4):
                root = Path(directory) / f"corpus-{index}"
                root.mkdir()
                (root / "one.md").write_text(
                    f"Graph agent evidence in study {index}. The graph agent uses verified tools.",
                    encoding="utf-8")
                (root / "two.md").write_text(
                    f"Study {index} compares graph planning with agent execution.",
                    encoding="utf-8")
                pages, state, _ = collect(root)
                clients.append(ResearchRetrievalToolClient(root, pages, state))
            traces = [capture_retrieval_trace(
                client, point_id=f"point-{index}", question="How does graph agent work?",
                terms=["graph", "agent"], source_allowlist=["one.md", "two.md"])
                for index, client in enumerate(clients[:3])]
            candidate = next(row for row in mine_dsh_traces(traces[:2])
                             if row["tools"] == ["snapshot_sources", "retrieve_point"])
            artifact = certify_read_motif(
                compile_read_motif(candidate, traces[:2], RETRIEVAL_TOOL_CONTRACTS),
                traces[2], RETRIEVAL_TOOL_CONTRACTS)
            client = clients[3]
            entry = {"source_dir": str(client.root), "point_id": "new-point",
                     "question": "How does graph agent work?",
                     "source_allowlist": ["one.md", "two.md"], "min_sources": 1}
            common = {"contracts": RETRIEVAL_TOOL_CONTRACTS,
                      "input_version": client.snapshot_digest,
                      "execute_tool": client.execute,
                      "verify_current": client.verify_current,
                      "is_read_only": lambda tool: tool in RETRIEVAL_TOOL_CONTRACTS}
            blocked = run_read_motif(
                artifact, bindings={"snapshot_sources": {"source_dir": str(client.root),
                                                       "input_version": client.snapshot_digest},
                                    "retrieve_point": entry}, **common)
            self.assertEqual(blocked.status, "needs_mediation")
            self.assertEqual(blocked.handoff.missing_params, {"retrieve_point": ["terms"]})
            signature = hashlib.sha256(json.dumps(
                blocked.handoff.to_dict(), sort_keys=True, ensure_ascii=False,
                separators=(",", ":")).encode()).hexdigest()
            resolution = SemanticResolution(
                resolution_type="slot_fill",
                slot_values={"retrieve_point": {"terms": ["graph", "agent"]}},
                metadata={"handoff_signature": signature})
            resumed = resume_read_motif(
                artifact, blocked, resolution,
                **{key: value for key, value in common.items()
                   if key != "input_version"})
            self.assertEqual(resumed.status, "completed")
            actual = resumed.outputs["retrieve_point"]["evidence"]
            direct = client.execute("retrieve_point", {
                **entry, "terms": ["graph", "agent"],
                "snapshot_sha256": client.snapshot_digest})["evidence"]
            self.assertEqual(actual, direct)
            self.assertGreaterEqual(len({row["source"] for row in actual}), 1)
            state = export_retrieval_state(resumed.manager, client=client,
                                           artifact=artifact)
            recovered, state_events = restore_retrieval_state(
                state, client=client, artifact=artifact)
            self.assertEqual(state_events[0]["event"], "retrieval_state_restored")
            called = []
            cached_run = run_read_motif(
                artifact, contracts=RETRIEVAL_TOOL_CONTRACTS,
                bindings={"snapshot_sources": {"source_dir": str(client.root),
                                               "input_version": client.snapshot_digest},
                          "retrieve_point": {**entry, "terms": ["graph", "agent"]}},
                input_version=client.snapshot_digest,
                execute_tool=lambda tool, params: (
                    called.append(tool) or client.execute(tool, params)),
                verify_current=client.verify_current,
                is_read_only=lambda tool: tool in RETRIEVAL_TOOL_CONTRACTS,
                manager=recovered)
            self.assertEqual(cached_run.status, "completed")
            self.assertEqual(called, [])
            self.assertEqual(cached_run.outputs["retrieve_point"]["evidence"], actual)
            self.assertGreaterEqual(sum(row["event"] == "dependency_cache_hit"
                                        for row in cached_run.events), 2)
            (client.root / "one.md").write_text("The source changed.", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                run_read_motif(
                    artifact, bindings={"snapshot_sources": {"source_dir": str(client.root),
                                                           "input_version": client.snapshot_digest},
                                        "retrieve_point": {**entry,
                                                           "terms": ["graph", "agent"]}},
                    **common)
            new_pages, new_source_state, _ = collect(client.root)
            new_client = ResearchRetrievalToolClient(
                client.root, new_pages, new_source_state)
            invalidated, events = restore_retrieval_state(
                state, client=new_client, artifact=artifact)
            self.assertEqual(events[0]["event"], "retrieval_snapshot_invalidated")
            self.assertEqual(len(invalidated.evidence.records), 0)


if __name__ == "__main__":
    unittest.main()
