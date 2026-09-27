#!/usr/bin/env python3
"""Audit source coverage and completion in private DSH research runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.adapters.research_trace_audit import (  # noqa: E402
    audit_events, audit_metrics, check_arxiv_versions, check_scoped_line_claims,
)

LOCAL = (ROOT / ".local").resolve()


def _private(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(LOCAL) or not resolved.is_file():
        raise ValueError("audit inputs must be existing private files under .local")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True,
                        help="private run directory with agent-events.jsonl and agent-metrics.json")
    parser.add_argument("--answer", type=Path)
    parser.add_argument("--exact-version-hashes", type=Path,
                        help="private JSON mapping exact arXiv IDs to separately fetched PDF SHA-256")
    parser.add_argument("--coverage-claims", type=Path,
                        help="private JSON list of human-registered source read/unread claims")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    all_events = []
    metrics = []
    for directory in args.run:
        base = directory.resolve(strict=True)
        if not base.is_relative_to(LOCAL) or not base.is_dir():
            parser.error("run directories must be under .local")
        events = _private(base / "agent-events.jsonl")
        met = _private(base / "agent-metrics.json")
        all_events.extend(json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()
                          if line.strip())
        metrics.append(json.loads(met.read_text(encoding="utf-8")))
    source_audit = audit_events(all_events)
    output = {**audit_metrics(metrics), **source_audit}
    if args.answer:
        answer = _private(args.answer).read_text(encoding="utf-8")
        hashes = json.loads(_private(args.exact_version_hashes).read_text(encoding="utf-8")) if args.exact_version_hashes else None
        if hashes is not None and (not isinstance(hashes, dict) or
                                   any(not isinstance(key, str) or not isinstance(value, str)
                                       for key, value in hashes.items())):
            parser.error("version hashes must be a JSON object of strings")
        output["cited_arxiv_versions"] = check_arxiv_versions(
            answer, source_audit["arxiv_pdf_reads"], hashes)
    if args.coverage_claims:
        claims = json.loads(_private(args.coverage_claims).read_text(encoding="utf-8"))
        if not isinstance(claims, list):
            parser.error("coverage claims must be a JSON list")
        output["scoped_line_claims"] = check_scoped_line_claims(
            claims, source_audit["scoped_line_reads"])
    target = args.output.resolve()
    if not target.is_relative_to(LOCAL):
        parser.error("output must be under .local")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.chmod(0o700)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    target.chmod(0o600)
    print(json.dumps({"model_requests": output["model_requests"],
                      "total_tokens": output["total_tokens"],
                      "mcp_calls": output["mcp_calls"],
                      "source_groups": len(output["scoped_line_reads"]) + len(output["scoped_pdf_reads"])
                      + len(output["arxiv_pdf_reads"]) + len(output["europe_pmc_reads"]),
                      "complete_runs": sum(row["complete"] for row in output["runs"]),
                      "runs": len(output["runs"]), "output": str(target)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
