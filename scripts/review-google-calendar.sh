#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
node "${project_root}/scripts/calendar-review-web.cjs" "$@"
