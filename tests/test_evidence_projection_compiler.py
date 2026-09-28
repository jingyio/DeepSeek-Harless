"""Certified output views retain evidence, fail closed, and restore exact bytes."""

from __future__ import annotations

import json
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.adapters.motif_output_projection import LatestToolProjector
from src.motif_core.offline.evidence_projection_compiler import compile_evidence_projections
from src.motif_core.offline.trace_compiler import artifact_signature
from src.motif_core.output_view_codecs import marked_html_visible_text_v1


TOOL = "read_email"


def email(title: str, *, unsafe: bool = False) -> str:
    metadata = {"message_id": "abc123", "thread_id": "thread123",
                "source_version": "abc123"}
    html = ("<html><head><style>p{color:black}</style></head><body>"
            f"<h3>{title}</h3><p>Abstract: evidence for the study.</p>"
            '<a href="https://example.test/' + 'very-long-link' * 50 + '">Full text</a>'
            '<img width="1" height="1" src="tracking" />'
            + ('<script>hidden evidence</script>' if unsafe else '')
            + "</body></html>")
    return ("SSS_STRUCTURED_METADATA_V1 " + json.dumps(metadata) + "\n"
            "<untrusted-tool-output>\nThread ID: thread123\r\n"
            "Subject: Research alert\r\n\r\n" + html
            + "\r\n</untrusted-tool-output>")


def artifact_with_projection() -> dict:
    artifact = {"status": "trace_validated_read_only", "tools": [TOOL],
                "source_trace_ids": ["task-a", "task-b"],
                "validation_trace_id": "task-c", "transfer_evidence": []}
    samples, traces = sample_evidence(
        (("task-a", "Paper A"), ("task-b", "Paper B"),
         ("task-c", "Paper C")))
    artifact["output_projections"] = compile_evidence_projections(
        artifact, traces, samples, {TOOL: "marked_html_visible_text_v1"})
    artifact["certified_digest"] = artifact_signature(artifact)
    return artifact


def sample_evidence(rows) -> tuple[dict, dict]:
    samples = {}
    traces = {}
    for trace_id, title in rows:
        sample = {"text": email(title),
                  "observation_sha256": hashlib.sha256(trace_id.encode()).hexdigest()}
        samples[trace_id] = {TOOL: sample}
        traces[trace_id] = SimpleNamespace(records=(SimpleNamespace(
            name=TOOL, eligible=True,
            observation_sha256=sample["observation_sha256"]),))
    return samples, traces


class EvidenceProjectionTest(unittest.TestCase):
    def test_compiler_requires_independent_preserved_evidence(self) -> None:
        artifact = artifact_with_projection()
        rule = artifact["output_projections"][TOOL]
        self.assertEqual(len(rule["proofs"]), 3)
        self.assertTrue(all(row["view_bytes"] < row["original_bytes"]
                            for row in rule["proofs"]))
        repeated, traces = sample_evidence((trace_id, "Same Paper")
                                           for trace_id in ("task-a", "task-b", "task-c"))
        with self.assertRaisesRegex(ValueError, "repeats the same result"):
            compile_evidence_projections(artifact, traces, repeated,
                                         {TOOL: "marked_html_visible_text_v1"})
        repeated["task-c"][TOOL]["observation_sha256"] = "wrong-trace"
        with self.assertRaisesRegex(ValueError, "trace-bound"):
            compile_evidence_projections(artifact, traces, repeated,
                                         {TOOL: "marked_html_visible_text_v1"})

    def test_visible_text_and_headers_survive_without_html_urls(self) -> None:
        view, stats = marked_html_visible_text_v1(email("Paper A"))
        self.assertIn("Paper A", view)
        self.assertIn("Abstract: evidence for the study.", view)
        self.assertIn("Subject: Research alert", view)
        self.assertNotIn("very-long-link", view)
        self.assertLess(stats["view_bytes"], stats["original_bytes"])
        with self.assertRaisesRegex(ValueError, "requiring original"):
            marked_html_visible_text_v1(email("Paper A", unsafe=True))

    def test_runtime_projects_latest_result_and_restores_crlf_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "artifact.json"
            artifact.write_text(json.dumps(artifact_with_projection()))
            projector = LatestToolProjector(artifact, root / "state")
            raw = email("Paper C")
            request = {"messages": [
                {"role": "assistant", "tool_calls": [{"id": "call-1", "type": "function",
                    "function": {"name": TOOL, "arguments": "{}"}}]},
                {"role": "tool", "tool_call_id": "call-1", "content": raw}]}
            projected = projector.project(request)
            view = json.loads(projected["messages"][-1]["content"])["sss_projection"]
            handle = re.search(r"handle=([0-9a-f]{8})", view["restore"]).group(1)
            self.assertIn("Paper C", view["evidence"])
            self.assertEqual(projector.expand(handle), raw)
            self.assertEqual(len(list((root / "state/expansions").iterdir())), 1)
            self.assertEqual(projector.project(request), projected)
            invalid = json.loads(json.dumps(request))
            invalid["messages"][-1]["content"] = email("Paper C", unsafe=True)
            self.assertEqual(projector.project(invalid), invalid)

    def test_signed_but_invalid_projection_proof_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            artifact = artifact_with_projection()
            artifact["output_projections"][TOOL]["proofs"][0]["view_sha256"] = "bad"
            artifact["certified_digest"] = artifact_signature(artifact)
            path = Path(temporary) / "artifact.json"
            path.write_text(json.dumps(artifact))
            with self.assertRaisesRegex(ValueError, "proof is invalid"):
                LatestToolProjector(path, Path(temporary) / "state")


if __name__ == "__main__":
    unittest.main()
