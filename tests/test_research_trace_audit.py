"""Regression checks for source coverage and answer completion audits."""

from __future__ import annotations

import json
import unittest
from copy import deepcopy

from src.adapters.research_trace_audit import (
    audit_events, audit_metrics, check_arxiv_versions, check_scoped_line_claims,
)


def pair(index: int, name: str, args: dict, result: dict, *, error: bool = False) -> list[dict]:
    call_id = f"call-{index}"
    return [{"type": "tool/call", "data": {"callId": call_id, "name": name,
             "arguments": json.dumps(args)}},
            {"type": "tool/result", "data": {"message": {
                "source": {"callId": call_id},
                "content": [{"type": "tool-result", "isError": error,
                             "content": [{"type": "text", "text": json.dumps(result)}]}]}}}]


class ResearchTraceAuditTests(unittest.TestCase):
    def test_compaction_replacement_cannot_invent_source_coverage(self) -> None:
        original = pair(1, "mcp__scoped_research_read__read_pinned_text",
                        {"source_id": "source-id"},
                        {"role": "paper", "sha256": "version-a",
                         "numbered_text": "71: observed"})
        replacement = deepcopy(original[1])
        replacement["surfaceOp"] = {"op": "replace", "startSeq": 2, "endSeq": 2}
        replacement["sourceEventSeqs"] = [2]
        replacement["data"]["message"]["content"][0]["content"][0]["text"] = json.dumps(
            {"role": "paper", "sha256": "version-a", "numbered_text": "999: forged"})
        audited = audit_events(original + [replacement])
        self.assertEqual(audited["tool_calls"], 1)
        self.assertEqual(audited["scoped_line_reads"][0]["line_ranges"], [[71, 71]])

    def test_coverage_uses_returned_lines_and_pages_not_requested_span(self) -> None:
        events = (
            pair(1, "mcp__scoped_research_read__read_scoped_text",
                 {"role": "week6", "start_line": 71, "max_lines": 100},
                 {"role": "week6", "sha256": "sha", "start_line": 71,
                  "next_line": 161, "numbered_text": "71: first\n72: second\n160: last"})
            + pair(2, "mcp__scoped_research_read__read_scoped_pdf_pages",
                   {"role": "week7", "start_page": 1},
                   {"role": "week7", "sha256": "pdf", "pages": [
                       {"pdf_page": 1, "text": "first"}, {"pdf_page": 2, "text": "second"}]})
        )
        audited = audit_events(events)
        self.assertEqual(audited["scoped_line_reads"][0]["line_ranges"],
                         [[71, 72], [160, 160]])
        self.assertEqual(audited["scoped_pdf_reads"][0]["pages"], [1, 2])

    def test_version_citation_requires_pin_or_separate_sha_match(self) -> None:
        events = pair(1, "mcp__literature_discovery__read_arxiv_pdf_pages",
                      {"arxiv_id": "2409.07429"},
                      {"arxiv_id": "2409.07429", "sha256": "abc",
                       "version_pinned": False, "pages": [{"pdf_page": 1}]})
        reads = audit_events(events)["arxiv_pdf_reads"]
        answer = "见 arXiv:2409.07429v1 第 1 页；另见 2501.00663v2。"
        statuses = check_arxiv_versions(answer, reads)
        self.assertEqual(statuses, [
            {"cited_id": "2409.07429v1", "status": "observed_unpinned_version_unknown"},
            {"cited_id": "2501.00663v2", "status": "no_pdf_read"},
        ])
        verified = check_arxiv_versions(answer, reads, {"2409.07429v1": "abc"})
        self.assertEqual(verified[0]["status"], "posthoc_sha_match")

    def test_structured_provider_failure_and_max_tokens_are_not_success(self) -> None:
        events = pair(1, "mcp__literature_discovery__search_arxiv", {"query": "topic"},
                      {"status": "unavailable", "results": []})
        audit = audit_events(events)
        self.assertEqual(audit["failed_tool_results"],
                         {"mcp__literature_discovery__search_arxiv": 1})
        metrics = audit_metrics([{"status": "done", "finish_reason": "max-tokens",
                                  "model_requests": 1, "totalTokens": 3000},
                                 {"status": "done", "finish_reason": "completed",
                                  "model_requests": 1, "totalTokens": 1000}])
        self.assertEqual([row["complete"] for row in metrics["runs"]], [False, True])
        self.assertEqual(metrics["total_tokens"], 4000)

    def test_zotero_read_is_recorded_without_annotation_text(self) -> None:
        events = pair(1, "mcp__scoped_zotero_read__read_pinned_zotero_annotation",
                      {"source_id": "source-id"},
                      {"role": "margin_note", "key": "EFGH5678", "version": 3,
                       "data_sha256": "digest", "marked_text": "private text"})
        rows = audit_events(events)["zotero_reads"]
        self.assertEqual(rows, [{"role": "margin_note", "key": "EFGH5678",
                                 "tool": "read_pinned_zotero_annotation", "version": 3,
                                 "data_sha256": "digest"}])
        self.assertNotIn("private text", json.dumps(rows))

    def test_registered_read_claims_find_false_unread_and_unsupported_read(self) -> None:
        reads = [{"role": "week6", "sha256": "digest", "line_ranges": [[1, 10]]}]
        claims = [{"role": "week6", "sha256": "digest", "start_line": 2,
                   "end_line": 5, "assertion": "none_read"},
                  {"role": "week6", "sha256": "digest", "start_line": 8,
                   "end_line": 12, "assertion": "all_read"}]
        result = check_scoped_line_claims(claims, reads)
        self.assertEqual([row["status"] for row in result],
                         ["contradicted", "not_established"])
        self.assertEqual([row["observed_line_count"] for row in result], [4, 3])


if __name__ == "__main__":
    unittest.main()
