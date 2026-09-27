"""The online DSH adapter may consume only a validated Motif library."""

import importlib.util
from pathlib import Path
import unittest

from tests.test_motif_controller import library


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/export-online-motif-manifest.py"
SPEC = importlib.util.spec_from_file_location("online_export", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class OnlineExportTests(unittest.TestCase):
    def rows(self):
        return {
            "search": {"required_params": ["query"], "output_fields": ["id"],
                       "read_only": True, "replay_stable": True,
                       "description": "Find a scoped source"},
            "read": {"required_params": ["doc_id"], "output_fields": ["text"],
                     "read_only": True, "replay_stable": True,
                     "description": "Read a scoped source"},
        }

    def test_certified_library_exports_and_tampering_fails(self):
        source = library()
        manifest = MODULE.export_manifest(
            source, self.rows(), {"search": {"query": "[A-Za-z]+"}},
            {"search": "id", "read": "text"})
        self.assertEqual(len(manifest["artifacts"]), 1)
        self.assertEqual(manifest["source_library_digest"], source["library_digest"])
        self.assertEqual(manifest["manifest_digest"], MODULE.digest({
            key: value for key, value in manifest.items()
            if key != "manifest_digest"}))
        source["artifacts"][0]["transfer_evidence"] = []
        with self.assertRaises(ValueError):
            MODULE.export_manifest(source, self.rows())

    def test_rejects_unapproved_version_field(self):
        with self.assertRaisesRegex(ValueError, "version fields"):
            MODULE.export_manifest(library(), self.rows(),
                                   version_fields={"search": "invented"})


if __name__ == "__main__":
    unittest.main()
