"""Read a Zotero collection's annotation inventory via the collection filter.

Zotero's local attachment ``/children`` can return an empty list even when the
collection's ``itemType=annotation`` query contains annotations. This adapter
uses the latter and returns metadata only; it never exports annotation text.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any


PAGE_SIZE = 100
ZOTERO_KEY = re.compile(r"[A-Z0-9]{8}\Z")
FetchPage = Callable[[str], tuple[list[dict[str, Any]], int]]


def local_fetch_page(url: str) -> tuple[list[dict[str, Any]], int]:
    """Fetch only Zotero's local HTTP API, bypassing shell proxy settings."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Zotero metadata reads must use the local API")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=15) as response:
        rows = json.load(response)
        total = int(response.headers["Total-Results"])
    if not isinstance(rows, list) or total < 0:
        raise ValueError("invalid Zotero annotation response")
    return rows, total


def collection_annotation_inventory(
    collection_key: str, *, fetch_page: FetchPage = local_fetch_page,
    base_url: str = "http://127.0.0.1:23119/api/users/0",
) -> list[dict[str, Any]]:
    """List annotation IDs, parents, pages, revisions and text hashes only."""
    if not ZOTERO_KEY.fullmatch(collection_key):
        raise ValueError("invalid Zotero collection key")
    result: list[dict[str, Any]] = []
    start = 0
    total: int | None = None
    while total is None or start < total:
        query = urllib.parse.urlencode({"itemType": "annotation", "limit": PAGE_SIZE,
                                        "start": start})
        url = f"{base_url}/collections/{collection_key}/items?{query}"
        rows, reported_total = fetch_page(url)
        if total is not None and reported_total != total:
            raise ValueError("Zotero annotation collection changed during inventory")
        total = reported_total
        if not rows and start < total:
            raise ValueError("Zotero annotation inventory ended early")
        for item in rows:
            data = item.get("data", {})
            if data.get("itemType") != "annotation":
                raise ValueError("Zotero collection filter returned a non-annotation")
            text = data.get("annotationText") or ""
            comment = data.get("annotationComment") or ""
            result.append({
                "key": item["key"], "parent_item": data.get("parentItem"),
                "page_label": data.get("annotationPageLabel"),
                "modified_at": data.get("dateModified"),
                "has_comment": bool(comment),
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "comment_sha256": hashlib.sha256(comment.encode("utf-8")).hexdigest(),
            })
        start += len(rows)
    if len(result) != total or len({row["key"] for row in result}) != total:
        raise ValueError("Zotero annotation inventory is incomplete or duplicated")
    return result
