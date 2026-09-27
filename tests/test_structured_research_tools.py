"""Version checks and parameter flow for generic research data tools."""

from __future__ import annotations

import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mcp import Client
from mcp.server.mcpserver.exceptions import ToolError

from src.mcp import structured_research_tools as tools
from src.semantic_inputs import SemanticInputRequired
from src.mcp.local_research_tools_server import server
from src.mcp.structured_research_server import server as focused_server


class StructuredResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(dir=tools.ROOT / ".local" / "python-workspace")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.store_patch = patch.object(tools, "_STORE", tools.HandleStore(self.directory / "handles.sqlite3"))
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def test_realistic_chain_and_changed_source_guard(self):
        first = self.directory / "first.json"
        second = self.directory / "second.json"
        first.write_text(json.dumps({"records": [
            {"task": "A", "before": 10, "after": 7},
            {"task": "A", "before": 8, "after": 5},
            {"task": "B", "before": 4, "after": 3},
        ]}), encoding="utf-8")
        second.write_text(json.dumps({"records": [
            {"task": "A", "before": 10, "after": 6},
            {"task": "A", "before": 8, "after": 5},
            {"task": "B", "before": 4, "after": 3},
        ]}), encoding="utf-8")
        source_a = tools.pin_source(str(first))["source_id"]
        source_b = tools.pin_source(str(second))["source_id"]
        dataset_a = tools.inspect_records(source_a, "records")
        dataset_b = tools.inspect_records(source_b, "records")
        self.assertEqual(dataset_a["record_count"], 3)
        measures = [{"name": "calls_saved", "op": "sum_difference",
                     "left": "before", "right": "after"}]
        old = tools.aggregate_records(dataset_a["dataset_id"], ["task"], measures)
        new = tools.aggregate_records(dataset_b["dataset_id"], ["task"], measures)
        self.assertEqual(old["groups"][0]["values"]["calls_saved"], 6)
        self.assertEqual(tools.compare_results(old["result_id"], new["result_id"])["changed_groups"], 1)
        self.assertFalse(tools.compare_sources(source_a, source_b)["byte_identical"])

        top = tools.aggregate_records(dataset_a["dataset_id"], ["task"], measures,
                                      order_by="calls_saved", limit=1)
        self.assertEqual(top["group_count"], 2)
        self.assertEqual(top["returned_groups"], 1)
        self.assertEqual(top["groups"][0]["group"]["task"], "A")

        first.write_text(first.read_text().replace('"after": 7', '"after": 2'), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Source changed"):
            tools.aggregate_records(dataset_a["dataset_id"], ["task"], measures)
        with self.assertRaisesRegex(ValueError, "Source changed"):
            tools.compare_results(old["result_id"], new["result_id"])

    def test_handle_chain_replays_identically_after_store_reopens(self):
        source = self.directory / "stable.json"
        source.write_text('[{"group":"A","value":2}]', encoding="utf-8")
        def run_chain():
            pinned = tools.pin_source(str(source))
            inspected = tools.inspect_records(pinned["source_id"])
            result = tools.aggregate_records(
                inspected["dataset_id"], ["group"],
                [{"name": "total", "op": "sum", "field": "value"}])
            return pinned["source_id"], inspected["dataset_id"], result["result_id"]
        original = run_chain()
        with patch.object(tools, "_STORE", tools.HandleStore(self.directory / "handles.sqlite3")):
            self.assertEqual(run_chain(), original)
        source.write_text('[{"group":"A","value":3}]', encoding="utf-8")
        changed = run_chain()
        self.assertNotEqual(changed, original)
        with self.assertRaisesRegex(ValueError, "Source changed"):
            tools.inspect_records(original[0])

    def test_path_scope_and_numeric_validation(self):
        with self.assertRaisesRegex(ValueError, "approved research input"):
            tools.pin_source(str(tools.ROOT / "README.md"))
        file = self.directory / "rows.csv"
        file.write_text("task,value\nA,not-a-number\n", encoding="utf-8")
        dataset = tools.inspect_records(tools.pin_source(str(file))["source_id"])["dataset_id"]
        with self.assertRaisesRegex(ValueError, "non-numeric"):
            tools.aggregate_records(dataset, [], [{"name": "total", "op": "sum", "field": "value"}])

    def test_task_relative_path_still_requires_approved_root(self):
        file = self.directory / "records.json"
        file.write_text('[{"value": 1}]', encoding="utf-8")
        with patch.dict("os.environ", {"SSS_RESEARCH_INPUT_DIR": str(self.directory)}):
            self.assertEqual(tools.pin_source("records.json")["bytes"], file.stat().st_size)
            with self.assertRaisesRegex(ValueError, "approved research input"):
                tools.pin_source(str(tools.ROOT / "README.md"))

    def test_source_listing_gives_paths_for_pin_without_reading_contents(self):
        folder = self.directory / "sources"
        folder.mkdir()
        (folder / "trial.json").write_text('[{"reward": 1}]', encoding="utf-8")
        (folder / "unknown.bin").write_bytes(b"private")
        with patch.dict("os.environ", {"SSS_RESEARCH_INPUT_DIR": str(self.directory)}):
            listed = tools.list_research_sources()
            self.assertEqual(listed["file_count"], 1)
            self.assertEqual(listed["files"][0]["path"], "sources/trial.json")
            self.assertNotIn("reward", str(listed))
            self.assertEqual(tools.pin_source(listed["files"][0]["path"])["bytes"], 15)

    def test_nested_numeric_field_can_be_aggregated(self):
        file = self.directory / "nested.json"
        file.write_text(json.dumps([
            {"task": "A", "metrics": {"calls": 2}},
            {"task": "A", "metrics": {"calls": 4}},
        ]), encoding="utf-8")
        inspected = tools.inspect_records(tools.pin_source(str(file))["source_id"])
        self.assertIn("metrics.calls", inspected["fields"])
        result = tools.aggregate_records(inspected["dataset_id"], ["task"],
                                         [{"name": "mean_calls", "op": "mean",
                                           "field": "metrics.calls"}])
        self.assertEqual(result["groups"][0]["values"]["mean_calls"], 3)

    def test_correlations_are_grouped_and_ties_use_average_ranks(self):
        file = self.directory / "predictions.csv"
        file.write_text("task,label,prediction\n"
                        "A,1,1\nA,2,2\nA,2,3\nA,4,4\n"
                        "B,1,4\nB,2,3\nB,3,2\nB,4,1\n", encoding="utf-8")
        dataset = tools.inspect_records(tools.pin_source(str(file))["source_id"])
        result = tools.aggregate_records(dataset["dataset_id"], ["task"], [
            {"name": "pearson", "op": "pearson_correlation",
             "left": "label", "right": "prediction"},
            {"name": "spearman", "op": "spearman_correlation",
             "left": "label", "right": "prediction"},
        ])
        by_task = {row["group"]["task"]: row["values"] for row in result["groups"]}
        self.assertTrue(math.isclose(by_task["A"]["spearman"], 0.9486832980505138))
        self.assertEqual(by_task["B"]["pearson"], -1.0)
        self.assertEqual(by_task["B"]["spearman"], -1.0)
        with self.assertRaisesRegex(ValueError, "unknown field"):
            tools.aggregate_records(dataset["dataset_id"], [], [
                {"name": "invalid", "op": "spearman_correlation",
                 "left": "missing", "right": "prediction"}])

        short = self.directory / "short.csv"
        short.write_text("label,prediction\n1,1\n2,2\n", encoding="utf-8")
        short_dataset = tools.inspect_records(tools.pin_source(str(short))["source_id"])
        with self.assertRaisesRegex(ValueError, "at least three"):
            tools.aggregate_records(short_dataset["dataset_id"], [], [
                {"name": "rho", "op": "spearman_correlation",
                 "left": "label", "right": "prediction"}])

        flat = self.directory / "flat.csv"
        flat.write_text("label,prediction\n1,1\n1,2\n1,3\n", encoding="utf-8")
        flat_dataset = tools.inspect_records(tools.pin_source(str(flat))["source_id"])
        with self.assertRaisesRegex(ValueError, "constant series"):
            tools.aggregate_records(flat_dataset["dataset_id"], [], [
                {"name": "rho", "op": "spearman_correlation",
                 "left": "label", "right": "prediction"}])

    def test_json_object_requests_explicit_record_array_choice(self):
        file = self.directory / "multiple.json"
        file.write_text(json.dumps({"rows": [{"n": 1}],
                                    "groups": [{"n": 2}], "status": "draft"}),
                        encoding="utf-8")
        source = tools.pin_source(str(file))["source_id"]
        with self.assertRaises(SemanticInputRequired) as raised:
            tools.inspect_records(source)
        self.assertEqual(raised.exception.parameter, "records_path")
        self.assertEqual(raised.exception.candidates, ("rows", "groups"))
        self.assertEqual(raised.exception.details["rows"],
                         {"record_count": 1, "fields": ["n"]})
        with self.assertRaises(ToolError) as tool_error:
            tools.mcp_safe(tools.inspect_records)(source)
        payload = json.loads(str(tool_error.exception))
        self.assertEqual(payload["error"], "semantic_input_required")
        self.assertEqual(payload["candidates"]["rows"]["fields"], ["n"])
        self.assertEqual(tools.inspect_records(source, "rows")["record_count"], 1)

    def test_rank_grouped_result_counts_stratum_winners_and_losers(self):
        file = self.directory / "paired.json"
        file.write_text(json.dumps([
            {"seed": 0, "policy": "A", "score": 1},
            {"seed": 0, "policy": "B", "score": 2},
            {"seed": 1, "policy": "A", "score": 4},
            {"seed": 1, "policy": "B", "score": 3},
        ]), encoding="utf-8")
        dataset = tools.inspect_records(tools.pin_source(str(file))["source_id"])
        result = tools.aggregate_records(dataset["dataset_id"], ["seed", "policy"],
                                         [{"name": "mean_score", "op": "mean", "field": "score"}])
        ranked = tools.rank_grouped_result(result["result_id"], "policy", "mean_score", ["seed"])
        self.assertEqual(ranked["strata_count"], 2)
        self.assertEqual(ranked["first_place_counts"], {"B": 1, "A": 1})
        self.assertEqual(ranked["last_place_counts"], {"A": 1, "B": 1})
        with self.assertRaisesRegex(ValueError, "partition"):
            tools.rank_grouped_result(result["result_id"], "policy", "mean_score", [])


class StructuredResearchMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_schemas_are_exposed(self):
        async with Client(server) as client:
            names = {tool.name for tool in (await client.list_tools()).tools}
        self.assertTrue({"list_research_sources", "pin_source", "inspect_records", "aggregate_records",
                         "rank_grouped_result",
                         "compare_sources", "compare_results"}.issubset(names))

    async def test_focused_schema_explains_measure_parameters_and_errors(self):
        async with Client(focused_server) as client:
            listed = {tool.name: tool for tool in (await client.list_tools()).tools}
            self.assertEqual(set(listed), {"list_research_sources", "pin_source", "inspect_records",
                                           "rank_grouped_result",
                                           "aggregate_records", "compare_sources",
                                           "compare_results"})
            schema = listed["aggregate_records"].input_schema
            measure = schema["$defs"]["MeasureSpec"]
            self.assertEqual(set(measure["required"]), {"name", "op"})
            self.assertIn("mean", measure["properties"]["op"]["enum"])
            self.assertIn("spearman_correlation", measure["properties"]["op"]["enum"])
            result = await client.call_tool("aggregate_records", {
                "dataset_id": "dataset-" + "0" * 32, "group_by": [],
                "measures": [{"op": "count"}],
            })
            self.assertTrue(result.is_error)
            self.assertIn("measures.0.name", result.content[0].text)


if __name__ == "__main__":
    unittest.main()
