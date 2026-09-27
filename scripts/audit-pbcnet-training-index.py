#!/usr/bin/env python3
"""Audit what PBCNet2.0's public CSVs can establish about train/test overlap."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / ".local").resolve()
MANIFEST = ROOT / "benchmarks/research_weekly_loop_v1/pbcnet_mutation_public_manifest.json"
DEFAULT_DATA = LOCAL / "benchmarks/research-weekly-loop/aidd-next-preflight/public-data-preflight"
REQUIRED_TEST = {"lig1", "lig2", "dir_1", "dir_2"}
REQUIRED_TRAIN = REQUIRED_TEST | {"smile1", "smile2"}


def checked_hash(path: Path, expected: str) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"source snapshot hash mismatch: {path.name}")


def read_tests(manifest: dict, directory: Path) -> tuple[set[str], set[str], set[str], dict]:
    ligands, paths, pdb_codes = set(), set(), set()
    targets = {}
    for entry in manifest["mutation_files"]:
        file = directory / f"{entry['directory']}.csv"
        checked_hash(file, entry["sha256"])
        with file.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or not REQUIRED_TEST <= set(reader.fieldnames):
                raise ValueError(f"mutation CSV missing identifiers: {file.name}")
            count = 0
            for row in reader:
                count += 1
                ligands.update((row["lig1"], row["lig2"]))
                paths.update((row["dir_1"], row["dir_2"]))
                for name in (row["lig1"], row["lig2"]):
                    match = re.search(r"(?:^|_)([0-9][A-Za-z0-9]{3})_", name)
                    if match:
                        pdb_codes.add(match.group(1).upper())
        targets[entry["target"]] = {"pair_rows": count, "directory": entry["directory"]}
    return ligands, paths, pdb_codes, targets


def audit(manifest: dict, data_dir: Path) -> dict:
    ligands, paths, pdb_codes, targets = read_tests(manifest, data_dir / "mutation")
    train_file = data_dir / manifest["training_index"]["file"]
    checked_hash(train_file, manifest["training_index"]["sha256"])
    if train_file.stat().st_size != manifest["training_index"]["size_bytes"]:
        raise ValueError("training index size mismatch")
    groups, train_ligands = set(), set()
    rows = exact_ligand_rows = exact_path_rows = pdb_name_rows = 0
    with train_file.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not REQUIRED_TRAIN <= set(reader.fieldnames):
            raise ValueError("training index missing expected identifiers")
        fields = reader.fieldnames
        for row in reader:
            rows += 1
            names = (row["lig1"], row["lig2"])
            locations = (row["dir_1"], row["dir_2"])
            train_ligands.update(names)
            groups.update(name.rsplit("_", 1)[0] for name in names)
            exact_ligand_rows += any(name in ligands for name in names)
            exact_path_rows += any(location in paths for location in locations)
            pdb_name_rows += any(code in value.upper()
                                 for code in pdb_codes for value in names + locations)
    return {
        "training_source": manifest["training_index"]["record"],
        "training_index_sha256": manifest["training_index"]["sha256"],
        "training_index_columns": fields,
        "training_pair_rows": rows,
        "training_unique_ligand_ids": len(train_ligands),
        "training_unique_bindingdb_groups_in_ids": len(groups),
        "mutation_targets": targets,
        "mutation_pair_rows": sum(value["pair_rows"] for value in targets.values()),
        "mutation_unique_ligand_ids": len(ligands),
        "mutation_pdb_codes_in_names": sorted(pdb_codes),
        "same_literal_ligand_id_rows": exact_ligand_rows,
        "same_literal_path_rows": exact_path_rows,
        "test_pdb_code_in_training_id_or_path_rows": pdb_name_rows,
        "interpretation": (
            "Zero literal identifier matches is not evidence of no biological leakage. "
            "The training index does not contain protein sequences, pocket residue identities, "
            "structure deposition dates or mutation test SMILES. Those require separately "
            "mapped structure and ligand sources before an identity/similarity/time audit."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_DATA / "training-index-audit.json")
    args = parser.parse_args()
    data_dir, output = args.data_dir.resolve(strict=True), args.out.resolve()
    if not data_dir.is_relative_to(LOCAL) or not output.is_relative_to(LOCAL):
        parser.error("public snapshots and output must stay under .local")
    result = audit(json.loads(MANIFEST.read_text(encoding="utf-8")), data_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"training_pair_rows": result["training_pair_rows"],
                      "mutation_pair_rows": result["mutation_pair_rows"],
                      "same_literal_ligand_id_rows": result["same_literal_ligand_id_rows"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
