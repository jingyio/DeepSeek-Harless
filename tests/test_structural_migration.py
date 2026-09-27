from __future__ import annotations

import tempfile
import unittest
import json
import sys
from pathlib import Path

from src.adapters.harness_semantic import _parse_response
from src.adapters.point_research_semantic import (
    parse_point_selection, prepare_point_selection, prepare_point_synthesis,
    prepare_simple_point_prompt, repair_same_page_selection_aliases,
)
from src.adapters.research_repair_semantic import parse_repair_queries, prepare_repair_answer
from src.adapters.migration_semantic import parse_migration_selection, prepare_migration_selection
from src.adapters.deep_research_semantic import (
    parse_evidence_selection, parse_research_plan, prepare_deep_synthesis,
    prepare_evidence_selection, prepare_research_plan,
)
from src.graph.runtime import Evidence, Motif, Node, execute
from src.workflows.migration import MIGRATION_MOTIF, SITE_MOTIF, VERIFY_MOTIF, discover_extra_abc_candidates
from src.workflows.native_value_migration import NATIVE_VALUE_MOTIF
from src.workflows.research import (
    ANSWER_COVERAGE_MOTIF, ANSWER_POINT_PREFLIGHT_MOTIF, EVIDENCE_CONTRACT_MOTIF,
    POINT_PAGE_PASSAGES_MOTIF, QUESTION_COVERAGE_MOTIF, RESEARCH_MOTIF, RESEARCH_REPAIR_MERGE_MOTIF,
    RETRIEVE_MOTIF, SOURCE_MOTIF, ground_query_terms, ground_repair_terms,
)


class MotifRuntimeTests(unittest.TestCase):
    def test_missing_evidence_stops_before_action(self) -> None:
        called = False

        def action(_state):
            nonlocal called
            called = True
            return {"done": True}

        motif = Motif("guard-test", (Node("work", (), ("approved",), ("done",), action),))
        result = execute(motif, {"approved": Evidence(True, "unknown", verified=False)})
        self.assertEqual(result.status, "needs_mediation")
        self.assertFalse(called)

    def test_invalid_dependency_rejected(self) -> None:
        motif = Motif("bad", (Node("later", ("missing",), (), (), lambda _: {}),))
        with self.assertRaises(ValueError):
            execute(motif, {})


