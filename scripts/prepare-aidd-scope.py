#!/usr/bin/env python3
"""Build a review-only AIDD scope from a verified private metadata snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    private = (ROOT / ".local").resolve()
    vault = args.vault.resolve(strict=True)
    snapshot = args.snapshot.resolve(strict=True)
    metadata_path = args.metadata.resolve(strict=True)
    out = args.out.resolve()
    if any(not path.is_relative_to(private) for path in (snapshot, metadata_path, out)):
        parser.error("snapshot, metadata and output must stay under .local")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if any(not row["unchanged"] for row in metadata["papers"] + metadata["annotations"]):
        raise ValueError("Zotero source changed since snapshot; prepare a new review packet")
    note_roles = {"current_state": (97, 119), "open_questions": (204, 252)}
    notes = []
    for row in metadata["notes"]:
        role = row["role"]
        if role not in note_roles:
            continue
        if not row["unchanged"]:
            raise ValueError(f"{role} changed since source review")
        path = (vault / row["vault_path"]).resolve(strict=True)
        if not path.is_relative_to(vault) or sha(path) != row["current_sha256"]:
            raise ValueError(f"{role} changed since metadata preflight")
        notes.append({"role": role, "vault_path": row["vault_path"],
                      "path": str(path), "sha256": row["current_sha256"],
                      "allowed_line_ranges": [list(note_roles[role])],
                      "external_model_excerpt_allowed": False})
    if len(notes) != len(note_roles):
        raise ValueError("required Obsidian note missing")
    pdfs = []
    for role, filename, page_ranges in (
        ("antibody_pdf", "antibody.pdf", [[1, 11]]),
        ("ligand_pdf", "ligand.pdf", [[1, 10], [13, 16]]),
    ):
        path = snapshot / filename
        pdfs.append({"role": role, "path": str(path), "sha256": sha(path),
                     "allowed_page_ranges": page_ranges,
                     "external_model_excerpt_allowed": False})
    zotero = []
    for row in metadata["papers"]:
        zotero.append({"role": row["role"] + "_item", "kind": "item",
                       "key": row["key"], "version": row["current_version"],
                       "data_sha256": row["current_data_sha256"],
                       "external_model_excerpt_allowed": False})
    for index, row in enumerate(metadata["annotations"], 1):
        zotero.append({"role": f"antibody_annotation_{index}", "kind": "annotation",
                       "key": row["key"], "version": row["current_version"],
                       "data_sha256": row["current_data_sha256"],
                       "external_model_excerpt_allowed": False})
    scope = {"status": "review_only", "obsidian_vault_root": str(vault),
             "sources": notes + pdfs, "zotero_sources": zotero,
             "metadata_sha256": sha(metadata_path)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(out, 0o600)
    print(json.dumps({"status": scope["status"], "notes": len(notes),
                      "pdfs": len(pdfs), "zotero_items": len(metadata["papers"]),
                      "annotations": len(metadata["annotations"]),
                      "model_approved_sources": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
