#!/usr/bin/env python3
"""Record a filled human review form against one immutable local research run.

The reviewer fills a separate JSON form after reading the blind review packet.
This command only validates and seals that form; it does not make the judgment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflows.research_review_gate import build_review_record  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--form", required=True, type=Path,
                        help="JSON assessment filled by the human reviewer")
    args = parser.parse_args()
    local = (ROOT / ".local").resolve(strict=True)
    run = args.run.resolve(strict=True)
    form = args.form.resolve(strict=True)
    if not run.is_relative_to(local) or not form.is_relative_to(local):
        parser.error("review files must stay under .local")
    if form.is_symlink() or not form.is_file():
        parser.error("review form must be a regular file")
    assessment = json.loads(form.read_text(encoding="utf-8"))
    record = build_review_record(run, assessment)
    destination = run / "human-review.json"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(record, output, ensure_ascii=False, indent=2)
        output.write("\n")
    print(json.dumps({"run": str(run), "verdict": assessment["verdict"],
                      "reviewed_files": len(record["file_sha256"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
