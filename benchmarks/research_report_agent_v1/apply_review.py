"""Create separately labelled, AI-reviewed demonstration PDFs from exact edits.

Original benchmark records, PDFs, tool outputs and scores are never modified.
This offline editorial operation is not an agent rerun and makes no model calls.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from report_ops import _export_pdf, _format_metric


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rebase(raw, run):
    text = str(raw).replace("\\", "/")
    if "/artifacts/" not in text:
        raise ValueError("Expected artifact path inside a recorded workspace.")
    workspace = (run / "workspace").resolve()
    path = (workspace / "artifacts" / text.split("/artifacts/", 1)[1]).resolve()
    if not path.is_relative_to(workspace) or not path.is_file():
        raise ValueError("Recorded artifact is unavailable or outside the workspace.")
    return path


def verify_pdf(path, pages, figures, metrics):
    import fitz
    bounds = []
    with fitz.open(path) as document:
        texts = []
        image_count = 0
        for index, page in enumerate(document):
            texts.append(page.get_text())
            image_count += len(page.get_images(full=True))
            for block in page.get_text("dict")["blocks"]:
                x0, y0, x1, y1 = block["bbox"]
                if x0 < 15 or y0 < 15 or x1 > page.rect.width - 15 or y1 > page.rect.height - 15:
                    bounds.append(index + 1)
        count = len(document)
    text = "\n".join(texts)
    checks = {"correct_page_count": count == pages, "correct_figure_count": image_count == figures,
              "label_present": "审阅演示版" in text, "no_page_overflow": not bounds,
              "primary_values_present": all(_format_metric(metrics[key], key) in text for key in ("n", "estimate", "ci_low", "ci_high", "p_value")),
              "no_unresolved_braces": "{" not in text and "}" not in text, "no_replacement_glyphs": "\ufffd" not in text}
    return {"passed": all(checks.values()), "checks": checks, "pages": count, "figures": image_count,
            "visual_review": "Render and inspect separately before delivery."}


def apply_edits(runs_root, data_root, edits_path, output_dir):
    edits = read(edits_path)
    rows = edits.get("reports", edits.get("cases", []))
    if not rows:
        raise ValueError("Replacement JSON must have reports[] (or cases[]) with run_directory and replacements[].")
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for entry in rows:
        directory = entry.get("run_directory") or entry.get("run") or entry["case_id"] + "_execute"
        run = (runs_root / directory).resolve()
        if not run.is_relative_to(runs_root.resolve()):
            raise ValueError("Run escaped selected evidence root.")
        manifest = read(run / "manifest.json")
        if manifest["mode"] != "execute":
            raise ValueError("This editorial batch is limited to requested execute reports.")
        record_paths = sorted((run / "workspace" / "records").glob("*.json"))
        original_hashes = {str(path): sha(path) for path in record_paths}
        registry = {record["id"]: record for record in map(read, record_paths)}
        reports = [record for record in registry.values() if record["kind"] == "report"]
        if len(reports) != 1:
            raise ValueError("Require exactly one original report record; do not guess among alternatives.")
        report = reports[0]["payload"]
        source_pdf = rebase(report["path"], run)
        if sha(source_pdf) != report["sha256"]:
            raise ValueError("Original report hash differs from its record.")
        original_hashes[str(source_pdf)] = sha(source_pdf)
        plan = deepcopy(registry[report["plan_id"]]["payload"])
        analysis = deepcopy(registry[report["analysis_id"]]["payload"])
        bundle = deepcopy(registry[report["figure_bundle_id"]]["payload"])
        unchanged_metric_digest = hashlib.sha256(json.dumps(analysis["metrics_dict"], sort_keys=True).encode()).hexdigest()
        for figure in bundle["figures"]:
            for extension, raw in figure["paths"].items():
                path = rebase(raw, run)
                if sha(path) != figure["sha256"][extension]:
                    raise ValueError("Original figure hash differs from its record.")
                original_hashes[str(path)] = sha(path)
                figure["paths"][extension] = str(path)
        before = deepcopy(plan["narrative"])
        applied = []
        for replacement in entry.get("replacements", []):
            field, old, new = replacement["field"], replacement["before"], replacement["after"]
            if field not in plan["narrative"] or not old or plan["narrative"][field].count(old) != 1:
                raise ValueError(f"Exact replacement not found exactly once: {directory}/{field}")
            plan["narrative"][field] = plan["narrative"][field].replace(old, new, 1)
            applied.append(replacement)
        plan["narrative"]["title"] = "【审阅演示版】\n" + plan["narrative"]["title"]
        # Explicit label in the PDF itself; the original metrics and figures
        # remain the same, and the editorial operation is documented alongside.
        os.environ.update(RRA_DATA_ROOT=str(data_root.resolve()), RRA_RUN_ROOT=str(output_dir.resolve()), RRA_CASE=manifest["case_id"])
        target = output_dir / f"{manifest['case_id']}_reviewed.pdf"
        _export_pdf(target, plan, analysis, bundle)
        checks = verify_pdf(target, plan["target_pages"], len(bundle["figures"]), analysis["metrics_dict"])
        if not checks["passed"]:
            raise ValueError(f"Reviewed PDF QA failed: {checks}")
        if any(sha(Path(path)) != digest for path, digest in original_hashes.items()):
            raise ValueError("Original evidence changed during editorial export.")
        result = {"case_id": manifest["case_id"], "run_id": manifest["run_id"], "source_pdf": str(source_pdf),
                  "source_sha256": report["sha256"], "reviewed_pdf": str(target.resolve()), "reviewed_sha256": sha(target),
                  "operation": "separate AI editorial demonstration; not a benchmark rerun", "new_model_calls": 0,
                  "original_records_and_artifacts_unchanged": True, "metric_dictionary_sha256": unchanged_metric_digest,
                  "original_figure_sha256": [item["sha256"] for item in bundle["figures"]],
                  "exact_replacements": applied, "narrative_before": before, "narrative_after": plan["narrative"],
                  "additional_changes": ["Title labelled as reviewed demonstration"],
                  "automated_checks": checks}
        target.with_suffix(".review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(result)
    index = {"schema_version": 1, "replacement_file": str(edits_path.resolve()), "replacement_sha256": sha(edits_path),
             "not_part_of_original_benchmark": True, "reports": results}
    (output_dir / "reviewed_reports_index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--replacements", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = apply_edits(args.runs_root.resolve(), args.data_root.resolve(), args.replacements.resolve(), args.output_dir.resolve())
    print(json.dumps({"reports": [row["reviewed_pdf"] for row in result["reports"]], "model_calls": 0,
                      "original_benchmark_unchanged": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