class MigrationTests(unittest.TestCase):
    def test_native_value_recipe_requires_exact_shape_and_preserves_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "package"
            package.mkdir()
            path = package / "native.py"
            source = (
                "from ast import literal_eval\n"
                "from jinja2._compat import text_type\n\n"
                "def native_concat(nodes):\n"
                "    head = list(nodes)\n"
                "    if len(head) == 1:\n"
                "        out = head[0]\n"
                "    else:\n"
                "        out = ''.join(text_type(v) for v in head)\n"
                "    try:\n"
                "        return literal_eval(out)\n"
                "    except ValueError:\n"
                "        return out\n"
            )
            path.write_text(source, encoding="utf-8")
            inputs = {"root": Evidence(temp, "test"), "file": Evidence("package/native.py", "test")}
            run = execute(NATIVE_VALUE_MOTIF, inputs)
            self.assertEqual(run.status, "completed")
            self.assertIn("if len(head) == 1 and not isinstance(out, text_type)", run.state["diff"].value)
            self.assertEqual(path.read_text(encoding="utf-8"), source)
            path.write_text(run.state["updated"].value["package/native.py"], encoding="utf-8")
            repeated = execute(NATIVE_VALUE_MOTIF, inputs)
            self.assertEqual(repeated.gap.kind, "already_migrated")
            path.write_text(source.replace("out = head[0]", "out = head[-1]"), encoding="utf-8")
            changed_shape = execute(NATIVE_VALUE_MOTIF, inputs)
            self.assertEqual(changed_shape.gap.kind, "unsupported_shape")
            self.assertNotIn("updated", changed_shape.state)

    def test_safe_import_is_prepared_without_changing_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.py"
            source = "from collections import Mapping as M  # old API\nvalue: M | None = None\n"
            path.write_text(source, encoding="utf-8")
            result = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(result.status, "completed")
            self.assertIn("from collections.abc import Mapping as M", result.state["diff"].value)
            self.assertEqual(path.read_text(encoding="utf-8"), source)
            self.assertEqual(len(result.state["proposals"].value), 1)

    def test_ambiguous_form_reaches_semantic_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.py"
            path.write_text("from collections import Mapping, OrderedDict\n", encoding="utf-8")
            result = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(result.status, "needs_mediation")
            self.assertEqual(result.gap.kind, "ambiguous_migration")
            self.assertEqual(len(result.state["gaps"].value), 1)
            self.assertEqual(result.state["diff"].value, "")

    def test_all_abc_combined_import_is_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.py"
            source = "from collections import MutableSet, MutableMapping, MutableSequence\n"
            path.write_text(source, encoding="utf-8")
            result = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(result.status, "completed")
            self.assertIn("from collections.abc import MutableSet, MutableMapping, MutableSequence",
                          result.state["diff"].value)
            self.assertEqual(len(result.state["site_runs"].value), 1)
            self.assertEqual(path.read_text(encoding="utf-8"), source)

    def test_include_scope_skips_unrelated_unparseable_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package = root / "package"
            package.mkdir()
            (package / "module.py").write_text("from collections import Mapping\n", encoding="utf-8")
            (root / "old_example.py").write_text("print 'Python 2'\n", encoding="utf-8")
            full = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(full.status, "needs_mediation")
            scoped = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test"),
                                               "includes": Evidence(["package"], "test")})
            self.assertEqual(scoped.status, "completed")
            self.assertEqual(set(scoped.state["updated"].value), {"package/module.py"})

    def test_repeated_qualified_abc_uses_share_verified_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.py"
            source = (
                "import collections\n"
                "class Example(collections.MutableMapping):\n"
                "    def __getitem__(self, key): return 1\n"
                "    def __setitem__(self, key, value): pass\n"
                "    def __delitem__(self, key): pass\n"
                "    def __iter__(self): return iter(())\n"
                "    def __len__(self): return 0\n"
                "mapping_ok = isinstance({}, collections.Mapping)\n"
                "callable_ok = isinstance(lambda: 1, collections.Callable)\n"
            )
            path.write_text(source, encoding="utf-8")
            result = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(result.status, "completed")
            self.assertEqual(len(result.state["proposals"].value), 4)
            self.assertEqual(len(result.state["site_runs"].value), 4)
            self.assertTrue(all(len(site["events"]) == 2 and site["status"] == "completed"
                                for site in result.state["site_runs"].value))
            updated = result.state["updated"].value["example.py"]
            self.assertIn("import collections.abc\n", updated)
            self.assertIn("collections.abc.MutableMapping", updated)
            self.assertIn("collections.abc.Mapping", updated)
            self.assertIn("collections.abc.Callable", updated)
            self.assertEqual(path.read_text(encoding="utf-8"), source)

    def test_shadowed_collections_stops_before_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.py"
            path.write_text(
                "import collections\ndef f(collections):\n    return collections.Mapping\n", encoding="utf-8"
            )
            result = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(result.status, "needs_mediation")
            self.assertEqual(len(result.state["gaps"].value), 1)
            self.assertEqual(result.state["diff"].value, "")

    def test_site_graph_rejects_unverified_binding(self) -> None:
        source = "import collections\nvalue = collections.Mapping\n"
        from hashlib import sha256
        inputs = {
            "file": Evidence("example.py", "test"),
            "source_text": Evidence(source, "test"),
            "source_sha256": Evidence(sha256(source.encode()).hexdigest(), "test"),
            "line": Evidence(2, "test"),
            "before": Evidence("value = collections.Mapping\n", "test"),
            "after": Evidence("value = collections.abc.Mapping\n", "test"),
            "operation": Evidence("rewrite_qualified_abc", "test"),
            "binding_verified": Evidence(False, "test"),
        }
        result = execute(SITE_MOTIF, inputs)
        self.assertEqual(result.status, "needs_mediation")
        self.assertEqual(result.gap.kind, "ambiguous_binding")
        self.assertNotIn("proposal", result.state)

    def test_two_attributes_on_one_line_stop_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "example.py"
            path.write_text(
                "import collections\nok = collections.Mapping and collections.Callable\n", encoding="utf-8"
            )
            result = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(result.status, "needs_mediation")
            self.assertEqual(result.gap.kind, "ambiguous_migration")
            self.assertEqual(len(result.state["gaps"].value), 1)

    def test_verified_preview_passes_in_copied_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as sandbox:
            root = Path(temp)
            source = root / "module.py"
            source.write_text("from collections import Mapping\nvalue = isinstance({}, Mapping)\n", encoding="utf-8")
            (root / "test_module.py").write_text(
                "import unittest\nimport module\nclass Tests(unittest.TestCase):\n"
                "    def test_mapping(self): self.assertTrue(module.value)\n", encoding="utf-8"
            )
            preview = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(preview.status, "completed")
            initial = {key: preview.state[key] for key in ("root", "files", "updated", "ready")}
            initial["sandbox_root"] = Evidence(sandbox, "test")
            initial["test_argv"] = Evidence([sys.executable, "-m", "unittest", "discover", "-q"], "test")
            verified = execute(VERIFY_MOTIF, initial)
            self.assertEqual(verified.status, "completed")
            self.assertEqual(verified.state["test_result"].value["exit_code"], 0)
            self.assertIn("from collections import Mapping", source.read_text(encoding="utf-8"))
            initial["test_argv"] = Evidence([sys.executable, "-c", "import sys; sys.exit(3)"], "test")
            failed = execute(VERIFY_MOTIF, initial)
            self.assertEqual(failed.status, "needs_mediation")
            self.assertEqual(failed.gap.kind, "tests_failed")
            self.assertEqual(failed.state["test_result"].value["exit_code"], 3)

    def test_failed_test_can_select_one_safe_alias_and_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as sandbox:
            root = Path(temp)
            (root / "module.py").write_text(
                "from collections import Sequence\nok = issubclass(list, Sequence)\n", encoding="utf-8"
            )
            (root / "unused.py").write_text("from collections import Iterable\n", encoding="utf-8")
            (root / "test_module.py").write_text(
                "import unittest\nimport module\nclass Tests(unittest.TestCase):\n"
                "    def test_sequence(self): self.assertTrue(module.ok)\n", encoding="utf-8"
            )
            initial = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            self.assertEqual(initial.status, "completed")
            self.assertEqual(initial.state["proposals"].value, [])
            state = {key: initial.state[key] for key in ("root", "files", "updated", "ready")}
            state["sandbox_root"] = Evidence(sandbox, "test")
            state["test_argv"] = Evidence([sys.executable, "-m", "unittest", "discover", "-q"], "test")
            failed = execute(VERIFY_MOTIF, state)
            self.assertEqual(failed.gap.kind, "tests_failed")
            checkout = Path(failed.state["staged_path"].value)
            candidates = discover_extra_abc_candidates(checkout)
            self.assertEqual({item["alias"] for item in candidates}, {"Sequence", "Iterable"})
            prompt = prepare_migration_selection(failed, candidates)
            self.assertIn("candidate_ids", prompt)
            chosen_id = next(item["id"] for item in candidates if item["alias"] == "Sequence")
            chosen = parse_migration_selection(
                json.dumps({"candidate_ids": [chosen_id], "diagnosis": "Missing ABC alias", "uncertainties": []}),
                candidates,
            )["selected"]
            with self.assertRaises(ValueError):
                parse_migration_selection('{"candidate_ids":["C99"],"diagnosis":"x","uncertainties":[]}', candidates)
            recovery = execute(MIGRATION_MOTIF, {
                "root": Evidence(str(checkout), "test"),
                "aliases": Evidence(["Sequence"], "validated_selection"),
                "selected_sites": Evidence([{key: item[key] for key in ("file", "line", "alias")} for item in chosen],
                                           "validated_selection"),
            })
            self.assertEqual(recovery.status, "completed")
            self.assertEqual(len(recovery.state["proposals"].value), 1)
            self.assertEqual(set(recovery.state["updated"].value), {"module.py"})
            retry_state = {key: recovery.state[key] for key in ("root", "files", "updated", "ready")}
            retry_state["sandbox_root"] = Evidence(sandbox, "test")
            retry_state["test_argv"] = state["test_argv"]
            retried = execute(VERIFY_MOTIF, retry_state)
            self.assertEqual(retried.status, "completed")
            self.assertIn("from collections import Sequence", (root / "module.py").read_text())

    def test_extra_alias_reuses_existing_abc_import(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = "import collections\nimport collections.abc\nok = isinstance([], collections.Sequence)\n"
            (Path(temp) / "module.py").write_text(source, encoding="utf-8")
            result = execute(MIGRATION_MOTIF, {
                "root": Evidence(temp, "test"),
                "aliases": Evidence(["Sequence"], "test"),
                "selected_sites": Evidence([{"file": "module.py", "line": 3, "alias": "Sequence"}], "test"),
            })
            self.assertEqual(result.status, "completed")
            self.assertEqual(len(result.state["proposals"].value), 1)
            self.assertIn("collections.abc.Sequence", result.state["updated"].value["module.py"])

    def test_unrelated_failure_has_no_abc_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as sandbox:
            root = Path(temp)
            (root / "test_unrelated.py").write_text(
                "import unittest\nclass Tests(unittest.TestCase):\n"
                "    def test_unrelated(self): self.assertTrue(False)\n", encoding="utf-8"
            )
            preview = execute(MIGRATION_MOTIF, {"root": Evidence(temp, "test")})
            state = {key: preview.state[key] for key in ("root", "files", "updated", "ready")}
            state["sandbox_root"] = Evidence(sandbox, "test")
            state["test_argv"] = Evidence([sys.executable, "-m", "unittest", "discover", "-q"], "test")
            failed = execute(VERIFY_MOTIF, state)
            self.assertEqual(failed.gap.kind, "tests_failed")
            self.assertEqual(discover_extra_abc_candidates(Path(failed.state["staged_path"].value)), [])


class ResearchTests(unittest.TestCase):
    def test_simple_point_baseline_has_same_obligations_without_point_routing(self) -> None:
        points = [{"id": "gate", "requirement": "Only success enters memory"},
                  {"id": "update", "requirement": "Memory updates after each task"}]
        evidence = [{"source": "paper.txt", "page": 4, "source_sha256": "a" * 64,
                     "snippet": "Only successful experiences enter memory after each task."}]
        prompt, citations = prepare_simple_point_prompt("How?", points, evidence)
        self.assertIn('"id":"gate"', prompt)
        self.assertIn('"id":"update"', prompt)
        self.assertEqual(list(citations), ["E1"])
        self.assertIn("All points may use the same retrieved evidence pool", prompt)

    def test_point_selection_rejects_cross_point_evidence(self) -> None:
        points = [{"id": "gate", "requirement": "Only success enters memory"},
                  {"id": "update", "requirement": "Memory updates after task"}]
        candidates = {
            "C1": {"point_id": "gate", "evidence": {"source": "paper.txt", "page": 4,
                                                     "snippet": "Only successful experiences are admitted."}},
            "C2": {"point_id": "update", "evidence": {"source": "paper.txt", "page": 4,
                                                       "snippet": "Memory is updated after each task."}},
        }
        self.assertIn("C1", prepare_point_selection("How?", points, candidates))
        valid = {"selections": [{"point_id": "gate", "evidence_id": "C1"},
                                {"point_id": "update", "evidence_id": "C2"}]}
        self.assertEqual(parse_point_selection(json.dumps(valid), points, candidates),
                         {"gate": ["C1"], "update": ["C2"]})
        invalid = {"selections": [{"point_id": "gate", "evidence_id": "C2"},
                                  {"point_id": "update", "evidence_id": "C1"}]}
        with self.assertRaises(ValueError):
            parse_point_selection(json.dumps(invalid), points, candidates)

    def test_same_page_selection_alias_is_audited_without_changing_page(self) -> None:
        points = [{"id": "context", "requirement": "History compression"},
                  {"id": "edit", "requirement": "Editor feedback"}]
        shared = {"source": "paper.pdf", "page": 4, "source_sha256": "a" * 64,
                  "snippet": "The page contains context management and editing."}
        candidates = {
            "context-C1": {"point_id": "context", "evidence": shared},
            "edit-C1": {"point_id": "edit", "evidence": shared},
        }
        raw = json.dumps({"selections": [
            {"point_id": "context", "evidence_id": "edit-C1"},
            {"point_id": "edit", "evidence_id": "edit-C1"},
        ]})
        with self.assertRaises(ValueError):
            parse_point_selection(raw, points, candidates)
        chosen, changes = repair_same_page_selection_aliases(raw, points, candidates)
        self.assertEqual(chosen, {"context": ["context-C1"], "edit": ["edit-C1"]})
        self.assertEqual(changes[0]["normalized_id"], "context-C1")
        candidates["context-C1"]["evidence"] = {**shared, "page": 3}
        with self.assertRaises(ValueError):
            repair_same_page_selection_aliases(raw, points, candidates)

    def test_point_selection_exposes_late_condition_in_top_window(self) -> None:
        points = [{"id": "update", "requirement": "New memory serves the next task"}]
        snippet = "section heading " + "filler " * 80 + "the updated memory serves the next task"
        candidates = {"C1": {"point_id": "update", "evidence": {
            "source": "paper.txt", "page": 4, "snippet": snippet,
        }}}
        prompt = prepare_point_selection("When?", points, candidates)
        self.assertIn("the updated memory serves the next task", prompt)

    def test_comparison_requires_two_independent_sources_and_packages_both(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "first.txt").write_text("Method Alpha uses visual descriptors to retrieve a pose.",
                                             encoding="utf-8")
            (root / "second.txt").write_text("Method Beta refines a pose by Gaussian rendering.",
                                              encoding="utf-8")
            source_run = execute(SOURCE_MOTIF, {"source_dir": Evidence(temp, "test")})
            pages = source_run.state["unique_pages"].value
            candidates = {
                "compare-C1": {"point_id": "compare", "evidence": {
                    **{key: pages[0][key] for key in ("source", "page", "source_sha256", "page_sha256")},
                    "snippet": "Method Alpha uses visual descriptors to retrieve a pose."}},
                "compare-C2": {"point_id": "compare", "evidence": {
                    **{key: pages[1][key] for key in ("source", "page", "source_sha256", "page_sha256")},
                    "snippet": "Method Beta refines a pose by Gaussian rendering."}},
            }
            points = [{"id": "compare", "requirement": "Compare Alpha and Beta methods",
                       "min_sources": 2}]
            one = {"selections": [{"point_id": "compare", "evidence_ids": ["compare-C1"]}]}
            with self.assertRaisesRegex(ValueError, "independent sources"):
                parse_point_selection(json.dumps(one), points, candidates)
            two = {"selections": [{"point_id": "compare",
                                   "evidence_ids": ["compare-C1", "compare-C2"]}]}
            selected_ids = parse_point_selection(json.dumps(two), points, candidates)
            self.assertEqual(selected_ids["compare"], ["compare-C1", "compare-C2"])
            selected = {"compare": [candidates[key]["evidence"] for key in selected_ids["compare"]]}
            packaged = execute(POINT_PAGE_PASSAGES_MOTIF, {
                "validated_answer_points": Evidence(points, "test"),
                "selected_evidence_by_point": Evidence(selected, "test"),
                "unique_pages": source_run.state["unique_pages"],
                "source_dir": source_run.state["source_dir"],
            })
            self.assertEqual(packaged.status, "completed")
            self.assertEqual({row["source"] for row in packaged.state["point_passages"].value["compare"]},
                             {"first.txt", "second.txt"})
            prompt, _, _ = prepare_point_synthesis(
                "How do the methods differ?", points, packaged.state["point_passages"].value)
            self.assertIn("Method Alpha", prompt)
            self.assertIn("Method Beta", prompt)

    def test_point_synthesis_rejects_cross_point_quote(self) -> None:
        points = [{"id": "gate", "requirement": "Only success enters memory"},
                  {"id": "update", "requirement": "Memory updates after task"}]
        selected = {
            "gate": {"source": "paper.txt", "page": 4, "source_sha256": "a" * 64,
                     "snippet": "Only successful experiences are admitted to memory."},
            "update": {"source": "paper.txt", "page": 4, "source_sha256": "a" * 64,
                       "snippet": "Memory is updated after each task completes."},
        }
        prompt, citations, scope = prepare_point_synthesis(
            "How?", points, {key: [value] for key, value in selected.items()})
        self.assertIn("Only successful experiences", prompt)
        self.assertEqual(scope, {"gate": {"E1"}, "update": {"E2"}})
        response = json.dumps({"claims": [{"point_id": "gate", "text": "Memory updates after tasks.",
                                         "supports": [{"evidence_id": "E2",
                                                       "quote": "Memory is updated after each task completes"}]}],
                               "uncertainties": []})
        claims, _, rejected = _parse_response(response, citations,
                                              point_ids={"gate", "update"}, point_citations=scope)
        self.assertEqual(claims, [])
        self.assertIn("cross-point evidence citation", rejected[0]["reason"])

        reused, _, rejected = _parse_response(
            response, citations, point_ids={"gate", "update"},
            point_citations=scope, allow_cross_point_reuse=True)
        self.assertEqual(len(reused), 1)
        self.assertEqual(rejected, [])

    def test_point_synthesis_accepts_five_verified_numeric_supports(self) -> None:
        citations = {f"E{index}": {"snippet": f"Metric {index} total equals {index * 10} across records."}
                     for index in range(1, 6)}
        raw = json.dumps({"claims": [{"point_id": "numeric", "text": "Five measured totals are listed.",
                                       "supports": [{"evidence_id": key, "quote": row["snippet"]}
                                                    for key, row in citations.items()]}],
                          "uncertainties": []})
        claims, _, rejected = _parse_response(
            raw, citations, point_ids={"numeric"},
            point_citations={"numeric": set(citations)})
        self.assertEqual(len(claims), 1)
        self.assertEqual(rejected, [])

    def test_point_passage_motif_reuses_multiple_verified_spans_on_same_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "paper.txt"
            source.write_text(
                "A fine-grained subtask becomes reusable. " + "filler " * 100
                + "A concrete product becomes a {product-name} placeholder. "
                + "filler " * 100 + "After each task, the memory is updated for the next task.",
                encoding="utf-8",
            )
            pages = execute(SOURCE_MOTIF, {"source_dir": Evidence(temp, "test")})
            selected = {}
            for point_id, terms in (
                ("abstract", ["fine-grained", "placeholder"]),
                ("update", ["memory is updated", "next task"]),
            ):
                run = execute(RETRIEVE_MOTIF, {
                    "unique_pages": pages.state["unique_pages"],
                    "source_dir": pages.state["source_dir"],
                    "question": Evidence(point_id, "test"),
                    "terms": Evidence(terms, "test"),
                })
                selected[point_id] = run.state["verified_evidence"].value[0]
            points = [{"id": "abstract", "requirement": "Subtask and placeholder"},
                      {"id": "update", "requirement": "Memory updated for next task"}]
            packaged = execute(POINT_PAGE_PASSAGES_MOTIF, {
                "validated_answer_points": Evidence(points, "test"),
                "selected_evidence_by_point": Evidence(selected, "test"),
                "unique_pages": pages.state["unique_pages"],
                "source_dir": pages.state["source_dir"],
            })
            self.assertEqual(packaged.status, "completed")
            passages = packaged.state["point_passages"].value
            self.assertEqual(passages["abstract"], passages["update"])
            self.assertGreater(len(passages["abstract"]), 1)
            combined = "".join(row["snippet"] for row in passages["abstract"])
            self.assertIn("fine-grained subtask", combined)
            self.assertIn("{product-name} placeholder", combined)
            self.assertIn("memory is updated for the next task", combined)
            prompt, citations, scope = prepare_point_synthesis("How?", points, passages)
            self.assertLess(len(prompt), 16_000)
            self.assertEqual(scope["abstract"], scope["update"])
            self.assertEqual(len(citations), len(passages["abstract"]))
            selected["update"] = {**selected["update"], "source_sha256": "wrong"}
            stale = execute(POINT_PAGE_PASSAGES_MOTIF, {
                "validated_answer_points": Evidence(points, "test"),
                "selected_evidence_by_point": Evidence(selected, "test"),
                "unique_pages": pages.state["unique_pages"],
                "source_dir": pages.state["source_dir"],
            })
            self.assertEqual(stale.gap.kind, "citation_mismatch")

    def test_two_answer_points_retrieve_different_windows_on_same_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "paper.txt").write_text(
                "Online admission uses a binary success evaluator before workflow induction. "
                + "irrelevant filler " * 90
                + "The memory is updated after the task and helps the next task.",
                encoding="utf-8",
            )
            sources = execute(SOURCE_MOTIF, {"source_dir": Evidence(temp, "test")})
            passages = []
            for requirement, terms in (
                ("What is the admission gate?", ["binary success", "workflow induction"]),
                ("When is memory updated?", ["memory is updated", "next task"]),
            ):
                run = execute(RETRIEVE_MOTIF, {
                    "unique_pages": sources.state["unique_pages"],
                    "source_dir": sources.state["source_dir"],
                    "question": Evidence(requirement, "test"),
                    "terms": Evidence(terms, "test"),
                })
                self.assertEqual(run.gap.kind, "semantic_synthesis")
                passages.append(run.state["verified_evidence"].value[0]["snippet"])
            self.assertNotEqual(passages[0], passages[1])
            self.assertIn("binary success evaluator", passages[0])
            self.assertIn("memory is updated", passages[1])

    def test_seven_point_answer_can_have_nine_narrow_claims(self) -> None:
        citations = {"E1": {"source": "paper.txt", "page": 1,
                            "snippet": "A source sentence supports a narrow research claim."}}
        raw = json.dumps({"claims": [
            {"point_id": "point", "text": f"Narrow claim {index}",
             "supports": [{"evidence_id": "E1", "quote": "A source sentence supports a narrow research claim"}]}
            for index in range(9)
        ], "uncertainties": []})
        accepted, _, rejected = _parse_response(raw, citations, point_ids={"point"})
        self.assertEqual(len(accepted), 9)
        self.assertEqual(rejected, [])

    def test_compound_point_can_use_four_verified_quotes(self) -> None:
        citations = {"E1": {"snippet": "First, locate suspicious files. Then, inspect relevant functions. "
                                       "Next, generate candidate patches. Finally, run regression tests."}}
        quotes = ["locate suspicious files", "inspect relevant functions",
                  "generate candidate patches", "run regression tests"]
        raw = json.dumps({"claims": [{"point_id": "process", "text": "Four supported stages",
                                        "supports": [{"evidence_id": "E1", "quote": quote} for quote in quotes]}],
                          "uncertainties": []})
        claims, _, rejected = _parse_response(raw, citations, point_ids={"process"})
        self.assertEqual(len(claims), 1)
        self.assertEqual(len(claims[0]["supports"]), 4)
        self.assertEqual(rejected, [])

    def test_retrieval_window_sent_to_synthesis_keeps_matched_condition(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            phrase = "For erroneous tool invocations add a tool chain with negative frequency"
            (Path(temp) / "paper.txt").write_text("background " * 90 + phrase + " more detail " * 40,
                                                  encoding="utf-8")
            sources = execute(SOURCE_MOTIF, {"source_dir": Evidence(temp, "test")})
            retrieved = execute(RETRIEVE_MOTIF, {
                "unique_pages": sources.state["unique_pages"],
                "source_dir": sources.state["source_dir"],
                "question": Evidence("How is the erroneous path recorded?", "test"),
                "terms": Evidence(["erroneous", "negative frequency"], "test"),
            })
            self.assertEqual(retrieved.gap.kind, "semantic_synthesis")
            snippet = retrieved.state["verified_evidence"].value[0]["snippet"]
            self.assertLessEqual(len(snippet), 750)
            self.assertIn(phrase, snippet)

    def test_repair_query_keeps_exact_partial_phrase_from_source(self) -> None:
        pages = [{"source": "paper.txt", "page": 1,
                  "text": "A recovery path forces a check after two consecutive erroneous calls."}]
        terms, _ = ground_repair_terms(
            ["two consecutive tool errors effective check", "recovery after tool errors"],
            pages, ["paper.txt"],
        )
        self.assertIn("two consecutive", terms)

    def test_local_repair_is_scoped_to_missing_points_and_verified_quotes(self) -> None:
        queries = parse_repair_queries(json.dumps({"queries": [
            {"point_id": "gap", "terms": ["negative frequency", "ToolPath"]},
        ]}), {"gap"})
        self.assertEqual(queries[0]["terms"], ["negative frequency", "ToolPath"])
        with self.assertRaises(ValueError):
            parse_repair_queries(json.dumps({"queries": [
                {"point_id": "other", "terms": ["negative frequency", "ToolPath"]},
            ]}), {"gap"})
        citations = {"R1": {"source": "paper.txt", "page": 2,
                            "source_sha256": "hash", "snippet": "An erroneous chain has negative frequency."}}
        prompt = prepare_repair_answer("What happens after an error?", [
            {"id": "gap", "requirement": "Explain negative path frequency"}], citations)
        self.assertIn("negative frequency", prompt)
        raw = json.dumps({"claims": [{"point_id": "gap", "text": "Erroneous paths receive negative frequency",
                                      "supports": [{"evidence_id": "R1",
                                                    "quote": "erroneous chain has negative frequency"}]}],
                          "uncertainties": []})
        repair_claims, repair_uncertainties, rejected = _parse_response(raw, citations, point_ids={"gap"})
        self.assertEqual(rejected, [])
        merged = execute(RESEARCH_REPAIR_MERGE_MOTIF, {
            "validated_answer_points": Evidence([
                {"id": "old", "requirement": "Explain the existing route"},
                {"id": "gap", "requirement": "Explain negative path frequency"}], "test"),
            "missing_ids": Evidence(["gap"], "test"),
            "original_claims": Evidence([{"point_id": "old", "text": "Old route", "supports": [
                {"evidence_id": "E1", "quote": "Existing route is reused"}]},
                {"point_id": "gap", "text": "Incomplete old claim", "supports": [
                    {"evidence_id": "E1", "quote": "Existing route is reused"}]}], "test"),
            "original_citations": Evidence({"E1": {"source": "paper.txt", "page": 1,
                                                "snippet": "Existing route is reused"}}, "test"),
            "repair_claims": Evidence(repair_claims, "test"),
            "repair_citations": Evidence(citations, "test"),
            "repair_uncertainties": Evidence(repair_uncertainties, "test"),
        })
        self.assertEqual(merged.status, "completed")
        self.assertEqual([item["text"] for item in merged.state["merged_claims"].value],
                         ["Old route", "Erroneous paths receive negative frequency"])
        coverage = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": Evidence([
                {"id": "old", "requirement": "Explain the existing route"},
                {"id": "gap", "requirement": "Explain negative path frequency"}], "test"),
            "claims": merged.state["merged_claims"],
            "citations": merged.state["merged_citations"],
            "uncertainties": merged.state["merged_uncertainties"],
        })
        self.assertEqual(coverage.status, "completed")

    def test_question_obligation_requires_validated_cited_claim(self) -> None:
        points = [{"id": "order", "requirement": "Explain parameter source priority"},
                  {"id": "fallback", "requirement": "Explain fallback after failure"}]
        preflight = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
            "answer_points": Evidence(points, "test"),
        })
        self.assertEqual(preflight.status, "completed")
        repeated = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
            "answer_points": Evidence([points[0], points[0]], "test"),
        })
        self.assertEqual(repeated.gap.kind, "invalid_answer_points")
        citations = {"E1": {"source": "paper.txt", "page": 1,
                            "snippet": "Dependency backtracking is tried first. Environment matching follows."}}
        raw = json.dumps({"claims": [{"point_id": "order", "text": "Dependency backtracking is first",
                                      "supports": [{"evidence_id": "E1",
                                                    "quote": "Dependency backtracking is tried first"}]}],
                          "uncertainties": [{"point_id": "fallback", "text": "fallback is not covered",
                                             "blocks_requirement": True}]})
        claims, _, rejected = _parse_response(raw, citations, point_ids={"order", "fallback"})
        self.assertEqual(rejected, [])
        run = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": preflight.state["validated_answer_points"],
            "citations": Evidence(citations, "test"),
            "claims": Evidence(claims, "test"),
            "uncertainties": Evidence([], "test"),
        })
        self.assertEqual(run.gap.kind, "incomplete_answer")
        self.assertEqual([row["id"] for row in run.state["point_coverage"].value
                          if row["status"] == "missing_cited_claim"], ["fallback"])
        bad_raw = raw.replace('"point_id": "order"', '"point_id": "unknown"')
        accepted, _, rejected = _parse_response(bad_raw, citations, point_ids={"order", "fallback"})
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)
        supported_fallback = {"point_id": "fallback", "text": "The agent falls back to the LLM",
                              "supports": [{"evidence_id": "E2", "quote": "fallback to an LLM call"}]}
        cited = {**citations, "E2": {"source": "paper.txt", "page": 2,
                                   "snippet": "Failure triggers fallback to an LLM call."}}
        complete = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": preflight.state["validated_answer_points"],
            "citations": Evidence(cited, "test"),
            "claims": Evidence([*claims, supported_fallback], "test"),
            "uncertainties": Evidence([], "test"),
        })
        self.assertEqual(complete.status, "completed")
        admitted_gap = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": preflight.state["validated_answer_points"],
            "citations": Evidence(cited, "test"),
            "claims": Evidence([*claims, supported_fallback], "test"),
            "uncertainties": Evidence([{"point_id": "fallback", "text": "one detail is still unclear",
                                        "blocks_requirement": True}], "test"),
        })
        self.assertEqual(admitted_gap.gap.kind, "incomplete_answer")
        self.assertEqual(admitted_gap.state["point_coverage"].value[1]["status"], "explicit_uncertainty")
        optional_detail = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": preflight.state["validated_answer_points"],
            "citations": Evidence(cited, "test"),
            "claims": Evidence([*claims, supported_fallback], "test"),
            "uncertainties": Evidence([{"point_id": "fallback", "text": "an unasked detail is unknown",
                                        "blocks_requirement": False}], "test"),
        })
        self.assertEqual(optional_detail.status, "completed")

    def test_declared_abstention_is_pending_review_not_missing_answer(self) -> None:
        points = [{"id": "identity", "requirement": "Identify the plotted run, or leave it open if unsupported",
                   "allow_abstention": True}]
        preflight = execute(ANSWER_POINT_PREFLIGHT_MOTIF, {
            "answer_points": Evidence(points, "test"),
        })
        self.assertEqual(preflight.status, "completed")
        citations = {"E1": {"source": "paper.txt", "page": 1,
                            "snippet": "Figure 7 shows algorithm results."}}
        uncertain = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": preflight.state["validated_answer_points"],
            "citations": Evidence(citations, "test"),
            "claims": Evidence([], "test"),
            "uncertainties": Evidence([{"point_id": "identity",
                                        "text": "The plotted run identity is absent from this page.",
                                        "blocks_requirement": True}], "test"),
        })
        self.assertEqual(uncertain.status, "completed")
        self.assertEqual(uncertain.state["point_coverage"].value[0]["status"],
                         "abstention_pending_review")
        missing = execute(QUESTION_COVERAGE_MOTIF, {
            "validated_answer_points": preflight.state["validated_answer_points"],
            "citations": Evidence(citations, "test"),
            "claims": Evidence([], "test"),
            "uncertainties": Evidence([], "test"),
        })
        self.assertEqual(missing.gap.kind, "incomplete_answer")

    def test_comparison_coverage_needs_quotes_from_two_sources(self) -> None:
        points = [{"id": "methods", "requirement": "Compare two recent methods", "min_sources": 2}]
        citations = {
            "E1": {"source": "alpha.txt", "page": 1, "snippet": "Alpha retrieves a camera pose."},
            "E2": {"source": "beta.txt", "page": 1, "snippet": "Beta refines a camera pose."},
        }
        first = {"point_id": "methods", "text": "Alpha retrieves a pose", "supports": [
            {"evidence_id": "E1", "quote": "Alpha retrieves a camera pose"}]}
        second = {"point_id": "methods", "text": "Beta refines a pose", "supports": [
            {"evidence_id": "E2", "quote": "Beta refines a camera pose"}]}
        inputs = {"validated_answer_points": Evidence(points, "test"),
                  "citations": Evidence(citations, "test"),
                  "claims": Evidence([first], "test"),
                  "uncertainties": Evidence([], "test")}
        incomplete = execute(QUESTION_COVERAGE_MOTIF, inputs)
        self.assertEqual(incomplete.gap.kind, "incomplete_answer")
        self.assertEqual(incomplete.state["point_coverage"].value[0]["status"], "insufficient_sources")
        inputs["claims"] = Evidence([first, second], "test")
        complete = execute(QUESTION_COVERAGE_MOTIF, inputs)
        self.assertEqual(complete.status, "completed")
        self.assertEqual(complete.state["point_coverage"].value[0]["cited_sources"],
                         ["alpha.txt", "beta.txt"])

    def test_required_answer_point_needs_a_matching_cited_claim(self) -> None:
        contract = [{"id": "validation", "source": "paper.txt", "page": 2,
                     "anchors": ["ValidateRepair checks the result against support evidence"]}]
        citations = {"E1": {"source": "paper.txt", "page": 2},
                     "E2": {"source": "other.txt", "page": 1}}
        inputs = {"contract": Evidence(contract, "test"),
                  "citations": Evidence(citations, "test"),
                  "claims": Evidence([{"text": "A different point", "supports": [
                      {"evidence_id": "E2", "quote": contract[0]["anchors"][0]}]}], "test")}
        missing = execute(ANSWER_COVERAGE_MOTIF, inputs)
        self.assertEqual(missing.gap.kind, "incomplete_answer")
        self.assertEqual(missing.state["answer_coverage"].value[0]["status"], "missing_claim_quote")
        inputs["claims"] = Evidence([{"text": "The result is validated", "supports": [
            {"evidence_id": "E1", "quote": "checks the result against support evidence"}]}], "test")
        covered = execute(ANSWER_COVERAGE_MOTIF, inputs)
        self.assertEqual(covered.status, "completed")
        self.assertEqual(covered.state["answer_coverage"].value[0]["status"], "cited_in_claim")

    def test_required_evidence_is_in_final_excerpt_or_stops(self) -> None:
        page = {
            "source": "paper.txt", "page": 1,
            "text": "Introduction. " + "background " * 100
                    + "Only frequent, closed, and executable fragments are materialized. "
                    + "Further explanation. " * 20,
            "page_sha256": "fixed-page-hash",
        }
        selected = {"source": "paper.txt", "page": 1,
                    "snippet": page["text"][:750], "source_sha256": "fixed-source-hash"}
        contract = [{"id": "acceptance", "source": "paper.txt", "page": 1,
                     "anchors": ["Only frequent, closed, and executable fragments"]}]
        inputs = {"unique_pages": Evidence([page], "test"),
                  "selected_evidence": Evidence([selected], "test"),
                  "contract": Evidence(contract, "test")}
        run = execute(EVIDENCE_CONTRACT_MOTIF, inputs)
        self.assertEqual(run.status, "completed")
        excerpt = run.state["grounded_evidence"].value[0]["snippet"]
        self.assertLessEqual(len(excerpt), 750)
        self.assertIn(contract[0]["anchors"][0], excerpt)
        self.assertEqual(run.state["coverage_checks"].value[0]["status"], "included_in_excerpt")
        inputs["selected_evidence"] = Evidence([], "test")
        missing = execute(EVIDENCE_CONTRACT_MOTIF, inputs)
        self.assertEqual(missing.gap.kind, "missing_required_evidence")
        inputs["selected_evidence"] = Evidence([selected], "test")
        inputs["contract"] = Evidence([{**contract[0], "anchors": ["nonexistent passage"]}], "test")
        absent = execute(EVIDENCE_CONTRACT_MOTIF, inputs)
        self.assertEqual(absent.gap.kind, "missing_required_evidence")

    def test_distant_same_page_anchors_use_distinct_verified_passages(self) -> None:
        first = "Positive motifs use successful traces"
        second = "ValidateRepair checks support evidence"
        page = {"source": "paper.txt", "page": 3,
                "text": first + " background " * 120 + second,
                "page_sha256": "page-hash"}
        selected = {"source": "paper.txt", "page": 3,
                    "snippet": page["text"][:750], "source_sha256": "source-hash"}
        contract = [{"id": "origin", "source": "paper.txt", "page": 3, "anchors": [first]},
                    {"id": "validation", "source": "paper.txt", "page": 3, "anchors": [second]}]
        run = execute(EVIDENCE_CONTRACT_MOTIF, {
            "unique_pages": Evidence([page], "test"),
            "selected_evidence": Evidence([selected], "test"),
            "contract": Evidence(contract, "test"),
        })
        self.assertEqual(run.status, "completed")
        evidence = run.state["grounded_evidence"].value[0]
        self.assertEqual(len(evidence["passages"]), 2)
        self.assertIn(first, evidence["snippet"])
        self.assertIn(second, evidence["snippet"])
        self.assertLessEqual(len(evidence["snippet"]), 750)
        joined_quote = f"{first} [... omitted ...] {second}"
        raw = json.dumps({"claims": [{"text": "Unsupported joined citation", "supports": [
            {"evidence_id": "E1", "quote": joined_quote}]}], "uncertainties": []})
        accepted, _, rejected = _parse_response(raw, {"E1": evidence})
        self.assertEqual(accepted, [])
        self.assertEqual(len(rejected), 1)

    def test_multistep_plan_reuses_verified_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "one.txt").write_text(
                "A motif runs verified tool operations. A missing parameter requires semantic mediation.",
                encoding="utf-8",
            )
            (Path(temp) / "two.txt").write_text(
                "A reusable fragment carries support and provenance. A failed guard stops execution.",
                encoding="utf-8",
            )
            sources = execute(SOURCE_MOTIF, {"source_dir": Evidence(temp, "test")})
            self.assertEqual(sources.status, "completed")
            plan_prompt = prepare_research_plan("When may a motif run and when should it stop?",
                                                sources.state["unique_pages"].value)
            self.assertIn("source catalog", plan_prompt.casefold())
            plan = parse_research_plan(json.dumps({"subquestions": [
                {"question": "Which verified tool operations may run?", "terms": ["motif", "verified"]},
                {"question": "What evidence supports stopping?", "terms": ["failed", "guard"]},
            ]}))
            with self.assertRaises(ValueError):
                parse_research_plan('{"subquestions":[{"question":"only one","terms":["a"]}]}')
            with self.assertRaises(ValueError):
                parse_research_plan(json.dumps({"subquestions": [
                    {"question": "Which verified operations may run?", "terms": ["guard", "fallback"]},
                    {"question": "What happens after execution fails?", "terms": ["fallback", "guard"]},
                ]}))
            subresults = []
            for item in plan:
                run = execute(RETRIEVE_MOTIF, {
                    "unique_pages": sources.state["unique_pages"],
                    "source_dir": sources.state["source_dir"],
                    "question": Evidence(item["question"], "test"),
                    "terms": Evidence(item["terms"], "test"),
                })
                self.assertEqual(run.gap.kind, "semantic_synthesis")
                subresults.append({"question": item["question"], "status": "evidence_verified",
                                   "evidence": run.state["verified_evidence"].value})
            prompt, citations = prepare_deep_synthesis("When may a motif run and when should it stop?", subresults)
            self.assertEqual({row["source"] for row in citations.values()}, {"one.txt", "two.txt"})
            self.assertIn("Coverage ledger", prompt)
            selection_prompt, candidates = prepare_evidence_selection("When may a motif run?", subresults)
            self.assertIn("Q1E1", selection_prompt)
            selected = parse_evidence_selection(json.dumps({"selections": [
                {"question_id": "Q1", "evidence_ids": ["Q1E1"]},
                {"question_id": "Q2", "evidence_ids": ["Q2E1"]},
            ]}), candidates, 2)
            self.assertEqual(selected, [["Q1E1"], ["Q2E1"]])
            with self.assertRaises(ValueError):
                parse_evidence_selection(json.dumps({"selections": [
                    {"question_id": "Q1", "evidence_ids": ["Q2E1"]},
                    {"question_id": "Q2", "evidence_ids": ["Q2E1"]},
                ]}), candidates, 2)

    def test_planned_terms_are_grounded_in_scoped_source(self) -> None:
        pages = [{"source": "method.txt", "text": "Parameter filling uses a dependency graph and fallback."},
                 {"source": "other.txt", "text": "Completely unrelated text."}]
        terms, changes = ground_query_terms(["parameter clarity", "failure fallback"], pages, ["method.txt"])
        self.assertEqual(terms, ["parameter", "fallback"])
        self.assertEqual(len(changes), 2)
        with self.assertRaises(Exception):
            ground_query_terms(["invented mystery"], pages, ["method.txt"])

    def test_semantic_quote_must_exist_in_selected_evidence(self) -> None:
        citations = {"E1": {"snippet": "The runtime executes verified parameter flow before asking the model."}}
        valid = json.dumps({"claims": [{"text": "The runtime executes parameter flow.", "supports": [{"evidence_id": "E1", "quote": "runtime executes verified parameter flow"}]}], "uncertainties": []})
        claims, _, rejected = _parse_response(valid, citations)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["supports"][0]["evidence_id"], "E1")
        self.assertEqual(rejected, [])
        invalid = valid.replace("runtime executes verified parameter flow", "the model executes everything")
        claims, uncertainties, rejected = _parse_response(invalid, citations)
        self.assertEqual(claims, [])
        self.assertEqual(len(rejected), 1)
        self.assertTrue(uncertainties)

    def test_quote_check_tolerates_pdf_spacing_loss(self) -> None:
        citations = {"E1": {"snippet": "Astructural operationruns when current evidence is sufficient."}}
        response = json.dumps({"claims": [{"text": "Structure needs evidence.", "supports": [{"evidence_id": "E1", "quote": "A structural operation runs when current evidence is sufficient"}]}], "uncertainties": []})
        claims, _, rejected = _parse_response(response, citations)
        self.assertEqual(len(claims), 1)
        self.assertEqual(len(claims[0]["supports"]), 1)
        self.assertEqual(rejected, [])

    def test_verified_evidence_stops_at_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "source.txt").write_text(
                "A runtime can verify a tool result before advancing the next graph node. "
                "An ambiguous result requires semantic mediation.", encoding="utf-8"
            )
            result = execute(RESEARCH_MOTIF, {
                "source_dir": Evidence(temp, "test"),
                "terms": Evidence(["runtime", "semantic"], "test"),
                "question": Evidence("When is mediation needed?", "test"),
            })
            self.assertEqual(result.status, "needs_mediation")
            self.assertEqual(result.gap.kind, "semantic_synthesis")
            self.assertEqual(result.state["verified_evidence"].value[0]["source"], "source.txt")


if __name__ == "__main__":
    unittest.main()
