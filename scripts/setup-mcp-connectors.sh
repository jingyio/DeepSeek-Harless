#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${project_root}/.venv312/bin/python"
if [[ ! -x "${python_bin}" ]]; then
  echo "Run npm run structure:setup first" >&2
  exit 2
fi

"${python_bin}" -m pip install 'numpy==2.3.3' 'pandas==2.3.2' 'matplotlib==3.10.6'
"${python_bin}" -m venv "${project_root}/.local/zotero-mcp-venv"
"${project_root}/.local/zotero-mcp-venv/bin/python" -m pip install 'zotero-mcp-server==0.13.1'
echo "Python, Quarto and Zotero MCP dependencies ready."
