#!/usr/bin/env python3
"""Record one model-proposed Motif code candidate without executing it.

Read JSON from stdin so task content and code do not appear in process args.
The candidate stays under ignored .local until independent traces certify it.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.motif_core.pure_code import validate_expression  # noqa: E402


FIELDS = {"trace_id", "tools", "from_tool", "from_field",
          "to_tool", "to_param", "expression"}


def record_candidate(candidate: dict, root: Path = ROOT) -> dict:
    if (not isinstance(candidate, dict) or set(candidate) != FIELDS
            or not isinstance(candidate["trace_id"], str)
            or not 1 <= len(candidate["trace_id"]) <= 120
            or not isinstance(candidate["tools"], list)
            or len(candidate["tools"]) != 2
            or candidate["tools"] != [candidate["from_tool"],
                                      candidate["to_tool"]]
            or any(not isinstance(candidate[key], str) or not candidate[key]
                   or len(candidate[key]) > 200 for key in FIELDS - {
                       "tools", "trace_id", "expression"})):
        raise ValueError("candidate needs one trace and a two-tool code gap")
    validate_expression(candidate["expression"])
    payload = {"status": "candidate_only", **candidate}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"))
    candidate_id = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    output = root / ".local" / "motifs" / "code-candidates" / f"{candidate_id}.json"
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (not output.parent.resolve().is_relative_to((root / ".local").resolve())
            or output.is_symlink()):
        raise ValueError("code candidate path escapes private workspace")
    if output.exists():
        if output.read_text(encoding="utf-8") != raw + "\n":
            raise ValueError("existing code candidate changed")
    else:
        try:
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise ValueError("code candidate was created concurrently") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(raw + "\n")
    return {"candidate_id": candidate_id, "path": str(output),
            "status": "candidate_only", "model_request_skipped": False}


def main() -> None:
    candidate = json.load(sys.stdin)
    print(json.dumps(record_candidate(candidate), ensure_ascii=False))


if __name__ == "__main__":
    main()
