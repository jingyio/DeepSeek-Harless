#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
log_file="${project_root}/.local/harness.log"

if [[ ! -f "${log_file}" ]]; then
  echo "尚未启动本地服务。请先运行 npm run dev。" >&2
  exit 1
fi

url="$(rg -o 'http://127\.0\.0\.1:8765/\?token=[^[:space:]]+' "${log_file}" | tail -n 1 || true)"
if [[ -z "${url}" ]]; then
  echo "未找到访问地址，请检查 ${log_file}。" >&2
  exit 1
fi

printf '%s\n' "${url}"
