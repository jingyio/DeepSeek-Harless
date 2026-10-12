"""Independent read-only v3 audit: raw API/MCP -> semantic receipts -> PDF.

No runner, tools, compiler or model calls are imported/executed. Only --output
is written. Scientific/visual review is a separate, hash-bound input, never
inferred from keywords or from a successful tool. --reviews may be omitted;
then delivered reports remain unreviewed rather than being called qualified.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

from evidence_io import (EvidenceRun, PREFIX, USAGE, canonical, digest, file_sha, read,
                         jsonlines, tool_rows, differences)
from recompute_statistics import recompute, numeric_differences

TOKEN = re.compile(r"\{\{([A-Za-z_][A-Za-z_0-9]*)\}\}")
REVIEW_CHECKS = ("design_and_method", "numeric_and_uncertainty_meaning", "unsupported_claims",
                 "figure_choice_and_consistency", "discussion_and_tradeoffs", "visual_readability")
FIGURES = {"independent_groups": {"distribution_ci", "group_ecdf", "effect_interval"},
           "paired": {"paired_change", "change_distribution", "effect_interval"},
           "regression": {"scatter_fit", "residuals", "effect_interval"}}


def formatting_issues(binding, figure_count):
    """Independent bounds check for logged format exemptions, never prose QA.

    Only exact label/ordinal strings may be removed from token-free source.
    The remaining text must have no unbound Arabic scientific numbers.
    Older calibration receipts predate this additional metadata.
    """
    if "formatting_references" not in binding:
        return []
    issues = []
    remaining = TOKEN.sub("", binding["template"])
    for reference in binding["formatting_references"]:
        raw = reference.get("text")
        if not isinstance(raw, str) or raw not in remaining or reference.get("passed") is not True:
            issues.append("Format exemption does not identify an actual accepted source substring")
            continue
        if reference.get("kind") == "figure_reference":
            match = re.fullmatch(r"(?:图|Figure\b|Fig\.)\s*(\d+(?:\s*[/／、,]\s*\d+)*)", raw, re.I)
            numbers = [int(n) for n in re.findall(r"\d+", raw)]
            if not match or numbers != reference.get("labels") or any(not 1 <= n <= figure_count for n in numbers) or reference.get("validated_against_actual_figure_count") != figure_count:
                issues.append("Figure reference does not match actual one-based figure labels")
        elif reference.get("kind") == "list_ordinal":
            number = reference.get("ordinal")
            sequence = reference.get("sequence", [])
            marker = re.fullmatch(r"[（(]\d{1,2}[）)]|\s*\d{1,2}[)）、]|\s*\d{1,2}\.\s+", raw)
            position = remaining.index(raw)
            consecutive = len(sequence) >= 2 and sequence == list(range(1, len(sequence) + 1))
            leading = len(sequence) == 1 and not remaining[:position].strip()
            if not marker or not isinstance(number, int) or not 1 <= number <= 99 or re.findall(r"\d+", raw) != [str(number)] or number not in sequence or not (consecutive or leading):
                issues.append("List ordinal is neither a bounded leading marker nor a consecutive list")
        else:
            issues.append("Unknown format exemption kind")
        remaining = remaining.replace(raw, " " * len(raw), 1)
    if re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?[%％]?", remaining):
        issues.append("Unbound numeric literal remains outside tokens and formatting labels")
    return issues


def semantic_argument_comparison(submitted, received, properties, required):
    """MCP binds declared top-level function parameters, sometimes dropping
    extra top-level keys. Expose that fact; never filter nested semantic text,
    add defaults, coerce types, or silently rewrite the model's decision.
    """
    if not isinstance(submitted, dict) or not isinstance(received, dict):
        return {"exact_match": submitted == received, "declared_parameters_match": False, "ignored_top_level": {}}
    declared = {k: v for k, v in submitted.items() if k in properties}
    extras = {k: v for k, v in submitted.items() if k not in properties}
    match = bool(properties) and all(k in submitted for k in required) and declared == received
    return {"exact_match": submitted == received, "declared_parameters_match": match,
            "ignored_top_level": extras if match else {}, "differences": differences(submitted, received)}


def prose_characters(submitted):
    if not isinstance(submitted, dict):
        return None
    sections = submitted.get("sections")
    body = [p for s in sections if isinstance(s, dict) for p in (s.get("paragraphs") or []) if isinstance(p, str)] if isinstance(sections, list) else []
    options = submitted.get("research_options")
    additions = [v for option in options if isinstance(option, dict) for k, v in option.items()
                 if k in {"name", "rationale", "tradeoff"} and isinstance(v, str)] if isinstance(options, list) else []
    if isinstance(submitted.get("comparison_summary"), str):
        additions.append(submitted["comparison_summary"])
    return {"section_paragraph_characters": sum(map(len, body)), "section_paragraphs": len(body),
            "research_option_characters": sum(map(len, additions)), "full_prose_characters": sum(map(len, body + additions)),
            "measurement": "Literal submitted text length including placeholder syntax; not a token estimate."}


def tool_outcome_counts(rows):
    """Classify observed outcomes without treating DSH events as wire captures.

    Malformed model JSON is an input property, not proof the call stopped before
    MCP. A harness can substitute an empty argument object and still receive a
    server-side schema error. Keep that count separate from outcome categories.
    """
    counts = Counter({key: 0 for key in ("successful_executions", "business_rejections",
                     "schema_error_results", "other_failed_attempts", "malformed_json_arguments")})
    for row in rows:
        if isinstance(row.get("arguments"), str):
            try:
                json.loads(row["arguments"])
            except (ValueError, TypeError):
                counts["malformed_json_arguments"] += 1
        if row.get("success") is True:
            counts["successful_executions"] += 1
        elif isinstance(row.get("output"), dict) and row["output"].get("ok") is False:
            counts["business_rejections"] += 1
        elif any("validation error" in text and "Arguments" in text for text in row.get("result_text", [])):
            counts["schema_error_results"] += 1
        else:
            counts["other_failed_attempts"] += 1
    return dict(counts)


class AuditRun(EvidenceRun):
    def run(self):
        self.result.update(evidence_passed=False, business_delivered=False, report=None,
                           selection=None, writing=None, statistics_review=None)
        try:
            self._run()
        except Exception as error:
            self.check(False, "Cannot finish run audit", error=f"{type(error).__name__}: {error}")
        self.result.update(evidence_passed=not self.errors, checks=self.check_count)
        return self.result

    def _run(self):
        self.manifest, self.metrics = read(self.path / "manifest.json"), read(self.path / "metrics.json")
        m = self.manifest
        self.result.update(manifest=m, metrics=self.metrics, mode=m["mode"], run_id=m["run_id"],
                           case_id=m["case_id"], repeat_id=m.get("repeat_id", 1))
        self.original_run = str(m["intake"]["data_root"]).replace("\\", "/").removesuffix("/sources")
        scenario = read(self.path / "scenario.json")
        workspace = scenario["servers"][0]["env"]["RRA_RUN_ROOT"]
        self.workspace_id = "workspace-" + hashlib.sha256(workspace.encode()).hexdigest()[:24]
        self.result["scenario_scoped_paths"] = self.normalize_runtime(scenario)
        self.source_hashes = {}
        for item in m["source_files"]:
            path = self.local(item["path"])
            self.source_hashes[path.name] = file_sha(path)
            self.check(self.source_hashes[path.name] == item["sha256"], "Frozen source byte mismatch", source=path.name)
        self.source_version = digest(self.source_hashes)
        self.result["source_sha256"] = self.source_hashes
        self.check(self.source_version == m.get("input_content_digest"), "Source content digest mismatch")
        self.check(digest(m["source_files"]) == m.get("input_sha256"), "Source manifest digest mismatch")
        self.check(m.get("benchmark_version") == 3 and m.get("comparison_protocol") == "free_presentation_and_narrative", "Not a v3 free-semantic run")
        self.check(m.get("semantic_barriers") == ["approve_analysis", "approve_presentation", "submit_report_text"], "Three declared semantic barriers missing or changed")
        self.check(m.get("mode") == self.job.get("mode", "baseline"), "Matrix mode mismatch")
        self.check(m.get("case_id") == self.job.get("case", m["case_id"]), "Matrix case mismatch")
        self.study = read(self.path / "sources" / "cases" / m["case_id"] / "study.json")
        self.check("benchmark_frozen_decisions" not in self.study, "Frozen decisions are prohibited in v3")
        self.rows = tool_rows(jsonlines(self.path / "agent-events.jsonl"))
        self.check(len({r["call_id"] for r in self.rows}) == len(self.rows), "Duplicate tool call IDs")
        self.audit_rows = jsonlines(self.path / "motif-audit.jsonl")
        self.result["motif_audit"] = self.audit_rows
        self._requests()
        self._calls()
        self._semantic_activity()
        self._layouts()
        self.result["event_file_sha256"] = file_sha(self.path / "agent-events.jsonl")
        accounting = self.result["accounting"]
        accounting.update(upstream_requests=accounting["llm_requests"], tool_calls=accounting["mcp_calls"],
                          verified_motif_bypasses=accounting["verified_bypasses"], tool_failure_count=accounting["tool_failures"])
        accounting["tool_outcomes"] = tool_outcome_counts(self.rows)
        accounting["tool_count_scope"] = ("tool_calls/mcp_calls are DSH MCP-tool invocation attempts, not transport packet counts. "
            "Successful executions have verified output receipts. Malformed model JSON is not by itself proof of a pre-MCP termination; "
            "schema-error results and explicit business rejections are reported separately.")
        deliveries = [r for r in self.rows if r["tool"] == PREFIX + "deliver_report"]
        self.result["delivery_attempts"] = [{"step": r["step"], "success": r["success"], "output": r["output"]} for r in deliveries]
        accepted = [r for r in deliveries if r["success"] and (r["output"] or {}).get("delivered") is True]
        if accepted:
            final = accepted[-1]
            self.result["business_delivered"] = (deliveries[-1] is final and self.metrics.get("status") == "done"
                and self.metrics.get("delivered") is True and self.metrics.get("report_quality_passed") is True)
            self.check(final["output"] == self.metrics.get("delivery"), "Actual final delivery differs from metrics")
            self._final(final)
        self.result["business_failure"] = None if self.result["business_delivered"] else {
            "status": self.metrics.get("status"), "finish_reason": self.metrics.get("finish_reason"), "last_deliver_successful": bool(accepted)}

    def _semantic_activity(self):
        requests = {r["request_id"]: r for r in self.result["requests"]}
        attempts = []
        for row in self.rows:
            name = row["tool"].removeprefix(PREFIX)
            if name not in {"approve_analysis", "approve_presentation", "submit_report_text"}:
                continue
            req = requests.get(row.get("request_id"), {})
            args = row["arguments"]
            attempts.append({"step": row["step"], "tool": name, "call_id": row["call_id"], "request_id": row.get("request_id"),
                "success": row["success"], "origin": row["origin"], "request_usage": req.get("usage"),
                "request_peak_estimate_cny": req.get("peak_estimate_cny"),
                "prose": prose_characters(args.get("report_text")) if name == "submit_report_text" and isinstance(args, dict) else None,
                "failure_output": row.get("output") if not row["success"] else None,
                "failure_text": row.get("result_text") if not row["success"] else None})
        by_tool = {}
        for name in ("approve_analysis", "approve_presentation", "submit_report_text"):
            selected = [r for r in attempts if r["tool"] == name]
            rids = {r["request_id"] for r in selected if r["request_id"] in requests}
            by_tool[name] = {"attempts": len(selected), "successes": sum(r["success"] for r in selected),
                "failures": sum(not r["success"] for r in selected), "distinct_requests": len(rids),
                "request_usage": dict(sum((Counter({k: requests[rid]["usage"].get(k, 0) for k in USAGE}) for rid in rids), Counter())),
                "request_peak_estimate_cny": sum(requests[rid]["peak_estimate_cny"] for rid in rids),
                "submitted_full_prose_characters_all_attempts": sum((r["prose"] or {}).get("full_prose_characters", 0) for r in selected),
                "prose_character_measurement_unknown": sum(name == "submit_report_text" and r["prose"] is None for r in selected)}
        failures = Counter(row["tool"].removeprefix(PREFIX) for row in self.rows if not row["success"])
        self.result["accounting"]["tool_failures_by_tool"] = dict(failures)
        self.result["semantic_activity"] = {"tools": by_tool, "attempts": attempts,
            "note": "Provider completion tokens cover the whole response including JSON and any explanation, not only prose. A request with multiple tools may appear in more than one tool bucket; phase totals count each request once. Every failed semantic submission is retained. Differences in free writing and repairs are not attributed solely to motif bypasses."}

    def producer(self, identifier, tool, before=None):
        matches = [r for r in self.rows if r["success"] and r["tool"] == PREFIX + tool
                   and (before is None or r["step"] < before)
                   and PurePosixPath(str((r["output"] or {}).get("_provenance", {}).get("record_path", "")).replace("\\", "/")).stem == identifier]
        if not matches:
            raise ValueError("No successful real tool output for " + identifier)
        return matches[-1]

    def semantic(self, identifier, kind, tool, before=None):
        value = self.record(identifier, kind)
        row = self.producer(identifier, tool, before)
        self.check(row["origin"] == "llm", "Semantic decision did not come from a real LLM request", tool=tool, call_id=row["call_id"])
        schema = next((item["function"]["parameters"] for tools in self.result["tool_schemas"].values() for item in tools
                       if item.get("function", {}).get("name") == PREFIX + tool), {})
        approval = value.get("semantic_approval", {})
        comparison = semantic_argument_comparison(row["arguments"], approval.get("arguments"),
                                                 schema.get("properties", {}), schema.get("required", []))
        self.check(approval.get("tool") == tool and comparison["declared_parameters_match"],
                   "Semantic receipt changes declared LLM-submitted arguments", tool=tool, differences=comparison.get("differences"))
        self.result.setdefault("semantic_argument_audit", []).append({"tool": tool, "call_id": row["call_id"],
            "record_id": identifier, "schema_sha256": digest(schema), **comparison,
            "note": "Original complete arguments remain in tool_sequence/raw API. An ignored schema-external top-level key is disclosed; all declared parameters and nested prose must match without edits."})
        return value, row

    def model_saw(self, row, previous, required_id):
        request = read(self.path / "model-requests" / (row["request_id"] + ".request.json"))
        found = []
        for message in request.get("messages", []):
            if message.get("role") == "tool" and message.get("tool_call_id") == previous["call_id"]:
                try:
                    found.append(json.loads(message.get("content", "")))
                except (ValueError, TypeError):
                    continue
        passed = (previous["step"] < row["step"] and any(value == previous["output"]
                  and required_id in json.dumps(value, ensure_ascii=False) for value in found))
        self.check(passed, "Semantic request lacks this run's actual preceding tool evidence", call_id=row["call_id"], expected_evidence=required_id)
        return passed

    def _final(self, delivery_row):
        output = delivery_row["output"]
        self.receipt(output)
        delivery = self.record(output["delivery_id"], "delivery")
        verification = self.record(delivery["verification_id"], "report_verification")
        report = self.record(delivery["report_id"], "report")
        layout = self.record(report["layout_id"], "report_layout")
        draft = self.record(report["draft_id"], "report_draft")
        text, text_call = self.semantic(draft["text_id"], "report_text", "submit_report_text", delivery_row["step"])
        packet = self.record(text["packet_id"], "evidence_packet")
        presentation, presentation_call = self.semantic(text["presentation_id"], "presentation_plan", "approve_presentation", text_call["step"])
        evidence = self.record(text["evidence_id"], "evidence")
        plan, plan_call = self.semantic(text["plan_id"], "analysis_plan", "approve_analysis", presentation_call["step"])
        analysis = self.record(text["analysis_id"], "analysis")
        bundle = self.record(packet["figure_bundle_id"], "figure_bundle")
        final_ids = [output["delivery_id"], delivery["verification_id"], delivery["report_id"], report["layout_id"], report["draft_id"],
                     draft["text_id"], text["packet_id"], text["presentation_id"], text["evidence_id"], text["plan_id"], text["analysis_id"], packet["figure_bundle_id"]]
        self.check(verification["report_id"] == delivery["report_id"] and layout["draft_id"] == report["draft_id"], "Final report lineage mismatch")
        self.check(all(p.get("plan_id") == text["plan_id"] for p in (delivery, verification, report, layout, draft, packet, presentation, evidence, analysis, bundle)), "Final records use different plans")
        self.check(all(p.get("analysis_id") == text["analysis_id"] for p in (draft, packet, presentation, evidence, bundle)), "Final records use different analyses")
        self.check(draft["packet_id"] == text["packet_id"] and packet["presentation_id"] == text["presentation_id"]
                   and packet["evidence_id"] == text["evidence_id"] == presentation["evidence_id"] == bundle["evidence_id"], "Presentation/text evidence chain differs")
        self.check(delivery_row["arguments"] == {"verification_id": delivery["verification_id"]}, "Final delivery arguments mismatch")
        self.check(verification["text_id"] == delivery["text_id"] == draft["text_id"], "Final narrative chain differs")
        self.check(all(p.get("quality_passed") is True for p in (delivery, verification, report, layout["engine"], packet)), "Final chain includes rejected artifact")
        result_call = self.producer(text["evidence_id"], "build_evidence", presentation_call["step"])
        packet_call = self.producer(text["packet_id"], "verify_figures", text_call["step"])
        saw_result = self.model_saw(presentation_call, result_call, text["evidence_id"])
        saw_packet = self.model_saw(text_call, packet_call, text["packet_id"])
        self.model_saw(text_call, result_call, text["evidence_id"])
        self.check(self.records[text["evidence_id"]]["authorized_tools"] == [] and self.records[text["packet_id"]]["authorized_tools"] == [], "Semantic barrier incorrectly allows deterministic continuation")
        chosen = presentation["presentation"]
        self.result["selection"] = {"presentation_id": text["presentation_id"], "from_call_id": presentation_call["call_id"],
            "request_id": presentation_call["request_id"], "after_actual_evidence": saw_result,
            "submitted": presentation_call["arguments"]["presentation"], "approved": chosen,
            "figures": chosen["figures"], "tables": chosen["tables"], "reason": chosen.get("reason")}
        self.result["analysis_decision"] = {"plan_id": text["plan_id"], "from_call_id": plan_call["call_id"], "request_id": plan_call["request_id"], "submitted": plan_call["arguments"], "approved_analysis": plan["plan"]}
        selected_kinds = [f["kind"] for f in chosen["figures"]]
        self.check(all(kind in FIGURES[plan["plan"]["design"]] for kind in selected_kinds), "Selected figure incompatible with approved design")
        self.check(selected_kinds == [f["kind"] for f in bundle["figures"]], "Actual figure bundle differs from approved choices")
        computed = recompute(self.path / "sources" / "cases" / self.manifest["case_id"] / "data.csv", plan["plan"])
        numeric_errors = numeric_differences(computed, analysis)
        self.check(not numeric_errors, "Independent CSV recomputation differs", differences=numeric_errors)
        self.result["statistics_review"] = {"passed": not numeric_errors, "recomputed": computed, "reported": {"statistics": analysis["statistics"], "diagnostics": analysis["diagnostics"]}, "issues": numeric_errors}
        self._writing(text, text_call, draft, chosen, evidence, computed, saw_packet)
        pdf = self.local(delivery["path"])
        sha = file_sha(pdf)
        self.check(all(p.get("path") == delivery["path"] and p.get("sha256") == sha for p in (output, delivery, verification, report, layout["engine"])), "Final PDF bytes/path differ from delivery chain")
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        with fitz.open(pdf) as document:
            pdf_text = [page.get_text("text") for page in document]
            pages = len(document)
            metadata = document.metadata
            footer = "合成数据 / Synthetic data" if draft["document"].get("synthetic") else "科研数据分析报告"
            furniture, body_text = [], []
            for i, page in enumerate(document):
                body = []
                for block in page.get_text("blocks"):
                    if block[6] != 0:
                        continue
                    lines = [line.strip() for line in block[4].splitlines() if line.strip()]
                    expected = ([footer], [str(i + 1)], [footer, str(i + 1)])
                    if block[1] >= page.rect.height - 45 and lines in expected:
                        furniture.append({"page": i + 1, "bbox": list(block[:4]), "text": block[4]})
                    else:
                        body.append(block[4])
                body_text.append("".join(body))
        # A paragraph may continue across pages. The PDF painting order places
        # footer text before that continuation; remove only the exact known
        # footer/page labels at their bottom-page coordinates, never prose.
        compact_pdf = re.sub(r"\s+", "", "".join(body_text))
        missing_prose = [{"section": i, "paragraph": j} for i, section in enumerate(text["rendered_sections"])
                         for j, paragraph in enumerate(section["paragraphs"])
                         if re.sub(r"\s+", "", paragraph) not in compact_pdf]
        self.check(not missing_prose, "Actual PDF extraction omits submitted body text", missing=missing_prose)
        self.check(pages == delivery["page_count"] == output["page_count"] == layout["engine"]["page_count"], "Actual PDF pages differ from recorded delivery")
        requirement = chosen["report"]
        self.check(requirement["page_mode"] == "auto" or (pages == requirement["pages"] if requirement["page_mode"] == "exact" else pages <= requirement["pages"]), "PDF violates approved page requirement")
        from PIL import Image
        images = []
        for index, figure in enumerate(bundle["figures"]):
            expected_metrics = {k: computed["statistics"][k] for k in ("n", "estimate", "ci_low", "ci_high", "p_value")}
            self.check(not numeric_differences(expected_metrics, figure.get("analysis_metrics", {})),
                       "Figure metadata differs from independently recomputed statistics", index=index)
            self.check(figure.get("data_rows") == computed["diagnostics"]["retained_rows"],
                       "Figure row count differs from retained source observations", index=index)
            for extension, original in figure["paths"].items():
                self.check(file_sha(self.local(original)) == figure["sha256"][extension], "Final figure file changed", index=index, extension=extension)
            p = self.local(figure["paths"]["png"])
            with Image.open(p) as image:
                rgba = image.convert("RGBA")
                pixels = hashlib.sha256(canonical(list(rgba.size)) + rgba.tobytes()).hexdigest()
                size = list(rgba.size)
            images.append({"index": index, "kind": figure["kind"], "title": figure.get("title"), "caption": figure.get("caption"),
                           "path": str(p), "sha256": file_sha(p), "rgba_sha256": pixels, "size": size})
            self.check(draft["document"]["figures"][index]["path"] == figure["paths"]["png"], "Final document references different figure")
        self.result["report"] = {"pdf_path": str(pdf), "original_pdf_path": delivery["path"], "sha256": sha, "page_count": pages,
            "text_by_page": pdf_text, "metadata": metadata, "figures": images, "report_id": delivery["report_id"],
            "body_text_by_page": body_text, "excluded_page_furniture": furniture,
            "pdf_text_check": "Every submitted paragraph is present after whitespace removal and exclusion of exact known footer/page labels below page_height-45pt. Raw page text remains preserved separately.",
            "draft_id": report["draft_id"], "text_id": draft["text_id"], "document": draft["document"],
            "warnings": delivery.get("warnings", []), "automatic_layout_audit": verification["audit"],
            "record_chain": [{"id": identifier, "kind": self.records[identifier]["kind"],
                "record_sha256": file_sha(self.path / "workspace" / "records" / (identifier + ".json"))} for identifier in final_ids]}

    def _writing(self, text, call, draft, chosen, evidence, computed, saw_packet):
        start_errors = len(self.errors)
        submitted = text["submitted_report_text"]
        self.check(submitted == call["arguments"]["report_text"], "Submitted narrative differs from actual model tool arguments")
        catalog = evidence["available_placeholders"]
        for binding in text["bindings"]:
            template = binding["template"]
            names = TOKEN.findall(template)
            self.check(set(names) == set(binding["tokens"]), "Text binding token set mismatch", field=binding["field"])
            for name, token in binding["tokens"].items():
                self.check(name in catalog and token == {k: catalog[name][k] for k in ("value", "display", "source")}, "Text token differs from actual evidence", token=name)
            expected = TOKEN.sub(lambda m: str(catalog[m[1]]["display"]), template)
            self.check(expected == binding["rendered"], "Unexpected prose rewrite during token expansion", field=binding["field"])
            issues = formatting_issues(binding, len(chosen["figures"]))
            self.check(not issues, "Formatting exemption exceeds actual figure/ordinal bounds", field=binding["field"], issues=issues)
        binding_by_field = {b["field"]: b for b in text["bindings"]}
        rendered = []
        for i, section in enumerate(submitted["sections"]):
            paragraphs = []
            for j, paragraph in enumerate(section["paragraphs"]):
                field = f"sections[{i}].paragraphs[{j}]"
                self.check(field in binding_by_field and binding_by_field[field]["template"] == paragraph, "Published paragraph not bound to original model prose", field=field)
                paragraphs.append(TOKEN.sub(lambda m: str(catalog[m[1]]["display"]), paragraph))
            rendered.append({"id": f"section-{i+1}", "heading": section["heading"], "paragraphs": paragraphs, "figure_indices": section.get("figure_indices", [])})
        options = submitted.get("research_options", [])
        if options:
            outline = chosen["report"]["outline"]
            target = next((i for i, row in enumerate(outline) if "next_steps" in row["roles"]),
                          next(i for i, row in enumerate(outline) if "limitations" in row["roles"]))
            def expand(field, raw):
                self.check(field in binding_by_field and binding_by_field[field]["template"] == raw, "Research-option text lost its LLM source", field=field)
                return TOKEN.sub(lambda m: str(catalog[m[1]]["display"]), raw)
            for i, option in enumerate(options):
                name, rationale, tradeoff = [expand(f"research_options[{i}].{key}", option[key]) for key in ("name", "rationale", "tradeoff")]
                rendered[target]["paragraphs"].append(f"{name}：{rationale} 取舍与限制：{tradeoff}")
            rendered[target]["paragraphs"].append(expand("comparison_summary", submitted["comparison_summary"]))
        self.check(rendered == text["rendered_sections"] == draft["document"]["sections"], "Final body is not solely submitted model text plus declared token/option transformations")
        # Verify numeric token values independently, not just the logged binding.
        values = {**computed["statistics"], **computed["diagnostics"]}
        values.pop("group_summaries", None)
        confidence = self.record(text["plan_id"])["plan"]["confidence"]
        values.update(confidence=confidence, confidence_pct=confidence * 100, alpha=1 - confidence, null_value=0, unit_increment=1)
        for prefix, group in zip(("reference", "comparison"), computed["statistics"].get("group_summaries", [])):
            values.update({prefix + "_" + k: group[k] for k in ("n", "mean", "sd")})
        for name, item in catalog.items():
            if isinstance(item["value"], (int, float)):
                tolerance = 1e-300 if name in {"p_value", "shapiro_p"} else 1e-10
                self.check(name in values and math.isclose(item["value"], values[name], rel_tol=1e-7, abs_tol=tolerance), "Narrative numeric catalog differs from recomputation", token=name)
                expected_display = str(item["value"]) if isinstance(item["value"], int) else f"{item['value']:.5g}"
                self.check(item["display"] == expected_display, "Narrative number formatting differs from recorded value", token=name)
        original_chars = sum(len(p) for section in submitted["sections"] for p in section["paragraphs"])
        self.result["writing"] = {"text_id": draft["text_id"], "from_call_id": call["call_id"], "request_id": call["request_id"],
            "after_verified_figures": saw_packet, "submitted_report_text": submitted, "rendered_sections": text["rendered_sections"],
            "bindings": text["bindings"], "transformations": text["transformations"],
            "authorship_passed": len(self.errors) == start_errors, "submitted_body_characters": original_chars,
            "submitted_prose_character_breakdown": prose_characters(submitted),
            "published_body_characters": sum(len(p) for section in rendered for p in section["paragraphs"]),
            "deterministic_outside_body": {k: draft["document"].get(k) for k in ("subtitle", "metrics", "provenance")},
            "scope_note": "Authorship tracks raw model text to final sections, not scientific correctness. The outline is submitted by the LLM; an omitted report title can default to study metadata (see selection.submitted versus approved). Captions, numeric table rendering, labels and provenance are deterministic and disclosed separately."}


def qualify(row, supplied):
    automatic = row.get("evidence_passed") is True and row.get("business_delivered") is True
    result = {"automatic_passed": automatic, "independent_review": {"status": "unreviewed"}, "qualified": None if automatic else False}
    if supplied is None:
        return result
    review = deepcopy(supplied)
    issues = []
    report, writing = row.get("report") or {}, row.get("writing") or {}
    if review.get("pdf_sha256") != report.get("sha256") or review.get("text_id") != writing.get("text_id"):
        issues.append("Review is not bound to this final PDF and text receipt")
    if not review.get("method") or not review.get("reviewer"):
        issues.append("Review method/reviewer missing; do not claim a fictional human review")
    if report.get("page_count") and review.get("reviewed_pages") != list(range(1, report["page_count"] + 1)):
        issues.append("Visual review does not explicitly cover all final PDF pages")
    checks = review.get("checks", {})
    for key in REVIEW_CHECKS:
        item = checks.get(key, {})
        if item.get("status") not in {"pass", "fail", "uncertain"} or not item.get("evidence"):
            issues.append("Missing explicit verdict and evidence: " + key)
    major = any(i.get("severity") in {"major", "blocker"} and i.get("resolved") is not True for i in review.get("issues", []))
    passed = (not issues and not major and all(checks[k]["status"] == "pass" for k in REVIEW_CHECKS))
    review["validation_issues"] = issues
    review["status"] = "pass" if passed else "fail" if major or any(i.get("status") == "fail" for i in checks.values()) else "uncertain"
    result.update(independent_review=review, qualified=bool(automatic and passed))
    return result


def pair_conditions(left, right):
    issues = []
    for key in ("source_sha256", "runtime_patch", "scenario_scoped_paths", "tool_schemas", "model_configs", "initial_context_normalized"):
        if left.get(key) != right.get(key):
            issues.append({"field": key, "differences": differences(left.get(key), right.get(key))})
    for key in ("model", "provider", "real_upstream", "thinking", "reasoning_effort", "contracts_digest", "tool_order", "prompt_sha256", "max_requests", "max_output", "compression", "automatic_retries", "pricing", "benchmark_code_sha256", "shared_dependency_code_sha256", "budget_implementation_sha256", "node", "dsh", "python"):
        if left.get("manifest", {}).get(key) != right.get("manifest", {}).get(key):
            issues.append({"field": "manifest." + key})
    ls = sorted({digest(v["normalized"]) for v in left.get("systems", {}).values()})
    rs = sorted({digest(v["normalized"]) for v in right.get("systems", {}).values()})
    if ls != rs:
        issues.append({"field": "scoped_system_messages"})
    return issues


def aggregate(names, runs, quality):
    result = {}
    for mode in ("baseline", "execute"):
        selected = [runs[name] for name in names if runs[name].get("mode", runs[name]["job"].get("mode", "baseline")) == mode]
        if not selected:
            continue
        costs = {period: sum(r.get("accounting", {}).get(period + "_estimate_cny", 0) for r in selected) for period in ("peak", "offpeak")}
        qualified = sum(quality[r["name"]]["qualified"] is True for r in selected)
        unreviewed = sum(quality[r["name"]]["qualified"] is None for r in selected)
        result[mode] = {"runs": len(selected), "business_delivered": sum(r.get("business_delivered") is True for r in selected),
            "evidence_passed": sum(r.get("evidence_passed") is True for r in selected), "qualified": qualified,
            "quality_pending": unreviewed, "qualified_rate": None if unreviewed else qualified / len(selected),
            **{period + "_estimate_cny": cost for period, cost in costs.items()},
            "cost_per_qualified": {period: cost / qualified if qualified and not unreviewed else None for period, cost in costs.items()},
            **{key: sum(r.get("accounting", {}).get(key, 0) or 0 for r in selected) for key in ("upstream_requests", "tool_calls", "verified_motif_bypasses", "tool_failure_count", "elapsed_seconds")},
            "usage": dict(sum((Counter(r.get("accounting", {}).get("usage", {})) for r in selected), Counter()))}
        result[mode]["tool_failures_by_tool"] = dict(sum((Counter(r.get("accounting", {}).get("tool_failures_by_tool", {})) for r in selected), Counter()))
        result[mode]["tool_outcomes"] = dict(sum((Counter(r.get("accounting", {}).get("tool_outcomes", {})) for r in selected), Counter()))
        result[mode]["semantic_submission_counts"] = {
            tool: {field: sum(r.get("semantic_activity", {}).get("tools", {}).get(tool, {}).get(field, 0) for r in selected)
                   for field in ("attempts", "successes", "failures", "submitted_full_prose_characters_all_attempts")}
            for tool in ("approve_analysis", "approve_presentation", "submit_report_text")}
        result[mode]["phases"] = {}
        for phase in ("semantic", "execution", "no_tool_response"):
            rows = [r.get("accounting", {}).get("phases", {}).get(phase, {}) for r in selected]
            result[mode]["phases"][phase] = {
                **{k: sum(row.get(k, 0) for row in rows) for k in ("requests", "peak_estimate_cny", "offpeak_estimate_cny")},
                "usage": dict(sum((Counter(row.get("usage", {})) for row in rows), Counter()))}
    return result


def audit_budget(path, objects, prior_ledger=None):
    issues, groups = [], defaultdict(list)
    if not path.is_file():
        return {"passed": False, "issues": ["Shared ledger snapshot missing"], "path": str(path)}
    raw_rows = jsonlines(path)
    for row in raw_rows:
        groups[row["request_id"]].append(row)
    selected_ids, selected_cost, global_cost, global_offpeak = set(), 0.0, 0.0, 0.0
    offpeak_complete = True
    for rid, rows in groups.items():
        if Counter(r["kind"] for r in rows) != {"reserve": 1, "settle": 1}:
            issues.append({"request_id": rid, "error": "Expected exactly one reserve and one settle"})
            continue
        settled = next(r for r in rows if r["kind"] == "settle")
        if not settled.get("usage") or settled.get("peak_estimate_cny") is None:
            issues.append({"request_id": rid, "error": "Unknown usage/cost"})
        if not math.isclose(sum(r["delta_cny"] for r in rows), settled.get("peak_estimate_cny", -1), abs_tol=1e-10):
            issues.append({"request_id": rid, "error": "Settlement arithmetic differs"})
        global_cost += settled.get("peak_estimate_cny", 0)
        if settled.get("offpeak_estimate_cny") is not None:
            global_offpeak += settled["offpeak_estimate_cny"]
        else:
            offpeak_complete = False
    for obj in objects.values():
        for row in getattr(obj, "costs", []):
            rid = row["request_id"]
            if rid in selected_ids:
                issues.append({"request_id": rid, "error": "Request appears in multiple run ledgers"})
            selected_ids.add(rid)
            settlement = next((r for r in groups.get(rid, []) if r["kind"] == "settle"), {})
            if settlement.get("usage") != row.get("usage") or settlement.get("run_id") != obj.manifest.get("run_id") or not math.isclose(settlement.get("peak_estimate_cny", -1), row.get("peak_estimate_cny", -2), abs_tol=1e-12):
                issues.append({"request_id": rid, "error": "Shared ledger differs from actual run request/usage"})
            selected_cost += row.get("peak_estimate_cny", 0)
    prior = None
    if prior_ledger:
        if not prior_ledger.is_file():
            issues.append({"error": "Prior ledger snapshot unavailable", "path": str(prior_ledger)})
        else:
            old_rows = jsonlines(prior_ledger)
            old_ids = {r["request_id"] for r in old_rows}
            extra = set(groups) - old_ids - selected_ids
            missing = selected_ids - (set(groups) - old_ids)
            prefix_matches = path.read_bytes().startswith(prior_ledger.read_bytes())
            if not prefix_matches or extra or missing:
                issues.append({"error": "New global requests are not exactly the audited new experiment requests", "prior_bytes_unchanged": prefix_matches,
                               "unaccounted_new_requests": sorted(extra), "not_new_run_requests": sorted(missing)})
            old_cost = sum(r.get("peak_estimate_cny", 0) for r in old_rows if r.get("kind") == "settle")
            old_settled = [r for r in old_rows if r.get("kind") == "settle"]
            old_offpeak = sum(r["offpeak_estimate_cny"] for r in old_settled) if all(r.get("offpeak_estimate_cny") is not None for r in old_settled) else None
            prior = {"path": str(prior_ledger), "sha256": file_sha(prior_ledger), "prefix_bytes_unchanged": prefix_matches,
                     "requests": len(old_ids), "peak_estimate_cny": old_cost,
                     "offpeak_estimate_cny": old_offpeak,
                     "new_requests": len(set(groups) - old_ids), "new_peak_estimate_cny": global_cost - old_cost,
                     "new_offpeak_estimate_cny": global_offpeak - old_offpeak if offpeak_complete and old_offpeak is not None else None,
                     "unaccounted_new_requests": sorted(extra)}
    return {"passed": not issues, "issues": issues, "path": str(path), "sha256": file_sha(path), "global_requests": len(groups),
            "audited_run_requests": len(selected_ids), "audited_run_peak_estimate_cny": selected_cost,
            "global_peak_estimate_cny": global_cost, "other_historical_requests": len(set(groups) - selected_ids), "prior_snapshot": prior,
            "global_offpeak_estimate_cny": global_offpeak if offpeak_complete else None,
            "note": "Provider token estimates, not invoices. All requests from discovered runs are checked; historical requests remain accounted separately."}


def report_notes(groups, runs, quality, totals):
    formal = [runs[name] for name in groups["evaluation"]]
    major = []
    for row in formal:
        for issue in quality[row["name"]]["independent_review"].get("issues", []):
            if issue.get("severity") in {"major", "blocker"} and issue.get("resolved") is not True:
                major.append({"run": row["name"], "case": row.get("case_id"), "mode": row.get("mode"),
                              "repeat_id": row.get("repeat_id"), **issue})
    costs = {group: {period + "_estimate_cny": sum(arm.get(period + "_estimate_cny", 0) for arm in totals[group].values())
                    for period in ("peak", "offpeak")} for group in groups}
    capacity = [{"run": row["name"], "step": call["step"], "output": call["output"]}
                for row in formal for call in row.get("tool_sequence", [])
                if call["tool"] == PREFIX + "submit_report_text" and not call["success"]
                and isinstance(call["output"], dict) and call["output"].get("capacity_preflight") is not None]
    return {"scientific_major_findings": major,
        "unreviewed_formal_runs": [r["name"] for r in formal if quality[r["name"]]["qualified"] is None],
        "formal_technical_deliveries": sum(r.get("business_delivered") is True for r in formal),
        "formal_qualified_deliveries": sum(quality[r["name"]]["qualified"] is True for r in formal),
        "costs_by_stage": costs,
        "layout": {"actual_layout_tool_calls": sum(r.get("layout", {}).get("layout_calls", 0) for r in formal),
            "same_draft_repeats": sum(r.get("layout", {}).get("agent_rework", {}).get("same_draft_layout_repeats", 0) for r in formal),
            "additional_drafts": sum(r.get("layout", {}).get("agent_rework", {}).get("additional_drafts", 0) for r in formal),
            "unique_internal_candidates": sum(r.get("layout", {}).get("unique_recorded_candidates", 0) for r in formal),
            "layout_tool_failures": sum(not call["success"] for r in formal for call in r.get("layout", {}).get("calls", [])),
            "earlier_text_capacity_rejections": capacity,
            "scope": "One layout call can test multiple candidates internally. Earlier text-capacity rejection is recorded separately; no blanket claim that all content was accepted immediately."},
        "interpretation_notes": [
            "所有预登记正式运行、工具拒绝、模型重提和失败都保留；不替换为最佳重复。",
            "tool_calls/mcp_calls表示DSH的MCP工具调用尝试，不是物理通信次数；成功执行、业务拒绝、schema错误单列。坏JSON不自动等同于发送MCP前终止。",
            "数值、来源、排版检查通过不代表科学文字正确；独立AI逐页审阅不是盲评或学科专家认证。",
            "两臂自由生成不同正文、图表选择和修复轨迹，费用差不能全部解释为Motif绕过的因果收益。",
            "DeepSeek API估费只计算provider token费用；排除服务器、实现开发、外部Codex独立AI审阅费用，不是总拥有成本，也不是平台账单。",
            "峰值为预算保守口径，非峰为相应费率估算；缓存命中与输出长度按实际usage保留。"]}


def audit(experiment, evaluation, training, reviews, ledger, library, prior_ledger=None, development_experiments=None):
    objects, runs, groups, issues = {}, {}, {}, []
    for group, path in (("evaluation", evaluation), ("training", training)):
        groups[group] = []
        try:
            jobs = read(path)
        except Exception as error:
            jobs = []
            issues.append({"issue": "Matrix unavailable", "group": group, "error": str(error)})
        for job in jobs:
            name = job.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]{1,100}", name) or name in objects:
                issues.append({"issue": "Unsafe or duplicate matrix run name", "name": name})
                continue
            obj = AuditRun(experiment / "runs" / name, job, group)
            objects[name], runs[name] = obj, obj.run()
            if obj.manifest:
                obj.check(obj.manifest.get("matrix_sha256") == file_sha(path), "Actual run matrix differs from submitted matrix")
                for field in ("repeat_id", "matrix_order", "experiment_role"):
                    obj.check(obj.manifest.get(field) == job.get(field), "Manifest job field differs from declared matrix", field=field)
                runs[name]["evidence_passed"] = not obj.errors
            groups[group].append(name)
    groups["development"] = []
    for path in sorted((experiment / "runs").iterdir()) if (experiment / "runs").is_dir() else []:
        if path.is_dir() and path.name not in objects:
            m = read(path / "manifest.json") if (path / "manifest.json").is_file() else {}
            obj = AuditRun(path, {"name": path.name, "mode": m.get("mode", "baseline")}, "development")
            objects[path.name], runs[path.name] = obj, obj.run()
            groups["development"].append(path.name)
    development_paths = []
    for development in development_experiments or []:
        development = development.resolve()
        if development == experiment.resolve() or development in development_paths:
            issues.append({"issue": "Development experiment duplicates another audited root", "path": str(development)})
            continue
        development_paths.append(development)
        if not (development / "runs").is_dir():
            issues.append({"issue": "Development experiment has no downloaded runs", "path": str(development)})
            continue
        for path in sorted((development / "runs").iterdir()):
            if not path.is_dir():
                continue
            # Preserve original directory/absolute path provenance. The display
            # key is namespaced because fresh experiments may reuse task names.
            name = development.name + "::" + path.name
            if name in objects:
                issues.append({"issue": "Duplicate development run key", "name": name})
                continue
            m = read(path / "manifest.json") if (path / "manifest.json").is_file() else {}
            obj = AuditRun(path, {"name": name, "mode": m.get("mode", "baseline")}, "development")
            objects[name], runs[name] = obj, obj.run()
            runs[name].update(name=name, source_experiment=str(development), original_run_name=path.name)
            groups["development"].append(name)
    review_rows = read(reviews) if reviews and reviews.is_file() else {}
    quality = {name: qualify(row, review_rows.get(name)) for name, row in runs.items()}
    cases = defaultdict(lambda: defaultdict(list))
    for name in groups["evaluation"]:
        row = runs[name]
        key = (row.get("case_id", row["job"].get("case", name)), row.get("repeat_id", row["job"].get("repeat_id", 1)))
        cases[key][row.get("mode", row["job"].get("mode", "baseline"))].append(name)
    pairs = []
    for (case, repeat), arms in sorted(cases.items()):
        if set(arms) != {"baseline", "execute"} or any(len(names) != 1 for names in arms.values()):
            pairs.append({"case_id": case, "repeat_id": repeat, "conditions_match": False, "issues": ["Exactly one run per arm required"], "runs": dict(arms)})
            continue
        bn, en = arms["baseline"][0], arms["execute"][0]
        problems = pair_conditions(runs[bn], runs[en])
        pairs.append({"case_id": case, "repeat_id": repeat, "baseline": bn, "execute": en, "conditions_match": not problems,
                      "issues": problems, "both_qualified": quality[bn]["qualified"] is True and quality[en]["qualified"] is True,
                      "note": "Different freely generated text or chart choices are legitimate; judge both against the same quality contract, not byte equality."})
    if len(groups["evaluation"]) != 16 or len(pairs) != 8 or len({p["case_id"] for p in pairs}) != 4:
        issues.append({"issue": "Expected four cases, two repeats, two arms = 16 formal runs"})
    training_roles = Counter(runs[n].get("manifest", {}).get("experiment_role") for n in groups["training"])
    if training_roles != {"train": 2, "certification": 1}:
        issues.append({"issue": "Expected two training cases and one independent certification", "observed": dict(training_roles)})
    formal_rows = [runs[n] for n in groups["evaluation"]]
    for field in ("benchmark_code_sha256", "shared_dependency_code_sha256", "contracts_digest", "model", "pricing", "max_requests", "max_output"):
        values = {digest(row.get("manifest", {}).get(field)) for row in formal_rows}
        if len(values) != 1:
            issues.append({"issue": "Formal runtime condition changed across the full matrix", "field": field})
    for previous, current in zip(formal_rows, formal_rows[1:]):
        before, after = previous.get("metrics", {}).get("ended_utc_epoch"), current.get("metrics", {}).get("started_utc_epoch")
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)) or after < before:
            issues.append({"issue": "Actual formal runs overlap, lack time evidence, or violate declared ordering", "previous": previous["name"], "next": current["name"]})
    totals = {group: aggregate(names, runs, quality) for group, names in groups.items()}
    train = totals["training"].get("baseline", {})
    totals["amortization"] = {"training_and_confirmation_peak_cny": train.get("peak_estimate_cny"),
        "training_and_confirmation_offpeak_cny": train.get("offpeak_estimate_cny"),
        "scenarios": [{"future_reports": n, "training_per_report_peak_cny": train.get("peak_estimate_cny", 0) / n,
                       "training_per_report_offpeak_cny": train.get("offpeak_estimate_cny", 0) / n} for n in (8, 100, 1000)],
        "note": "Hypothetical amortization, not measured deployment; all development costs remain separately counted. Unknown human engineering/review costs are not zero."}
    # Reuse only our prior independent witness audit, vendored alongside this
    # reviewer. It reads source receipts and actual trace adjacency, never the
    # benchmark compiler's assertion alone.
    from library_witnesses import audit_library
    try:
        library_result = audit_library(library, objects, set(groups["evaluation"]))
    except Exception as error:
        library_result = {"passed": False, "issues": [f"Cannot audit library: {type(error).__name__}: {error}"]}
    budget = audit_budget(ledger, objects, prior_ledger)
    return {"version": 3, "experiment_id": experiment.name, "experiment": str(experiment.resolve()),
        "evidence_passed": not issues and budget["passed"] and library_result["passed"]
                           and all(row["evidence_passed"] for row in runs.values()) and all(p["conditions_match"] for p in pairs),
        "issues": issues, "runs": runs, "groups": groups, "aggregate": totals, "pairs": pairs, "quality": quality,
        "development_experiments": [str(path) for path in development_paths],
        "budget": budget, "library": library_result,
        "report_notes": report_notes(groups, runs, quality, totals),
        "auditor_sources": {p.name: file_sha(p) for p in Path(__file__).parent.glob("*.py")},
        "limitations": ["Automatic numerical, provenance and layout checks do not prove scientific prose correct.",
                        "A review marked unreviewed must not be counted as a qualified report.",
                        "Different free semantic outputs mean this measures system delivery, not same-text causal execution effects.",
                        "Synthetic data and four tasks/two repeats do not establish broad scientific generalization.",
                        "Peak/offpeak costs are provider-usage estimates; this script does not obtain invoices."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path)
    parser.add_argument("--training", type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--prior-ledger", type=Path, help="Previous untouched snapshot: every new request must belong to the audited experiment")
    parser.add_argument("--development-experiment", type=Path, action="append", default=[],
                        help="Additional preserved experiment root; its runs are counted as development, never training/evaluation. Repeatable.")
    parser.add_argument("--library", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.experiment, args.evaluation or args.experiment / "evaluation-matrix.json",
                   args.training or args.experiment / "training-matrix.json", args.reviews,
                   args.ledger or args.experiment / "global-ledger.jsonl", args.library or args.experiment / "library.json",
                   args.prior_ledger, args.development_experiment)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"evidence_passed": result["evidence_passed"], "runs": len(result["runs"]),
                      "qualified": sum(q["qualified"] is True for q in result["quality"].values()),
                      "quality_pending": sum(q["qualified"] is None for q in result["quality"].values()),
                      "output": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if result["evidence_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
