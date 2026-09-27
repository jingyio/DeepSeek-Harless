#!/usr/bin/env python3
"""Render an opt-in, host-bound DSH overlay without touching the live profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config" / "sss-runtime.patch.yml"
OUTPUT = ROOT / ".local" / "sss-runtime" / "harness.patch.yml"


def render(source_root: Path, motif_path: Path,
           retrieval_motif_path: Path) -> Path:
    source_root = source_root.resolve(strict=True)
    motif_path = motif_path.resolve(strict=True)
    retrieval_motif_path = retrieval_motif_path.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("source root must be a directory")
    python = ROOT / ".venv312" / "bin" / "python"
    if not python.is_file():
        raise ValueError("SSS Python environment is missing")
    replacements = {
        "__SSS_GUARD_PLUGIN__": (ROOT / "src" / "adapters" /
                                  "dsh_sss_guard.mjs").resolve(strict=True).as_uri(),
        "__SSS_MCP_PYTHON__": str(python),
        "__SSS_PROJECT_ROOT__": str(ROOT),
        "__SSS_SOURCE_ROOT__": str(source_root),
        "__SSS_SOURCE_MOTIF__": str(motif_path),
        "__SSS_RETRIEVAL_MOTIF__": str(retrieval_motif_path),
    }
    rendered = TEMPLATE.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, json.dumps(value, ensure_ascii=False))
    if "__SSS_" in rendered:
        raise ValueError("unresolved SSS Harness patch placeholder")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    OUTPUT.chmod(0o600)
    return OUTPUT


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT / "reference")
    parser.add_argument("--motif", type=Path,
                        default=ROOT / ".local" / "motifs" / "research-source-read.json")
    parser.add_argument("--retrieval-motif", type=Path,
                        default=ROOT / ".local" / "motifs" / "research-retrieval.json")
    args = parser.parse_args()
    print(render(args.source_root, args.motif, args.retrieval_motif))
