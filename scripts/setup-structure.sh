#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${SSS_PYTHON:-}"
if [[ -z "${python_bin}" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    python_bin="$(command -v python3.12)"
  elif [[ -x "/Users/apple/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3" ]]; then
    python_bin="/Users/apple/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
  else
    echo "Python 3.10+ is required; set SSS_PYTHON to its executable" >&2
    exit 2
  fi
fi
"${python_bin}" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
"${python_bin}" -m venv "${project_root}/.venv312"
"${project_root}/.venv312/bin/python" -m pip install --no-deps --pre 'deepseek-harness-sdk==0.1.5rc1'
"${project_root}/.venv312/bin/python" -m pip install 'pydantic==2.13.5' 'pypdf==6.13.3' 'pytest==8.4.2'
"${project_root}/.venv312/bin/python" -m pip install 'mcp==2.2.0'
echo "Structure runtime ready: ${project_root}/.venv312/bin/python"
