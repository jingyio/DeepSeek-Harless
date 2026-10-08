"""Exercise one bounded, real read-only chain per research MCP connector.

Private source identifiers and provider responses stay under .local. The public
summary contains only tool names, success/failure, and structural checks. This
is a connector/task-chain probe, not a Motif quality or cost experiment.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from mcp import Client


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
OUT = LOCAL / "benchmarks" / "mcp-internal-readonly-20260928"
PAPER_SCOPE = LOCAL / "benchmarks/research-weekly-loop/paper-impact-p1-20260927/source-scope.json"
MAIL_SCOPE = LOCAL / "benchmarks/research-weekly-loop/gmail-request-pilot-20260928/scope.json"
AIDD_SCOPE = LOCAL / "benchmarks/research-weekly-loop/aidd-sar-baseline-decision-20260928/source-scope.json"


def doctor_module():
    spec = importlib.util.spec_from_file_location("sss_doctor_mcp", ROOT / "scripts/doctor-mcp.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DOCTOR = doctor_module()


def private_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def ok(reply: object) -> bool:
    if bool(getattr(reply, "is_error", getattr(reply, "isError", False))):
        return False
    data = getattr(reply, "structured_content", None)
    if isinstance(data, dict) and data.get("status") in {"unavailable", "error", "failed"}:
        return False
    return True


def serialized(reply: object) -> str:
    value = getattr(reply, "structured_content", None)
    if value is None:
        value = getattr(reply, "content", None)
    return json.dumps(value, ensure_ascii=False, default=str)


def nested_json_result(reply: object) -> object:
    data = getattr(reply, "structured_content", None)
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        try:
            return json.loads(data["result"])
        except ValueError:
            pass
    content = getattr(reply, "content", None)
    if content:
        raw = getattr(content[0], "text", None)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except ValueError:
                pass
    return data


async def literature() -> dict:
    # Public paper, independent of private user material. Known-ID read is a
    # fallback check if discovery itself is unavailable, not a claimed chain.
    record: dict = {"connector": "literature_discovery", "steps": []}
    async with Client(DOCTOR._stdio_parameters("literature_discovery"),
                      read_timeout_seconds=25) as client:
        search = await client.call_tool("search_arxiv", {
            "query": "Attention Is All You Need", "field": "title", "limit": 3})
        payload = getattr(search, "structured_content", None)
        record["steps"].append({"tool": "search_arxiv",
                                "status": "ok" if ok(search) else "provider_unavailable",
                                "result_count": len(payload.get("papers") or [])
                                if isinstance(payload, dict) else None})
        paper_id = None
        if ok(search) and isinstance(payload, dict):
            papers = payload.get("papers") or []
            for paper in papers:
                if isinstance(paper, dict):
                    candidate = paper.get("arxiv_id") or paper.get("id")
                    if isinstance(candidate, str) and re.fullmatch(r"\d{4}\.\d{4,5}", candidate):
                        paper_id = candidate
                        break
        fallback = paper_id is None
        paper = await client.call_tool("get_arxiv_paper", {
            "arxiv_id": paper_id or "1706.03762"})
        record["steps"].append({"tool": "get_arxiv_paper",
                                "status": "ok" if ok(paper) else "provider_unavailable",
                                "input_from_search": not fallback})
        crossref = await client.call_tool("search_crossref_works", {
            "query": "Investigating the volume and diversity of data needed for generalizable antibody antigen prediction",
            "field": "title", "limit": 3})
        crossref_result = getattr(crossref, "structured_content", None)
        candidates = crossref_result.get("works") if isinstance(crossref_result, dict) else None
        doi = next((entry.get("doi") for entry in candidates
                    if isinstance(entry, dict) and isinstance(entry.get("doi"), str)), None) \
            if isinstance(candidates, list) else None
        record["steps"].append({"tool": "search_crossref_works",
                                "status": "ok" if ok(crossref) and doi else "provider_unavailable",
                                "result_count": len(candidates) if isinstance(candidates, list) else None})
        if doi:
            verified = await client.call_tool("verify_doi_metadata", {"doi": doi})
            metadata = getattr(verified, "structured_content", None)
            record["steps"].append({"tool": "verify_doi_metadata",
                                    "status": "ok" if ok(verified) and isinstance(metadata, dict)
                                    and metadata.get("doi", "").lower() == doi.lower()
                                    else "identity_mismatch",
                                    "input_from_search": True})
    return record


async def zotero() -> dict:
    scope = json.loads(PAPER_SCOPE.read_text(encoding="utf-8"))
    parent = next(source for source in scope["zotero_sources"] if source["kind"] == "item")
    record: dict = {"connector": "zotero", "steps": []}
    async with Client(DOCTOR._stdio_parameters("zotero"), read_timeout_seconds=25) as client:
        metadata = await client.call_tool("zotero_get_item_metadata", {
            "item_key": parent["key"], "format": "json"})
        item = nested_json_result(metadata)
        item_ok = ok(metadata) and isinstance(item, dict) and item.get("key") == parent["key"]
        record["steps"].append({"tool": "zotero_get_item_metadata",
                                "status": "ok" if item_ok else "identity_mismatch"})
        if not item_ok:
            return record
        annotations = await client.call_tool("zotero_get_annotations", {
            "item_key": item["key"], "limit": 10, "format": "json"})
        entries = nested_json_result(annotations)
        record["steps"].append({"tool": "zotero_get_annotations",
                                "status": "ok" if ok(annotations) and isinstance(entries, list)
                                else "invalid_result", "annotation_count": len(entries)
                                if isinstance(entries, list) else None,
                                "input_from_metadata": True})
    return record


async def obsidian() -> dict:
    scope = json.loads(PAPER_SCOPE.read_text(encoding="utf-8"))
    source = next(source for source in scope["sources"] if source.get("vault_path"))
    allowed = source.get("allowed_line_ranges")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("approved note line range required")
    os.environ["SSS_RESEARCH_SCOPE_FILE"] = str(PAPER_SCOPE)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location(
        "sss_scoped_obsidian_probe", ROOT / "src/mcp/scoped_obsidian_read_server.py")
    assert spec and spec.loader
    scoped = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scoped)
    record: dict = {"connector": "obsidian", "steps": []}
    listed = scoped.list_scoped_notes()
    record["steps"].append({"tool": "list_scoped_notes", "status": "ok"
                            if listed.get("count", 0) > 0 else "empty_scope"})
    first, last = allowed[0]
    result = await scoped.read_scoped_note(source["role"], first, last - first + 1)
    record["steps"].append({"tool": "read_scoped_note", "status": "ok",
                            "approved_line_count": result["returned_max_lines"],
                            "version_checked": True,
                            "via_real_obsidian_mcp": True})
    return record


async def gmail() -> dict:
    scope = json.loads(MAIL_SCOPE.read_text(encoding="utf-8"))
    record: dict = {"connector": "google_gmail", "steps": []}
    async with Client(DOCTOR._stdio_parameters("google_gmail"), read_timeout_seconds=25) as client:
        for tool, args in [("search_emails", {"query": scope["query"], "maxResults": 3})]:
            try:
                reply = await client.call_tool(tool, args)
                status = "ok" if ok(reply) else "tool_error"
                step = {"tool": tool, "status": status}
                if tool == "search_emails" and status == "ok":
                    data = getattr(reply, "structured_content", None)
                    selected = data.get("selected_message_id") if isinstance(data, dict) else None
                    ids = data.get("message_ids") if isinstance(data, dict) else None
                    step["unique_scoped_message"] = (
                        isinstance(ids, list) and len(ids) == 1 and
                        selected == ids[0] == scope["message_id"])
                record["steps"].append(step)
                if status != "ok" or not step.get("unique_scoped_message"):
                    break
                reply = await client.call_tool("read_email", {
                    "messageId": selected, "format": "headers_only"})
                record["steps"].append({"tool": "read_email",
                                        "status": "ok" if ok(reply) else "tool_error",
                                        "input_from_search": True})
            except Exception as exc:
                record["steps"].append({"tool": tool, "status": "exception",
                                        "error_type": type(exc).__name__})
                break
    return record


async def calendar() -> dict:
    # This checks the real API path but is not a real research scheduling task.
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    start = now.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end = start + timedelta(hours=8)
    record: dict = {"connector": "google_calendar", "steps": []}
    async with Client(DOCTOR._stdio_parameters("google_calendar"), read_timeout_seconds=25) as client:
        calendars = await client.call_tool("list-calendars", {})
        listing = nested_json_result(calendars)
        listed = ok(calendars) and isinstance(listing, dict) and isinstance(
            listing.get("calendars"), list)
        record["steps"].append({"tool": "list-calendars",
                                "status": "ok" if listed else "invalid_result"})
        if not listed:
            return record
        freebusy = await client.call_tool("get-freebusy", {
            "calendars": [{"id": "primary"}], "timeMin": start.isoformat(),
            "timeMax": end.isoformat(), "timeZone": "Asia/Shanghai"})
        data = nested_json_result(freebusy)
        checked = ok(freebusy) and isinstance(data, dict) and isinstance(
            data.get("calendars"), dict) and "primary" in data["calendars"]
        record["steps"].append({"tool": "get-freebusy",
                                "status": "ok" if checked else "invalid_result",
                                "calendar_scope": "primary",
                                "research_scheduling_task": False})
    return record


async def local_research() -> dict:
    # Public AIDD CSV was already approved as a research input in the prior trial.
    scope = json.loads(AIDD_SCOPE.read_text(encoding="utf-8"))
    source = next(item for item in scope["public_data_sources"]
                  if Path(item["path"]).suffix.lower() == ".csv")
    source_path = Path(source["path"])
    record: dict = {"connector": "local_research_tools", "steps": []}
    async with Client(DOCTOR._stdio_parameters("local_research_tools"),
                      read_timeout_seconds=25) as client:
        steps = [
            ("list_research_sources", {"directory": str(source_path.parent)}),
            ("pin_source", {"path": str(source_path)}),
        ]
        for tool, args in steps:
            reply = await client.call_tool(tool, args)
            status = "ok" if ok(reply) else "tool_error"
            record["steps"].append({"tool": tool, "status": status})
            if status != "ok":
                return record
            if tool == "pin_source":
                matched = re.search(r"source-[0-9a-f]{32}", serialized(reply))
                if not matched:
                    record["steps"].append({"tool": "inspect_records",
                                            "status": "missing_source_id"})
                    return record
                pinned_id = matched.group()
        for tool, args in [
            ("inspect_records", {"source_id": pinned_id}),
            ("preview_quarto", {"path": "connector-chain/report.qmd"}),
        ]:
            reply = await client.call_tool(tool, args)
            status = "ok" if ok(reply) else "tool_error"
            record["steps"].append({"tool": tool, "status": status})
            if status != "ok":
                break
    return record


async def main() -> None:
    results = []
    for function in (literature, zotero, obsidian, local_research, gmail, calendar):
        try:
            results.append(await function())
        except Exception as exc:
            results.append({"connector": function.__name__, "steps": [],
                            "status": "exception", "error_type": type(exc).__name__,
                            "error_module": getattr(exc, "name", None)})
    report = {"checked_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
              "paid_model_requests": 0, "writes_to_user_apps": 0, "results": results}
    private_json(OUT / "result.json", report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
