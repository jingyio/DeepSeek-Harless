#!/usr/bin/env python3
"""Extract page-labelled PDF text into the ignored local runtime directory."""

import argparse
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract PDF text with page labels")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--max-pages", type=int, default=60)
    args = parser.parse_args()

    pdf = args.pdf.expanduser().resolve(strict=True)
    if not pdf.is_file() or pdf.suffix.lower() != ".pdf":
        parser.error("input must be an existing PDF file")
    if args.max_pages < 1:
        parser.error("--max-pages must be positive")

    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()[:16]
    reader = PdfReader(str(pdf))
    if reader.is_encrypted:
        raise SystemExit("Encrypted PDF: please provide an unlocked copy")

    output_dir = PROJECT_ROOT / ".local" / "papers" / "extracted"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{digest}.md"

    limit = min(len(reader.pages), args.max_pages)
    sections = [f"# Extracted text: {pdf.name}", "", "Source PDF text may have layout errors. Page numbers are PDF page positions."]
    low_text_pages = []
    total_chars = 0
    for index in range(limit):
        content = (reader.pages[index].extract_text() or "").strip()
        total_chars += len(content)
        if len(content) < 80:
            low_text_pages.append(index + 1)
        sections.extend(["", f"## PDF page {index + 1}", "", content or "[No extractable text]"])

    output.write_text("\n".join(sections) + "\n", encoding="utf-8")
    print(json.dumps({
        "source": str(pdf),
        "extracted_text": str(output),
        "pdf_pages": len(reader.pages),
        "processed_pages": limit,
        "characters": total_chars,
        "low_text_pages": low_text_pages,
        "truncated": limit < len(reader.pages),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
