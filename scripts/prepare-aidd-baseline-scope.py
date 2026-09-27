#!/usr/bin/env python3
"""Add frozen public Idea State files to a review-only private AIDD scope."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / ".local").resolve()
MANIFEST = ROOT / "benchmarks/research_weekly_loop_v1/aidd_public_sources.json"
PUBLIC_ROOT = LOCAL / "reference/research-workflow"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-scope", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    private_path = args.private_scope.resolve(strict=True)
    output = args.out.resolve()
    if not private_path.is_relative_to(LOCAL) or not output.is_relative_to(LOCAL):
        parser.error("scope paths must stay under .local")
    private = json.loads(private_path.read_text(encoding="utf-8"))
    if (private.get("status") != "review_only"
            or not isinstance(private.get("sources"), list)
            or not isinstance(private.get("zotero_sources"), list)
            or len(private["sources"]) != 4
            or len(private["zotero_sources"]) != 8
            or any(row.get("external_model_excerpt_allowed") is not False
                   for row in private["sources"] + private["zotero_sources"])):
        raise ValueError("private AIDD scope is not the expected unapproved review range")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    revision = subprocess.check_output(
        ["git", "-C", str(PUBLIC_ROOT), "rev-parse", "HEAD"], text=True).strip()
    if revision != manifest["repository_commit"]:
        raise ValueError("public Idea State checkout changed since the task freeze")
    public = []
    for row in manifest["sources"]:
        path = (PUBLIC_ROOT / row["relative_path"]).resolve(strict=True)
        if (not path.is_file() or not path.is_relative_to(PUBLIC_ROOT)
                or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]):
            raise ValueError("public Idea State file changed since the task freeze")
        public.append({"role": row["role"], "path": str(path),
                       "sha256": row["sha256"],
                       "origin": "public_research_workflow",
                       "external_model_excerpt_allowed": True})
    output_scope = {**private, "sources": private["sources"] + public,
                    "public_repository_commit": revision,
                    "private_scope_sha256": hashlib.sha256(
                        private_path.read_bytes()).hexdigest()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(output_scope, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    os.chmod(output, 0o600)
    print(json.dumps({"status": output_scope["status"],
                      "private_sources_pending": 12,
                      "public_sources_model_readable": len(public),
                      "repository_commit": revision}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
