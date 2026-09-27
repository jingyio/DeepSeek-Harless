"""Compile verified scalar transfers into bounded Motif-local programs."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compile_local_programs(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    programs = {}
    for target in artifact["tools"][1:]:
        steps = [{"op": "copy_verified_field",
                  "from_tool": edge["from_tool"],
                  "from_field": edge["from_field"],
                  "to_param": edge["to_param"]}
                 for edge in artifact["transfer_evidence"]
                 if edge["to_tool"] == target]
        if steps:
            body = {"language": "sss-local-ops-v1", "target_tool": target,
                    "steps": steps}
            programs[target] = {**body, "program_digest": _digest(body)}
    return programs
