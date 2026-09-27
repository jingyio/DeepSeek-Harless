#!/usr/bin/env bash
set -euo pipefail
umask 077

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
gmail_dir="${project_root}/.local/google-gmail"
credentials="${gmail_dir}/oauth-client.json"
mode="${1:-read}"
case "${mode}" in
  read) tokens="${gmail_dir}/tokens.json"; scopes="gmail.readonly" ;;
  send) tokens="${gmail_dir}/send-tokens.json"; scopes="gmail.send" ;;
  *) echo "Usage: $0 [read|send]" >&2; exit 2 ;;
esac
if [[ ! -f "${credentials}" ]]; then
  credentials="${project_root}/.local/google-calendar/oauth-client.json"
fi
if [[ ! -f "${credentials}" ]]; then
  echo "Place a Google OAuth Desktop app client JSON at ${gmail_dir}/oauth-client.json" >&2
  echo "The existing Calendar OAuth client at .local/google-calendar/oauth-client.json may also be reused." >&2
  echo "Enable Gmail API and add your account as a test user in Google Cloud first." >&2
  exit 2
fi
mkdir -p "${gmail_dir}"
chmod 700 "${gmail_dir}"
chmod 600 "${credentials}"
export GMAIL_OAUTH_PATH="${credentials}"
export GMAIL_CREDENTIALS_PATH="${tokens}"
export GMAIL_MCP_STATE_DIR="${gmail_dir}"

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

"${project_root}/node_modules/.bin/gmail-mcp" auth "--scopes=${scopes}"
if [[ -f "${tokens}" ]]; then chmod 600 "${tokens}"; fi
