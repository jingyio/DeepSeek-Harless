#!/usr/bin/env bash
set -euo pipefail
umask 077

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export DSH_HOME="${project_root}/.local/dsh"
export SSS_MCP_PYTHON="${project_root}/.venv312/bin/python"
export SSS_PROJECT_ROOT="${project_root}"
export SSS_ZOTERO_MCP="${project_root}/scripts/zotero-readonly-mcp.cjs"
export SSS_ZOTERO_UPSTREAM="${project_root}/.local/zotero-mcp-venv/bin/zotero-mcp"
export SSS_GOOGLE_CALENDAR_MCP="${project_root}/scripts/calendar-guarded-mcp.cjs"
export SSS_GOOGLE_CALENDAR_STATE="${project_root}/.local/google-calendar"
export SSS_GOOGLE_OAUTH_CREDENTIALS="${project_root}/.local/google-calendar/oauth-client.json"
export SSS_GOOGLE_CALENDAR_TOKEN_PATH="${project_root}/.local/google-calendar/tokens.json"
export SSS_GOOGLE_GMAIL_MCP="${project_root}/scripts/gmail-guarded-mcp.cjs"
export SSS_GOOGLE_GMAIL_OAUTH="${project_root}/.local/google-gmail/oauth-client.json"
if [[ ! -f "${SSS_GOOGLE_GMAIL_OAUTH}" ]]; then
  export SSS_GOOGLE_GMAIL_OAUTH="${project_root}/.local/google-calendar/oauth-client.json"
fi
export SSS_GOOGLE_GMAIL_TOKENS="${project_root}/.local/google-gmail/tokens.json"
export SSS_GOOGLE_GMAIL_STATE="${project_root}/.local/google-gmail"
mkdir -p "${DSH_HOME}"
chmod 700 "${project_root}/.local" "${DSH_HOME}"

if [[ -f "${project_root}/.local/obsidian-api-key" ]]; then
  export SSS_OBSIDIAN_API_KEY="$(<"${project_root}/.local/obsidian-api-key")"
fi
if [[ -f "${project_root}/.local/obsidian-ca.crt" ]]; then
  export NODE_EXTRA_CA_CERTS="${project_root}/.local/obsidian-ca.crt"
fi
if [[ -f "${project_root}/.local/serpapi-api-key" && -f "${project_root}/.local/serpapi-monthly-search-budget" ]]; then
  export SERPAPI_API_KEY="$(<"${project_root}/.local/serpapi-api-key")"
  export SERPAPI_MONTHLY_SEARCH_BUDGET="$(<"${project_root}/.local/serpapi-monthly-search-budget")"
fi

# Node does not inherit macOS's system proxy settings. Reuse the configured
# local proxy so Calendar OAuth refresh and API calls work from MCP subprocesses.
if [[ -z "${HTTPS_PROXY:-}" ]] && command -v scutil >/dev/null 2>&1; then
  proxy_host="$(scutil --proxy | awk '/^[[:space:]]*HTTPSProxy[[:space:]]*:/ { print $3; exit }')"
  proxy_port="$(scutil --proxy | awk '/^[[:space:]]*HTTPSPort[[:space:]]*:/ { print $3; exit }')"
  if [[ -n "${proxy_host}" && -n "${proxy_port}" ]] &&
     nc -z -w 1 "${proxy_host}" "${proxy_port}" >/dev/null 2>&1; then
    export HTTPS_PROXY="http://${proxy_host}:${proxy_port}"
    export HTTP_PROXY="${HTTPS_PROXY}"
    export NO_PROXY="localhost,127.0.0.1,::1${NO_PROXY:+,${NO_PROXY}}"
  fi
fi
if [[ -n "${HTTPS_PROXY:-}" && " ${NODE_OPTIONS:-} " != *" --use-env-proxy "* ]] &&
   node --help | grep -q -- '--use-env-proxy'; then
  export NODE_OPTIONS="${NODE_OPTIONS:-} --use-env-proxy"
fi

if ! "${SSS_MCP_PYTHON}" -c 'import mcp' >/dev/null 2>&1; then
  echo "SSS workflow tools are not installed; run npm run structure:setup first" >&2
  exit 2
fi

"${SSS_MCP_PYTHON}" "${project_root}/scripts/build-mcp-patch.py"

"${project_root}/node_modules/.bin/dsh" \
  --profile web \
  --patch "${project_root}/.local/dsh/active-mcp.patch.yml" \
  --host 127.0.0.1 --port 8765 --no-open 2>&1 | tee "${project_root}/.local/harness.log"
