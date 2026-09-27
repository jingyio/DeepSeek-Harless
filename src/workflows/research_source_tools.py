"""Real read-only research tools and privacy-minimal execution traces."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.adapters.dsh_trajectory import DshTrace, ToolContract, ToolRecord


SOURCE_TOOL_CONTRACTS = {
    "hash_source": ToolContract(("source",), True, ("sha256",)),
    "read_source": ToolContract(("source", "sha256"), True),
}
SUPPORTED_SOURCE_SUFFIXES = frozenset({".pdf", ".md", ".txt", ".json"})


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ResearchSourceToolClient:
    def __init__(self, root: Path, source: str, expected_sha256: str):
        self.root = root.resolve(strict=True)
        if (not self.root.is_dir() or not source or Path(source).name != source
                or Path(source).suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES
                or len(expected_sha256) != 64):
            raise ValueError("invalid versioned research source tool binding")
        self.source = source
        self.expected_sha256 = expected_sha256

    def verify_current(self) -> None:
        path = self.root / self.source
        if (path.is_symlink() or not path.is_file() or path.stat().st_size > 10_000_000
                or _sha(path.read_bytes()) != self.expected_sha256):
            raise ValueError("research source changed during Motif execution")

    def execute(self, tool: str, params: dict[str, Any]) -> dict[str, Any]:
        if tool not in SOURCE_TOOL_CONTRACTS or params.get("source") != self.source:
            raise ValueError("unverified research source tool")
        self.verify_current()
        path = self.root / self.source
        raw = path.read_bytes()
        if _sha(raw) != self.expected_sha256:
            raise ValueError("research source changed during Motif execution")
        if tool == "hash_source":
            if set(params) != {"source"}:
                raise ValueError("hash_source parameter schema changed")
            return {"sha256": self.expected_sha256}
        if set(params) != {"source", "sha256"} or params["sha256"] != self.expected_sha256:
            raise ValueError("read_source requires the current hash_source result")
        # Keep the same parser and output shape as the existing source Motif.
        from src.workflows.motif_research_sources import _parse
        parsed = _parse(path, raw, self.expected_sha256)
        self.verify_current()
        return {"pages": parsed}


def capture_source_read_trace(path: Path) -> DshTrace:
    """Observe actual tool calls; retain only a summary of the parsed document."""
    path = path.resolve(strict=True)
    digest = _sha(path.read_bytes())
    client = ResearchSourceToolClient(path.parent, path.name, digest)
    rows = []
    hash_params = {"source": path.name}
    hash_result = client.execute("hash_source", hash_params)
    read_params = {"source": path.name, "sha256": hash_result["sha256"]}
    read_result = client.execute("read_source", read_params)
    for index, (tool, params, result) in enumerate((
        ("hash_source", hash_params, hash_result),
        ("read_source", read_params, read_result),
    ), 1):
        observation = (result if tool == "hash_source" else
                       {"page_count": len(result["pages"]), "source_sha256": digest})
        result_hash = _sha(json.dumps(observation, sort_keys=True,
                                      ensure_ascii=False).encode("utf-8"))
        sources = ({"sha256": {"from_tool": "hash_source", "from_field": "sha256"}}
                   if tool == "read_source" else None)
        rows.append(ToolRecord(tool, params, result_hash, True,
                               "eligible_read", index, observation, sources))
    return DshTrace(
        trace_id="source-" + _sha(str(path).encode("utf-8"))[:16],
        records=tuple(rows), segments=(("hash_source", "read_source"),),
        task_fingerprint=digest,
    )
