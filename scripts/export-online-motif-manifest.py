#!/usr/bin/env python3
"""Export a validated read-only Motif library for the DSH online adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.tool_contract_loader import parse_tool_contracts
from src.motif_core.offline.library_builder import validate_read_motif_library
from src.motif_core.read_executor import _validate_artifact


def digest(value: dict) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def export_manifest(library: dict, contract_rows: dict,
                    slot_rules: dict | None = None,
                    version_fields: dict | None = None) -> dict:
    """Only a certified library may produce a model-bypass manifest."""
    validate_read_motif_library(library)
    contracts = parse_tool_contracts(contract_rows)
    artifacts = []
    used_tools = set()
    for artifact in library["artifacts"]:
        _validate_artifact(artifact, contracts)
        if artifact["status"] != "trace_validated_read_only":
            raise ValueError("online Motif must be certified read-only")
        tools = [tool.rstrip("+") for tool in artifact["tools"]]
        if len(tools) != len(set(tools)):
            # Repeated tools need an invocation-indexed online state model.
            continue
        if len(tools) < 2:
            continue
        for tool in tools:
            contract = contracts[tool]
            if not contract.read_only or not contract.replay_stable:
                raise ValueError("online Motif tool is not replay-stable read-only")
            if not contract.description or len(contract.description) > 160:
                raise ValueError("online Motif tool needs bounded documentation")
        used_tools.update(tools)
        artifacts.append({
            "motif_id": artifact["motif_id"],
            "certified_digest": artifact["certified_digest"],
            "tools": tools,
            "transfer_evidence": artifact["transfer_evidence"],
            "supporting_task_count": len(artifact["source_task_fingerprints"]),
            "validation_task_fingerprint": artifact["validation_task_fingerprint"],
        })
    if not artifacts:
        raise ValueError("library has no online-eligible read Motif")
    rules = slot_rules or {}
    if (not isinstance(rules, dict) or set(rules) - used_tools
            or any(not isinstance(params, dict)
                   or set(params) - set(contracts[tool].required_params)
                   or any(not isinstance(pattern, str) or not pattern
                          for pattern in params.values())
                   for tool, params in rules.items())):
        raise ValueError("slot rules must name certified required parameters")
    versions = version_fields or {}
    if (not isinstance(versions, dict) or set(versions) - used_tools
            or any(not isinstance(field, str)
                   or field not in contracts[tool].output_fields
                   for tool, field in versions.items())):
        raise ValueError("version fields must name approved tool outputs")
    manifest = {
        "schema_version": 1,
        "source_library_digest": library["library_digest"],
        "artifacts": artifacts,
        "contracts": {
            tool: {
                "required_params": list(contracts[tool].required_params),
                "output_fields": list(contracts[tool].output_fields),
                "default_params": dict(contracts[tool].default_params),
                "description": contracts[tool].description,
                "read_only": True,
            } for tool in sorted(used_tools)
        },
        "slot_rules": rules,
        "version_fields": versions,
    }
    manifest["manifest_digest"] = digest(manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", required=True, type=Path)
    parser.add_argument("--contracts", required=True, type=Path)
    parser.add_argument("--slot-rules", type=Path)
    parser.add_argument("--version-fields", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    library = json.loads(args.library.read_text(encoding="utf-8"))
    contracts = json.loads(args.contracts.read_text(encoding="utf-8"))
    rules = (json.loads(args.slot_rules.read_text(encoding="utf-8"))
             if args.slot_rules else {})
    versions = (json.loads(args.version_fields.read_text(encoding="utf-8"))
                if args.version_fields else {})
    manifest = export_manifest(library, contracts, rules, versions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    args.output.chmod(0o600)
    print(json.dumps({"output": str(args.output),
                      "eligible_motifs": len(manifest["artifacts"]),
                      "manifest_digest": manifest["manifest_digest"]}))


if __name__ == "__main__":
    main()
