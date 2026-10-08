"""Read only researcher-approved Obsidian notes for one private trial.

The trial manifest lives under .local and names exact file versions. This
adapter exposes no vault search or write capability to the trial Agent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pypdf import PdfReader

from src.mcp.structured_research_tools import HandleStore


ROOT = Path(__file__).resolve().parents[2]
LOCAL = (ROOT / ".local").resolve()
_HANDLE_STORE = HandleStore(LOCAL / "scoped-research-handles" / "handles.sqlite3")


def _scope_file() -> Path:
    raw = os.environ.get("SSS_RESEARCH_SCOPE_FILE", "")
    if not raw:
        raise RuntimeError("A private trial scope file is required")
    path = Path(raw).resolve(strict=True)
    if not path.is_relative_to(LOCAL) or not path.is_file():
        raise ValueError("Trial scope must be a file under SSS/.local")
    return path


def _scope() -> dict[str, Any]:
    path = _scope_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise ValueError("Invalid trial scope")
    return data


def _approved_note(role: str) -> tuple[dict[str, Any], str]:
    scope = _scope()
    vault_root = Path(scope.get("obsidian_vault_root", "")).resolve(strict=True)
    matches = [row for row in scope["sources"] if isinstance(row, dict)
               and row.get("role") == role and row.get("vault_path")]
    if len(matches) != 1 or matches[0].get("external_model_excerpt_allowed") is not True:
        raise ValueError("This note is not approved for model access")
    row = matches[0]
    path = Path(row["path"]).resolve(strict=True)
    if not path.is_file() or not path.is_relative_to(vault_root):
        raise ValueError("Note path is outside the selected vault")
    relative = path.relative_to(vault_root).as_posix()
    if row["vault_path"] != relative:
        raise ValueError("Vault path does not match the selected note")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row.get("sha256"):
        raise ValueError("Approved note version changed; renew the trial scope")
    return row, relative


def _approved_local(role: str, suffixes: set[str]) -> tuple[dict[str, Any], bytes]:
    scope = _scope()
    matches = [row for row in scope["sources"] if isinstance(row, dict)
               and row.get("role") == role and not row.get("vault_path")]
    if len(matches) != 1 or matches[0].get("external_model_excerpt_allowed") is not True:
        raise ValueError("This local source is not approved for model access")
    row = matches[0]
    path = Path(row["path"]).resolve(strict=True)
    if not path.is_file() or path.suffix.lower() not in suffixes or path.stat().st_size > 10_000_000:
        raise ValueError("Unsupported or oversized scoped source")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row.get("sha256"):
        raise ValueError("Approved source version changed; renew the trial scope")
    return row, raw


def _numbered_lines(content: str, start_line: int, max_lines: int) -> dict[str, Any]:
    if not 1 <= start_line <= 10_000 or not 1 <= max_lines <= 1000:
        raise ValueError("Read from line 1–10000 and request 1–1000 lines")
    lines = content.splitlines()
    if start_line > len(lines):
        raise ValueError("Start line exceeds source length")
    returned_limit = min(max_lines, 100)
    selected = lines[start_line - 1:start_line - 1 + returned_limit]
    numbered = "\n".join(f"{start_line + i}: {line}" for i, line in enumerate(selected))
    if len(numbered) > 10_000:
        numbered = numbered[:10_000]
    next_line = start_line + len(selected)
    return {"start_line": start_line, "requested_max_lines": max_lines,
            "returned_max_lines": returned_limit, "total_lines": len(lines), "next_line":
            next_line if next_line <= len(lines) else None, "numbered_text": numbered}


def _approved_note_read_limit(allowed: Any, start_line: int,
                              max_lines: int) -> tuple[int, int | None]:
    if not 1 <= start_line <= 10_000 or not 1 <= max_lines <= 1000:
        raise ValueError("Read from line 1–10000 and request 1–1000 lines")
    if allowed is None:
        return max_lines, None
    if (not isinstance(allowed, list) or not allowed
            or any(not isinstance(span, list) or len(span) != 2
                   or any(type(number) is not int for number in span)
                   or not 1 <= span[0] <= span[1] for span in allowed)):
        raise ValueError("Invalid approved note line ranges")
    approved_end = next((last for first, last in allowed
                         if first <= start_line <= last), None)
    if approved_end is None:
        raise ValueError("Note start line is outside approved excerpt")
    return min(max_lines, 100, approved_end - start_line + 1), approved_end


def list_scoped_notes() -> dict[str, Any]:
    """List note roles in this trial without reading or exposing note contents."""
    scope = _scope()
    notes = [{"role": row["role"], "vault_path": row["vault_path"],
              "sha256": row["sha256"],
              "allowed_line_ranges": row.get("allowed_line_ranges")}
             for row in scope["sources"] if isinstance(row, dict)
             and row.get("vault_path") and row.get("external_model_excerpt_allowed") is True]
    return {"notes": notes, "count": len(notes)}


async def read_scoped_note(role: str, start_line: int = 1,
                           max_lines: int = 80) -> dict[str, Any]:
    """Read bounded lines through Obsidian MCP from an approved exact note version."""
    row, relative = _approved_note(role)
    allowed = row.get("allowed_line_ranges")
    bounded_lines, approved_end = _approved_note_read_limit(
        allowed, start_line, max_lines)
    key_file = LOCAL / "obsidian-api-key"
    cert_file = LOCAL / "obsidian-ca.crt"
    token = key_file.read_text(encoding="utf-8").strip()
    if not token or not cert_file.is_file():
        raise RuntimeError("Obsidian MCP credentials are unavailable")
    async with httpx2.AsyncClient(
        verify=str(cert_file), headers={"Authorization": "Bearer " + token},
        timeout=15, trust_env=False,
    ) as http:
        async with streamable_http_client(
            "https://127.0.0.1:27124/mcp/", http_client=http,
        ) as streams:
            async with ClientSession(*streams[:2]) as session:
                await session.initialize()
                reply = await session.call_tool("vault_read", {"path": relative})
                if reply.is_error or len(reply.content) != 1 or reply.content[0].type != "text":
                    raise RuntimeError("Obsidian could not read the approved note")
                payload = json.loads(reply.content[0].text)
                content = payload.get("content") if isinstance(payload, dict) else None
                if not isinstance(content, str) or payload.get("path") != relative:
                    raise RuntimeError("Obsidian returned an unexpected note")
                if hashlib.sha256(content.encode("utf-8")).hexdigest() != row["sha256"]:
                    raise ValueError("Obsidian note differs from approved file version")
                result = _numbered_lines(content, start_line, bounded_lines)
                if approved_end is not None and result["next_line"] is not None:
                    if result["next_line"] > approved_end:
                        result["next_line"] = None
                return {"role": role, "vault_path": relative, "sha256": row["sha256"],
                        **result, "requested_max_lines": max_lines,
                        "clipped_to_approved_excerpt": bounded_lines < min(max_lines, 100)}


def list_scoped_local_sources() -> dict[str, Any]:
    """List approved local text/PDF source roles without exposing their contents."""
    scope = _scope()
    sources = [{"role": row["role"], "format": Path(row["path"]).suffix.lower().lstrip("."),
                "sha256": row["sha256"]}
               for row in scope["sources"] if isinstance(row, dict)
               and not row.get("vault_path") and row.get("external_model_excerpt_allowed") is True]
    return {"sources": sources, "count": len(sources)}


def read_scoped_text(role: str, start_line: int = 1, max_lines: int = 80) -> dict[str, Any]:
    """Read bounded, numbered lines from an approved local Markdown or text file."""
    row, raw = _approved_local(role, {".md", ".txt"})
    content = raw.decode("utf-8")
    return {"role": role, "sha256": row["sha256"],
            **_numbered_lines(content, start_line, max_lines)}


def read_scoped_pdf_pages(role: str, start_page: int = 1,
                          max_pages: int = 2) -> dict[str, Any]:
    """Read up to two page-labelled text excerpts from an approved local PDF."""
    if not 1 <= start_page <= 1000 or not 1 <= max_pages <= 1000:
        raise ValueError("Read from page 1–1000 and request 1–1000 pages")
    from io import BytesIO

    row, raw = _approved_local(role, {".pdf"})
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or len(reader.pages) > 1000 or start_page > len(reader.pages):
        raise ValueError("PDF is encrypted, too long or page is unavailable")
    allowed = row.get("allowed_page_ranges")
    approved_end = len(reader.pages)
    if allowed is not None:
        if (not isinstance(allowed, list) or not allowed
                or any(not isinstance(span, list) or len(span) != 2
                       or any(type(number) is not int for number in span)
                       or not 1 <= span[0] <= span[1] <= len(reader.pages)
                       for span in allowed)):
            raise ValueError("Invalid approved PDF page ranges")
        selected_end = next((last for first, last in allowed
                             if first <= start_page <= last), None)
        if selected_end is None:
            raise ValueError("PDF start page is outside approved excerpt")
        approved_end = selected_end
    returned_pages = min(max_pages, 2, approved_end - start_page + 1)
    pages = []
    for page in range(start_page, start_page + returned_pages):
        content = (reader.pages[page - 1].extract_text() or "").strip()
        pages.append({"pdf_page": page, "text": content[:6000],
                      "total_chars": len(content), "truncated": len(content) > 6000,
                      "low_text": len(content) < 80})
    return {"role": role, "sha256": row["sha256"],
            "pdf_page_count": len(reader.pages), "pages": pages,
            "requested_max_pages": max_pages, "returned_pages": len(pages),
            "clipped_to_tool_limit": max_pages > 2,
            "clipped_to_approved_excerpt": start_page + min(max_pages, 2) - 1 > approved_end,
            "next_page": start_page + len(pages) if start_page + len(pages) <= approved_end
                         else None}


def pin_scoped_source(role: str) -> dict[str, Any]:
    """Pin one approved source and return an opaque source_id for bounded reads."""
    scope = _scope()
    matches = [row for row in scope["sources"] if isinstance(row, dict)
               and row.get("role") == role]
    if len(matches) != 1:
        raise ValueError("Expected exactly one approved source with this role")
    row = matches[0]
    if row.get("vault_path"):
        verified, _ = _approved_note(role)
        kind = "note"
    else:
        verified, _ = _approved_local(role, {".md", ".txt", ".pdf"})
        kind = "pdf" if Path(verified["path"]).suffix.lower() == ".pdf" else "text"
    scope_path = _scope_file()
    source_id = _HANDLE_STORE.put("source", {
        "origin": "scoped_research_read", "scope_path": str(scope_path),
        "scope_sha256": hashlib.sha256(scope_path.read_bytes()).hexdigest(),
        "role": role, "sha256": verified["sha256"], "kind": kind,
    })
    return {"source_id": source_id, "role": role,
            "sha256": verified["sha256"], "kind": kind}


def pin_scoped_note(role: str) -> dict[str, Any]:
    """Pin an approved Obsidian note; reject local text and PDF source roles."""
    _approved_note(role)
    return pin_scoped_source(role)


def _resolve_pinned(source_id: str, expected_kind: str) -> str:
    entry = _HANDLE_STORE.get(source_id, "source")
    scope_path = _scope_file()
    if (entry.get("origin") != "scoped_research_read"
            or entry.get("scope_path") != str(scope_path)
            or entry.get("scope_sha256") != hashlib.sha256(scope_path.read_bytes()).hexdigest()
            or entry.get("kind") != expected_kind):
        raise ValueError("Source handle scope or type changed; pin the source again")
    role = entry.get("role")
    if not isinstance(role, str):
        raise ValueError("Invalid source handle role")
    if expected_kind == "note":
        row, _ = _approved_note(role)
    else:
        row, _ = _approved_local(role, {".pdf"} if expected_kind == "pdf"
                                  else {".md", ".txt"})
    if row["sha256"] != entry.get("sha256"):
        raise ValueError("Source handle version changed; pin the source again")
    return role


async def read_pinned_note(source_id: str, start_line: int = 1,
                           max_lines: int = 80) -> dict[str, Any]:
    """Read an Obsidian note by a previously returned, version-bound source_id."""
    role = _resolve_pinned(source_id, "note")
    return {"source_id": source_id,
            **await read_scoped_note(role, start_line, max_lines)}


async def read_pinned_approved_note_excerpt(source_id: str) -> dict[str, Any]:
    """Read only the note lines explicitly approved by this task's scope."""
    role = _resolve_pinned(source_id, "note")
    row, _ = _approved_note(role)
    spans = row.get("allowed_line_ranges")
    if (not isinstance(spans, list) or not 1 <= len(spans) <= 4
            or any(not isinstance(span, list) or len(span) != 2
                   or any(type(line) is not int for line in span)
                   or not 1 <= span[0] <= span[1]
                   or span[1] - span[0] + 1 > 100 for span in spans)
            or sum(last - first + 1 for first, last in spans) > 120):
        raise ValueError("Approved note excerpt is missing or exceeds 120 lines")
    ordered = sorted(spans)
    if any(left[1] >= right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("Approved note line ranges overlap")
    segments = []
    for first, last in ordered:
        excerpt = await read_scoped_note(role, start_line=first,
                                         max_lines=last - first + 1)
        if excerpt.get("sha256") != row["sha256"]:
            raise ValueError("Approved note version changed while reading")
        segments.append({"start_line": first, "end_line": last,
                         "numbered_text": excerpt["numbered_text"]})
    return {"source_id": source_id, "role": role, "sha256": row["sha256"],
            "segments": segments}


def read_pinned_text(source_id: str, start_line: int = 1,
                     max_lines: int = 80) -> dict[str, Any]:
    """Read bounded lines from a pinned local text source."""
    role = _resolve_pinned(source_id, "text")
    return {"source_id": source_id,
            **read_scoped_text(role, start_line, max_lines)}


def read_pinned_pdf_pages(source_id: str, start_page: int = 1,
                          max_pages: int = 2) -> dict[str, Any]:
    """Read bounded pages from a pinned local PDF source."""
    role = _resolve_pinned(source_id, "pdf")
    return {"source_id": source_id,
            **read_scoped_pdf_pages(role, start_page, max_pages)}


def _normalized_pdf_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip().casefold()


def _approved_pdf_page_numbers(row: dict[str, Any], page_count: int) -> list[int]:
    ranges = row.get("allowed_page_ranges")
    if ranges is None:
        pages = list(range(1, page_count + 1))
    else:
        if (not isinstance(ranges, list) or not ranges
                or any(not isinstance(span, list) or len(span) != 2
                       or any(type(number) is not int for number in span)
                       or not 1 <= span[0] <= span[1] <= page_count
                       for span in ranges)):
            raise ValueError("Invalid approved PDF page ranges")
        pages = sorted({page for first, last in ranges for page in range(first, last + 1)})
    if len(pages) > 100:
        raise ValueError("PDF locator needs an approved range of at most 100 pages")
    return pages


def locate_pinned_pdf_quote(source_id: str, quote: str) -> dict[str, Any]:
    """Find an exact quote in approved PDF pages; only a unique page yields a read handle.

    This locates text, not scientific relevance. Whitespace and Unicode width are
    normalized because PDF extraction may insert line breaks inside a sentence.
    """
    role = _resolve_pinned(source_id, "pdf")
    if (not isinstance(quote, str) or not 12 <= len(quote) <= 500
            or any(ord(char) < 32 and char not in "\t\r\n" for char in quote)):
        raise ValueError("Quote must be 12–500 visible characters")
    needle = _normalized_pdf_text(quote)
    if len(needle) < 12:
        raise ValueError("Normalized quote is too short")
    from io import BytesIO

    row, raw = _approved_local(role, {".pdf"})
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 1000:
        raise ValueError("PDF is encrypted or has an invalid page count")
    allowed = _approved_pdf_page_numbers(row, len(reader.pages))
    matches = []
    for page_number in allowed:
        extracted = reader.pages[page_number - 1].extract_text() or ""
        normalized = _normalized_pdf_text(extracted)
        offset = normalized.find(needle)
        if offset >= 0:
            matches.append({"pdf_page": page_number,
                            "snippet": normalized[max(0, offset - 60):
                                                  min(len(normalized), offset + len(needle) + 60)][:240],
                            "page_text_sha256": hashlib.sha256(extracted.encode()).hexdigest()})
    result: dict[str, Any] = {
        "source_id": source_id, "role": role, "sha256": row["sha256"],
        "quote_sha256": hashlib.sha256(needle.encode()).hexdigest(),
        "scanned_pages": len(allowed), "match_count": len(matches),
        "matches": matches[:10], "matches_truncated": len(matches) > 10,
        "status": "unique" if len(matches) == 1 else
                  "not_found" if not matches else "ambiguous",
    }
    if len(matches) == 1:
        scope_path = _scope_file()
        result["match_id"] = _HANDLE_STORE.put("match", {
            "scope_path": str(scope_path),
            "scope_sha256": hashlib.sha256(scope_path.read_bytes()).hexdigest(),
            "source_id": source_id, "role": role, "pdf_page": matches[0]["pdf_page"],
            "page_text_sha256": matches[0]["page_text_sha256"],
            "normalized_quote": needle,
        })
    return result


def read_pinned_pdf_match(match_id: str) -> dict[str, Any]:
    """Read the unique approved PDF page named by a locator's versioned handle."""
    match = _HANDLE_STORE.get(match_id, "match")
    scope_path = _scope_file()
    if (match.get("scope_path") != str(scope_path)
            or match.get("scope_sha256") != hashlib.sha256(scope_path.read_bytes()).hexdigest()):
        raise ValueError("PDF match scope changed; locate the quote again")
    source_id = match.get("source_id")
    role = _resolve_pinned(source_id, "pdf")
    if role != match.get("role"):
        raise ValueError("PDF match source changed")
    from io import BytesIO

    row, raw = _approved_local(role, {".pdf"})
    reader = PdfReader(BytesIO(raw))
    page = match.get("pdf_page")
    if (reader.is_encrypted or type(page) is not int
            or page not in _approved_pdf_page_numbers(row, len(reader.pages))):
        raise ValueError("PDF match page is outside the approved range")
    extracted = reader.pages[page - 1].extract_text() or ""
    if (hashlib.sha256(extracted.encode()).hexdigest() != match.get("page_text_sha256")
            or match.get("normalized_quote") not in _normalized_pdf_text(extracted)):
        raise ValueError("PDF match no longer resolves to the same text")
    return {"match_id": match_id,
            **read_pinned_pdf_pages(source_id, start_page=page, max_pages=1)}


def create_server(*, handle_mode: bool, notes_only: bool = False) -> MCPServer:
    """Keep the earlier role-read pilot stable while enabling provenance trials."""
    instance = MCPServer(
        "sss-scoped-research-read",
        instructions="Only approved, version-locked Obsidian notes and local research files are visible. "
        "Read bounded lines or PDF pages. A changed source or missing external-model "
        "approval blocks reading. No vault search or write operation is available.",
    )
    listing = (list_scoped_notes,) if notes_only else (list_scoped_notes, list_scoped_local_sources)
    for function in listing:
        instance.add_tool(function, annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    if notes_only:
        functions = (pin_scoped_note, read_pinned_approved_note_excerpt)
    elif handle_mode:
        functions = (pin_scoped_source, read_pinned_note,
                     read_pinned_approved_note_excerpt, read_pinned_text,
                     read_pinned_pdf_pages, locate_pinned_pdf_quote,
                     read_pinned_pdf_match)
    else:
        functions = (read_scoped_note, read_scoped_text, read_scoped_pdf_pages)
    for function in functions:
        instance.add_tool(function, annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    return instance


server = create_server(handle_mode=os.environ.get("SSS_SCOPED_HANDLE_MODE") == "1",
                       notes_only=os.environ.get("SSS_SCOPED_NOTES_ONLY") == "1")


if __name__ == "__main__":
    server.run(transport="stdio")
