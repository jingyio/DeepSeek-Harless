"""Check diversity, frozen inputs and read-only case isolation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp import Client, StdioServerParameters

from benchmarks.research_decision_portfolio_v1 import build_fixtures as fixtures
from benchmarks.research_decision_portfolio_v1 import mock_apps_server as apps
from src.adapters.tool_contract_loader import parse_tool_contracts


ROOT = Path(fixtures.__file__).resolve().parent


def scoped(case: str, short: str) -> str:
    app, suffix = short.split(":", 1)
    return f"{app}:{case}:{suffix}"


class ResearchDecisionPortfolioTest(unittest.TestCase):
    def setUp(self):
        apps._handles.clear()
        apps._datasets.clear()
        apps._discovered.clear()

    def test_nine_independent_decisions_in_three_distinct_families(self):
        lock = json.loads((ROOT / "fixtures.lock.json").read_text())
        self.assertEqual(set(lock["families"]), {
            "literature_claim_revision", "result_provenance_triage",
            "collaboration_decision_handoff"})
        self.assertEqual([len(ids) for ids in lock["families"].values()], [3, 3, 3])
        self.assertEqual(len({case for ids in lock["families"].values() for case in ids}), 9)
        for filename, digest in lock["sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / filename).read_bytes()).hexdigest(), digest)

    def test_motif_contracts_name_only_observable_fields(self):
        project = ROOT.parent.parent
        rows = json.loads((project / "config/research-portfolio-tool-contracts.json")
                          .read_text())
        contracts = parse_tool_contracts(rows)
        self.assertEqual(len(contracts), 8)
        self.assertTrue(all(contract.read_only and contract.replay_stable
                            for contract in contracts.values()))
        self.assertIn("root_object_id", contracts[
            "mcp__research_portfolio_fixture__read_event"].output_fields)

    def test_every_case_has_bounded_sources_and_separate_review(self):
        for case_id, spec in fixtures.CASES.items():
            with self.subTest(case_id=case_id), patch.dict(os.environ,
                                                          {"SSS_PORTFOLIO_CASE": case_id}):
                task = (ROOT / "cases" / case_id / "task.md").read_text()
                hidden = json.loads((ROOT / "cases" / case_id / "review.json").read_text())
                sources = json.loads((ROOT / "cases" / case_id / "sources.json").read_text())
                event = apps.read_event(f"event:{case_id}:01")
                self.assertEqual(event["root_objects"],
                                 [scoped(case_id, value) for value in spec["roots"]])
                self.assertEqual(hidden["case_id"], case_id)
                self.assertEqual(hidden["numerical_reference"],
                                 fixtures.numerical_reference(sources["objects"]))
                self.assertNotIn("fatal", task)
                for object_id in event["root_objects"]:
                    handle = apps.pin_resource(object_id)
                    read = apps.read_pinned(handle["source_id"])
                    self.assertEqual(handle["version_sha256"], read["version_sha256"])
                    self.assertTrue(read["synthetic"])
                with self.assertRaisesRegex(ValueError, "outside"):
                    apps.pin_resource("paper:other:p01")

    def test_table_comparison_reports_protocol_change_without_interpreting_it(self):
        with patch.dict(os.environ, {"SSS_PORTFOLIO_CASE": "r_assay_batch"}):
            apps.read_event("event:r_assay_batch:01")
            commit = apps.pin_resource(scoped("r_assay_batch", "github:c01"))["source_id"]
            apps.read_pinned(commit)
            older = apps.read_pinned(apps.pin_resource(
                scoped("r_assay_batch", "wps:d00"))["source_id"])
            newer = apps.read_pinned(apps.pin_resource(
                scoped("r_assay_batch", "wps:d01"))["source_id"])
            old_id, new_id = older["value"]["dataset_id"], newer["value"]["dataset_id"]
            result = apps.compare_tables(old_id, new_id)
            self.assertEqual(result["status"], "compared")
            self.assertTrue(result["protocol_changed"])
            self.assertTrue(result["changed_rows"])
            aggregate = apps.aggregate_rate(new_id, "substrate")
            self.assertEqual(len(aggregate["groups"]), 2)
            self.assertEqual(apps.read_rows(new_id, 0, 20)["total"], 4)

    def test_hardware_mix_has_real_weighting_conflict(self):
        spec = fixtures.CASES["r_hardware_mix"]["objects"]
        old = fixtures.numerical_reference({"old": spec["wps:d00"]})["old"]
        new = fixtures.numerical_reference({"new": spec["wps:d01"]})["new"]
        self.assertTrue(all(n["numerator"] / n["denominator"] <
                            o["numerator"] / o["denominator"]
                            for o, n in zip(old, new, strict=True)))
        unweighted_old = sum(row["numerator"] for row in old) / sum(
            row["denominator"] for row in old)
        new_weighted = (4 * new[0]["numerator"] + new[1]["numerator"]) / (
            4 * new[0]["denominator"] + new[1]["denominator"])
        self.assertAlmostEqual(unweighted_old, 0.605)
        self.assertAlmostEqual(new_weighted, 0.703)

    def test_source_change_invalidates_existing_handle(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            case_dir = root / "cases" / "l_state_update"
            case_dir.mkdir(parents=True)
            path = case_dir / "sources.json"
            content = (ROOT / "cases" / "l_state_update" / "sources.json").read_bytes()
            path.write_bytes(content)
            with patch.object(apps, "ROOT", root), patch.dict(os.environ,
                  {"SSS_PORTFOLIO_CASE": "l_state_update"}):
                apps.read_event("event:l_state_update:01")
                annotation = apps.pin_resource(scoped("l_state_update", "zotero:a01"))["source_id"]
                apps.read_pinned(annotation)
                source_id = apps.pin_resource(scoped("l_state_update", "paper:p01"))["source_id"]
                data = json.loads(path.read_text())
                data["objects"][scoped("l_state_update", "paper:p01")]["text"] += " 新版本。"
                path.write_text(json.dumps(data, ensure_ascii=False))
                with self.assertRaisesRegex(ValueError, "changed since pin"):
                    apps.read_pinned(source_id)

    def test_exact_excerpt_requires_a_pinned_text_source(self):
        with patch.dict(os.environ, {"SSS_PORTFOLIO_CASE": "l_state_update"}):
            apps.read_event("event:l_state_update:01")
            with self.assertRaisesRegex(ValueError, "not been discovered"):
                apps.pin_resource(scoped("l_state_update", "paper:p01"))
            apps.read_pinned(apps.pin_resource(
                scoped("l_state_update", "zotero:a01"))["source_id"])
            source = apps.pin_resource(scoped("l_state_update", "paper:p01"))["source_id"]
            result = apps.locate_excerpt(source, "外部状态")
            self.assertEqual(result["positions"], [14])
            self.assertTrue(result["unique"])
            self.assertFalse(apps.locate_excerpt(source, "模型内部参数变化")["unique"])


class ResearchDecisionPortfolioMcpTest(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_mcp_round_trip_for_each_family(self):
        project = ROOT.parent.parent
        for case_id, short_id in (("l_state_update", "zotero:a01"),
                                  ("r_assay_batch", "wps:d01"),
                                  ("c_negative_control", "gmail:m01")):
            with self.subTest(case_id=case_id):
                object_id = scoped(case_id, short_id)
                params = StdioServerParameters(
                    command=sys.executable,
                    args=[str(ROOT / "mock_apps_server.py")], cwd=project,
                    env={"SSS_PORTFOLIO_CASE": case_id, "PYTHONPATH": str(project)},
                )
                async with Client(params, read_timeout_seconds=20) as client:
                    offered = {tool.name for tool in (await client.list_tools()).tools}
                    self.assertEqual(offered, {"read_event", "pin_resource", "read_pinned",
                                               "read_rows", "aggregate_rate", "compare_tables",
                                               "find_dependents", "locate_excerpt"})
                    event = await client.call_tool("read_event",
                        {"event_id": f"event:{case_id}:01"})
                    self.assertFalse(event.is_error)
                    self.assertIn(object_id, json.loads(event.content[0].text)["root_objects"])
                    pinned = await client.call_tool("pin_resource", {"object_id": object_id})
                    self.assertFalse(pinned.is_error)
                    source_id = json.loads(pinned.content[0].text)["source_id"]
                    read = await client.call_tool("read_pinned", {"source_id": source_id})
                    self.assertFalse(read.is_error)
                    self.assertEqual(json.loads(read.content[0].text)["object_id"], object_id)


if __name__ == "__main__":
    unittest.main()
