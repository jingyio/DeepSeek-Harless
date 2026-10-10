"""Compile v2 receipt transfers from successful ordinary, real DSH trajectories.

The learner is the v1 adjacency/opaque-parameter matcher, imported unchanged.
Tools and allowed successors are manually designed; this only confirms and
compiles observed authorized transfers, not autonomous workflow discovery.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v1.compile_motifs import (
    digest, read, load_run as legacy_load_run, compile_library as legacy_compile_library)


def load_run(path, contracts):
    path = Path(path)
    manifest, metrics = read(path / "manifest.json"), read(path / "metrics.json")
    if manifest.get("benchmark_version") != 2 or metrics.get("delivered") is not True:
        raise ValueError("v2 training requires successful deliver_report business acceptance")
    row = legacy_load_run(path, contracts)
    source = {Path(item["path"]).name: item["sha256"] for item in manifest["source_files"]}
    row["csv_sha256"] = source["data.csv"]
    row["input_content_digest"] = manifest["input_content_digest"]
    row["benchmark_split"] = manifest.get("benchmark_split")
    return row


def learned_chains(artifacts):
    """Describe maximal observed edge paths; never supply new execution rules."""
    successors = {}
    targets = set()
    for edge in artifacts:
        successors.setdefault(edge["from_tool"], []).append(edge)
        targets.add(edge["to_tool"])
    roots = sorted(set(successors) - targets)
    chains = []
    def walk(node, edges, visited):
        next_edges = [edge for edge in successors.get(node, []) if edge["to_tool"] not in visited]
        if not next_edges:
            if edges:
                chains.append({"tools": [edges[0]["from_tool"], *[edge["to_tool"] for edge in edges]],
                               "motif_ids": [edge["motif_id"] for edge in edges],
                               "edge_count": len(edges)})
            return
        for edge in sorted(next_edges, key=lambda item: item["to_tool"]):
            walk(edge["to_tool"], [*edges, edge], visited | {edge["to_tool"]})
    for root in roots:
        walk(root, [], {root})
    return sorted(chains, key=lambda row: (-row["edge_count"], row["tools"]))


def compile_library(training, certification, contracts):
    rows = [*training, certification]
    if any(row.get("benchmark_split") not in (None, "train") for row in training):
        raise ValueError("Held-out benchmark evaluation/certification tasks cannot enter training")
    if certification.get("benchmark_split") not in (None, "certification"):
        raise ValueError("Independent certification must not use held-out benchmark evaluation tasks")
    fingerprints = [row["csv_sha256"] for row in rows]
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("Repeated datasets/aliases are not independent training or certification tasks")
    result = legacy_compile_library(training, certification, contracts)
    # This is diagnostic evidence coverage, never an alternative source of
    # execution edges. Include rejected candidates observed in only one task.
    all_observed = set().union(*(set(row["edges"]) for row in rows))
    coverage = []
    for edge in sorted(all_observed):
        witnesses = [row["case_id"] for row in training if edge in row["edges"]]
        certified = edge in certification["edges"]
        item = dict(zip(("from_tool", "from_field", "to_tool", "to_param"), edge))
        item.update(training_case_ids=witnesses, training_task_count=len(witnesses),
                    independently_witnessed=certified, eligible=len(witnesses) >= 2 and certified)
        coverage.append(item)
    result.pop("library_digest", None)
    result.update(benchmark_version=2,
                  scope="benchmark-local v2; manually designed tool/authorization surface; observed receipt transfers only",
                  certification_meaning="independent successful trajectory witness, not a formal proof",
                  training_csv_sha256=fingerprints[:-1], certification_csv_sha256=fingerprints[-1],
                  observed_authorized_edge_coverage=coverage,
                  learned_chains=learned_chains(result["artifacts"]))
    result["library_digest"] = digest(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", nargs="+", required=True, type=Path)
    parser.add_argument("--certify", required=True, type=Path)
    parser.add_argument("--contracts", type=Path, default=Path(__file__).with_name("tool_contracts.json"))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    contracts = read(args.contracts)
    result = compile_library([load_run(path, contracts) for path in args.train],
                             load_run(args.certify, contracts), contracts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"motifs": len(result["artifacts"]), "chains": result["learned_chains"],
                      "library_digest": result["library_digest"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
