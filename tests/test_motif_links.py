"""Cross-Motif links must be learned from traces and remain evidence scoped."""

import json
import tempfile
import unittest
from pathlib import Path

from src.adapters.dsh_trajectory import DshTrace, ToolContract, ToolRecord
from src.motif_core.controller import MotifController
from src.motif_core.handoff import SemanticResolution
from src.motif_core.offline.library_builder import (
    _digest, build_read_motif_library, library_from_certified,
)
from src.motif_core.offline.link_compiler import compile_read_links


CONTRACTS = {
    "search": ToolContract(("query",), True, ("id",)),
    "read": ToolContract(("doc_id",), True, ("text",)),
    "extract": ToolContract(("text",), True, ("section",)),
    "summarize": ToolContract(("section",), True, ("summary",)),
}


def trace(label, *, valid_bridge=True):
    identifier = label.upper()
    rows = (
        ToolRecord("search", {"query": label}, "s", True, "eligible_read", 1,
                   {"id": identifier}),
        ToolRecord("read", {"doc_id": identifier}, "r", True, "eligible_read", 2,
                   {"text": f"text-{identifier}"},
                   {"doc_id": {"from_tool": "search", "from_field": "id"}}),
        ToolRecord("extract", {"text": f"text-{identifier}"}, "e", True,
                   "eligible_read", 3, {"section": f"section-{identifier}"},
                   {"text": {"from_tool": "read", "from_field": "text"}}
                   if valid_bridge else None),
        ToolRecord("summarize", {"section": f"section-{identifier}"}, "m", True,
                   "eligible_read", 4, {"summary": f"summary-{identifier}"},
                   {"section": {"from_tool": "extract", "from_field": "section"}}),
    )
    return DshTrace(label, rows, (("search", "read", "extract", "summarize"),),
                    f"independent-task-{label}")


def projected_library():
    training = [trace("a"), trace("b")]
    heldout = [trace("c")]
    full = build_read_motif_library(training, heldout, CONTRACTS)
    left = next(row for row in full["artifacts"]
                if row["tools"] == ["search", "read"])
    right = next(row for row in full["artifacts"]
                 if row["tools"] == ["extract", "summarize"])
    links = compile_read_links(training, heldout, [left, right], CONTRACTS)
    library = library_from_certified([left, right])
    library["links"] = links
    library["library_digest"] = _digest({key: value for key, value in library.items()
                                         if key != "library_digest"})
    return library, training, left, right


def three_motif_library(*, style_gap=False):
    contracts = {**CONTRACTS,
                 "verify": ToolContract(("summary",), True, ("checked",)),
                 "pack": ToolContract(("checked",), True, ("package",))}
    if style_gap:
        contracts["summarize"] = ToolContract(("section", "style"), True,
                                               ("summary",))

    def long_trace(label):
        base = trace(label)
        identifier = label.upper()
        initial = list(base.records)
        if style_gap:
            old = initial[3]
            initial[3] = ToolRecord(
                old.name, {**old.arguments, "style": "brief"},
                old.observation_sha256, old.eligible, old.reason, old.event_seq,
                old.observation, old.parameter_sources)
        tail = (
            ToolRecord("verify", {"summary": f"summary-{identifier}"}, "v",
                       True, "eligible_read", 5,
                       {"checked": f"checked-{identifier}"},
                       {"summary": {"from_tool": "summarize",
                                    "from_field": "summary"}}),
            ToolRecord("pack", {"checked": f"checked-{identifier}"}, "p",
                       True, "eligible_read", 6,
                       {"package": f"package-{identifier}"},
                       {"checked": {"from_tool": "verify",
                                    "from_field": "checked"}}),
        )
        return DshTrace(label, tuple(initial) + tail,
                        (("search", "read", "extract", "summarize",
                          "verify", "pack"),), base.task_fingerprint)

    training = [long_trace("a"), long_trace("b")]
    heldout = [long_trace("c")]
    full = build_read_motif_library(training, heldout, contracts)
    pairs = (["search", "read"], ["extract", "summarize"],
             ["verify", "pack"])
    artifacts = [next(row for row in full["artifacts"] if row["tools"] == pair)
                 for pair in pairs]
    library = library_from_certified(artifacts)
    library["links"] = compile_read_links(training, heldout, artifacts, contracts)
    library["library_digest"] = _digest({key: value for key, value in library.items()
                                         if key != "library_digest"})
    return library, contracts


