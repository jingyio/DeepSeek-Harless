"""The paid AIDD entry point must match the reviewed scope and approval."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run-aidd-initial-pilot.py"
SPEC = importlib.util.spec_from_file_location("aidd_pilot_gate", SCRIPT)
assert SPEC and SPEC.loader
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AiddPaidGateTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "source.md"
        source.write_text("frozen", encoding="utf-8")
        rows = [{"role": f"private_{n}", "path": str(source),
                 "sha256": sha(source), "external_model_excerpt_allowed": False}
                for n in range(4)]
        rows += [{"role": f"public_{n}", "path": str(source),
                  "sha256": sha(source), "origin": "public_research_workflow",
                  "external_model_excerpt_allowed": True}
                 for n in range(4)]
        zotero = [{"role": f"item_{n}", "external_model_excerpt_allowed": False}
                  for n in range(8)]
        self.review = root / "review.json"
        self.approved = root / "approved.json"
        self.approval = root / "approval.json"
        self.prompt = root / "prompt.md"
        self.config = root / "patch.yml"
        self.prompt.write_text("research question", encoding="utf-8")
        self.config.write_text("limited tools", encoding="utf-8")
        self.review.write_text(json.dumps({"status": "review_only", "sources": rows,
                                           "zotero_sources": zotero}), encoding="utf-8")
        self.path_patch = patch.multiple(
            pilot, REVIEW_SCOPE=self.review, APPROVED_SCOPE=self.approved,
            APPROVAL=self.approval, PROMPT_FILE=self.prompt, PATCH=self.config)
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)

    def approve_copy(self) -> None:
        scope = json.loads(self.review.read_text(encoding="utf-8"))
        scope["status"] = "approved_for_model"
        for row in scope["sources"] + scope["zotero_sources"]:
            row["external_model_excerpt_allowed"] = True
        self.approved.write_text(json.dumps(scope), encoding="utf-8")
        self.approval.write_text(json.dumps({
            "approved": True, "review_scope_sha256": sha(self.review),
            "approved_scope_sha256": sha(self.approved),
            "prompt_sha256": sha(self.prompt), "patch_sha256": sha(self.config),
            "model": "deepseek-flash", "max_requests": 30, "max_usd": 2,
        }), encoding="utf-8")

    def test_review_only_scope_does_not_start_paid_run(self) -> None:
        self.assertEqual(pilot._check_scope(paid=False)[0]["status"], "review_only")
        with self.assertRaisesRegex(ValueError, "no researcher-approved scope"):
            pilot._check_scope(paid=True)

    def test_exact_approval_passes_and_scope_drift_fails(self) -> None:
        self.approve_copy()
        with patch.object(pilot, "verify_zotero") as verify:
            self.assertEqual(pilot._check_scope(paid=True)[0]["status"],
                             "approved_for_model")
            self.assertEqual(verify.call_count, 8)
        scope = json.loads(self.approved.read_text(encoding="utf-8"))
        scope["sources"][0]["allowed_page_ranges"] = [[1, 2]]
        self.approved.write_text(json.dumps(scope), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from the reviewed"):
            pilot._check_scope(paid=True)

    def test_prompt_change_invalidates_approval(self) -> None:
        self.approve_copy()
        self.prompt.write_text("changed research question", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "approval does not match"):
            pilot._check_scope(paid=True)


if __name__ == "__main__":
    unittest.main()
