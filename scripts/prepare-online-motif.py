#!/usr/bin/env python3
"""Prepare an opt-in DSH plugin patch for a frozen online Motif experiment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "config/online-motif.patch.yml"


def prepare(manifest: Path, task: Path) -> dict:
    manifest = manifest.resolve(strict=True)
    task = task.resolve(strict=True)
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    structured = json.loads(task.read_text(encoding="utf-8"))
    if (declared.get("schema_version") != 1
            or not declared.get("manifest_digest")
            or structured.get("schema_version") != 1
            or not structured.get("session_id")):
        raise ValueError("manifest and task must be frozen versioned JSON")
    verifier = ("import fs from 'node:fs'; "
                "import {validateOnlineManifest, parseStructuredTask} "
                "from './src/motif_core/online_skill_runtime.mjs'; "
                "const manifest=JSON.parse(fs.readFileSync(process.argv[1])); "
                "const task=JSON.parse(fs.readFileSync(process.argv[2])); "
                "validateOnlineManifest(manifest); parseStructuredTask(task,manifest);")
    subprocess.run(["node", "--input-type=module", "-e", verifier,
                    str(manifest), str(task)], cwd=ROOT, check=True,
                   capture_output=True, text=True)
    plugin = (ROOT / "src/adapters/dsh_online_motif.mjs").resolve(strict=True)
    rendered = TEMPLATE.read_text(encoding="utf-8").replace(
        "__SSS_ONLINE_MOTIF_PLUGIN__", json.dumps(plugin.as_uri()))
    patch_hash = hashlib.sha256(rendered.encode()).hexdigest()[:16]
    output = ROOT / ".local/online-motif/patches" / f"{patch_hash}.patch.yml"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_text(encoding="utf-8") != rendered:
        raise ValueError("existing online Motif patch changed")
    output.write_text(rendered, encoding="utf-8")
    output.chmod(0o600)
    return {"patch": str(output), "manifest": str(manifest),
            "task": str(task), "session_id": structured["session_id"],
            "mode": "shadow by default; execute requires explicit environment setting",
            "paid_api_called": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.manifest, args.task), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
