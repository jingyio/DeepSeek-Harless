#!/usr/bin/env bash
set -euo pipefail
umask 077

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
key_file="${project_root}/.local/obsidian-api-key"
cert_file="${project_root}/.local/obsidian-ca.crt"
if ! curl -ksSf --max-time 5 'https://127.0.0.1:27124/' -o /dev/null; then
  echo "Obsidian Local REST API is not responding on its default HTTPS port 27124." >&2
  echo "Install and enable the plugin in your active vault first." >&2
  exit 2
fi

read -r -s -p 'Paste the Local REST API key from Obsidian plugin settings: ' api_key
echo
if [[ -z "${api_key}" ]]; then
  echo "No API key supplied" >&2
  exit 2
fi

curl -ksSf --max-time 10 'https://127.0.0.1:27124/obsidian-local-rest-api.crt' -o "${cert_file}"
openssl x509 -in "${cert_file}" -noout >/dev/null
status="$(printf 'header = "Authorization: Bearer %s"\n' "${api_key}" | \
  curl -sS --config - --cacert "${cert_file}" -o /dev/null -w '%{http_code}' \
  'https://127.0.0.1:27124/vault/' || true)"
if [[ "${status}" != "200" ]]; then
  rm -f "${cert_file}"
  echo "Obsidian API key validation failed (HTTP ${status}); nothing was saved." >&2
  exit 2
fi

printf '%s' "${api_key}" > "${key_file}"
chmod 600 "${key_file}" "${cert_file}"
echo "Obsidian MCP connection ready. Restart npm run dev to load it."
