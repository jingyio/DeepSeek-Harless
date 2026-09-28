"""Check the offline audit's temporal and version bindings."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit-motif-pdf-evidence.py"
SPEC = importlib.util.spec_from_file_location("motif_pdf_audit", SCRIPT)
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


def call(seq: int, call_id: str, name: str, arguments: dict) -> dict:
    return {"seq": seq, "type": "tool/call", "data": {
        "callId": call_id, "name": "mcp__scoped_research_read__" + name,
        "arguments": json.dumps(arguments)}}


def result(seq: int, call_id: str, value: dict) -> dict:
    return {"seq": seq, "type": "tool/result", "data": {"message": {
        "source": {"callId": call_id}, "content": [{"isError": False,
            "content": [{"type": "text", "text": json.dumps(value)}]}]}}}


class EvidenceAuditTest(unittest.TestCase):
    def test_locator_requires_prior_matching_handle_and_source_version(self) -> None:
        quote = "An exact observation with enough characters"
        page = {"pdf_page": 2, "text": "Intro. " + quote + ". End.",
                "total_chars": 58, "truncated": False, "low_text": False}
        events = [
            call(1, "read-a", "read_pinned_pdf_match", {"match_id": "h"}),
            result(2, "read-a", {"match_id": "h", "sha256": "v1", "pages": [page]}),
            call(3, "loc", "locate_pinned_pdf_quote", {"quote": quote}),
            result(4, "loc", {"status": "unique", "match_id": "h", "sha256": "v1"}),
            call(5, "read-b", "read_pinned_pdf_match", {"match_id": "h"}),
            result(6, "read-b", {"match_id": "h", "sha256": "v2", "pages": [page]}),
            call(7, "read-c", "read_pinned_pdf_match", {"match_id": "h"}),
            result(8, "read-c", {"match_id": "h", "sha256": "v1", "pages": [page]}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in events),
                            encoding="utf-8")
            report = audit_module.audit(path)
        self.assertEqual(report["locator_unique_reads"], 1)
        self.assertEqual(report["locator_matched_pages"], 1)
        self.assertNotIn(quote, json.dumps(report))

    def test_unmatched_and_future_annotation_cannot_anchor_page(self) -> None:
        quote = "Earlier exact quote that appears on the page"
        page = {"pdf_page": 1, "text": quote + " remaining page text"}
        events = [
            call(1, "page", "read_pinned_pdf_pages", {}),
            result(2, "page", {"pages": [page]}),
            call(3, "annotation", "read_pinned_zotero_annotation", {}),
            result(4, "annotation", {"marked_text": quote,
                                     "marked_truncated": False}),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in events),
                            encoding="utf-8")
            report = audit_module.audit(path)
        self.assertEqual(report["matched_pages"], 0)


if __name__ == "__main__":
    unittest.main()
