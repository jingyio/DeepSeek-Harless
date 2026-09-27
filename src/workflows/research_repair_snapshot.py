"""Bind a local research repair to the complete prior Motif source snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.graph.runtime import Evidence


def verify_repair_source_trace(trace: dict[str, Any], source_dir: Path,
                               pages: list[dict[str, Any]]) -> None:
    if trace.get("motif") != "bounded-reference-source-cache-v1" or trace.get("status") != "completed":
        raise ValueError("repair parent lacks a completed source Motif")
    evidence = trace.get("evidence")
    if not isinstance(evidence, dict):
        raise ValueError("repair parent lacks a source evidence witness")
    directory_witness = evidence.get("source_dir")
    page_witness = evidence.get("unique_pages")
    if not isinstance(directory_witness, dict) or not isinstance(page_witness, dict):
        raise ValueError("repair parent lacks a source evidence witness")
    expected_dir = Evidence(str(source_dir.resolve()), "user_input").digest
    expected_pages = Evidence(pages, "current_source_pages").digest
    if (directory_witness.get("digest") != expected_dir
            or page_witness.get("digest") != expected_pages):
        raise ValueError("repair source snapshot changed; use an incremental run")
