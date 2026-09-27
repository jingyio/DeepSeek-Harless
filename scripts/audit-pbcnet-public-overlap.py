#!/usr/bin/env python3
"""Count exact raw SMILES overlap in one PBCNet training index and SAR labels.

This is a data-availability diagnostic, not a train/test leakage verdict.
No structures, labels, or row identifiers are printed or written.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(training_csv: Path, sar_dir: Path) -> dict:
    train_smiles: set[str] = set()
    train_rows = train_missing = 0
    with training_csv.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not {"smile1", "smile2"}.issubset(reader.fieldnames or []):
            raise ValueError("training CSV lacks smile1/smile2")
        for row in reader:
            train_rows += 1
            for field in ("smile1", "smile2"):
                value = (row[field] or "").strip()
                if value:
                    train_smiles.add(value)
                else:
                    train_missing += 1

    files = sorted(sar_dir.glob("*.csv"))
    if not files:
        raise ValueError("SAR label directory has no CSV files")
    series = []
    test_smiles: set[str] = set()
    overlapping_smiles: set[str] = set()
    for path in files:
        rows = missing = overlap_rows = 0
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if "smiles" not in (reader.fieldnames or []):
                raise ValueError(f"SAR label CSV lacks smiles: {path.name}")
            for row in reader:
                rows += 1
                value = (row["smiles"] or "").strip()
                if not value:
                    missing += 1
                    continue
                test_smiles.add(value)
                if value in train_smiles:
                    overlap_rows += 1
                    overlapping_smiles.add(value)
        series.append({"name": path.stem, "sha256": digest(path),
                       "rows": rows, "missing_smiles": missing,
                       "exact_raw_overlap_rows": overlap_rows})

    return {"method": "literal SMILES equality after whitespace trim; no canonicalization",
            "training_csv": training_csv.name,
            "training_sha256": digest(training_csv),
            "training_rows": train_rows,
            "training_missing_smiles_fields": train_missing,
            "training_unique_raw_smiles": len(train_smiles),
            "sar_files": len(files),
            "sar_rows": sum(item["rows"] for item in series),
            "sar_missing_smiles": sum(item["missing_smiles"] for item in series),
            "sar_unique_raw_smiles": len(test_smiles),
            "exact_raw_overlap_rows": sum(item["exact_raw_overlap_rows"] for item in series),
            "exact_raw_overlap_unique_smiles": len(overlapping_smiles),
            "series": series,
            "limitation": "One training CSV only; no target, pair, series, date, canonical structure, or model split verification."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("training_csv", type=Path)
    parser.add_argument("sar_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = audit(args.training_csv, args.sar_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        output = args.out.resolve()
        local = (Path(__file__).resolve().parents[1] / ".local").resolve()
        if not output.is_relative_to(local):
            parser.error("output must stay under .local")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        output.chmod(0o600)
    print(json.dumps({key: report[key] for key in
                      ("training_rows", "sar_files", "sar_rows",
                       "exact_raw_overlap_rows", "exact_raw_overlap_unique_smiles")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
