#!/usr/bin/env bash
set -euo pipefail
umask 077

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
credentials="${project_root}/.local/google-calendar/oauth-client.json"
tokens="${project_root}/.local/google-calendar/tokens.json"
if [[ ! -f "${credentials}" ]]; then
  echo "Place a Google OAuth Desktop app client JSON at ${credentials}" >&2
  echo "Enable Google Calendar API and add your account as a test user in Google Cloud first." >&2
  exit 2
fi
chmod 600 "${credentials}"
export GOOGLE_OAUTH_CREDENTIALS="${credentials}"
export GOOGLE_CALENDAR_MCP_TOKEN_PATH="${tokens}"
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
"${project_root}/node_modules/.bin/google-calendar-mcp" auth
if [[ -f "${tokens}" ]]; then chmod 600 "${tokens}"; fi
