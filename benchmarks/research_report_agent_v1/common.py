"""Case-scoped, content-addressed records for the real report benchmark.

Only generated study inputs are synthetic. Records bind actual files and never
permit a caller-selected filesystem path. No oracle data is exposed here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _root(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"{variable} is required")
    return Path(value).expanduser().resolve()


def get_case_dir() -> Path:
    case = os.environ.get("RRA_CASE", "")
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", case):
        raise ValueError("RRA_CASE must be an explicit case identifier")
    root = _root("RRA_DATA_ROOT") / "cases"
    result = (root / case).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError("case escaped input scope")
    for name in ("data.csv", "study.json", "task.txt"):
        path = result / name
        if not path.is_file() or not path.resolve().is_relative_to(result):
            raise ValueError(f"missing or unsafe study input: {name}")
    return result


def get_run_dir() -> Path:
    result = _root("RRA_RUN_ROOT")
    source = get_case_dir()
    if result == source or result.is_relative_to(source) or source.is_relative_to(result):
        raise ValueError("run directory must be separate from source data")
    result.mkdir(parents=True, exist_ok=True)
    return result


def get_study() -> dict:
    value = json.loads((get_case_dir() / "study.json").read_text(encoding="utf-8"))
    if value.get("study_id") != os.environ["RRA_CASE"]:
        raise ValueError("study identifier does not match selected scope")
    return value


def study_version() -> str:
    directory = get_case_dir()
    value = {name: sha256_file(directory / name) for name in ("data.csv", "study.json")}
    return hashlib.sha256(canonical(value)).hexdigest()


def workspace_id() -> str:
    return "workspace-" + hashlib.sha256(str(get_run_dir()).encode()).hexdigest()[:24]


def artifact_path(relative: str) -> Path:
    """Return a contained output path; callers may write only inside this run."""
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("artifact path must be a contained relative path")
    result = (get_run_dir() / relative_path).resolve()
    if not result.is_relative_to(get_run_dir()):
        raise ValueError("artifact path escaped run scope")
    result.parent.mkdir(parents=True, exist_ok=True)
    return result


def _record_id(kind: str, body: dict) -> str:
    return "rra-" + kind + "-" + hashlib.sha256(canonical(body)).hexdigest()[:32]


def put_record(kind: str, payload: dict, authorized_tools=()) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", kind):
        raise ValueError("invalid record kind")
    if not isinstance(payload, dict):
        raise ValueError("record payload must be an object")
    permissions = sorted(set(authorized_tools))
    if any(not re.fullmatch(r"[a-z][a-z0-9_]*", name) for name in permissions):
        raise ValueError("permissions must be bare tool names")
    body = {"kind": kind, "payload": payload, "source_version": study_version(),
            "workspace_id": workspace_id(), "authorized_tools": permissions}
    identifier = _record_id(kind, body)
    path = artifact_path(f"records/{identifier}.json")
    encoded = canonical({"id": identifier, **body})
    if path.exists() and path.read_bytes() != encoded:
        raise ValueError("content-addressed record collision")
    path.write_bytes(encoded)
    return identifier


def get_record(identifier: str, kind: str | None = None) -> dict:
    if not re.fullmatch(r"rra-[a-z][a-z0-9_]{0,31}-[0-9a-f]{32}", identifier):
        raise ValueError("invalid record identifier")
    path = artifact_path(f"records/{identifier}.json")
    if not path.is_file():
        raise ValueError("record is unavailable in this run")
    raw = path.read_bytes()
    record = json.loads(raw)
    if record.get("id") != identifier:
        raise ValueError("record identifier mismatch")
    body = {key: value for key, value in record.items() if key != "id"}
    if _record_id(record["kind"], body) != identifier:
        raise ValueError("record content changed")
    if kind is not None and record["kind"] != kind:
        raise ValueError(f"expected {kind} record")
    if record["source_version"] != study_version():
        raise ValueError("source data changed; request a new semantic plan")
    if record["workspace_id"] != workspace_id():
        raise ValueError("record belongs to another workspace")
    is_plan = record["kind"].endswith("plan") or record["kind"].startswith("plan_")
    record["_provenance"] = {
        "workspace_id": record["workspace_id"],
        "data_sha256": sha256_file(get_case_dir() / "data.csv"),
        "study_sha256": record["source_version"],
        "record_sha256": hashlib.sha256(raw).hexdigest(),
        "record_path": str(path),
        "authorized_tools": record["authorized_tools"],
        "plan_id": identifier if is_plan else record["payload"].get("plan_id"),
    }
    return record


def tool_response(identifier: str, field: str, extra: dict | None = None) -> dict:
    record = get_record(identifier)
    result = {"ok": True, field: identifier, "source_version": record["source_version"],
              "_provenance": record["_provenance"]}
    if extra:
        if any(key in result for key in extra):
            raise ValueError("extra response fields cannot replace provenance")
        result.update(extra)
    return result
