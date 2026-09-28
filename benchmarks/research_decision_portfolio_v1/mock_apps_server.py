"""Case-scoped, read-only MCP for the synthetic research decision portfolio.

Only the selected case's agent-visible event and source objects are loaded.
The separate review file is never opened by this server.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Annotated

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field


ROOT = Path(__file__).resolve().parent
_handles: dict[str, tuple[str, str]] = {}
_datasets: dict[str, str] = {}
_discovered: set[str] = set()

EventId = Annotated[str, Field(
    pattern=r"^event:[a-z_]+:01$",
    description="从任务卡复制事件 ID；先读事件才会得到本题初始对象 ID。")]
ObjectId = Annotated[str, Field(
    pattern=r"^(?:paper|zotero|obsidian|wps|github|gmail|calendar):[a-z][a-z0-9_]*$",
    description="应用对象 ID，须先由 read_event、read_pinned.links 或 find_dependents 返回；"
                "不能把 source_id 或 dataset_id 当成对象 ID。")]
SourceId = Annotated[str, Field(
    pattern=r"^source-[0-9a-f]{32}$",
    description="只能使用 pin_resource 返回的 source_id；它绑定对象的内容版本。")]
DatasetId = Annotated[str, Field(
    pattern=r"^dataset-[0-9a-f]{32}$",
    description="只能使用 read_pinned 读取表格后返回的 value.dataset_id。")]


def _case_dir() -> Path:
    case = os.environ.get("SSS_PORTFOLIO_CASE", "")
    if not case or not case.isascii() or not all(ch.islower() or ch.isdigit() or ch == "_"
                                                  for ch in case):
        raise ValueError("SSS_PORTFOLIO_CASE must name one frozen fixture")
    path = ROOT / "cases" / case
    if not (path / "sources.json").is_file():
        raise ValueError("unknown portfolio case")
    return path


def _sources() -> dict:
    return json.loads((_case_dir() / "sources.json").read_text(encoding="utf-8"))


def _version(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _object(object_id: str) -> dict:
    try:
        return _sources()["objects"][object_id]
    except KeyError as exc:
        raise ValueError("object is outside the selected case") from exc


def read_event(event_id: EventId) -> dict:
    """Read this task's update and discover its scoped source IDs."""
    event = _sources()["event"]
    if event_id != event["event_id"]:
        raise ValueError("event is outside the selected case")
    _discovered.update(event["root_objects"])
    roots = event["root_objects"]
    return {**event, "root_object_id": roots[0],
            "additional_object_id": roots[1] if len(roots) > 1 else None,
            "version_sha256": _version(event)}


def pin_resource(object_id: ObjectId) -> dict:
    """Bind one authorized application object to its current content version."""
    obj = _object(object_id)
    if object_id not in _discovered:
        raise ValueError("object has not been discovered from this event or a scoped relation")
    version = _version(obj)
    source_id = "source-" + hashlib.sha256(
        f"{_case_dir().name}:{object_id}:{version}".encode()).hexdigest()[:32]
    _handles[source_id] = (object_id, version)
    return {"object_id": object_id, "source_id": source_id,
            "version_sha256": version, "app": obj["app"], "kind": obj["kind"],
            "synthetic": True}


def _pinned(source_id: str) -> tuple[str, dict, str]:
    try:
        object_id, version = _handles[source_id]
    except KeyError as exc:
        raise ValueError("unknown source_id; call pin_resource first") from exc
    obj = _object(object_id)
    if _version(obj) != version:
        raise ValueError("object changed since pin; obtain a new source_id")
    return object_id, obj, version


def read_pinned(source_id: SourceId) -> dict:
    """Read a pinned note, paper excerpt, annotation, email, log or table schema."""
    object_id, obj, version = _pinned(source_id)
    if obj["kind"] == "table":
        dataset_id = "dataset-" + hashlib.sha256(source_id.encode()).hexdigest()[:32]
        _datasets[dataset_id] = source_id
        value = {"title": obj["title"], "fields": sorted(obj["rows"][0]),
                 "row_count": len(obj["rows"]), "metric": obj["metric"],
                 "protocol": obj.get("protocol", ""), "dataset_id": dataset_id}
    else:
        value = {key: obj[key] for key in ("title", "text", "links", "depends_on")}
        _discovered.update(obj.get("links", []))
        for index, linked in enumerate(obj.get("links", [])[:4]):
            value[f"link_{index}_object_id"] = linked
    return {"source_id": source_id, "object_id": object_id,
            "version_sha256": version, "value": value, "synthetic": True}


def _dataset(dataset_id: str) -> tuple[str, dict, str]:
    try:
        source_id = _datasets[dataset_id]
    except KeyError as exc:
        raise ValueError("unknown dataset_id; inspect a pinned table first") from exc
    _, obj, version = _pinned(source_id)
    if obj["kind"] != "table":
        raise ValueError("dataset is not a table")
    return source_id, obj, version


