#!/usr/bin/env python3
"""Serve pinned Qwen3 embeddings locally for SSS's bounded Motif decisions.

Use .local/laya-venv/bin/python; weights stay under .local/models. The process
binds only to loopback and never downloads at runtime.
"""

from __future__ import annotations

import json
import os
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import torch
import torch.nn.functional as functional
from transformers import AutoModel, AutoTokenizer


ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / ".local/models/qwen3-embedding-0.6b"
MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
MODEL_SHA256 = "0437e45c94563b09e13cb7a64478fc406947a93cb34a7e05870fc8dcd48e23fd"
MAX_TOKENS = 2048  # The Motif decision scope is much smaller than model capacity.


class LocalEmbedder:
    def __init__(self):
        if not (MODEL_DIR / "model.safetensors").is_file():
            raise FileNotFoundError("download the pinned embedding weights first")
        with (MODEL_DIR / "model.safetensors").open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != MODEL_SHA256:
                raise ValueError("embedding weights do not match the pinned SHA-256")
        device_name = os.environ.get("SSS_EMBED_DEVICE") or (
            "mps" if torch.backends.mps.is_available() else "cpu")
        if device_name not in {"mps", "cpu"}:
            raise ValueError("SSS_EMBED_DEVICE must be mps or cpu")
        self.device = torch.device(device_name)
        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_DIR, local_files_only=True, padding_side="left")
        self.model = AutoModel.from_pretrained(
            MODEL_DIR, local_files_only=True,
            dtype=torch.float16 if device_name == "mps" else torch.float32,
        ).to(self.device).eval()

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Reject overlength input instead of silently dropping task evidence.
        encoded = self.tokenizer(texts, padding=True, truncation=False,
                                 return_tensors="pt")
        if encoded["input_ids"].shape[1] > MAX_TOKENS:
            raise ValueError("candidate input exceeds the local token budget")
        encoded = {key: value.to(self.device) for key, value in encoded.items()}
        with torch.inference_mode():
            outputs = self.model(**encoded)
            # Left padding makes the final position the last real token.
            vectors = outputs.last_hidden_state[:, -1, :].float()
            vectors = functional.normalize(vectors, p=2, dim=1)
        return vectors.cpu().tolist()


class Handler(BaseHTTPRequestHandler):
    embedder: LocalEmbedder

    def do_POST(self):
        if self.path != "/v1/embeddings":
            self._reply(404, {"error": "unknown endpoint"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 32000:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(length))
            texts = payload.get("input") if isinstance(payload, dict) else None
            if (not isinstance(payload, dict) or payload.get("model") != MODEL_ID
                    or not isinstance(texts, list) or not 2 <= len(texts) <= 13
                    or any(not isinstance(item, str) or not item.strip()
                           or len(item) > 2000 for item in texts)):
                raise ValueError("invalid bounded embedding request")
            vectors = self.embedder.embed(texts)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self._reply(400, {"error": str(error)})
            return
        self._reply(200, {"model": MODEL_ID,
                          "data": [{"index": index, "embedding": vector}
                                   for index, vector in enumerate(vectors)]})

    def _reply(self, code: int, body: dict):
        data = json.dumps(body, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format_string, *args):
        # Do not log request bodies or texts. The default line omits bodies too.
        return


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    Handler.embedder = LocalEmbedder()
    server = HTTPServer(("127.0.0.1", 8776), Handler)
    print(f"SSS local embeddings ready at http://127.0.0.1:8776/v1/embeddings",
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
