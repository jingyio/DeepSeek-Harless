"""Model-proposed pure code becomes a Motif node only after task evidence."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.adapters.dsh_trajectory import DshTrace, ToolContract, ToolRecord
from src.motif_core.offline.dynamic_code_nodes import certify_dynamic_code_node
from src.motif_core.offline.library_builder import library_from_certified
from src.motif_core.offline.trace_compiler import (
    artifact_signature, certify_read_motif, compile_read_motif,
)
from src.motif_core.pure_code import evaluate, run_isolated
from src.motif_core.read_executor import _validate_artifact, run_read_motif


CONTRACTS = {
    "pin": ToolContract(("role",), True, ("raw_id",)),
    "read": ToolContract(("doc_id",), True, ("text",)),
}

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/compile-dsh-motif-library.py"
SPEC = importlib.util.spec_from_file_location("compile_dsh_with_code", SCRIPT)
COMPILER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPILER)
EXPORT_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export-online-motif-manifest.py"
EXPORT_SPEC = importlib.util.spec_from_file_location("export_code_skill", EXPORT_SCRIPT)
EXPORTER = importlib.util.module_from_spec(EXPORT_SPEC)
EXPORT_SPEC.loader.exec_module(EXPORTER)
PROPOSE_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/propose-motif-code.py"
PROPOSE_SPEC = importlib.util.spec_from_file_location("propose_code", PROPOSE_SCRIPT)
PROPOSER = importlib.util.module_from_spec(PROPOSE_SPEC)
PROPOSE_SPEC.loader.exec_module(PROPOSER)


def trace(label: str) -> DshTrace:
    raw = f" note-{label} "
    target = f"NOTE-{label.upper()}"
    return DshTrace(
        f"trace-{label}",
        (ToolRecord("pin", {"role": label}, "pin-hash", True, "eligible_read",
                    1, {"raw_id": raw}),
         ToolRecord("read", {"doc_id": target}, "read-hash", True,
                    "eligible_read", 2, {"text": target})),
        (("pin", "read"),), f"task-{label}")


def certified_base():
    training = [trace("alpha"), trace("beta")]
    heldout = trace("gamma")
    candidate = {"status": "candidate_only", "motif_id": "pin-read",
                 "tools": ["pin", "read"],
                 "source_trace_ids": [item.trace_id for item in training]}
    compiled = compile_read_motif(candidate, training, CONTRACTS)
    return certify_read_motif(compiled, heldout, CONTRACTS), training, heldout


def proposal(expression: str = "upper(strip(x))") -> dict[str, str]:
    return {"from_tool": "pin", "from_field": "raw_id",
            "to_tool": "read", "to_param": "doc_id", "expression": expression}


class DynamicCodeNodeTests(unittest.TestCase):
    def test_pure_expression_blocks_import_attribute_and_file_access(self) -> None:
        self.assertEqual(run_isolated("upper(strip(x))", " hello "), "HELLO")
        self.assertEqual(evaluate("regex_capture('([0-9]+)', x)", "page 42"), "42")
        for expression in ("__import__('os').system('id')", "x.__class__",
                           "open('/etc/passwd').read()", "[z for z in x]",
                           "x * 999999999"):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                evaluate(expression, "private")

    def test_code_node_is_certified_then_executes_inside_motif(self) -> None:
        base, training, heldout = certified_base()
        self.assertEqual(base["transfer_evidence"], [])
        skill = certify_dynamic_code_node(base, proposal(), training, heldout,
                                          CONTRACTS)
        self.assertEqual(skill["code_nodes"][0]["kind"], "pure_code")
        self.assertEqual(skill["code_dag"]["nodes"], [
            "pin", skill["code_nodes"][0]["node_id"], "read"])
        calls = []

        def execute(tool, params):
            calls.append((tool, dict(params)))
            return {"raw_id": " new-d "} if tool == "pin" else {"text": "checked"}

        result = run_read_motif(
            skill, contracts=CONTRACTS, bindings={"pin": {"role": "new"}},
            input_version="source-v1", execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, [("pin", {"role": "new"}),
                                 ("read", {"doc_id": "NEW-D"})])
        self.assertEqual([event["event"] for event in result.events
                          if event["event"] == "local_code_executed"],
                         ["local_code_executed"])

    def test_bad_heldout_code_or_tampered_skill_does_not_run(self) -> None:
        base, training, heldout = certified_base()
        with self.assertRaisesRegex(ValueError, "contradicts"):
            certify_dynamic_code_node(base, proposal("lower(strip(x))"),
                                      training, heldout, CONTRACTS)
        with self.assertRaisesRegex(ValueError, "independent task evidence"):
            certify_dynamic_code_node(base, proposal(), training, training[0],
                                      CONTRACTS)
        skill = certify_dynamic_code_node(base, proposal(), training, heldout,
                                          CONTRACTS)
        changed = copy.deepcopy(skill)
        changed["code_nodes"][0]["expression"] = "strip(x)"
        changed["dependencies"]["code_nodes"][0]["expression"] = "strip(x)"
        changed["certified_digest"] = artifact_signature(changed)
        with self.assertRaisesRegex(ValueError, "code node differs"):
            _validate_artifact(changed, CONTRACTS)

    def test_dynamic_candidate_is_promoted_by_library_compiler(self) -> None:
        base, training, heldout = certified_base()
        library = library_from_certified([base])
        candidate = {"trace_id": training[0].trace_id,
                     "tools": ["pin", "read"], **proposal()}
        upgraded = COMPILER.attach_code_candidates(
            library, [candidate], training, [heldout], CONTRACTS)
        self.assertEqual(len(upgraded["artifacts"][0]["code_nodes"]), 1)
        rows = {
            "pin": {"required_params": ["role"], "read_only": True,
                    "replay_stable": True, "output_fields": ["raw_id"],
                    "description": "Pin one approved source"},
            "read": {"required_params": ["doc_id"], "read_only": True,
                     "replay_stable": True, "output_fields": ["text"],
                     "description": "Read one approved source"},
        }
        manifest = EXPORTER.export_manifest(upgraded, rows)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            check = subprocess.run([
                "node", "--input-type=module", "-e",
                "import fs from 'node:fs'; "
                "import {validateOnlineManifest} from "
                "'./src/motif_core/online_skill_runtime.mjs'; "
                "validateOnlineManifest(JSON.parse(fs.readFileSync(process.argv[1])));",
                str(path)], cwd=Path(__file__).resolve().parents[1],
                capture_output=True, text=True)
            self.assertEqual(check.returncode, 0, check.stderr)
        rejected = COMPILER.attach_code_candidates(
            library_from_certified([base]),
            [{"trace_id": training[0].trace_id,
              "tools": ["pin", "read"], **proposal("lower(strip(x))")}],
            training, [heldout], CONTRACTS)
        self.assertNotIn("code_nodes", rejected["artifacts"][0])
        self.assertEqual(len(rejected["rejected"]), 1)

    def test_model_candidate_is_recorded_privately_without_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            proposed = PROPOSER.record_candidate({
                "trace_id": "trace-alpha", "tools": ["pin", "read"],
                **proposal()}, Path(temporary))
            path = Path(proposed["path"])
            self.assertTrue(path.is_file())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())["status"],
                             "candidate_only")
            self.assertFalse(proposed["model_request_skipped"])
            with patch.object(COMPILER, "ROOT", Path(temporary)):
                loaded = COMPILER._code_candidate_file(path)
                self.assertEqual(loaded["expression"], "upper(strip(x))")
                path.write_text(path.read_text().replace("strip", "lower"),
                                encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "hash changed"):
                    COMPILER._code_candidate_file(path)


if __name__ == "__main__":
    unittest.main()
