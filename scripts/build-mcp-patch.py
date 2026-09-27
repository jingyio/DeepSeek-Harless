"""Compose the local DSH MCP patch from ready connectors.

No credential value is written to disk. The YAML references process env vars.
"""

from __future__ import annotations

import os
import socket
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
PATCH = LOCAL / "dsh" / "active-mcp.patch.yml"


def listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def build() -> list[str]:
    text = (ROOT / "config" / "sss-mcp.patch.yml").read_text(encoding="utf-8")
    enabled = ["local_research_tools", "literature_discovery"]
    zotero = LOCAL / "zotero-mcp-venv" / "bin" / "zotero-mcp"
    if zotero.is_file() and listening(23119):
        text += """    - id: sss-zotero-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: zotero
        transport: stdio
        command: !!js process.env.SSS_ZOTERO_MCP
        cwd: !!js process.env.SSS_PROJECT_ROOT
        env:
          ZOTERO_LOCAL: 'true'
          ZOTERO_MCP_SCHEMA_REFRESH: '0'
          SSS_ZOTERO_UPSTREAM: !!js process.env.SSS_ZOTERO_UPSTREAM
        failOnStartupError: true
"""
        enabled.append("zotero")

    calendar = ROOT / "scripts" / "calendar-guarded-mcp.cjs"
    credentials = LOCAL / "google-calendar" / "oauth-client.json"
    tokens = LOCAL / "google-calendar" / "tokens.json"
    if calendar.is_file() and credentials.is_file() and tokens.is_file():
        text += """    - id: sss-google-calendar-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: google_calendar
        transport: stdio
        command: !!js process.env.SSS_GOOGLE_CALENDAR_MCP
        cwd: !!js process.env.SSS_PROJECT_ROOT
        env:
          GOOGLE_OAUTH_CREDENTIALS: !!js process.env.SSS_GOOGLE_OAUTH_CREDENTIALS
          GOOGLE_CALENDAR_MCP_TOKEN_PATH: !!js process.env.SSS_GOOGLE_CALENDAR_TOKEN_PATH
          ENABLED_TOOLS: 'list-calendars,list-events,search-events,get-event,list-colors,get-freebusy,get-current-time'
        failOnStartupError: true
"""
        enabled.append("google_calendar")

    gmail = ROOT / "scripts" / "gmail-guarded-mcp.cjs"
    gmail_client = LOCAL / "google-gmail" / "oauth-client.json"
    if not gmail_client.is_file():
        gmail_client = LOCAL / "google-calendar" / "oauth-client.json"
    gmail_tokens = LOCAL / "google-gmail" / "tokens.json"
    if gmail.is_file() and gmail_client.is_file() and gmail_tokens.is_file():
        text += """    - id: sss-google-gmail-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: google_gmail
        transport: stdio
        command: !!js process.env.SSS_GOOGLE_GMAIL_MCP
        cwd: !!js process.env.SSS_PROJECT_ROOT
        env:
          GMAIL_OAUTH_PATH: !!js process.env.SSS_GOOGLE_GMAIL_OAUTH
          GMAIL_CREDENTIALS_PATH: !!js process.env.SSS_GOOGLE_GMAIL_TOKENS
          GMAIL_MCP_STATE_DIR: !!js process.env.SSS_GOOGLE_GMAIL_STATE
          GMAIL_MCP_DRY_RUN: 'true'
        failOnStartupError: true
"""
        enabled.append("google_gmail")

    obsidian_key = os.environ.get("SSS_OBSIDIAN_API_KEY", "")
    if obsidian_key and (LOCAL / "obsidian-ca.crt").is_file() and listening(27124):
        text += """    - id: sss-obsidian-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: obsidian
        transport: streamable-http
        url: https://127.0.0.1:27124/mcp/
        headers:
          Authorization: !!js '`Bearer ${process.env.SSS_OBSIDIAN_API_KEY}`'
        failOnStartupError: true
"""
        enabled.append("obsidian")

    PATCH.parent.mkdir(parents=True, exist_ok=True)
    PATCH.write_text(text, encoding="utf-8")
    PATCH.chmod(0o600)
    return enabled


if __name__ == "__main__":
    print("MCP servers: " + ", ".join(build()))
