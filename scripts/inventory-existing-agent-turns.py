#!/usr/bin/env python3
"""Audit natural DSH turn boundaries from a private manifest of baseline traces.

The script never writes raw tool arguments, source text, or model messages to
the public repository. A structural candidate is only an upper bound; human
review of semantic choices and delivery quality remains necessary.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / ".local").resolve()
sys.path.insert(0, str(ROOT))

from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402


def load_script(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def private_path(value: str, *, must_exist: bool = True) -> Path:
    path = (ROOT / value).resolve(strict=must_exist)
    if not path.is_relative_to(LOCAL):
        raise ValueError("manifest, raw events, and outputs must remain under .local")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    manifest_path = private_path(args.manifest)
    output_path = private_path(args.out, must_exist=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    traces = manifest.get("event_paths")
    if not isinstance(traces, list) or not traces or not all(
            isinstance(path, str) for path in traces):
        parser.error("manifest.event_paths must be a nonempty list of paths")
    if len(traces) != len(set(traces)):
        parser.error("duplicate event path")

    specs: dict = {}
    for path in sorted((ROOT / "config").glob("*contracts.json")):
        incoming = json.loads(path.read_text(encoding="utf-8"))
        if specs.keys() & incoming.keys():
            parser.error(f"duplicate tool contracts in {path}")
        specs.update(incoming)
    contracts = parse_tool_contracts(specs)
    opportunity = load_script("turn_opportunity_audit",
                              ROOT / "scripts/audit-motif-turn-opportunities.py")
    step_cost = load_script("turn_step_cost", ROOT / "scripts/summarize-dsh-step-cost.py")

    rows = []
    for relative in traces:
        source = private_path(relative)
        raw = source.read_bytes()
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        audit = opportunity.audit(events, contracts, trace_id=relative)
        audit["events_sha256"] = hashlib.sha256(raw).hexdigest()
        rows.append({"audit": audit,
                     "step_cost": step_cost.summarize_events(events, run=relative)})

    result = {
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "traces": rows,
        "totals": {
            "traces": len(rows),
            "model_messages": sum(row["audit"]["model_messages"] for row in rows),
            "tool_calls": sum(row["audit"]["tool_calls"] for row in rows),
            "isolated_safe_target_steps_upper_bound": sum(
                len(row["audit"]["isolated_safe_target_steps"]) for row in rows),
        },
        "interpretation": "Mechanical upper bounds only; not verified skips, net savings, or qualified decisions.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    output_path.chmod(0o600)
    print(json.dumps(result["totals"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
