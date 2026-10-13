"""科学元组与独立证据边界回归；合成反例只作工程检查，不作科研效果证据。"""
import copy
import json
import unittest

from scenarios.research_ppt.evidence import SCHEMA_PATH, source_snapshot, validate_scientific_evidence


SOURCE = "a" * 64
TEXT = "🙂\nFigure 5. xformers latency 122 ms on A100, batch 1. FA2 latency 85 ms."
QUOTE = "xformers latency 122 ms on A100, batch 1."


def fixture(panel=False):
    start = TEXT.index(QUOTE)
    claim = {"claim_id": "latency-1", "source_id": "source-test", "version_sha256": SOURCE,
             "page": 5, "span": {"start": start, "end": start + len(QUOTE), "quote": QUOTE},
             "result": {"value": "122", "method": "xformers", "metric": "latency", "unit": "ms",
                        "condition": {"hardware": "A100", "batch": "1"}}, "fact_id": "reviewed-latency"}
    sources = {"source-test": {"version_sha256": SOURCE, "pages": [{"page": 5, "text": TEXT}]}}
    if panel:
        claim["panel"] = "Figure 5/right"
        sources["source-test"]["panels"] = [{"page": 5, "panel": "Figure 5/right", "complete": True}]
    fact = {key: copy.deepcopy(value) for key, value in claim.items() if key not in {"claim_id", "fact_id"}}
    fact["review"] = {"kind": "human_direct_result", "reviewed_by": "engineering-fixture-reviewer",
                      "reviewed_at": "2026-10-12"}
    return {"schema_version": 1, "claims": [claim]}, sources, {"reviewed-latency": fact}


def codes(report):
    return {row["code"] for row in report["diagnostics"]} | {
        row["code"] for check in report["checks"] for row in check["diagnostics"]}


