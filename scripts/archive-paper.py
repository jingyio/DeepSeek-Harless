#!/usr/bin/env python3
"""Preview or copy a reviewed PDF and note into the local archive."""

import argparse
import json
import re
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAPER_ROOT = PROJECT_ROOT / "office" / "papers"
SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview or apply literature archiving")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--note", required=True, type=Path)
    parser.add_argument("--year", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--slug", required=True)
    parser.add_argument("--apply", action="store_true", help="Copy after human approval")
    args = parser.parse_args()

    pdf = args.pdf.expanduser().resolve(strict=True)
    note = args.note.expanduser().resolve(strict=True)
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        parser.error("--pdf must point to a PDF file")
    if not note.is_file() or note.suffix.lower() != ".md":
        parser.error("--note must point to a Markdown file")
    if not re.fullmatch(r"(?:19|20)\d{2}|unknown", args.year):
        parser.error("--year must be a four-digit year or unknown")
    for name, value in (("category", args.category), ("slug", args.slug)):
        if not SAFE_NAME.fullmatch(value) or value in {".", ".."}:
            parser.error(f"--{name} must contain only lowercase letters, digits, dots, hyphens, or underscores")

    pdf_target = PAPER_ROOT / "archive" / args.year / args.category / f"{args.slug}.pdf"
    note_target = PAPER_ROOT / "notes" / args.year / args.category / f"{args.slug}.md"
    if pdf_target.exists() or note_target.exists():
        parser.error("destination already exists; choose a different slug or review the existing item")

    plan = {"source_pdf": str(pdf), "source_note": str(note), "archive_pdf": str(pdf_target), "archive_note": str(note_target), "mode": "apply" if args.apply else "preview"}
    if not args.apply:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    pdf_target.parent.mkdir(parents=True, exist_ok=True)
    note_target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(pdf, pdf_target)
        shutil.copy2(note, note_target)
    except Exception:
        if pdf_target.exists():
            pdf_target.unlink()
        if note_target.exists():
            note_target.unlink()
        raise
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
