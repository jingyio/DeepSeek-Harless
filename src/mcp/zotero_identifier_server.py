"""Read-only, exact identifier lookup in the local personal Zotero library.

Only a DOI or arXiv ID may be queried. Broad search hits are filtered locally;
unrelated item metadata never leaves this tool. Group libraries are not searched.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from src.mcp.scoped_zotero_read_server import _data_digest, _identifier, _item_identifiers

BASE = "http://127.0.0.1:23119/api/users/0/items"
MAX_RESULTS = 500
server = MCPServer(
    "sss-zotero-identifier",
    instructions="Look up an explicit DOI or arXiv ID in the indexed personal Zotero library. "
    "Only exact matches are returned; an empty result does not rule out a group-library item. "
    "No broad search, annotations, full text or writes are available.",
)


def _search_page(query: str, start: int) -> tuple[list[dict[str, Any]], int]:
    params = urllib.parse.urlencode({"q": query, "qmode": "everything",
                                     "itemType": "-attachment", "start": start,
                                     "limit": 100})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(BASE + "?" + params, timeout=15) as response:
        items = json.load(response)
        total_header = response.headers.get("Total-Results")
    if total_header is None:
        raise ValueError("Zotero search omitted total count")
    total = int(total_header)
    if not isinstance(items, list) or total < 0 or total > MAX_RESULTS:
        raise ValueError("Zotero identifier search is incomplete")
    return items, total


def lookup_zotero_identifier(identifier: str) -> dict[str, Any]:
    """Return versioned metadata only for one exact DOI/arXiv match.

    `not_found` means no exact match in Zotero's indexed personal library,
    not a guarantee about group libraries or unindexed data.
    """
    kind, token = _identifier(identifier)
    matches: dict[str, dict[str, Any]] = {}
    start = 0
    while True:
        items, total = _search_page(token, start)
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
                continue
            data = item["data"]
            if data.get("itemType") in {"attachment", "annotation", "note"}:
                continue
            identifiers = _item_identifiers(data)
            doi = data.get("DOI")
            if kind == "arxiv" and isinstance(doi, str):
                try:
                    _, normalized_doi = _identifier(doi)
                    if normalized_doi == "10.48550/arxiv." + token:
                        identifiers.add(("arxiv", token))
                except ValueError:
                    pass
            if (kind, token) not in identifiers:
                continue
            key = item.get("key")
            version = item.get("version")
            if not isinstance(key, str) or type(version) is not int:
                raise ValueError("Zotero exact match lacks stable item identity")
            matches[key] = {
                "item_key": key, "version": version,
                "data_sha256": _data_digest(item),
                "title": str(data.get("title") or "")[:500],
                "doi": doi if isinstance(doi, str) else None,
                "url": str(data.get("url") or "")[:500],
            }
        start += len(items)
        if start >= total:
            break
        if not items:
            raise ValueError("Zotero returned an incomplete search page")
    common = {"identifier_type": kind, "identifier": token,
              "search_scope": "indexed_personal_library"}
    if not matches:
        return {**common, "status": "not_found", "match_count": 0}
    if len(matches) > 1:
        return {**common, "status": "multiple_exact_matches",
                "match_count": len(matches)}
    return {**common, "status": "unique_match", "match_count": 1,
            **next(iter(matches.values()))}


server.add_tool(lookup_zotero_identifier, annotations=ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, openWorldHint=False))


if __name__ == "__main__":
    server.run(transport="stdio")
