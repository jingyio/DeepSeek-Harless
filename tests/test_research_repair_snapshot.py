"""A repair may reuse an answer only with the exact prior source collection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.graph.runtime import Evidence, execute
from src.workflows.research import SOURCE_MOTIF
from src.workflows.research_repair_snapshot import verify_repair_source_trace


class ResearchRepairSnapshotTests(unittest.TestCase):
    def test_added_source_invalidates_repair_even_if_old_citation_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source_dir = Path(temporary).resolve()
            (source_dir / "paper.txt").write_text("Original cited passage.", encoding="utf-8")
            original = execute(SOURCE_MOTIF, {"source_dir": Evidence(str(source_dir), "test")})
            self.assertEqual(original.status, "completed")
            trace = original.report()
            verify_repair_source_trace(trace, source_dir, original.state["unique_pages"].value)

            (source_dir / "new.txt").write_text("A new conflicting result.", encoding="utf-8")
            changed = execute(SOURCE_MOTIF, {"source_dir": Evidence(str(source_dir), "test")})
            self.assertEqual(changed.status, "completed")
            with self.assertRaisesRegex(ValueError, "snapshot changed"):
                verify_repair_source_trace(trace, source_dir, changed.state["unique_pages"].value)


if __name__ == "__main__":
    unittest.main()
