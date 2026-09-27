#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -f "$ROOT_DIR/.local/models/qwen3-embedding-0.6b/model.safetensors" ]]; then
  echo "Pinned Qwen3 embedding weights are missing under .local/models." >&2
  exit 1
fi
if [[ ! -x "$ROOT_DIR/.local/laya-venv/bin/python" ]]; then
  echo "The local model Python environment is missing." >&2
  exit 1
fi
export HF_HUB_OFFLINE=1
exec "$ROOT_DIR/.local/laya-venv/bin/python" "$ROOT_DIR/scripts/local_embedding_server.py"
