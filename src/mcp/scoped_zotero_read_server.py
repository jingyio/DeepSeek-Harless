"""Version-bound, read-only Zotero metadata and annotations for one approved task.

The task scope names exact item keys, revisions and canonical content hashes.
Only selected text is returned to the model. This server is opt-in and is not
part of the default 87-tool connector catalog.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from src.mcp.structured_research_tools import HandleStore

ROOT = Path(__file__).resolve().parents[2]
LOCAL = (ROOT / ".local").resolve()
ZOTERO_KEY = re.compile(r"[A-Z0-9]{8}\Z")
_HANDLE_STORE = HandleStore(LOCAL / "scoped-research-handles" / "handles.sqlite3")
server = MCPServer(
    "sss-scoped-zotero-read",
    instructions="Only task-approved Zotero items and annotations are visible. "
    "Pin a listed role before reading. A revision, content, permission or scope change "
    "invalidates the handle. No Zotero search or write operation is available.",
)


def _scope_file() -> Path:
    raw = os.environ.get("SSS_RESEARCH_SCOPE_FILE", "")
    if not raw:
        raise RuntimeError("A private task scope is required")
    path = Path(raw).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(LOCAL):
        raise ValueError("Task scope must be a file under SSS/.local")
    return path


def _scope() -> dict[str, Any]:
    data = json.loads(_scope_file().read_text(encoding="utf-8"))
    rows = data.get("zotero_sources") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Task scope has no Zotero source list")
    return data


def _row(role: str) -> dict[str, Any]:
    matches = [row for row in _scope()["zotero_sources"] if isinstance(row, dict)
               and row.get("role") == role]
    if len(matches) != 1 or matches[0].get("external_model_excerpt_allowed") is not True:
        raise ValueError("Zotero source is not uniquely approved for model access")
    row = matches[0]
    if (not isinstance(row.get("key"), str) or not ZOTERO_KEY.fullmatch(row["key"])
            or row.get("kind") not in {"item", "annotation"}
            or type(row.get("version")) is not int or row["version"] < 0
            or not isinstance(row.get("data_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["data_sha256"])):
        raise ValueError("Invalid scoped Zotero entry")
    return row


def _fetch_item(key: str) -> dict[str, Any]:
    if not ZOTERO_KEY.fullmatch(key):
        raise ValueError("Invalid Zotero item key")
    url = "http://127.0.0.1:23119/api/users/0/items/" + urllib.parse.quote(key)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=15) as response:
        data = json.load(response)
    if not isinstance(data, dict) or data.get("key") != key or not isinstance(data.get("data"), dict):
        raise ValueError("Zotero returned an unexpected item")
    return data


def _data_digest(item: dict[str, Any]) -> str:
    raw = json.dumps(item["data"], ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _verified(row: dict[str, Any]) -> dict[str, Any]:
    item = _fetch_item(row["key"])
    item_type = item["data"].get("itemType")
    if ((item_type == "annotation") != (row["kind"] == "annotation")
            or item.get("version") != row["version"]
            or _data_digest(item) != row["data_sha256"]):
        raise ValueError("Zotero source version changed; renew the task scope")
    return item


def list_scoped_zotero_sources() -> dict[str, Any]:
    """List task-approved Zotero roles, kinds and keys without text content."""
    roles = [row.get("role") for row in _scope()["zotero_sources"]
             if isinstance(row, dict) and row.get("external_model_excerpt_allowed") is True]
    rows = []
    for role in roles:
        row = _row(role)
        rows.append({"role": row["role"], "kind": row["kind"], "key": row["key"],
                     "version": row["version"], "data_sha256": row["data_sha256"]})
    return {"sources": rows, "count": len(rows)}


def pin_scoped_zotero_source(role: str) -> dict[str, Any]:
    """Pin an approved Zotero item or annotation to an opaque source_id."""
    row = _row(role)
    _verified(row)
    scope_path = _scope_file()
    source_id = _HANDLE_STORE.put("source", {
        "origin": "scoped_zotero_read", "scope_path": str(scope_path),
        "scope_sha256": hashlib.sha256(scope_path.read_bytes()).hexdigest(),
        "role": role, "key": row["key"], "kind": row["kind"],
        "version": row["version"], "data_sha256": row["data_sha256"],
    })
    return {"source_id": source_id, "role": role, "key": row["key"],
            "kind": row["kind"], "version": row["version"],
            "data_sha256": row["data_sha256"]}


def _pinned(source_id: str, kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    handle = _HANDLE_STORE.get(source_id, "source")
    scope_path = _scope_file()
    if (handle.get("origin") != "scoped_zotero_read"
            or handle.get("scope_path") != str(scope_path)
            or handle.get("scope_sha256") != hashlib.sha256(scope_path.read_bytes()).hexdigest()
            or handle.get("kind") != kind):
        raise ValueError("Zotero source handle scope or kind changed")
    row = _row(handle["role"])
    if any(row[field] != handle.get(field) for field in
           ("key", "kind", "version", "data_sha256")):
        raise ValueError("Zotero source approval changed")
    return row, _verified(row)


def read_pinned_zotero_item(source_id: str) -> dict[str, Any]:
    """Read bounded bibliographic metadata for one pinned non-annotation item."""
    row, item = _pinned(source_id, "item")
    data = item["data"]
    abstract = str(data.get("abstractNote") or "")
    return {"source_id": source_id, "role": row["role"], "key": row["key"],
            "version": row["version"], "data_sha256": row["data_sha256"],
            "item_type": data.get("itemType"), "title": str(data.get("title") or "")[:1000],
            "date": data.get("date"), "publication_title": data.get("publicationTitle"),
            "doi": data.get("DOI"), "url": data.get("url"),
            "abstract": abstract[:4000], "abstract_total_chars": len(abstract),
            "abstract_truncated": len(abstract) > 4000}


def read_pinned_zotero_annotation(source_id: str) -> dict[str, Any]:
    """Read bounded annotation text, comment and PDF page label from one pin."""
    row, item = _pinned(source_id, "annotation")
    data = item["data"]
    marked = str(data.get("annotationText") or "")
    comment = str(data.get("annotationComment") or "")
    parent_key = data.get("parentItem")
    relation: dict[str, Any] = {"status": "unverified",
                                "attachment_key": parent_key,
                                "approved_paper_key": None}
    if isinstance(parent_key, str) and ZOTERO_KEY.fullmatch(parent_key):
        approved_papers = [source for source in _scope()["zotero_sources"]
                           if isinstance(source, dict) and source.get("kind") == "item"
                           and source.get("external_model_excerpt_allowed") is True]
        if any(source.get("key") == parent_key for source in approved_papers):
            paper = next(source for source in approved_papers
                         if source.get("key") == parent_key)
            verified_paper = _verified(_row(paper["role"]))
            if verified_paper["data"].get("itemType") != "attachment":
                relation = {"status": "verified_direct_paper",
                            "attachment_key": None, "approved_paper_key": parent_key}
        else:
            # Zotero annotations normally belong to a PDF attachment. Resolve
            # only its parent pointer; expose no unapproved attachment content.
            try:
                attachment = _fetch_item(parent_key)
            except (OSError, ValueError, KeyError):
                attachment = None
            paper_key = attachment["data"].get("parentItem") if attachment else None
            if attachment and attachment["data"].get("itemType") == "attachment":
                for paper in approved_papers:
                    if paper.get("key") == paper_key:
                        verified_paper = _verified(_row(paper["role"]))
                        if verified_paper["data"].get("itemType") != "attachment":
                            relation = {"status": "verified_attachment_to_paper",
                                        "attachment_key": parent_key,
                                        "attachment_version": attachment.get("version"),
                                        "approved_paper_key": paper_key}
                        break
    return {"source_id": source_id, "role": row["role"], "key": row["key"],
            "version": row["version"], "data_sha256": row["data_sha256"],
            "parent_item": parent_key, "parent_relation": relation,
            "page_label": data.get("annotationPageLabel"),
            "marked_text": marked[:6000], "marked_total_chars": len(marked),
            "marked_truncated": len(marked) > 6000,
            "researcher_comment": comment[:6000], "comment_total_chars": len(comment),
            "comment_truncated": len(comment) > 6000,
            "modified_at": data.get("dateModified")}


for function in (list_scoped_zotero_sources, pin_scoped_zotero_source,
                 read_pinned_zotero_item, read_pinned_zotero_annotation):
    server.add_tool(function, annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, openWorldHint=False))


if __name__ == "__main__":
    server.run(transport="stdio")
