"""Freeze user-provided CSV, optional context/outline and request without inventing design."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
import re


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_text(path: Path, *, maximum: int = 1_000_000) -> str:
    raw = Path(path).read_bytes()
    if len(raw) > maximum:
        raise ValueError(f"Input exceeds {maximum} bytes: {Path(path).name}")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Inputs must be UTF-8; convert their encoding before running") from exc


def materialize(*, data: Path, request_file: Path, destination: Path,
                study_json: Path | None = None, outline_file: Path | None = None,
                case_id: str | None = None) -> dict:
    """Copy immutable inputs into destination/cases/id; no case-name dispatch.

    This deliberately does not infer paired subjects, randomization, units,
    missingness assumptions, statistical design or requested report length.
    The tools/LLM must use provided study descriptions or ask for clarification.
    """
    csv_text = read_text(data, maximum=20_000_000)
    table = list(csv.reader(io.StringIO(csv_text)))
    if not table or len(table) < 2 or not table[0] or any(not name.strip() for name in table[0]):
        raise ValueError("CSV needs a nonempty header and at least one data row")
    if len(set(table[0])) != len(table[0]) or any(len(row) != len(table[0]) for row in table[1:]):
        raise ValueError("CSV headers must be unique and row widths consistent")
    request = read_text(request_file).strip()
    if not request:
        raise ValueError("A nonempty user request is required")
    supplied = json.loads(read_text(study_json)) if study_json else {}
    if not isinstance(supplied, dict):
        raise ValueError("--study-json must contain a JSON object")
    if "benchmark_frozen_decisions" in supplied:
        raise ValueError("v3 main experiment requires free presentation and narrative; frozen decisions are not accepted")
    # Match the record layer's strict canonical JSON before any paid execution.
    json.dumps(supplied, ensure_ascii=False, allow_nan=False)
    outline = read_text(outline_file).strip() if outline_file else None
    if outline_file and not outline:
        raise ValueError("An outline file cannot be empty")
    fingerprint = sha(json.dumps({"csv": sha(csv_text.encode()), "request": request,
                                  "study": supplied, "outline": outline},
                                 ensure_ascii=False, sort_keys=True).encode())
    case_id = case_id or "input_" + fingerprint[:20]
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", case_id):
        raise ValueError("Invalid case identifier")
    # User context is evidence, not trusted executable instructions. Source paths
    # cannot redirect the service away from this scoped copy.
    study = dict(supplied)
    study.update(study_id=case_id, data_file="data.csv", row_count=len(table) - 1,
                 user_request=request, schema_version="research-report-input-v3")
    study.setdefault("title", "用户科研数据分析")
    study.setdefault("description", "未提供研究设计说明；不得由文件名或案例编号推断独立性、配对或因果关系。")
    study.setdefault("columns", {column: "用户未提供字段解释" for column in table[0]})
    study.setdefault("units", {})
    study.setdefault("report_requirements", {})
    if not isinstance(study["report_requirements"], dict):
        raise ValueError("report_requirements must be an object")
    if "synthetic" not in study:
        study["source_status"] = "user_provided; real/synthetic status unspecified"
    if outline is not None:
        study["user_outline"] = outline
        # Keep the original outline verbatim in user input. JSON is not evaluated.
        request += "\n\n用户提供的报告大纲（保留其标题和顺序，按其意图组织报告）：\n" + outline
    folder = Path(destination).resolve() / "cases" / case_id
    payloads = {"data.csv": csv_text,
                "study.json": json.dumps(study, ensure_ascii=False, indent=2) + "\n",
                "task.txt": request + "\n"}
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in payloads.items():
        target = folder / name
        if target.exists() and target.read_bytes() != content.encode("utf-8"):
            raise ValueError("Frozen input already exists with different content; use a fresh run directory")
        target.write_text(content, encoding="utf-8", newline="\n")
        target.chmod(0o600)
    return {"data_root": str(Path(destination).resolve()), "case_id": case_id,
            "folder": str(folder), "input_fingerprint": fingerprint,
            "original_filenames": {"data": Path(data).name, "request": Path(request_file).name,
                                   "study": Path(study_json).name if study_json else None,
                                   "outline": Path(outline_file).name if outline_file else None},
            "source_sha256": {name: sha((folder / name).read_bytes()) for name in payloads},
            "study_context_supplied": bool(study_json), "outline_supplied": bool(outline_file)}
