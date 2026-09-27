"""The online runner starts only a matching, budget-gated SSS projection."""

import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_motif_controller import library


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run-online-motif-task.py"
SPEC = importlib.util.spec_from_file_location("online_runner", SCRIPT)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)
EXPORT_SPEC = importlib.util.spec_from_file_location(
    "online_export", ROOT / "scripts/export-online-motif-manifest.py")
EXPORT = importlib.util.module_from_spec(EXPORT_SPEC)
EXPORT_SPEC.loader.exec_module(EXPORT)


class ProjectionStackTests(unittest.TestCase):
    def fixture(self, directory: Path) -> tuple[Path, Path, Path, Path]:
        source = library()
        artifact = directory / "artifact.json"
        artifact.write_text(json.dumps(source["artifacts"][0]), encoding="utf-8")
        manifest = EXPORT.export_manifest(
            source, {
                "search": {"required_params": ["query"], "output_fields": ["id"],
                           "read_only": True, "replay_stable": True,
                           "description": "Find a scoped source"},
                "read": {"required_params": ["doc_id"], "output_fields": ["text"],
                         "read_only": True, "replay_stable": True,
                         "description": "Read a scoped source"},
            },
            {"search": {"query": "[A-Za-z]+"}},
            {"search": "id", "read": "text"})
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        task = directory / "task.json"
        task.write_text(json.dumps({
            "schema_version": 1, "task_id": "projection-integration",
            "session_id": "projection-integration-session",
            "intent": "Read the scoped source", "input_version": "v1",
            "bindings": {"search": {"query": "alpha"}},
            "source_versions": {"search": "A", "read": "A"},
        }), encoding="utf-8")
        prompt = directory / "prompt.txt"
        prompt.write_text("Read the scoped source.", encoding="utf-8")
        return artifact, manifest_path, task, prompt

    @staticmethod
    def arguments(artifact: Path, manifest: Path, task: Path, prompt: Path) -> list[str]:
        return ["--manifest", str(manifest), "--task", str(task),
                "--base-patch", str(ROOT / "config/structured-research-phase.patch.yml"),
                "--prompt", str(prompt),
                "--embedding-endpoint", "http://127.0.0.1:8776/v1/embeddings",
                "--embedding-model", "qwen3-embedding-0.6b",
                "--projection-artifact", str(artifact), "--budget-usd", "0.01"]

    def test_preview_and_single_entry_stack(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            args = self.arguments(*self.fixture(Path(temp)))
            preview = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT,
                                     text=True, capture_output=True, timeout=20)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            summary = json.loads(preview.stdout)
            self.assertEqual(summary["projection_mode"], "SSS latest tool batch")
            self.assertEqual(summary["provider_budget_cap_usd"], 0.01)
            self.assertFalse(summary["paid_api_called"])
            with patch.object(sys, "argv", [str(SCRIPT), *args, "--call-model"]), \
                    patch.object(RUNNER.subprocess, "call", return_value=0) as start:
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(RUNNER.main(), 0)
            command = start.call_args.args[0]
            self.assertIn("--motif-output-projection", command)
            self.assertEqual(command[command.index("--mode") + 1], "plain")
            self.assertEqual(command[command.index("--budget-usd") + 1], "0.01")
            self.assertEqual(command[command.index("--motif-output-projection") + 1],
                             str(Path(args[args.index("--projection-artifact") + 1]).resolve()))
            self.assertEqual(start.call_args.kwargs["env"]["SSS_ONLINE_PROJECTION_CHILD"], "1")

    def test_rejects_artifact_outside_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            artifact, manifest, task, prompt = self.fixture(directory)
            other = next(row for row in library(two_paths=True)["artifacts"]
                         if row["tools"][0] == "lookup")
            artifact.write_text(json.dumps(other), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), *self.arguments(artifact, manifest, task, prompt)],
                cwd=ROOT, text=True, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("projection artifact is not in this online Motif manifest",
                          result.stderr)


if __name__ == "__main__":
    unittest.main()
