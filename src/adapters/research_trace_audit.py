"""Mechanical source-coverage audit for private DSH research traces.

This module checks what the Agent actually read and whether a turn completed.
It deliberately makes no judgment about whether a passage supports a claim.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .dsh_event_projection import is_original_tool_result

ARXIV_VERSION = re.compile(r"\b(\d{4}\.\d{4,5})v(\d+)\b")
NUMBERED_LINE = re.compile(r"^(\d+):", re.MULTILINE)


def _tool_payload(event: Mapping[str, Any]) -> tuple[bool, dict[str, Any] | None]:
    """Return tool success and its JSON object, if any, without source text."""
    data = event.get("data")
    message = data.get("message") if isinstance(data, dict) else None
    blocks = message.get("content") if isinstance(message, dict) else None
    if not isinstance(blocks, list) or len(blocks) != 1:
        return False, None
    block = blocks[0]
    if not isinstance(block, dict) or block.get("isError") is True:
        return False, None
    content = block.get("content")
    if not isinstance(content, list) or len(content) != 1:
        return False, None
    text = content[0].get("text") if isinstance(content[0], dict) else None
    if not isinstance(text, str) or text.startswith("Error:"):
        return False, None
    try:
        payload = json.loads(text)
    except ValueError:
        return True, None
    if not isinstance(payload, dict):
        return True, None
    if isinstance(payload.get("status"), str) and payload["status"] in {"unavailable", "error", "failed"}:
        return False, payload
    return True, payload


def _merge_numbers(numbers: Iterable[int]) -> list[list[int]]:
    ordered = sorted(set(numbers))
    merged: list[list[int]] = []
    for number in ordered:
        if not merged or number > merged[-1][1] + 1:
            merged.append([number, number])
        else:
            merged[-1][1] = number
    return merged


def audit_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize successful reads from paired tool events in one or more turns."""
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    counts: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    line_reads: dict[tuple[str, str], set[int]] = defaultdict(set)
    page_reads: dict[tuple[str, str], set[int]] = defaultdict(set)
    arxiv_reads: dict[tuple[str, str], dict[str, Any]] = {}
    pmc_reads: set[tuple[str, str, str]] = set()
    zotero_reads: set[tuple[str, str, str, int, str]] = set()
    for event in events:
        kind = event.get("type")
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        if kind == "tool/call":
            call_id, name = data.get("callId"), data.get("name")
            if not isinstance(call_id, str) or not isinstance(name, str):
                continue
            try:
                args = json.loads(data.get("arguments", ""))
            except (TypeError, ValueError):
                args = {}
            calls[call_id] = name, args if isinstance(args, dict) else {}
            counts[name] += 1
        elif kind == "tool/result" and is_original_tool_result(event):
            message = data.get("message")
            source = message.get("source") if isinstance(message, dict) else None
            call_id = source.get("callId") if isinstance(source, dict) else None
            if call_id not in calls:
                continue
            name, _args = calls[call_id]
            success, payload = _tool_payload(event)
            if not success:
                failures[name] += 1
                continue
            if payload is None:
                continue
            if name.endswith(("read_scoped_text", "read_scoped_note",
                              "read_pinned_text", "read_pinned_note")):
                role, digest = payload.get("role"), payload.get("sha256")
                if isinstance(role, str) and isinstance(digest, str):
                    line_reads[role, digest].update(
                        int(match.group(1)) for match in NUMBERED_LINE.finditer(
                            str(payload.get("numbered_text", ""))))
            elif name.endswith(("read_scoped_pdf_pages", "read_pinned_pdf_pages")):
                role, digest = payload.get("role"), payload.get("sha256")
                if isinstance(role, str) and isinstance(digest, str):
                    page_reads[role, digest].update(
                        page["pdf_page"] for page in payload.get("pages", [])
                        if isinstance(page, dict) and isinstance(page.get("pdf_page"), int))
            elif name.endswith("read_arxiv_pdf_pages"):
                paper_id, digest = payload.get("arxiv_id"), payload.get("sha256")
                if isinstance(paper_id, str) and isinstance(digest, str):
                    key = paper_id, digest
                    record = arxiv_reads.setdefault(key, {"arxiv_id": paper_id,
                        "sha256": digest, "version_pinned": bool(payload.get("version_pinned")),
                        "pages": set()})
                    record["pages"].update(
                        page["pdf_page"] for page in payload.get("pages", [])
                        if isinstance(page, dict) and isinstance(page.get("pdf_page"), int))
            elif name.endswith("read_europe_pmc_section"):
                pmcid, section, digest = (payload.get("pmcid"), payload.get("section_id"),
                                          payload.get("sha256"))
                if all(isinstance(value, str) for value in (pmcid, section, digest)):
                    pmc_reads.add((pmcid, section, digest))
            elif name.endswith(("read_pinned_zotero_item", "read_pinned_zotero_annotation")):
                role, key, digest, version = (payload.get("role"), payload.get("key"),
                                              payload.get("data_sha256"), payload.get("version"))
                if (all(isinstance(value, str) for value in (role, key, digest))
                        and type(version) is int):
                    zotero_reads.add((role, key, name.rsplit("__", 1)[-1], version, digest))
    return {
        "tool_calls": sum(counts.values()),
        "mcp_calls": sum(count for name, count in counts.items() if name.startswith("mcp__")),
        "tool_counts": dict(sorted(counts.items())),
        "failed_tool_results": dict(sorted(failures.items())),
        "scoped_line_reads": [{"role": role, "sha256": digest,
                               "line_ranges": _merge_numbers(numbers)}
                              for (role, digest), numbers in sorted(line_reads.items())],
        "scoped_pdf_reads": [{"role": role, "sha256": digest,
                              "pages": sorted(numbers)}
                             for (role, digest), numbers in sorted(page_reads.items())],
        "arxiv_pdf_reads": [{**{key: value for key, value in row.items() if key != "pages"},
                             "pages": sorted(row["pages"])}
                            for _key, row in sorted(arxiv_reads.items())],
        "europe_pmc_reads": [{"pmcid": pmcid, "section_id": section,
                              "sha256": digest}
                             for pmcid, section, digest in sorted(pmc_reads)],
        "zotero_reads": [{"role": role, "key": key, "tool": tool,
                           "version": version, "data_sha256": digest}
                          for role, key, tool, version, digest in sorted(zotero_reads)],
    }