def read_rows(dataset_id: DatasetId, offset: int = 0, limit: int = 20) -> dict:
    """Return a bounded range of raw, version-bound table rows."""
    source_id, obj, version = _dataset(dataset_id)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("invalid row range")
    return {"dataset_id": dataset_id, "source_id": source_id,
            "version_sha256": version, "offset": offset, "total": len(obj["rows"]),
            "rows": obj["rows"][offset:offset + limit], "synthetic": True}


def aggregate_rate(dataset_id: DatasetId, group_by: str) -> dict:
    """Sum the declared numerator and denominator for one chosen group field."""
    source_id, obj, version = _dataset(dataset_id)
    contract = obj["metric"]
    if group_by not in contract["allowed_groups"]:
        raise ValueError("group field is outside the metric contract")
    sums = defaultdict(lambda: [0, 0])
    for row in obj["rows"]:
        top, bottom = row[contract["numerator"]], row[contract["denominator"]]
        if (type(top) is not int or type(bottom) is not int or
                bottom <= 0 or top < 0 or top > bottom):
            raise ValueError("invalid metric row")
        sums[row[group_by]][0] += top
        sums[row[group_by]][1] += bottom
    groups = [{group_by: key, "numerator": top, "denominator": bottom,
               "value": top / bottom}
              for key, (top, bottom) in sorted(sums.items())]
    return {"dataset_id": dataset_id, "source_id": source_id,
            "version_sha256": version, "group_by": group_by,
            "metric_id": contract["id"], "groups": groups, "synthetic": True}


def compare_tables(previous_dataset_id: DatasetId, current_dataset_id: DatasetId) -> dict:
    """Compare same-key rows; report changes without explaining their meaning."""
    _, old, old_version = _dataset(previous_dataset_id)
    _, new, new_version = _dataset(current_dataset_id)
    if old["metric"] != new["metric"]:
        raise ValueError("metric contracts differ; semantic review required")
    fields = old["metric"]["allowed_groups"] + ["seed"]
    def keyed(rows: list[dict]) -> dict[tuple, dict]:
        result = {}
        for row in rows:
            key = tuple(row.get(field) for field in fields)
            if None in key or key in result:
                raise ValueError("missing or duplicated row key")
            result[key] = row
        return result
    before, after = keyed(old["rows"]), keyed(new["rows"])
    if before.keys() != after.keys():
        return {"status": "row_keys_changed", "synthetic": True}
    changed = [{"key": dict(zip(fields, key, strict=True)),
                "before": before[key], "after": after[key]}
               for key in sorted(before) if before[key] != after[key]]
    return {"status": "compared", "previous_version_sha256": old_version,
            "current_version_sha256": new_version,
            "protocol_changed": old.get("protocol", "") != new.get("protocol", ""),
            "changed_rows": changed,
            "synthetic": True}


def find_dependents(object_id: ObjectId) -> dict:
    """Find scoped notes that explicitly depend on an object, with index version."""
    _object(object_id)
    if object_id not in _discovered:
        raise ValueError("source object has not been discovered")
    objects = _sources()["objects"]
    claims = [{"object_id": identifier, "title": obj["title"]}
              for identifier, obj in sorted(objects.items())
              if object_id in obj.get("depends_on", [])]
    _discovered.update(claim["object_id"] for claim in claims)
    return {"object_id": object_id, "claims": claims,
            "claim_object_id": claims[0]["object_id"] if len(claims) == 1 else None,
            "index_version_sha256": _version(objects), "synthetic": True}


def locate_excerpt(source_id: SourceId, exact_text: str) -> dict:
    """Locate an exact quoted phrase in one pinned document; return all offsets."""
    if not 3 <= len(exact_text) <= 200:
        raise ValueError("exact_text must contain 3 to 200 characters")
    object_id, obj, version = _pinned(source_id)
    if obj["kind"] == "table":
        raise ValueError("excerpt search requires a text object")
    content = obj["text"]
    positions = []
    cursor = 0
    while True:
        at = content.find(exact_text, cursor)
        if at < 0:
            break
        positions.append(at)
        cursor = at + 1
    return {"source_id": source_id, "object_id": object_id,
            "version_sha256": version, "positions": positions,
            "unique": len(positions) == 1, "synthetic": True}


server = MCPServer("sss-research-decision-portfolio",
                   instructions="Read-only, case-scoped synthetic research sources. "
                   "Pinned handles bind objects to content versions. "
                   "Calculations and exact text locations do not determine scientific meaning.")
for function in (read_event, pin_resource, read_pinned, read_rows,
                 aggregate_rate, compare_tables, find_dependents, locate_excerpt):
    server.add_tool(function, name=function.__name__,
                    annotations=ToolAnnotations(readOnlyHint=True,
                                                destructiveHint=False,
                                                openWorldHint=False))


if __name__ == "__main__":
    _case_dir()
    server.run(transport="stdio")