class MotifLinkTests(unittest.TestCase):
    def test_graph_handoff_replays_after_restart_only_with_same_evidence(self):
        library, contracts = three_motif_library(style_gap=True)

        def tool_result(tool, _params):
            return {"search": {"id": "N"}, "read": {"text": "text-N"},
                    "extract": {"section": "section-N"},
                    "summarize": {"summary": "summary-N"},
                    "verify": {"checked": "checked-N"},
                    "pack": {"package": "package-N"}}[tool]

        first = MotifController(
            library, contracts=contracts, execute_tool=tool_result,
            verify_current=lambda: None, is_read_only=lambda _: True)
        gap = first.execute_goal(required_output="pack",
                                 bindings={"search": {"query": "new"}}, input_version="v1")
        self.assertEqual(gap.status, "needs_mediation")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "read-graph-checkpoint.json"
            path.write_text(json.dumps(first.export_replay_checkpoint()), encoding="utf-8")
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
        calls = []
        restored = MotifController(
            library, contracts=contracts,
            execute_tool=lambda tool, params: (calls.append(tool) or tool_result(tool, params)),
            verify_current=lambda: None, is_read_only=lambda _: True)
        resumed_gap = restored.replay_checkpoint(checkpoint, current_input_version="v1")
        self.assertEqual(resumed_gap.status, "needs_mediation")
        self.assertEqual(calls, ["search", "read", "extract"])
        done = restored.resume_slots(SemanticResolution(
            resolution_type="slot_fill", slot_values={"summarize": {"style": "brief"}},
            metadata={"handoff_signature": _digest(resumed_gap.handoff.to_dict())}))
        self.assertEqual(done.status, "completed")
        self.assertEqual(calls, ["search", "read", "extract", "summarize", "verify", "pack"])

        changed = MotifController(
            library, contracts=contracts, execute_tool=tool_result,
            verify_current=lambda: None, is_read_only=lambda _: True)
        with self.assertRaisesRegex(ValueError, "stale or invalid"):
            changed.replay_checkpoint(checkpoint, current_input_version="v2")
        altered = json.loads(json.dumps(checkpoint))
        altered["bindings"]["search"]["query"] = "other"
        with self.assertRaisesRegex(ValueError, "stale or invalid"):
            changed.replay_checkpoint(altered, current_input_version="v1")
        drifted = MotifController(
            library, contracts=contracts,
            execute_tool=lambda tool, params: ({"section": "section-M"}
                                               if tool == "extract" else tool_result(tool, params)),
            verify_current=lambda: None, is_read_only=lambda _: True)
        with self.assertRaisesRegex(ValueError, "no longer reaches"):
            drifted.replay_checkpoint(checkpoint, current_input_version="v1")
        self.assertIsNone(drifted.pending_plan)
        self.assertIsNone(drifted.last)

    def test_intermediate_gap_reenters_graph_and_continues(self):
        library, contracts = three_motif_library(style_gap=True)
        calls = []

        def execute(tool, params):
            calls.append(tool)
            return {"search": {"id": "N"}, "read": {"text": "text-N"},
                    "extract": {"section": "section-N"},
                    "summarize": {"summary": "summary-N"},
                    "verify": {"checked": "checked-N"},
                    "pack": {"package": "package-N"}}[tool]

        controller = MotifController(
            library, contracts=contracts, execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        gap = controller.execute_goal(
            required_output="pack", bindings={"search": {"query": "new"}},
            input_version="v1")
        self.assertEqual(gap.status, "needs_mediation")
        self.assertEqual(calls, ["search", "read", "extract"])
        done = controller.resume_slots(SemanticResolution(
            resolution_type="slot_fill",
            slot_values={"summarize": {"style": "brief"}},
            metadata={"handoff_signature": _digest(gap.handoff.to_dict())}))
        self.assertEqual(done.status, "completed")
        self.assertEqual(calls, ["search", "read", "extract", "summarize",
                                 "verify", "pack"])
        self.assertEqual(sum(row["event"] == "certified_motif_link_applied"
                             for row in done.events), 2)

    def test_changed_completed_observation_cannot_reenter_old_gap(self):
        library, contracts = three_motif_library(style_gap=True)
        results = {"search": {"id": "N"}, "read": {"text": "text-N"},
                   "extract": {"section": "section-N"},
                   "summarize": {"summary": "summary-N"},
                   "verify": {"checked": "checked-N"},
                   "pack": {"package": "package-N"}}
        controller = MotifController(
            library, contracts=contracts,
            execute_tool=lambda tool, _params: dict(results[tool]),
            verify_current=lambda: None, is_read_only=lambda _: True)
        gap = controller.execute_goal(required_output="pack",
                                      bindings={"search": {"query": "new"}},
                                      input_version="v1")
        self.assertEqual(gap.status, "needs_mediation")
        gap.run.outputs["extract"]["section"] = "changed-after-handoff"
        with self.assertRaisesRegex(ValueError, "cannot reenter"):
            controller.resume_slots(SemanticResolution(
                resolution_type="slot_fill",
                slot_values={"summarize": {"style": "brief"}},
                metadata={"handoff_signature": _digest(gap.handoff.to_dict())}))

    def test_branching_graph_joins_two_verified_sources(self):
        contracts = {
            "search": ToolContract(("query",), True, ("id",)),
            "read": ToolContract(("doc_id",), True, ("text",)),
            "extract": ToolContract(("text",), True, ("section",)),
            "summarize": ToolContract(("section",), True, ("summary",)),
            "classify": ToolContract(("text",), True, ("class",)),
            "tag": ToolContract(("class",), True, ("label",)),
            "merge": ToolContract(("summary", "label"), True, ("merged",)),
            "pack": ToolContract(("merged",), True, ("package",)),
        }
        names = ("search", "read", "extract", "summarize", "classify",
                 "tag", "merge", "pack")

        def branch_trace(label):
            identifier = label.upper()
            values = {
                "search": ({"query": label}, {"id": identifier}, None),
                "read": ({"doc_id": identifier}, {"text": f"text-{identifier}"},
                         {"doc_id": {"from_tool": "search", "from_field": "id"}}),
                "extract": ({"text": f"text-{identifier}"},
                            {"section": f"section-{identifier}"},
                            {"text": {"from_tool": "read", "from_field": "text"}}),
                "summarize": ({"section": f"section-{identifier}"},
                              {"summary": f"summary-{identifier}"},
                              {"section": {"from_tool": "extract",
                                           "from_field": "section"}}),
                "classify": ({"text": f"text-{identifier}"},
                             {"class": f"class-{identifier}"},
                             {"text": {"from_tool": "read", "from_field": "text"}}),
                "tag": ({"class": f"class-{identifier}"},
                        {"label": f"label-{identifier}"},
                        {"class": {"from_tool": "classify",
                                   "from_field": "class"}}),
                "merge": ({"summary": f"summary-{identifier}",
                           "label": f"label-{identifier}"},
                          {"merged": f"merged-{identifier}"},
                          {"summary": {"from_tool": "summarize",
                                       "from_field": "summary"},
                           "label": {"from_tool": "tag", "from_field": "label"}}),
                "pack": ({"merged": f"merged-{identifier}"},
                         {"package": f"package-{identifier}"},
                         {"merged": {"from_tool": "merge",
                                     "from_field": "merged"}}),
            }
            rows = tuple(ToolRecord(name, values[name][0], name, True,
                                    "eligible_read", index,
                                    values[name][1], values[name][2])
                         for index, name in enumerate(names, 1))
            return DshTrace(label, rows, (names,), f"task-{label}")

        training = [branch_trace("a"), branch_trace("b")]
        heldout = [branch_trace("c")]
        full = build_read_motif_library(training, heldout, contracts)
        pairs = [("search", "read"), ("extract", "summarize"),
                 ("classify", "tag"), ("merge", "pack")]
        artifacts = [next(row for row in full["artifacts"]
                          if tuple(row["tools"]) == pair) for pair in pairs]
        library = library_from_certified(artifacts)
        library["links"] = compile_read_links(training, heldout, artifacts,
                                             contracts)
        self.assertEqual(len(library["links"]), 4)
        library["library_digest"] = _digest({key: value for key, value in library.items()
                                             if key != "library_digest"})
        calls = []

        def execute(tool, params):
            calls.append((tool, dict(params)))
            return {name: branch_trace("n").records[index].observation
                    for index, name in enumerate(names)}[tool]

        controller = MotifController(
            library, contracts=contracts, execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        result = controller.execute_goal(
            required_output="pack", bindings={"search": {"query": "n"}},
            input_version="v1")
        self.assertEqual(result.status, "completed")
        self.assertEqual([name for name, _ in calls], list(names))
        self.assertEqual(calls[-2][1], {"summary": "summary-N",
                                        "label": "label-N"})

    def test_three_motif_graph_executes_without_a_hop_limit(self):
        library, contracts = three_motif_library()
        self.assertEqual(len(library["links"]), 2)
        calls = []

        def execute(tool, params):
            calls.append(tool)
            return {"search": {"id": "N"}, "read": {"text": "text-N"},
                    "extract": {"section": "section-N"},
                    "summarize": {"summary": "summary-N"},
                    "verify": {"checked": "checked-N"},
                    "pack": {"package": "package-N"}}[tool]

        controller = MotifController(
            library, contracts=contracts, execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        result = controller.execute_goal(
            required_output="pack", bindings={"search": {"query": "new"}},
            input_version="v1")
        self.assertEqual(result.status, "completed")
        self.assertEqual(calls, ["search", "read", "extract", "summarize",
                                 "verify", "pack"])
        self.assertEqual(sum(row["event"] == "certified_motif_link_applied"
                             for row in result.events), 2)

    def test_certified_link_runs_predecessor_then_target(self):
        library, _, _, _ = projected_library()
        self.assertEqual(len(library["links"]), 1)
        calls = []

        def execute(tool, params):
            calls.append((tool, dict(params)))
            return {"search": {"id": "N"},
                    "read": {"text": "text-N"},
                    "extract": {"section": "section-N"},
                    "summarize": {"summary": "summary-N"}}[tool]

        controller = MotifController(
            library, contracts=CONTRACTS, execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        done = controller.execute_goal(
            required_output="summarize", bindings={"search": {"query": "new"}},
            input_version="v1")
        self.assertEqual(done.status, "completed")
        self.assertEqual(calls, [
            ("search", {"query": "new"}), ("read", {"doc_id": "N"}),
            ("extract", {"text": "text-N"}),
            ("summarize", {"section": "section-N"})])
        self.assertIn("certified_motif_link_applied",
                      [row["event"] for row in done.events])

    def test_link_reentry_after_missing_predecessor_slot(self):
        library, _, _, _ = projected_library()
        calls = []

        def execute(tool, params):
            calls.append(tool)
            return {"search": {"id": "N"}, "read": {"text": "text-N"},
                    "extract": {"section": "section-N"},
                    "summarize": {"summary": "summary-N"}}[tool]

        controller = MotifController(
            library, contracts=CONTRACTS, execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        gap = controller.execute_linked_goal(
            required_output="summarize", bindings={}, input_version="v1")
        self.assertEqual(gap.status, "needs_mediation")
        self.assertEqual(calls, [])
        done = controller.resume_slots(SemanticResolution(
            resolution_type="slot_fill", slot_values={"search": {"query": "new"}},
            metadata={"handoff_signature": _digest(gap.handoff.to_dict())}))
        self.assertEqual(done.status, "completed")
        self.assertEqual(calls, ["search", "read", "extract", "summarize"])

    def test_missing_heldout_provenance_rejects_link(self):
        library, training, left, right = projected_library()
        self.assertEqual(len(library["links"]), 1)
        rejected = compile_read_links(training, [trace("c", valid_bridge=False)],
                                      [left, right], CONTRACTS)
        self.assertEqual(rejected, [])

    def test_unknown_action_between_motifs_is_a_barrier(self):
        library, training, left, right = projected_library()
        original = trace("c")
        barrier = ToolRecord("unknown", {}, None, False, "unapproved_tool", 3)
        heldout = DshTrace("c-with-barrier",
                           original.records[:2] + (barrier,) + original.records[2:],
                           (("search", "read"), ("extract", "summarize")),
                           "independent-task-c-with-barrier")
        self.assertEqual(compile_read_links(training, [heldout],
                                            [left, right], CONTRACTS), [])

    def test_current_predecessor_output_missing_stops_successor(self):
        library, _, _, _ = projected_library()
        calls = []

        def execute(tool, params):
            calls.append(tool)
            return {"search": {"id": "N"}, "read": {"different": "text-N"}}[tool]

        controller = MotifController(
            library, contracts=CONTRACTS, execute_tool=execute,
            verify_current=lambda: None, is_read_only=lambda _: True)
        result = controller.execute_goal(
            required_output="summarize", bindings={"search": {"query": "new"}},
            input_version="v1")
        self.assertEqual(result.status, "blocked")
        self.assertEqual(calls, ["search", "read"])

    def test_tampered_link_is_rejected_before_any_tool_call(self):
        library, _, _, _ = projected_library()
        library["links"][0]["from_field"] = "invented"
        library["library_digest"] = _digest({key: value for key, value in library.items()
                                             if key != "library_digest"})
        with self.assertRaisesRegex(ValueError, "link"):
            MotifController(library, contracts=CONTRACTS,
                            execute_tool=lambda *_: self.fail("ran a tool"),
                            verify_current=lambda: None,
                            is_read_only=lambda _: True)


if __name__ == "__main__":
    unittest.main()
