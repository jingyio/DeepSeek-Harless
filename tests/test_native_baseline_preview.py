"""The native-agent preview must copy the same bounded source set."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class NativeBaselinePreviewTests(unittest.TestCase):
    def test_directory_preview_copies_sources_and_obligations_without_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            sources = Path(temporary) / "sources"
            sources.mkdir()
            (sources / "first.txt").write_text("First method retrieves poses.", encoding="utf-8")
            (sources / "second.md").write_text("Second method refines poses.", encoding="utf-8")
            points_path = Path(temporary) / "points.json"
            points_path.write_text(json.dumps([{"id": "methods",
                                                "requirement": "Compare two recent methods",
                                                "min_sources": 2}]), encoding="utf-8")
            result = subprocess.run([
                sys.executable, str(ROOT / "scripts" / "run-native-baseline.py"),
                "Compare the two methods", "--source-dir", str(sources),
                "--answer-points", str(points_path),
            ], cwd=ROOT, capture_output=True, text=True, check=True)
            output = Path(result.stdout.strip().split("report=")[-1])
            inventory = json.loads((output / "sources.json").read_text(encoding="utf-8"))
            self.assertEqual({row["filename"] for row in inventory}, {"first.txt", "second.md"})
            prompt = (output / "prompt.txt").read_text(encoding="utf-8")
            self.assertIn('"min_sources": 2', prompt)
            self.assertIn("max_model_requests=unset", result.stdout)
            self.assertFalse((output / "metrics.json").exists())


if __name__ == "__main__":
    unittest.main()
