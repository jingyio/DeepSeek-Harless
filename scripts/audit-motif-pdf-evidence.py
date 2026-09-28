#!/usr/bin/env python3
"""Offline, content-free audit of possible quote-anchored PDF output views.

This is an opportunity audit, not a certified Motif projection: an exact quote
match does not prove that other text on the page is irrelevant to the task.
Only aggregate counts and byte lengths leave the private trace directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.motif_core.output_view_codecs import pdf_match_quote_window_v1  # noqa: E402


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def tool_observations(path: Path) -> list[tuple[int, str, dict[str, Any], str, dict]]:
    calls: dict[str, tuple[str, dict]] = {}
    observations = []
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            arguments = data.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except ValueError:
                    arguments = {}
            calls[data.get("callId", "")] = (
                data.get("name", ""), arguments if isinstance(arguments, dict) else {})
        if event.get("type") != "tool/result":
            continue
        message = data.get("message", {})
        name, arguments = calls.get(message.get("source", {}).get("callId", ""), ("", {}))
        if not name.endswith(("read_pinned_pdf_pages", "read_pinned_pdf_match",
                              "read_pinned_zotero_annotation", "locate_pinned_pdf_quote")):
            continue
        blocks = message.get("content", [])
        if (len(blocks) != 1 or blocks[0].get("isError")
                or len(blocks[0].get("content", [])) != 1):
            continue
        raw = blocks[0]["content"][0].get("text")
        if not isinstance(raw, str):
            continue
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        if isinstance(value, dict):
            observations.append((event["seq"], name, value, raw, arguments))
    return observations


def quote_windows(text: str, quotes: list[str], radius: int = 250) -> tuple[int, int]:
    """Return counts and normalized-character coverage, not the private snippets."""
    page = normalized(text)
    spans = []
    count = 0
    for quote in quotes:
        needle = normalized(quote)
        if len(needle) < 20 or page.count(needle) != 1:
            continue
        position = page.find(needle)
        spans.append((max(0, position - radius),
                      min(len(page), position + len(needle) + radius)))
        count += 1
    if not spans:
        return 0, 0
    spans.sort()
    merged = [spans[0]]
    for start, end in spans[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return count, sum(end - start for start, end in merged)


def audit(path: Path) -> dict[str, Any]:
    observations = tool_observations(path)
    annotations: list[tuple[int, str]] = []
    summary: dict[str, Any] = {
        "trace": str(path), "annotation_reads": 0, "pdf_reads": 0,
        "pdf_pages": 0, "matched_pages": 0, "matched_quote_occurrences": 0,
        "selected_tool_result_bytes": sum(len(row[3].encode("utf-8"))
                                          for row in observations),
        "pdf_result_bytes": 0, "pdf_page_text_characters": 0,
        "matched_page_text_characters": 0,
        "matched_page_quote_window_characters": 0,
        "locator_unique_reads": 0, "locator_matched_pages": 0,
        "locator_page_text_characters": 0,
        "locator_quote_window_characters": 0,
        "locator_candidate_codec_passed": 0,
        "locator_candidate_view_bytes": 0,
        "locator_candidate_original_bytes": 0,
    }
    locators: dict[str, tuple[int, str, dict[str, Any]]] = {}
    for seq, name, value, raw, arguments in observations:
        if name.endswith("read_pinned_zotero_annotation"):
            summary["annotation_reads"] += 1
            marked = value.get("marked_text")
            if (isinstance(marked, str) and not value.get("marked_truncated")
                    and len(normalized(marked)) >= 20):
                annotations.append((seq, marked))
        elif name.endswith("locate_pinned_pdf_quote"):
            match_id = value.get("match_id")
            quote = arguments.get("quote")
            source_hash = value.get("sha256")
            if (value.get("status") == "unique"
                    and isinstance(match_id, str) and match_id
                    and isinstance(quote, str) and len(normalized(quote)) >= 20
                    and isinstance(source_hash, str)):
                locators[match_id] = (seq, quote, value)
        else:
            summary["pdf_reads"] += 1
            summary["pdf_result_bytes"] += len(raw.encode("utf-8"))
            locator = locators.get(arguments.get("match_id")) if name.endswith(
                "read_pinned_pdf_match") else None
            if locator and (locator[0] >= seq or value.get("match_id") != arguments["match_id"]
                            or value.get("sha256") != locator[2].get("sha256")):
                locator = None
            if locator:
                summary["locator_unique_reads"] += 1
                try:
                    _, stats = pdf_match_quote_window_v1(raw, {
                        "quote": locator[1], "locator": locator[2],
                        "match_id": arguments["match_id"]})
                except (ValueError, TypeError, KeyError):
                    pass
                else:
                    summary["locator_candidate_codec_passed"] += 1
                    summary["locator_candidate_original_bytes"] += stats["original_bytes"]
                    summary["locator_candidate_view_bytes"] += stats["view_bytes"]
            for page in value.get("pages", []):
                if not isinstance(page, dict) or not isinstance(page.get("text"), str):
                    continue
                summary["pdf_pages"] += 1
                text = page["text"]
                summary["pdf_page_text_characters"] += len(text)
                earlier = [quote for read_seq, quote in annotations if read_seq < seq]
                count, coverage = quote_windows(text, earlier)
                if count:
                    summary["matched_pages"] += 1
                    summary["matched_quote_occurrences"] += count
                    summary["matched_page_text_characters"] += len(text)
                    summary["matched_page_quote_window_characters"] += coverage
                if locator:
                    locator_count, locator_coverage = quote_windows(text, [locator[1]])
                    if locator_count:
                        summary["locator_matched_pages"] += 1
                        summary["locator_page_text_characters"] += len(text)
                        summary["locator_quote_window_characters"] += locator_coverage
    summary["hypothetical_window_characters_removed"] = max(
        0, summary["matched_page_text_characters"]
        - summary["matched_page_quote_window_characters"])
    summary["locator_window_characters_removable_if_task_is_quote_check"] = max(
        0, summary["locator_page_text_characters"]
        - summary["locator_quote_window_characters"])
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+", type=Path)
    args = parser.parse_args()
    print(json.dumps([audit(path) for path in args.traces],
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
