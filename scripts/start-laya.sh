#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -x "$ROOT_DIR/.local/laya-venv/bin/laya-serve" ]]; then
  echo "Laya environment missing. Install laya[serve]==0.3.20 in .local/laya-venv first." >&2
  exit 1
fi

export HF_HOME="$ROOT_DIR/.local/laya-cache"
export HF_HUB_OFFLINE="1"
export LAYA_HOST="127.0.0.1"
export LAYA_PORT="8766"
export LAYA_PRELOAD="0"
export LAYA_MODELS="multilingual"
exec "$ROOT_DIR/.local/laya-venv/bin/laya-serve"
