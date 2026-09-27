#!/usr/bin/env python3
"""Extract local reference text for research; output stays in ignored .local/."""

from pathlib import Path
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".local" / "research"
OUTPUT.mkdir(parents=True, exist_ok=True)

for source in sorted((ROOT / "reference").glob("*.pdf")):
    pages = PdfReader(source).pages
    destination = OUTPUT / f"{source.stem}.txt"
    destination.write_text(
        "\n\n".join(
            f"\n=== PAGE {index} ===\n{page.extract_text() or ''}"
            for index, page in enumerate(pages, 1)
        ),
        encoding="utf-8",
    )
    print(f"{source.name}: {len(pages)} pages -> {destination.relative_to(ROOT)}")
