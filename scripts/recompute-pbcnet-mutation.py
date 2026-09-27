#!/usr/bin/env python3
"""Recompute the public PBCNet2.0 mutation summary from frozen CSV rows."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / ".local").resolve()
MANIFEST = ROOT / "benchmarks/research_weekly_loop_v1/pbcnet_mutation_public_manifest.json"
DEFAULT_DATA = LOCAL / "benchmarks/research-weekly-loop/aidd-next-preflight/public-data-preflight/mutation"
DEFAULT_SHEET = DEFAULT_DATA.parent / "Supplementary-Data-6.xlsx"
DEFAULT_OUT = DEFAULT_DATA.parent / "mutation-recomputation.json"
EXCEL_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pearson(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 3:
        raise ValueError("correlation needs at least three paired values")
    x_mean, y_mean = statistics.fmean(left), statistics.fmean(right)
    x_dev = [x - x_mean for x in left]
    y_dev = [y - y_mean for y in right]
    denominator = math.sqrt(math.fsum(x * x for x in x_dev)
                            * math.fsum(y * y for y in y_dev))
    if denominator == 0:
        raise ValueError("correlation is undefined for a constant series")
    return math.fsum(x * y for x, y in zip(x_dev, y_dev)) / denominator


def average_ranks(values: list[float]) -> list[float]:
    ranked = [0.0] * len(values)
    order = sorted(range(len(values)), key=values.__getitem__)
    start = 0
    while start < len(order):
        stop = start + 1
        while stop < len(order) and values[order[stop]] == values[order[start]]:
            stop += 1
        mean_rank = (start + 1 + stop) / 2
        for index in order[start:stop]:
            ranked[index] = mean_rank
        start = stop
    return ranked


def csv_metrics(path: Path) -> dict[str, float | int]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {"Label", "pre"} <= set(reader.fieldnames):
            raise ValueError("mutation CSV lacks Label/pre columns")
        rows = list(reader)
    actual, predicted = [], []
    for row in rows:
        pair = float(row["Label"]), float(row["pre"])
        if not all(math.isfinite(value) for value in pair):
            raise ValueError("mutation CSV contains a nonfinite value")
        actual.append(pair[0])
        predicted.append(pair[1])
    return {"pairs": len(rows), "pearson": pearson(actual, predicted),
            "spearman": pearson(average_ranks(actual), average_ranks(predicted))}


def spreadsheet_numbers(path: Path, cells: set[str]) -> dict[str, float]:
    """Read cached numeric cells from this frozen single-sheet OOXML source."""
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    result = {}
    for cell in root.findall(".//x:c", EXCEL_NS):
        ref = cell.get("r")
        if ref not in cells:
            continue
        value = cell.find("x:v", EXCEL_NS)
        if value is None or value.text is None:
            raise ValueError(f"supplementary cell {ref} has no cached number")
        result[ref] = float(value.text)
    if result.keys() != cells:
        raise ValueError("supplementary workbook lacks required cached cells")
    return result


def recompute(manifest: dict, data_dir: Path, supplementary: Path) -> dict:
    if digest(supplementary) != manifest["supplementary_file"]["sha256"]:
        raise ValueError("supplementary workbook changed")
    columns = [row["supplementary_column"] for row in manifest["mutation_files"]]
    refs = {f"{column}{number}" for column in columns
            for number in (2, manifest["supplementary_file"]["pearson_row"],
                           manifest["supplementary_file"]["spearman_row"])}
    refs |= {"K23", "K24"}
    sheet = spreadsheet_numbers(supplementary, refs)
    results = []
    for row in manifest["mutation_files"]:
        file = data_dir / f"{row['directory']}.csv"
        if digest(file) != row["sha256"]:
            raise ValueError(f"public mutation CSV changed: {row['directory']}")
        measured = csv_metrics(file)
        column = row["supplementary_column"]
        expected_pearson = sheet[f"{column}23"]
        expected_spearman = sheet[f"{column}24"]
        if (not math.isclose(measured["pearson"], expected_pearson, abs_tol=1e-12)
                or not math.isclose(measured["spearman"], expected_spearman,
                                    abs_tol=1e-12)):
            raise ValueError(f"raw rows do not reproduce supplementary {column}")
        results.append({"target": row["target"], "directory": row["directory"],
                        "csv_sha256": row["sha256"], "pair_rows": measured["pairs"],
                        "supplementary_compounds": int(sheet[f"{column}2"]),
                        "pearson": measured["pearson"],
                        "spearman": measured["spearman"],
                        "supplementary_column": column})
    macro_pearson = statistics.fmean(row["pearson"] for row in results)
    macro_spearman = statistics.fmean(row["spearman"] for row in results)
    if (not math.isclose(macro_pearson, sheet["K23"], abs_tol=1e-12)
            or not math.isclose(macro_spearman, sheet["K24"], abs_tol=1e-12)):
        raise ValueError("macro mean does not reproduce supplementary")
    return {"source_repository": manifest["source_repository"],
            "source_commit": manifest["commit"],
            "supplementary_sha256": manifest["supplementary_file"]["sha256"],
            "method": "Pearson on Label/pre; Spearman as Pearson on average ranks; unweighted mean across 8 targets",
            "targets": results, "total_pair_rows": sum(row["pair_rows"] for row in results),
            "supplementary_total_compounds": sum(row["supplementary_compounds"] for row in results),
            "macro_pearson": macro_pearson, "macro_spearman": macro_spearman,
            "scientific_limit": "This reproduces reported correlations, not training/test leakage or model predictions from structures."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--supplementary", type=Path, default=DEFAULT_SHEET)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    paths = [args.data_dir.resolve(strict=True), args.supplementary.resolve(strict=True),
             args.out.resolve()]
    if any(not path.is_relative_to(LOCAL) for path in paths):
        parser.error("public input snapshots and output must stay under .local")
    result = recompute(json.loads(MANIFEST.read_text(encoding="utf-8")), paths[0], paths[1])
    paths[2].parent.mkdir(parents=True, exist_ok=True)
    paths[2].write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    paths[2].chmod(0o600)
    print(json.dumps({"targets": len(result["targets"]),
                      "pair_rows": result["total_pair_rows"],
                      "macro_spearman": result["macro_spearman"]},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
