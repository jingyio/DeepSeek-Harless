#!/usr/bin/env python3
"""Freeze researcher-approved phase-A source snapshots for a fair pilot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workflows.research_weekly_trial import freeze_initial_trial  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True,
                        help="private intake JSON under .local/")
    parser.add_argument("--out", type=Path, required=True,
                        help="frozen manifest under .local/")
    args = parser.parse_args()
    local = (ROOT / ".local").resolve(strict=True)
    intake_path = args.intake.resolve(strict=True)
    out_parent = args.out.parent.resolve(strict=True)
    if (not intake_path.is_relative_to(local)
            or not out_parent.is_relative_to(local)):
        raise ValueError("private intake and manifest must stay under .local")
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    manifest = freeze_initial_trial(intake, local_root=local)
    # Create a private, new manifest. Never follow an existing output symlink.
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        json.dump(manifest, output, ensure_ascii=False, indent=2)
    print(json.dumps({"task_id": manifest["task_id"],
                      "task_digest": manifest["task_digest"],
                      "source_count": len(manifest["sources"]),
                      "manifest": str(args.out.resolve())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
