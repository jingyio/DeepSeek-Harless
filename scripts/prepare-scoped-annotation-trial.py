#!/usr/bin/env python3
"""Freeze a metadata-only preview for an independent annotation decision.

The private input spec and generated source scope remain under .local. This
script neither reads annotation text into its output nor calls a paid model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / ".local").resolve()
sys.path.insert(0, str(ROOT))

from src.mcp.scoped_zotero_read_server import _data_digest, _fetch_item  # noqa: E402


def _private(path: Path, value: dict) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError(f"frozen trial file changed: {path.name}")
    if not path.exists():
        path.write_text(encoded, encoding="utf-8")
    path.chmod(0o600)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(spec_path: Path) -> dict:
    spec_path = spec_path.resolve(strict=True)
    if not spec_path.is_relative_to(LOCAL):
        raise ValueError("private input spec must be under .local")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    out = Path(spec["out"]).resolve()
    if not out.is_relative_to(LOCAL):
        raise ValueError("trial output must be under .local")
    if not isinstance(spec.get("annotation_keys"), list) or not 1 <= len(
            spec["annotation_keys"]) <= 6 or len(set(spec["annotation_keys"])) != len(
                spec["annotation_keys"]):
        raise ValueError("select 1–6 distinct real annotations")
    if not 0 < float(spec["budget_usd"]) <= 10:
        raise ValueError("budget must be positive and at most US$10")
    arm_budgets = spec.get("arm_budget_usd", {"baseline": spec["budget_usd"]})
    if (not isinstance(arm_budgets, dict) or not arm_budgets
            or set(arm_budgets) - {"baseline", "motif"}
            or any(not isinstance(value, (int, float)) or not 0 < value <= 10
                   for value in arm_budgets.values())
            or sum(arm_budgets.values()) > float(spec["budget_usd"])):
        raise ValueError("arm budgets must fit the approved total budget")
    vault = Path(spec["vault_root"]).resolve(strict=True)
    note = Path(spec["note_path"]).resolve(strict=True)
    pdf = Path(spec["pdf_path"]).resolve(strict=True)
    prompt = Path(spec["prompt_path"]).resolve(strict=True)
    if (not note.is_file() or not note.is_relative_to(vault)
            or not pdf.is_file() or pdf.stat().st_size > 10_000_000
            or pdf.suffix.lower() != ".pdf" or not prompt.is_relative_to(ROOT)):
        raise ValueError("source or prompt is outside the permitted locations")
    lines = spec["note_allowed_lines"]
    if (not isinstance(lines, list) or len(lines) != 2
            or any(type(value) is not int for value in lines)
            or not 1 <= lines[0] <= lines[1] <= len(note.read_text(
                encoding="utf-8").splitlines())):
        raise ValueError("invalid note line scope")
    page_count = len(PdfReader(str(pdf)).pages)
    if not 1 <= page_count <= 100:
        raise ValueError("PDF page count exceeds the scoped locator limit")
    paper = _fetch_item(spec["paper_key"])
    attachment = _fetch_item(spec["attachment_key"])
    if (paper["data"].get("itemType") in {"annotation", "attachment"}
            or attachment["data"].get("itemType") != "attachment"
            or attachment["data"].get("parentItem") != paper["key"]
            or pdf.parent.name != attachment["key"]):
        raise ValueError("paper, attachment and PDF do not form one source chain")
    rows = [{"role": "selected_paper", "kind": "item", "key": paper["key"],
             "version": paper["version"], "data_sha256": _data_digest(paper),
             "external_model_excerpt_allowed": True}]
    annotation_metadata = []
    for index, key in enumerate(spec["annotation_keys"], 1):
        item = _fetch_item(key)
        data = item["data"]
        if data.get("itemType") != "annotation" or data.get(
                "parentItem") != attachment["key"]:
            raise ValueError("selected annotation is not on the approved PDF")
        rows.append({"role": f"selected_annotation_{index}", "kind": "annotation",
                     "key": key, "version": item["version"],
                     "data_sha256": _data_digest(item),
                     "external_model_excerpt_allowed": True})
        annotation_metadata.append({"key": key,
                                    "page_label": data.get("annotationPageLabel"),
                                    "version": item["version"],
                                    "modified_at": data.get("dateModified")})
    scope = {"status": "awaiting_approval", "task_id": spec["task_id"],
             "obsidian_vault_root": str(vault),
             "sources": [
                 {"role": "current_state", "path": str(note),
                  "vault_path": note.relative_to(vault).as_posix(),
                  "sha256": _digest(note), "allowed_line_ranges": [lines],
                  "external_model_excerpt_allowed": True},
                 {"role": "selected_pdf", "path": str(pdf),
                  "sha256": _digest(pdf),
                 "allowed_page_ranges": [[1, page_count]],
                  "external_model_excerpt_allowed": True}],
             "zotero_sources": rows,
             "zotero_attachment_relationships": [{
                 "key": attachment["key"], "version": attachment["version"],
                 "data_sha256": _data_digest(attachment),
                 "parent_paper_key": paper["key"]}]}
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    scope_path = out / "source-scope.json"
    _private(scope_path, scope)
    preview = {"task_id": spec["task_id"], "paper_title": paper["data"].get("title"),
               "paper_key": paper["key"], "annotation_count": len(annotation_metadata),
               "annotation_metadata": annotation_metadata,
               "note_vault_path": note.relative_to(vault).as_posix(),
               "note_allowed_lines": lines, "pdf_pages": page_count,
               "model": "deepseek-flash", "budget_cap_usd": spec["budget_usd"],
               "arm_budget_usd": arm_budgets,
               "read_only": True, "simulated_release": True,
               "prompt_sha256": _digest(prompt),
               "scope_sha256": _digest(scope_path),
               "approval_status": "pending", "output": str(out)}
    _private(out / "RUN-PREVIEW.json", preview)
    return preview


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    args = parser.parse_args()
    preview = prepare(args.spec)
    print(json.dumps({key: preview[key] for key in (
        "task_id", "paper_title", "annotation_count", "note_allowed_lines",
        "pdf_pages", "budget_cap_usd", "approval_status", "output")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
