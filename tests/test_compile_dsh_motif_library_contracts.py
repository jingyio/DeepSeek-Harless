"""The CLI must retain parameter shapes needed by executable MCP motifs."""

from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.adapters.dsh_trajectory import ToolContract
from tests.test_trace_compiled_read_motif import event_pair

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/compile-dsh-motif-library.py"
CHAIN_SCRIPT = ROOT / "scripts/compile-witnessed-read-chains.py"
IDENTITY_SCRIPT = ROOT / "scripts/freeze-dsh-task-identity.py"


def load_cli(path=SCRIPT):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContractLoadingTests(unittest.TestCase):
    def test_real_structured_mcp_contract_keeps_shapes_and_defaults(self):
        cli = load_cli()
        rows = json.loads((ROOT / "tests/fixtures/contracts/structured-research-tool-contracts.json")
                          .read_text(encoding="utf-8"))
        contracts = cli._contracts(rows)
        aggregate = contracts["mcp__local_research_tools__aggregate_records"]
        inspect = contracts["mcp__local_research_tools__inspect_records"]
        self.assertEqual(dict(aggregate.parameter_shapes), {
            "group_by": "string_list_allow_empty", "measures": "measure_list"})
        self.assertEqual(dict(inspect.default_params), {"records_path": ""})
        self.assertEqual(aggregate.provenance_params, ("dataset_id",))
        self.assertTrue(aggregate.replay_stable)
        self.assertTrue(inspect.replay_stable)
        self.assertTrue(contracts["mcp__local_research_tools__pin_source"].replay_stable)

    def test_invalid_shape_or_duplicate_default_is_rejected(self):
        cli = load_cli()
        base = {"required_params": ["dataset_id"], "read_only": True,
                "replay_stable": True}
        with self.assertRaisesRegex(ValueError, "invalid approved tool contract"):
            cli._contracts({"aggregate": {"required_params": ["dataset_id"],
                                          "read_only": True}})
        with self.assertRaisesRegex(ValueError, "invalid parameter shape"):
            cli._contracts({"aggregate": {**base,
                            "parameter_shapes": [["dataset_id", "unknown"]]}})
        with self.assertRaisesRegex(ValueError, "invalid default_params"):
            cli._contracts({"aggregate": {**base,
                            "default_params": [["mode", "a"], ["mode", "b"]]}})

    def test_witnessed_compiler_combines_real_application_contracts(self):
        cli = load_cli(CHAIN_SCRIPT)
        contracts = cli._contracts([
            ROOT / "tests/fixtures/contracts/scoped-research-handle-contracts.json",
            ROOT / "tests/fixtures/contracts/scoped-zotero-handle-contracts.json",
        ])
        read_pdf = contracts["mcp__scoped_research_read__read_pinned_pdf_pages"]
        self.assertEqual(dict(read_pdf.default_params),
                         {"start_page": 1, "max_pages": 2})
        self.assertEqual(read_pdf.witness_default_only,
                         ("start_page", "max_pages"))
        self.assertEqual(read_pdf.provenance_params, ("source_id",))
        with self.assertRaisesRegex(ValueError, "duplicate tool names"):
            cli._contracts([ROOT / "tests/fixtures/contracts/scoped-research-handle-contracts.json"] * 2)

    def test_real_jsonl_events_load_but_external_paths_do_not(self):
        cli = load_cli()
        with TemporaryDirectory(dir=ROOT / ".local") as folder:
            trace = Path(folder) / "events.jsonl"
            trace.write_text('{"type":"tool/call","data":{}}\n'
                             '{"type":"tool/result","data":{}}\n', encoding="utf-8")
            self.assertEqual([row["type"] for row in cli._events(trace)],
                             ["tool/call", "tool/result"])
            trace.write_text('{"type":"tool/call"}\nnot-json\n', encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                cli._events(trace)
        with self.assertRaisesRegex(ValueError, "under SSS/.local"):
            cli._events(ROOT / "README.md")

    def test_full_library_trace_uses_frozen_identity_not_claimed_fingerprint(self):
        cli = load_cli()
        freezer = load_cli(IDENTITY_SCRIPT)
        with TemporaryDirectory(dir=ROOT / ".local") as folder:
            base = Path(folder)
            (base / "manifest.json").write_text(json.dumps({
                "task_id": "sample", "question": "Which source supports the claim?"}),
                encoding="utf-8")
            (base / "events.jsonl").write_text("\n".join(json.dumps(row) for row in
                event_pair(1, "pin", {"path": "paper.json"},
                           {"source_id": "source-" + "a" * 32})) + "\n",
                encoding="utf-8")
            freezer.freeze(base, "decision-sample")
            contracts = {"pin": ToolContract(("path",), True, ("source_id",))}
            traced = cli._trace({"trace_id": "run", "identity": "task-identity.json",
                                 "events": "events.jsonl",
                                 "task_fingerprint": "forged-other-decision"},
                                base, contracts)
            self.assertEqual(traced.task_fingerprint, "decision-sample")
            with self.assertRaisesRegex(ValueError, "frozen identity"):
                cli._trace({"trace_id": "run", "events": "events.jsonl",
                            "task_fingerprint": "forged-other-decision"}, base, contracts)


if __name__ == "__main__":
    unittest.main()
