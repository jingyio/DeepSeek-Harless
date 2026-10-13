from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from benchmarks.research_report_agent_v3.intake import materialize
from benchmarks.research_report_agent_v3.generate_cases import generate
from benchmarks.research_report_agent_v3.compile_motifs import compile_library, learned_chains
from benchmarks.research_report_agent_v3.prepare_experiment import matrices
from benchmarks.research_report_agent_v3.run_matrix import validate_jobs


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / "unknown.csv"
        self.csv.write_text("person,x,y\na,1,2\nb,3,4\n", encoding="utf-8")
        self.request = self.root / "request.txt"
        self.request.write_text("分析数据，生成简明PDF。", encoding="utf-8")

    def test_no_scientific_assumptions_invented_from_csv_or_filename(self):
        result = materialize(data=self.csv, request_file=self.request, destination=self.root / "frozen")
        study = json.loads((Path(result["folder"]) / "study.json").read_text(encoding="utf-8"))
        self.assertNotIn("design", study)
        self.assertNotIn("synthetic", study)
        self.assertEqual(study["report_requirements"], {})
        self.assertEqual(study["units"], {})
        self.assertIn("未提供", study["description"])
        self.assertEqual((Path(result["folder"]) / "task.txt").read_text(encoding="utf-8").strip(), "分析数据，生成简明PDF。")

    def test_outline_preserved_and_request_changes_fingerprint(self):
        outline = self.root / "outline.txt"
        outline.write_text("结果\n局限\n后续研究", encoding="utf-8")
        first = materialize(data=self.csv, request_file=self.request, outline_file=outline, destination=self.root / "a")
        second = materialize(data=self.csv, request_file=self.request, outline_file=outline, destination=self.root / "b")
        self.assertEqual(first["input_fingerprint"], second["input_fingerprint"])
        self.assertEqual(first["source_sha256"], second["source_sha256"])
        self.assertIn("结果\n局限\n后续研究", (Path(first["folder"]) / "task.txt").read_text(encoding="utf-8"))
        self.request.write_text("现在只要一页。", encoding="utf-8")
        changed = materialize(data=self.csv, request_file=self.request, destination=self.root / "c")
        self.assertNotEqual(first["input_fingerprint"], changed["input_fingerprint"])

    def test_frozen_inputs_reject_overwrite_or_malformed_csv(self):
        materialize(data=self.csv, request_file=self.request, destination=self.root / "a", case_id="same")
        self.request.write_text("新的要求", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Frozen"):
            materialize(data=self.csv, request_file=self.request, destination=self.root / "a", case_id="same")
        self.csv.write_text("x,x\n1,2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unique"):
            materialize(data=self.csv, request_file=self.request, destination=self.root / "b")

    def test_main_experiment_rejects_frozen_semantic_choices(self):
        study = self.root / 'study.json'
        study.write_text(json.dumps({'benchmark_frozen_decisions': {}}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'free presentation'):
            materialize(data=self.csv, request_file=self.request, study_json=study, destination=self.root / 'frozen')

    def test_seven_synthetic_tasks_no_pipeline_prompt_and_distinct_datasets(self):
        result = generate(self.root / "data")
        self.assertEqual(len(result["cases"]), 7)
        self.assertEqual([row["split"] for row in result["cases"]].count("evaluation"), 4)
        datasets = []
        for case in result["cases"]:
            folder = self.root / "data" / "cases" / case["case_id"]
            task = (folder / "task.txt").read_text(encoding="utf-8")
            for token in ("approve_workflow", "render_figures", "motif", "allow_deterministic"):
                self.assertNotIn(token, task.lower())
            datasets.append((folder / "data.csv").read_bytes())
        self.assertEqual(len(set(datasets)), 7)

    def test_seed_offset_changes_only_new_outputs_and_records_actual_oracle_seed(self):
        pilot = generate(self.root / "pilot")
        formal = generate(self.root / "formal", seed_offset=100000)
        self.assertEqual(formal["seed_offset"], 100000)
        for before, after in zip(pilot["cases"], formal["cases"], strict=True):
            self.assertEqual(after["seed"], before["seed"] + 100000)
            name = before["case_id"]
            pilot_csv = self.root / "pilot" / "cases" / name / "data.csv"
            formal_csv = self.root / "formal" / "cases" / name / "data.csv"
            self.assertNotEqual(pilot_csv.read_bytes(), formal_csv.read_bytes())
            self.assertEqual((pilot_csv.parent / "task.txt").read_bytes(), (formal_csv.parent / "task.txt").read_bytes())
            oracle = json.loads((self.root / "formal" / "oracles" / (name + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(oracle["seed"], after["seed"])

    def test_generator_will_not_rewrite_previous_experiment(self):
        generate(self.root / 'data')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            generate(self.root / 'data', seed_offset=1)

    def test_matrix_preserves_sixteen_runs_and_reverses_arm_order(self):
        training, evaluation = matrices()
        validate_jobs(training)
        validate_jobs(evaluation)
        self.assertEqual(len(training), 3)
        self.assertEqual(len(evaluation), 16)
        self.assertEqual([row['experiment_role'] for row in training], ['train', 'train', 'certification'])
        cases = {row['case'] for row in evaluation}
        self.assertEqual(len(cases), 4)
        for case in cases:
            first = [row['mode'] for row in evaluation if row['case'] == case and row['repeat_id'] == 1]
            second = [row['mode'] for row in evaluation if row['case'] == case and row['repeat_id'] == 2]
            self.assertEqual(set(first), {'baseline', 'execute'})
            self.assertEqual(first, list(reversed(second)))
        broken = [dict(row) for row in evaluation]
        broken[0]['matrix_order'] = 9
        with self.assertRaisesRegex(ValueError, 'declared sequence'):
            validate_jobs(broken)



class CompilerTests(unittest.TestCase):
    def test_declared_evaluation_cannot_be_relabelled_for_learning(self):
        with self.assertRaisesRegex(ValueError, 'roles'):
            compile_library([{'experiment_role': 'evaluation'}], {'experiment_role': 'certification'}, {})
    def test_independent_dataset_alias_rejected(self):
        # Must fail before trusting tool schemas or witness structure.
        make = lambda case: {"case_id": case, "csv_sha256": "same", "experiment_role": "certification" if case == "cert" else "train"}
        with self.assertRaisesRegex(ValueError, "aliases"):
            compile_library([make("one"), make("two")], make("cert"), {})

    def test_long_chains_derive_only_from_observed_edges(self):
        edges = [{"from_tool": "a", "to_tool": "b", "motif_id": "ab"},
                 {"from_tool": "b", "to_tool": "c", "motif_id": "bc"},
                 {"from_tool": "d", "to_tool": "e", "motif_id": "de"}]
        chains = learned_chains(edges)
        self.assertEqual(chains[0], {"tools": ["a", "b", "c"], "motif_ids": ["ab", "bc"], "edge_count": 2})
        self.assertEqual(chains[1]["tools"], ["d", "e"])
        self.assertFalse(any("c" in row["tools"] and "d" in row["tools"] for row in chains))

    def test_ten_edges_require_independent_witnesses_and_coverage_reports_gaps(self):
        # Offline artificial graph, not a real model or report experiment.
        prefix = "mcp__research_report__"
        contracts, edges = {}, {}
        for index in range(11):
            name = prefix + f"node_{index}"
            contracts[name] = {"required_params": [f"id_{index - 1}"] if index else ["plan"],
                               "output_fields": [f"id_{index}"],
                               "execution": "workspace_idempotent" if index else "semantic"}
            if index:
                edge = (prefix + f"node_{index - 1}", f"id_{index - 1}", name, f"id_{index - 1}")
                edges[edge] = [{"from_call_id": f"c{index - 1}", "to_call_id": f"c{index}"}]
        def observed(case):
            return {"case_id": case, "run_id": case, "csv_sha256": case,
                    "events_sha256": case, "tool_schemas": {}, "edges": dict(edges),
                    "experiment_role": "certification" if case == "cert" else "train", "semantic_decisions": []}
        first, second, cert = observed("first"), observed("second"), observed("cert")
        result = compile_library([first, second], cert, contracts)
        self.assertEqual(len(result["artifacts"]), 10)
        self.assertEqual(result["learned_chains"][0]["edge_count"], 10)
        self.assertTrue(all(row["eligible"] for row in result["observed_authorized_edge_coverage"]))
        cert["edges"].pop(next(iter(edges)))
        reduced = compile_library([first, second], cert, contracts)
        self.assertEqual(len(reduced["artifacts"]), 9)
        rejected = [row for row in reduced["observed_authorized_edge_coverage"] if not row["eligible"]]
        self.assertEqual(len(rejected), 1)
        self.assertFalse(rejected[0]["independently_witnessed"])


if __name__ == "__main__":
    unittest.main()
