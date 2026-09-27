"""Case-scoped, read-only MCP facade for synthetic WPS/Obsidian/Zotero sources.

This is a development fixture. The Agent sees one case selected by
SSS_MEETING_CASE; it cannot browse other cases through this server.
Every returned handle binds an application object to the bytes read at pin time.
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
from openpyxl import load_workbook
from pydantic import Field


ROOT = Path(__file__).resolve().parent
V2_ROOT = ROOT.parent / "meeting_decision_chain_v2"
V2_CASE_IDS = frozenset(("model_rsi_state", "aidd_mutation",
                         "agent_tool_transfer"))
V3_ROOT = ROOT.parent / "meeting_decision_chain_v3"
V3_CASE_IDS = frozenset(("rna_batch", "retrieval_language", "robot_protocol"))
V4_ROOT = ROOT.parent / "meeting_decision_chain_v4"
V4_CASE_IDS = frozenset(("battery_cold", "corpus_shift", "remote_assay"))
V5_ROOT = ROOT.parent / "meeting_decision_chain_v5"
V5_CASE_IDS = frozenset(("microscopy_vendor", "chemistry_substrate",
                         "materials_scaleup"))
CASE_IDS = frozenset(("family_shift", "label_audit", "hardware_latency",
                      "novel_queries", "site_transfer", "tail_terms",
                      "lot_stability")) | V2_CASE_IDS | V3_CASE_IDS | V4_CASE_IDS | V5_CASE_IDS
_handles: dict[str, tuple[str, str]] = {}
_datasets: dict[str, str] = {}

EventId = Annotated[str, Field(
    pattern=r"^event:[a-z_]+:w[0-9]{2}$",
    description="事件 ID；从任务输入取得，例如 event:novel_queries:w39。")]
ObjectId = Annotated[str, Field(
    pattern=r"^(?:wps|obsidian|zotero):[a-z_]+:[A-Za-z0-9_]+$",
    description="应用对象 ID；取自 read_change 的 experiment_id / previous_experiment_id，"
                "或 find_dependent_claims 的 note_id / annotation_id。claim_id 不是可固定对象。")]
CurrentExperimentId = Annotated[str, Field(
    pattern=r"^wps:[a-z_]+:run_2026w39$",
    description="只填 read_change.experiment_id（当前实验）；previous_experiment_id 不在当前主张索引中。")]
SourceId = Annotated[str, Field(
    pattern=r"^source-[0-9a-f]{32}$",
    description="只能填 pin_object 刚返回的 source_id，不能填 WPS/Obsidian/Zotero 对象 ID。")]
DatasetId = Annotated[str, Field(
    pattern=r"^dataset-[0-9a-f]{32}$",
    description="只能填 read_pinned_object 对实验表返回的 value.dataset_id。")]


def _case() -> str:
    case = os.environ.get("SSS_MEETING_CASE", "")
    if case not in CASE_IDS:
        raise ValueError("SSS_MEETING_CASE must name one approved fixture")
    return case


def _path(kind: str) -> Path:
    names = {"event": "event.json", "experiment": "experiment.xlsx",
             "previous_experiment": "previous_experiment.xlsx",
             "metric": "metric.json", "note": "note.json",
             "annotation": "annotation.json"}
    if kind not in names:
        raise ValueError("unknown source kind")
    case = _case()
    base = (V5_ROOT if case in V5_CASE_IDS else
            V4_ROOT if case in V4_CASE_IDS else
            V3_ROOT if case in V3_CASE_IDS else
            V2_ROOT if case in V2_CASE_IDS else ROOT)
    return base / "sources" / case / names[kind]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(kind: str) -> dict:
    return json.loads(_path(kind).read_text(encoding="utf-8"))


def _object_kind(object_id: str) -> str:
    case = _case()
    allowed = {f"wps:{case}:run_2026w39": "experiment",
               f"wps:{case}:run_2026w38": "previous_experiment",
               f"obsidian:{case}:claim": "note",
               f"zotero:{case}:annotation": "annotation"}
    try:
        return allowed[object_id]
    except KeyError as exc:
        raise ValueError("object is outside this case") from exc


def read_change(event_id: EventId) -> dict:
    """Read the selected update event; its result identifies the changed object."""
    event = _json("event")
    if event_id != event["event_id"]:
        raise ValueError("event is outside this case")
    return {**event, "event_version": _sha(_path("event")), "synthetic": True}


def pin_object(object_id: ObjectId) -> dict:
    """Pin an approved application object; return an opaque source_id for reading."""
    kind = _object_kind(object_id)
    version = _sha(_path(kind))
    source_id = "source-" + hashlib.sha256(
        f"{_case()}:{object_id}:{version}".encode()).hexdigest()[:32]
    _handles[source_id] = (object_id, version)
    return {"source_id": source_id, "object_id": object_id, "kind": kind,
            "version_sha256": version, "synthetic": True}


def _pinned(source_id: str) -> tuple[str, str, str]:
    try:
        object_id, version = _handles[source_id]
    except KeyError as exc:
        raise ValueError("unknown source handle") from exc
    kind = _object_kind(object_id)
    if version != _sha(_path(kind)):
        raise ValueError("source changed since pin; pin a new version")
    return object_id, kind, version


def _rows(kind: str) -> tuple[list[str], list[dict]]:
    workbook = load_workbook(_path(kind), read_only=True, data_only=True)
    try:
        if workbook.sheetnames != ["实验记录"]:
            raise ValueError("experiment worksheet changed")
        values = workbook.active.iter_rows(values_only=True)
        fields = list(next(values))
        if len(fields) != len(set(fields)) or any(not isinstance(x, str) for x in fields):
            raise ValueError("invalid experiment fields")
        rows = [dict(zip(fields, cells, strict=True)) for cells in values
                if any(value is not None for value in cells)]
        return fields, rows
    finally:
        workbook.close()


def read_pinned_object(source_id: SourceId) -> dict:
    """Read by the opaque source_id returned by pin_object, never by object_id."""
    object_id, kind, version = _pinned(source_id)
    if kind in ("experiment", "previous_experiment"):
        fields, rows = _rows(kind)
        dataset_id = "dataset-" + hashlib.sha256(
            f"{source_id}:{_sha(_path('metric'))}".encode()).hexdigest()[:32]
        _datasets[dataset_id] = source_id
        value = {"fields": fields, "row_count": len(rows),
                 "metric_contract": _json("metric"), "dataset_id": dataset_id}
    else:
        value = _json(kind)
    return {"source_id": source_id, "object_id": object_id,
            "version_sha256": version, "value": value, "synthetic": True}


def _dataset(dataset_id: str) -> tuple[str, str, str]:
    try:
        source_id = _datasets[dataset_id]
    except KeyError as exc:
        raise ValueError("unknown dataset handle; inspect a pinned experiment") from exc
    object_id, kind, version = _pinned(source_id)
    if kind not in ("experiment", "previous_experiment"):
        raise ValueError("dataset is not an experiment table")
    expected = "dataset-" + hashlib.sha256(
        f"{source_id}:{_sha(_path('metric'))}".encode()).hexdigest()[:32]
    if dataset_id != expected:
        raise ValueError("metric contract changed since inspection")
    return source_id, kind, version


def read_dataset_rows(dataset_id: DatasetId, offset: int = 0, limit: int = 20) -> dict:
    """Inspect a bounded page of raw records from a version-bound dataset."""
    source_id, kind, version = _dataset(dataset_id)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("invalid row range")
    _, rows = _rows(kind)
    return {"dataset_id": dataset_id, "source_id": source_id,
            "version_sha256": version, "offset": offset, "total": len(rows),
            "rows": rows[offset:offset + limit], "synthetic": True}


def aggregate_pinned_experiment(dataset_id: DatasetId, group_by: list[str]) -> dict:
    """Sum a declared numerator/denominator by chosen fields; infer no conclusion."""
    source_id, kind, version = _dataset(dataset_id)
    object_id = _handles[source_id][0]
    contract = _json("metric")
    fields, rows = _rows(kind)
    if not group_by or len(group_by) > 2 or len(set(group_by)) != len(group_by):
        raise ValueError("select one or two distinct group fields")
    if any(g not in contract["allowed_groups"] or g not in fields for g in group_by):
        raise ValueError("group field is outside the declared metric")
    numerator, denominator = contract["numerator"], contract["denominator"]
    if numerator not in fields or denominator not in fields:
        raise ValueError("metric fields changed")
    totals: dict[tuple, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        top, bottom = row[numerator], row[denominator]
        if (type(top) is not int or type(bottom) is not int or
            top < 0 or bottom <= 0 or
            (contract["id"] == "correct_rate" and top > bottom)):
            raise ValueError("invalid metric input")
        bucket = totals[tuple(row[g] for g in group_by)]
        bucket[0] += top
        bucket[1] += bottom
    groups = [{**dict(zip(group_by, key, strict=True)), "numerator": top,
               "denominator": bottom, "value": top / bottom}
              for key, (top, bottom) in sorted(totals.items())]
    return {"dataset_id": dataset_id, "source_id": source_id, "object_id": object_id,
            "version_sha256": version, "metric_id": contract["id"],
            "group_by": group_by, "groups": groups, "synthetic": True}


def find_dependent_claims(object_id: CurrentExperimentId) -> dict:
    """Find claims for the current experiment_id only, not the previous run."""
    if _object_kind(object_id) != "experiment":
        raise ValueError("dependency lookup needs an experiment object")
    note = _json("note")
    if note["depends_on"] != object_id:
        raise ValueError("dependency index and source disagree")
    case = _case()
    index_version = hashlib.sha256(":".join((
        _sha(_path("experiment")), _sha(_path("note")),
        _sha(_path("annotation")))).encode()).hexdigest()
    return {"experiment_id": object_id, "claims": [{
        "claim_id": note["claim_id"],
        "note_id": f"obsidian:{case}:claim",
        "annotation_id": f"zotero:{case}:annotation",
    }], "index_version_sha256": index_version, "synthetic": True}


server = MCPServer(
    "sss-meeting-decision-fixture",
    instructions="Read-only synthetic WPS, Obsidian and Zotero fixture. "
    "An update identifies a changed object; pinned handles bind its version. "
    "Numerical aggregation does not make the research decision.",
)
for function in (read_change, pin_object, read_pinned_object,
                 read_dataset_rows, aggregate_pinned_experiment, find_dependent_claims):
    server.add_tool(function, name=function.__name__,
                    annotations=ToolAnnotations(readOnlyHint=True,
                                                destructiveHint=False,
                                                openWorldHint=False))


if __name__ == "__main__":
    _case()
    server.run(transport="stdio")
