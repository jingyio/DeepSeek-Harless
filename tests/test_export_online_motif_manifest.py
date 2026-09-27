"""The online DSH adapter may consume only a validated Motif library."""

import importlib.util
from pathlib import Path
import unittest

from tests.test_motif_controller import library
from src.motif_core.offline.trace_compiler import artifact_signature
from src.motif_core.offline.library_builder import _digest as library_digest


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
        program = manifest["artifacts"][0]["local_programs"]["read"]
        self.assertEqual(program["steps"], [{
            "op": "copy_verified_field", "from_tool": "search",
            "from_field": "id", "to_param": "doc_id"}])
        self.assertEqual(program["program_digest"], MODULE.digest({
            key: value for key, value in program.items()
            if key != "program_digest"}))
        self.assertEqual(source["artifacts"][0]["local_programs"]["read"], program)
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

    def test_skill_code_must_match_its_certified_parameter_edge(self):
        source = library()
        artifact = source["artifacts"][0]
        artifact["local_programs"]["read"]["steps"][0]["from_field"] = "other"
        artifact["certified_digest"] = artifact_signature(artifact)
        source["library_digest"] = library_digest({
            key: value for key, value in source.items()
            if key != "library_digest"})
        with self.assertRaisesRegex(ValueError, "local code differs"):
            MODULE.export_manifest(source, self.rows())

    def test_approved_interleaving_read_is_exported_without_becoming_a_motif(self):
        rows = self.rows()
        rows["list_sources"] = {"required_params": [], "output_fields": [],
                                "read_only": True, "replay_stable": True,
                                "description": "List approved sources"}
        rows["write_note"] = {"required_params": ["text"], "output_fields": [],
                              "read_only": False, "replay_stable": False,
                              "description": "Write a note"}
        manifest = MODULE.export_manifest(library(), rows)
        self.assertIn("list_sources", manifest["contracts"])
        self.assertNotIn("write_note", manifest["contracts"])
        self.assertEqual(manifest["artifacts"][0]["tools"], ["search", "read"])


if __name__ == "__main__":
    unittest.main()
