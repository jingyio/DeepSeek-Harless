#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m venv "${project_root}/.venv"
"${project_root}/.venv/bin/python" -m pip install --disable-pip-version-check -r "${project_root}/requirements-office.txt"
mkdir -p "${project_root}/office/papers/inbox" "${project_root}/office/papers/archive" "${project_root}/office/papers/notes" "${project_root}/.local/papers/drafts"
