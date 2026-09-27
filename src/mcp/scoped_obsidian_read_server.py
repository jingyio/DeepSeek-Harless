"""Read only researcher-approved Obsidian notes for one private trial.

The trial manifest lives under .local and names exact file versions. This
adapter exposes no vault search or write capability to the trial Agent.
"""

from __future__ import annotations

import hashlib
import json
import os
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
    if allowed is not None:
        if (not isinstance(allowed, list) or not allowed
                or any(not isinstance(span, list) or len(span) != 2
                       or any(type(number) is not int for number in span)
                       or not 1 <= span[0] <= span[1] for span in allowed)):
            raise ValueError("Invalid approved note line ranges")
        last_line = start_line + min(max_lines, 100) - 1
        if not any(first <= start_line <= last_line <= last
                   for first, last in allowed):
            raise ValueError("Requested note lines exceed approved excerpt")
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
                return {"role": role, "vault_path": relative, "sha256": row["sha256"],
                        **_numbered_lines(content, start_line, max_lines)}


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
    if not 1 <= start_page <= 1000 or not 1 <= max_pages <= 2:
        raise ValueError("Read at most two PDF pages from page 1–1000")
    from io import BytesIO

    row, raw = _approved_local(role, {".pdf"})
    reader = PdfReader(BytesIO(raw))
    if reader.is_encrypted or len(reader.pages) > 1000 or start_page > len(reader.pages):
        raise ValueError("PDF is encrypted, too long or page is unavailable")
    allowed = row.get("allowed_page_ranges")
    if allowed is not None:
        if (not isinstance(allowed, list) or not allowed
                or any(not isinstance(span, list) or len(span) != 2
                       or any(type(number) is not int for number in span)
                       or not 1 <= span[0] <= span[1] <= len(reader.pages)
                       for span in allowed)):
            raise ValueError("Invalid approved PDF page ranges")
        last_page = min(start_page + max_pages - 1, len(reader.pages))
        if not any(first <= start_page <= last_page <= last
                   for first, last in allowed):
            raise ValueError("Requested PDF pages exceed approved excerpt")
    pages = []
    for page in range(start_page, min(start_page + max_pages, len(reader.pages) + 1)):
        content = (reader.pages[page - 1].extract_text() or "").strip()
        pages.append({"pdf_page": page, "text": content[:6000],
                      "total_chars": len(content), "truncated": len(content) > 6000,
                      "low_text": len(content) < 80})
    return {"role": role, "sha256": row["sha256"],
            "pdf_page_count": len(reader.pages), "pages": pages}


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


def create_server(*, handle_mode: bool) -> MCPServer:
    """Keep the earlier role-read pilot stable while enabling provenance trials."""
    instance = MCPServer(
        "sss-scoped-research-read",
        instructions="Only approved, version-locked Obsidian notes and local research files are visible. "
        "Read bounded lines or PDF pages. A changed source or missing external-model "
        "approval blocks reading. No vault search or write operation is available.",
    )
    for function in (list_scoped_notes, list_scoped_local_sources):
        instance.add_tool(function, annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    if handle_mode:
        functions = (pin_scoped_source, read_pinned_note, read_pinned_text,
                     read_pinned_pdf_pages)
    else:
        functions = (read_scoped_note, read_scoped_text, read_scoped_pdf_pages)
    for function in functions:
        instance.add_tool(function, annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, openWorldHint=False))
    return instance


server = create_server(handle_mode=os.environ.get("SSS_SCOPED_HANDLE_MODE") == "1")


if __name__ == "__main__":
    server.run(transport="stdio")
