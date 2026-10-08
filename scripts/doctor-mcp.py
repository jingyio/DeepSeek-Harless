"""Check the six research MCP connectors without a model call or data writes.

Only tool names, counts, and pass/fail status leave the connector processes.
Run with --list-only to avoid all provider read calls.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp import Client, ClientSession, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
CALENDAR_TOOLS = "list-calendars,list-events,search-events,get-event,list-colors,get-freebusy,get-current-time"
EXPECTED = {
    "local_research_tools": 13,
    "literature_discovery": 11,
    "zotero": 21,
    "google_calendar": 13,
    "google_gmail": 13,
    "obsidian": 19,
}
if (LOCAL / "serpapi-api-key").is_file() and (LOCAL / "serpapi-monthly-search-budget").is_file():
    try:
        if int((LOCAL / "serpapi-monthly-search-budget").read_text().strip()) > 0:
            EXPECTED["literature_discovery"] += 1
    except ValueError:
        pass
PROBES: dict[str, tuple[str, dict[str, Any]]] = {
    "local_research_tools": ("python_environment", {}),
    "literature_discovery": ("get_arxiv_paper", {"arxiv_id": "1706.03762"}),
    "zotero": ("zotero_write_capabilities", {}),
    "google_calendar": ("list-calendars", {}),
    "google_gmail": ("list_email_labels", {}),
    "obsidian": ("vault_list", {}),
}


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _google_proxy_env() -> dict[str, str]:
    env = os.environ.copy()
    if not env.get("HTTPS_PROXY") and sys.platform == "darwin":
        try:
            state = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True,
                                   timeout=3, check=True).stdout
            host = re.search(r"^\s*HTTPSProxy\s*:\s*(\S+)", state, re.M)
            port = re.search(r"^\s*HTTPSPort\s*:\s*(\d+)", state, re.M)
            if host and port:
                with socket.create_connection((host.group(1), int(port.group(1))), timeout=1):
                    pass
                env["HTTPS_PROXY"] = f"http://{host.group(1)}:{port.group(1)}"
                env["HTTP_PROXY"] = env["HTTPS_PROXY"]
                env["NO_PROXY"] = "localhost,127.0.0.1,::1" + (
                    "," + env["NO_PROXY"] if env.get("NO_PROXY") else "")
        except (OSError, subprocess.SubprocessError):
            pass
    if env.get("HTTPS_PROXY") and "--use-env-proxy" not in env.get("NODE_OPTIONS", ""):
        try:
            node_help = subprocess.run(["node", "--help"], capture_output=True, text=True,
                                       timeout=3, check=True).stdout
            if "--use-env-proxy" in node_help:
                env["NODE_OPTIONS"] = (env.get("NODE_OPTIONS", "") + " --use-env-proxy").strip()
        except (OSError, subprocess.SubprocessError):
            pass
    env["SSS_NO_OPEN"] = "1"
    return env


def _stdio_parameters(name: str) -> StdioServerParameters:
    env = _google_proxy_env()
    if name == "local_research_tools":
        return StdioServerParameters(command=sys.executable,
                                     args=["-m", "src.mcp.local_research_tools_server"], cwd=ROOT, env=env)
    if name == "literature_discovery":
        if (LOCAL / "serpapi-api-key").is_file() and (LOCAL / "serpapi-monthly-search-budget").is_file():
            env["SERPAPI_API_KEY"] = (LOCAL / "serpapi-api-key").read_text().strip()
            env["SERPAPI_MONTHLY_SEARCH_BUDGET"] = (LOCAL / "serpapi-monthly-search-budget").read_text().strip()
        return StdioServerParameters(command=sys.executable,
                                     args=["-m", "src.mcp.literature_discovery_server"], cwd=ROOT, env=env)
    if name == "zotero":
        env.update(SSS_ZOTERO_UPSTREAM=str(LOCAL / "zotero-mcp-venv/bin/zotero-mcp"),
                   ZOTERO_LOCAL="true", ZOTERO_MCP_SCHEMA_REFRESH="0")
        return StdioServerParameters(command="node", args=["scripts/zotero-readonly-mcp.cjs"],
                                     cwd=ROOT, env=env)
    if name == "google_calendar":
        env.update(GOOGLE_OAUTH_CREDENTIALS=str(LOCAL / "google-calendar/oauth-client.json"),
                   GOOGLE_CALENDAR_MCP_TOKEN_PATH=str(LOCAL / "google-calendar/tokens.json"),
                   SSS_GOOGLE_CALENDAR_STATE=str(LOCAL / "google-calendar"),
                   ENABLED_TOOLS=CALENDAR_TOOLS)
        return StdioServerParameters(command="node", args=["scripts/calendar-guarded-mcp.cjs"],
                                     cwd=ROOT, env=env)
    if name == "google_gmail":
        client = LOCAL / "google-gmail/oauth-client.json"
        if not client.is_file():
            client = LOCAL / "google-calendar/oauth-client.json"
        env.update(GMAIL_OAUTH_PATH=str(client),
                   GMAIL_CREDENTIALS_PATH=str(LOCAL / "google-gmail/tokens.json"),
                   GMAIL_MCP_STATE_DIR=str(LOCAL / "google-gmail"), GMAIL_MCP_DRY_RUN="true")
        return StdioServerParameters(command="node", args=["scripts/gmail-guarded-mcp.cjs"],
                                     cwd=ROOT, env=env)
    raise ValueError(name)


def _ready(name: str) -> bool:
    if name == "zotero":
        return (LOCAL / "zotero-mcp-venv/bin/zotero-mcp").is_file() and _listening(23119)
    if name == "google_calendar":
        return all((LOCAL / "google-calendar" / item).is_file()
                   for item in ("oauth-client.json", "tokens.json"))
    if name == "google_gmail":
        return (LOCAL / "google-gmail/tokens.json").is_file() and (
            (LOCAL / "google-gmail/oauth-client.json").is_file()
            or (LOCAL / "google-calendar/oauth-client.json").is_file())
    if name == "obsidian":
        return (LOCAL / "obsidian-api-key").is_file() and (LOCAL / "obsidian-ca.crt").is_file() \
            and _listening(27124)
    return True


async def _check_stdio(name: str, live: bool) -> dict[str, Any]:
    async with Client(_stdio_parameters(name), read_timeout_seconds=25) as client:
        tools = (await client.list_tools()).tools
        names = {tool.name for tool in tools}
        result: dict[str, Any] = {"tools": len(tools), "expected_tools": EXPECTED[name],
                                  "probe": "skipped"}
        if live:
            tool, arguments = PROBES[name]
            if tool not in names:
                raise RuntimeError("probe tool absent")
            reply = await client.call_tool(tool, arguments)
            result["probe"] = "ok" if not reply.is_error else "failed"
        return result


async def _check_obsidian(live: bool) -> dict[str, Any]:
    import httpx2

    token = (LOCAL / "obsidian-api-key").read_text(encoding="utf-8").strip()
    async with httpx2.AsyncClient(verify=str(LOCAL / "obsidian-ca.crt"),
                                  headers={"Authorization": "Bearer " + token},
                                  timeout=15, trust_env=False) as http:
        async with streamable_http_client("https://127.0.0.1:27124/mcp/", http_client=http) as streams:
            async with ClientSession(*streams[:2]) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                names = {tool.name for tool in tools}
                result: dict[str, Any] = {"tools": len(tools), "expected_tools": EXPECTED["obsidian"],
                                          "probe": "skipped"}
                if live:
                    tool, arguments = PROBES["obsidian"]
                    if tool not in names:
                        raise RuntimeError("probe tool absent")
                    reply = await session.call_tool(tool, arguments)
                    result["probe"] = "ok" if not reply.is_error else "failed"
                return result


async def check(name: str, live: bool) -> dict[str, Any]:
    if not _ready(name):
        return {"status": "not_configured", "tools": 0, "expected_tools": EXPECTED[name],
                "probe": "skipped"}
    try:
        async with asyncio.timeout(40):
            result = await (_check_obsidian(live) if name == "obsidian"
                            else _check_stdio(name, live))
        result["status"] = "ok" if result["tools"] == EXPECTED[name] and result["probe"] != "failed" \
            else "degraded"
        return result
    except Exception as exc:
        return {"status": "failed", "tools": 0, "expected_tools": EXPECTED[name],
                "probe": "failed", "error_type": type(exc).__name__}


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-only", action="store_true", help="list MCP tools without provider reads")
    parser.add_argument("--json", action="store_true", help="print machine-readable status")
    args = parser.parse_args()
    report = {"dsh_listening": _listening(8765), "connectors": {}}
    for name in EXPECTED:
        report["connectors"][name] = await check(name, not args.list_only)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print("DeepSeek Harness:", "listening" if report["dsh_listening"] else "stopped")
        for name, item in report["connectors"].items():
            print(f"{name:22} {item['status']:14} {item['tools']:2}/{item['expected_tools']:2} tools"
                  f"  probe={item['probe']}")
    return 0 if report["dsh_listening"] and all(
        item["status"] == "ok" for item in report["connectors"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
