#!/usr/bin/env python3
"""Download pinned Qwen3 weights into ignored local data and verify SHA-256."""

import argparse
import hashlib
import subprocess
from pathlib import Path

from huggingface_hub import snapshot_download


ROOT = Path(__file__).resolve().parents[1]
target = ROOT / ".local/models/qwen3-embedding-0.6b"
revision = "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
expected_sha256 = "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"
parser = argparse.ArgumentParser()
parser.add_argument("--mirror", action="store_true",
                    help="use the mirror for the large weight file; still verify official SHA-256")
args = parser.parse_args()


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


weights = target / "model.safetensors"
verified = weights.is_file() and digest(weights) == expected_sha256
patterns = ["*.json", "*.txt", "README.md"]
if not verified and not args.mirror:
    patterns.append("*.safetensors")
snapshot_download(repo_id="Qwen/Qwen3-Embedding-0.6B", revision=revision,
                  local_dir=target, allow_patterns=patterns)
if not verified and args.mirror:
    partial = target / "model.safetensors.part"
    subprocess.run([
        "curl", "--silent", "--show-error", "--location", "--fail",
        "--retry", "5", "--retry-delay", "3", "--continue-at", "-",
        "--output", str(partial),
        f"https://hf-mirror.com/Qwen/Qwen3-Embedding-0.6B/resolve/{revision}/model.safetensors",
    ], check=True)
    if digest(partial) != expected_sha256:
        raise RuntimeError("mirror weights do not match the official SHA-256")
    partial.replace(weights)
if not weights.is_file() or digest(weights) != expected_sha256:
    raise RuntimeError("embedding weights are missing or do not match the official SHA-256")
print(target)
