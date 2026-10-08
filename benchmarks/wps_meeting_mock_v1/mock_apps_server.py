"""Read-only MCP facade over three separate synthetic application sources.

The facade is a development fixture, not a WPS, Obsidian, or Zotero connector.
Only the four approved object IDs are exposed. A pinned handle fails after its
source bytes change; this supports tool/parameter-flow diagnostics only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from benchmarks.wps_meeting_mock_v1.run_mock import DEFAULT_BOOK, metrics, read_rows, validate


HERE = Path(__file__).resolve().parent
APP_DATA = HERE / "mock_app_sources.json"
_handles: dict[str, tuple[str, str]] = {}


def _sources() -> dict:
    return json.loads(APP_DATA.read_text(encoding="utf-8"))


def _version(object_id: str) -> str:
    sources = _sources()
    if object_id == "wps:experiment_log":
        raw = DEFAULT_BOOK.read_bytes()
    elif object_id in sources:
        raw = json.dumps(sources[object_id], ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    else:
        raise ValueError("object is outside the mock task scope")
    return hashlib.sha256(raw).hexdigest()


def list_mock_sources() -> dict:
    """List names and kinds of the task's approved synthetic objects."""
    return {"sources": [
        {"object_id": "wps:experiment_log", "app": "wps", "title": "合成实验记录"},
        *({"object_id": key, "app": value["app"], "title": value["title"]}
          for key, value in sorted(_sources().items())),
    ], "synthetic": True}


def pin_mock_source(object_id: str) -> dict:
    """Bind one approved object to its current version and return source_id."""
    version = _version(object_id)
    token = hashlib.sha256(f"{object_id}:{version}".encode()).hexdigest()[:32]
    source_id = f"source-{token}"
    _handles[source_id] = (object_id, version)
    return {"source_id": source_id, "object_id": object_id,
            "version_sha256": version, "synthetic": True}


def _pinned(source_id: str) -> tuple[str, str]:
    item = _handles.get(source_id)
    if item is None:
        raise ValueError("unknown or expired mock source_id")
    object_id, version = item
    if _version(object_id) != version:
        raise ValueError("mock source changed; pin a new version")
    return item


def read_pinned_mock_source(source_id: str) -> dict:
    """Read the pinned WPS rows or the pinned note and its provenance."""
    object_id, version = _pinned(source_id)
    if object_id == "wps:experiment_log":
        rows = read_rows(DEFAULT_BOOK)
        validate(rows)
        return {"object_id": object_id, "version_sha256": version,
                "records": rows, "synthetic": True}
    return {"object_id": object_id, "version_sha256": version,
            **_sources()[object_id], "synthetic": True}


def calculate_pinned_wps_metrics(source_id: str) -> dict:
    """Recompute totals from pinned WPS bytes; make no research decision."""
    object_id, version = _pinned(source_id)
    if object_id != "wps:experiment_log":
        raise ValueError("source_id is not the WPS experiment table")
    rows = read_rows(DEFAULT_BOOK)
    validate(rows)
    return {"object_id": object_id, "version_sha256": version,
            "metric_definition": "sum(correct) / sum(test_cases) for each variant",
            "metrics": metrics(rows), "synthetic": True}


server = MCPServer(
    "sss-synthetic-meeting-apps",
    instructions="Synthetic read-only WPS, Obsidian, and Zotero task sources. "
    "Pin an approved object before reading or calculating. Source versions "
    "are checked on every call. Paper titles and content are fictional.",
)
for function in (list_mock_sources, pin_mock_source, read_pinned_mock_source,
                 calculate_pinned_wps_metrics):
    server.add_tool(function, name=function.__name__,
                    annotations=ToolAnnotations(readOnlyHint=True,
                                                destructiveHint=False,
                                                openWorldHint=False))


if __name__ == "__main__":
    server.run(transport="stdio")