def check_arxiv_versions(answer: str, reads: Iterable[Mapping[str, Any]],
                         exact_version_hashes: Mapping[str, str] | None = None
                         ) -> list[dict[str, Any]]:
    """Check version mentions against observed exact IDs or post-hoc PDF hashes."""
    hashes = exact_version_hashes or {}
    rows = list(reads)
    found: list[dict[str, Any]] = []
    for base, version in sorted(set(ARXIV_VERSION.findall(answer))):
        cited = f"{base}v{version}"
        exact = [row for row in rows if row.get("arxiv_id") == cited
                 and row.get("version_pinned") is True]
        base_reads = [row for row in rows if row.get("arxiv_id") == base]
        if exact:
            status = "observed_exact_version"
        elif cited in hashes and any(row.get("sha256") == hashes[cited]
                                     for row in base_reads):
            status = "posthoc_sha_match"
        elif base_reads:
            status = "observed_unpinned_version_unknown"
        else:
            status = "no_pdf_read"
        found.append({"cited_id": cited, "status": status})
    return found


def check_scoped_line_claims(claims: Iterable[Mapping[str, Any]],
                             reads: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Check registered read/unread claims against lines returned by tools.

    A human or separate reviewer must identify the claim and exact source span.
    This function does not infer meaning from the answer text.
    """
    by_source: dict[tuple[str, str], set[int]] = defaultdict(set)
    for row in reads:
        role, digest = row.get("role"), row.get("sha256")
        if not isinstance(role, str) or not isinstance(digest, str):
            continue
        for span in row.get("line_ranges", []):
            if (isinstance(span, list) and len(span) == 2
                    and all(type(value) is int for value in span)):
                by_source[role, digest].update(range(span[0], span[1] + 1))
    checked = []
    for claim in claims:
        role, digest, start, end, assertion = (
            claim.get("role"), claim.get("sha256"), claim.get("start_line"),
            claim.get("end_line"), claim.get("assertion"))
        if (not isinstance(role, str) or not isinstance(digest, str)
                or type(start) is not int or type(end) is not int
                or not 1 <= start <= end or end - start > 10000
                or assertion not in {"all_read", "none_read"}):
            raise ValueError("invalid scoped line coverage claim")
        covered = by_source[role, digest].intersection(range(start, end + 1))
        if assertion == "all_read":
            status = "supported" if len(covered) == end - start + 1 else "not_established"
        else:
            status = "contradicted" if covered else "not_established"
        checked.append({"role": role, "sha256": digest,
                        "start_line": start, "end_line": end, "assertion": assertion,
                        "observed_line_count": len(covered), "status": status})
    return checked


def audit_metrics(metrics: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """A nonempty answer is not completion when DSH stopped at max-tokens."""
    rows = list(metrics)
    return {
        "runs": [{"status_recorded": row.get("status"),
                  "finish_reason": row.get("finish_reason"),
                  "complete": row.get("finish_reason") == "completed",
                  "model_requests": row.get("model_requests", 0)} for row in rows],
        "model_requests": sum(int(row.get("model_requests", 0)) for row in rows),
        "total_tokens": sum(int(row.get("totalTokens", 0)) for row in rows),
    }
