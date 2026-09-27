#!/usr/bin/env python3
"""Refresh a private AIDD source inventory without exporting source text."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.zotero_annotation_inventory import collection_annotation_inventory  # noqa: E402
from src.mcp.scoped_zotero_read_server import _data_digest, _fetch_item  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    vault = args.vault.resolve(strict=True)
    snapshot = args.snapshot.resolve(strict=True)
    output = args.out.resolve()
    private_root = (ROOT / ".local").resolve()
    if not snapshot.is_relative_to(private_root) or not output.is_relative_to(private_root):
        parser.error("snapshot and output must be under .local")
    papers = []
    for role, filename in (("antibody", "antibody-item.json"),
                           ("ligand", "ligand-item.json")):
        old = json.loads((snapshot / filename).read_text(encoding="utf-8"))
        current = _fetch_item(old["key"])
        papers.append({"role": role, "key": old["key"],
                       "snapshot_version": old["version"], "current_version": current["version"],
                       "snapshot_data_sha256": _data_digest(old),
                       "current_data_sha256": _data_digest(current),
                       "unchanged": (old["version"] == current["version"]
                                     and _data_digest(old) == _data_digest(current))})
    old_annotations = json.loads((snapshot / "antibody-annotations.json").read_text(encoding="utf-8"))
    if not isinstance(old_annotations, list):
        raise ValueError("expected a snapshot annotation list")
    old_by_key = {item["key"]: item for item in old_annotations}
    current_inventory = collection_annotation_inventory(args.collection)
    current_annotations = []
    for row in current_inventory:
        item = _fetch_item(row["key"])
        old = old_by_key.get(row["key"])
        current_annotations.append({"key": row["key"], "parent_item": row["parent_item"],
                                    "page_label": row["page_label"],
                                    "snapshot_version": old.get("version") if old else None,
                                    "current_version": item["version"],
                                    "current_data_sha256": _data_digest(item),
                                    "unchanged": bool(old and old["version"] == item["version"]
                                                      and _data_digest(old) == _data_digest(item))})
    notes = []
    for role, relative, snapshot_name in (
        ("research_context", "00-System/研究背景.md", "research-context.md"),
        ("current_state", "00-System/当前状态.md", "current-status.md"),
        ("open_questions", "00-System/开放问题.md", "open-questions.md"),
        ("aidd_index", "Papers/Zotero Collections/AIDD.md", "AIDD-index.md"),
    ):
        path = (vault / relative).resolve(strict=True)
        if not path.is_relative_to(vault) or not path.is_file():
            raise ValueError("note escaped or missing from vault")
        baseline = snapshot / snapshot_name
        notes.append({"role": role, "vault_path": relative,
                      "snapshot_sha256": digest(baseline), "current_sha256": digest(path),
                      "unchanged": digest(baseline) == digest(path),
                      "bytes": path.stat().st_size})
    result = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "collection_key": args.collection, "papers": papers,
              "annotations": current_annotations, "notes": notes,
              "authorization": {"external_model_excerpt_allowed": False,
                                "paid_model_run_allowed": False}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(output, 0o600)
    print(json.dumps({"paper_count": len(papers),
                      "papers_unchanged": sum(row["unchanged"] for row in papers),
                      "annotation_count": len(current_annotations),
                      "annotations_unchanged": sum(row["unchanged"] for row in current_annotations),
                      "note_count": len(notes),
                      "notes_unchanged": sum(row["unchanged"] for row in notes)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