class EvidenceTests(unittest.TestCase):
    def test_literal_quote_even_with_number_is_unknown_without_independent_tuple(self):
        sidecar, sources, _ = fixture()
        report = validate_scientific_evidence(sidecar, sources)
        self.assertEqual(report["status"], "unknown")
        self.assertTrue(report["mechanical_passed"])
        self.assertFalse(report["passed"])
        self.assertFalse(report["scientific_quality_certified"])
        self.assertIn("independent_fact_missing", codes(report))

    def test_independently_reviewed_exact_direct_tuple_passes_limited_scope(self):
        sidecar, sources, facts = fixture(panel=True)
        report = validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["passed"])
        self.assertFalse(report["scientific_quality_certified"])
        self.assertIn("not_semantic_support", report["scope"])

    def test_valid_quote_cannot_authorize_wrong_method_metric_value_or_unit(self):
        for field, wrong in (("method", "FA2"), ("metric", "throughput"), ("value", "155"), ("unit", "TFLOPS")):
            with self.subTest(field=field):
                sidecar, sources, facts = fixture()
                sidecar["claims"][0]["result"][field] = wrong
                report = validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
                self.assertEqual(report["status"], "fail")
                self.assertIn("reviewed_result_mismatch", codes(report))

    def test_missing_shot_condition_is_not_inferred_from_quote(self):
        sidecar, sources, facts = fixture()
        facts["reviewed-latency"]["result"]["condition"]["shot"] = "5"
        report = validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(d["field"] == "result.condition" for d in report["checks"][0]["diagnostics"]))

    def test_empty_or_wrong_type_conditions_rejected_not_filled(self):
        for condition in ({}, "5-shot", {"shot": 5}, {"hardware": None}, {"hardware": "  "}):
            with self.subTest(condition=condition):
                sidecar, sources, facts = fixture()
                sidecar["claims"][0]["result"]["condition"] = condition
                self.assertEqual(validate_scientific_evidence(sidecar, sources, trusted_facts=facts)["status"], "fail")

    def test_source_version_page_and_authorization_fail_independently(self):
        for field, wrong, code in (("version_sha256", "b" * 64, "source_version_changed"),
                                   ("page", 4, "source_page_unavailable"),
                                   ("source_id", "source-not-approved", "source_not_authorized")):
            with self.subTest(field=field):
                sidecar, sources, facts = fixture()
                sidecar["claims"][0][field] = wrong
                report = validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
                self.assertEqual(report["status"], "fail")
                self.assertIn(code, codes(report))

    def test_unicode_span_uses_codepoints_and_rejects_utf16_shift(self):
        sidecar, sources, facts = fixture()
        self.assertEqual(validate_scientific_evidence(sidecar, sources, trusted_facts=facts)["status"], "pass")
        sidecar["claims"][0]["span"]["start"] += 1
        sidecar["claims"][0]["span"]["end"] += 1
        report = validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
        self.assertIn("source_span_mismatch", codes(report))

    def test_duplicate_quote_is_bound_by_position_not_first_matching_string(self):
        sidecar, sources, facts = fixture()
        original = sources["source-test"]["pages"][0]["text"]
        sources["source-test"]["pages"][0]["text"] = original + "\n" + QUOTE
        claim = sidecar["claims"][0]
        claim["span"]["start"] = len(original) + 1
        claim["span"]["end"] = claim["span"]["start"] + len(QUOTE)
        report = validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
        self.assertEqual(report["status"], "fail")
        self.assertIn("reviewed_source_binding_mismatch", codes(report))
        self.assertNotIn("source_span_mismatch", codes(report))

    def test_panel_missing_unknown_and_known_truncated_panel_fails(self):
        sidecar, sources, facts = fixture(panel=True)
        sources["source-test"]["panels"] = []
        self.assertEqual(validate_scientific_evidence(sidecar, sources, trusted_facts=facts)["status"], "unknown")
        sources["source-test"]["panels"] = [{"page": 5, "panel": "Figure 5/right", "complete": False}]
        report = validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
        self.assertEqual(report["status"], "fail")
        self.assertIn("panel_incomplete", codes(report))

    def test_agent_self_review_is_rejected_and_unreviewed_host_fact_unknown(self):
        sidecar, sources, facts = fixture()
        facts["reviewed-latency"]["review"] = {"kind": "model_generated", "reviewed_by": "agent", "reviewed_at": "now"}
        self.assertEqual(validate_scientific_evidence(sidecar, sources, trusted_facts=facts)["status"], "unknown")
        sidecar["claims"][0]["review"] = {"kind": "human_direct_result", "reviewed_by": "fake"}
        self.assertEqual(validate_scientific_evidence(sidecar, sources)["status"], "fail")

    def test_absent_empty_and_malformed_evidence_do_not_pass(self):
        self.assertEqual(validate_scientific_evidence(None, {})["status"], "unknown")
        self.assertEqual(validate_scientific_evidence({"schema_version": 1, "claims": []}, {})["status"], "unknown")
        sidecar, sources, _ = fixture()
        for wrong in (True, 1.0, 2):
            with self.subTest(version=wrong):
                changed = copy.deepcopy(sidecar)
                changed["schema_version"] = wrong
                self.assertEqual(validate_scientific_evidence(changed, sources)["status"], "fail")

    def test_duplicate_claim_and_bool_page_rejected(self):
        sidecar, sources, facts = fixture()
        sidecar["claims"].append(copy.deepcopy(sidecar["claims"][0]))
        self.assertIn("duplicate_claim_id", codes(validate_scientific_evidence(sidecar, sources, trusted_facts=facts)))
        sidecar["claims"] = [sidecar["claims"][0]]
        sidecar["claims"][0]["page"] = True
        self.assertEqual(validate_scientific_evidence(sidecar, sources, trusted_facts=facts)["status"], "fail")

    def test_host_projection_only_includes_read_sources_and_is_a_copy(self):
        handles = {"read": {"read": True, "row": {"version_sha256": SOURCE},
                            "parsed": {"pages": [{"page": 1, "text": "source"}]}},
                   "not-read": {"read": False}}
        projected = source_snapshot(handles)
        self.assertEqual(set(projected), {"read"})
        projected["read"]["pages"][0]["text"] = "changed"
        self.assertEqual(handles["read"]["parsed"]["pages"][0]["text"], "source")

    def test_no_argument_mutation_and_schema_available(self):
        sidecar, sources, facts = fixture()
        before = copy.deepcopy((sidecar, sources, facts))
        validate_scientific_evidence(sidecar, sources, trusted_facts=facts)
        self.assertEqual((sidecar, sources, facts), before)
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["$defs"]["claim"]["properties"]["span"]["$ref"], "#/$defs/span")


if __name__ == "__main__":
    unittest.main()
