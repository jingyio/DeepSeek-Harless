"""Independent, read-only audit of matched real DSH/Motif report runs.

No benchmark implementation, agent, compiler or evaluator is imported. The only
write is --output (default EXP/review/matched-summary.json). PyMuPDF and Pillow
are required to verify actual PDF text/pages and decoded PNG pixels. Missing
evidence/dependencies are failures, never assumed matches. All listed attempts,
including unsuccessful runs and calls, remain in the output.

Example, from the repository root::

    python /path/to/work/v22-review/review_matched_runs.py --repo /path/to/repo \
      --experiment .local/research-report-agent-v22-20261010 \
      --output .local/research-report-agent-v22-20261010/review/matched-summary.json

Exit 0: evidence audit and every formal matched pair passed. Exit 2: incomplete,
inconsistent, or unsuccessful formal comparison; JSON still contains all results.
Natural-request differences are diagnostic, not matched-content failures.
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

PREFIX = "mcp__research_report__"
USAGE = ("prompt_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
         "completion_tokens", "total_tokens")
SEMANTIC = {"inspect_study", "approve_workflow", "approve_interpretation"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def jsonlines(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()] if Path(path).is_file() else []


def parse_args(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def tool_rows(events):
    """Keep the initial append result, not later presentation-only updates."""
    rows, by_id = [], {}
    for index, event in enumerate(events):
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            row = {"step": len(rows) + 1, "call_id": data.get("callId"),
                   "tool": data.get("name"), "arguments": parse_args(data.get("arguments")),
                   "call_event_index": index, "output": None, "success": False}
            rows.append(row)
            by_id[row["call_id"]] = row
        if event.get("type") != "tool/result":
            continue
        op = event.get("surfaceOp")
        if not (op is None or op == "append" or isinstance(op, dict) and op.get("op") == "append"):
            continue
        row = by_id.get(data.get("message", {}).get("source", {}).get("callId"))
        if row is None or "result_event_index" in row:
            continue
        failed, output, texts = bool(data.get("error")), None, []
        for block in data.get("message", {}).get("content", []):
            failed |= block.get("isError") is True
            for content in block.get("content", []):
                if content.get("type") == "text":
                    text = content.get("text", "")
                    texts.append(text)
                    try:
                        value = json.loads(text)
                        if isinstance(value, dict):
                            output = value
                    except ValueError:
                        pass
        row.update(output=output, result_event_index=index, result_text=texts,
                   success=bool(output and not failed and all(output.get(k) is not False
                                for k in ("ok", "passed", "quality_passed"))))
    return rows


def response_data(path):
    text = Path(path).read_text(encoding="utf-8")
    chunks = ([json.loads(text)] if text.lstrip().startswith("{") else
              [json.loads(line[5:]) for line in text.splitlines()
               if line.startswith("data:") and line[5:].strip() != "[DONE]"])
    usage, calls = None, {}
    for chunk in chunks:
        if isinstance(chunk.get("usage"), dict):
            usage = chunk["usage"]
        for choice in chunk.get("choices", []):
            part = choice.get("delta") or choice.get("message") or {}
            for index, call in enumerate(part.get("tool_calls", [])):
                item = calls.setdefault(call.get("index", index), {"id": "", "name": "", "arguments": ""})
                if call.get("id"):
                    item["id"] = call["id"]
                item["name"] += call.get("function", {}).get("name", "")
                item["arguments"] += call.get("function", {}).get("arguments", "")
    return usage, list(calls.values())


def differences(left, right, path="$", limit=80):
    """Exact JSON comparison; retain scientific values, whitespace and ordering."""
    result = []

    def visit(a, b, here):
        if len(result) >= limit:
            return
        if type(a) is not type(b):
            result.append({"path": here, "baseline": a, "execute": b})
        elif isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    result.append({"path": here + "." + key, "baseline": a.get(key),
                                   "execute": b.get(key), "missing_key": True})
                else:
                    visit(a[key], b[key], here + "." + key)
        elif isinstance(a, list):
            if len(a) != len(b):
                result.append({"path": here + ".length", "baseline": len(a), "execute": len(b)})
            for index, (x, y) in enumerate(zip(a, b)):
                visit(x, y, f"{here}[{index}]")
        elif a != b:
            result.append({"path": here, "baseline": a, "execute": b})
    visit(left, right, path)
    return result[:limit]


class RunAudit:
    def __init__(self, run, job, group):
        self.path, self.job, self.group = Path(run), job, group
        self.errors, self.check_count, self.records = [], 0, {}
        self.result = {"name": self.path.name, "group": group, "job": job,
                       "path": str(self.path), "issues": self.errors}
        self.manifest, self.metrics, self.rows = {}, {}, []
        self.original_run = ""

    def check(self, condition, issue, **context):
        self.check_count += 1
        if not condition:
            self.errors.append({"issue": issue, **context})
        return bool(condition)

    def local(self, original):
        """Map only the recorded original run root into this downloaded run."""
        value = str(original).replace("\\", "/")
        if not self.original_run or not value.startswith(self.original_run + "/"):
            raise ValueError("Artifact does not belong to this recorded run: " + value)
        relative = PurePosixPath(value[len(self.original_run) + 1:])
        if ".." in relative.parts or relative.is_absolute():
            raise ValueError("Unsafe artifact path: " + value)
        local = (self.path / Path(*relative.parts)).resolve()
        if not local.is_relative_to(self.path.resolve()):
            raise ValueError("Artifact escapes downloaded run: " + value)
        return local

    def record(self, identifier, kind=None):
        if not isinstance(identifier, str) or not re.fullmatch(r"rra-[a-z_]+-[a-f0-9]{32}", identifier):
            raise ValueError("Invalid referenced record ID: " + repr(identifier))
        if identifier not in self.records:
            path = self.path / "workspace" / "records" / (identifier + ".json")
            value = read(path)
            expected_id = "rra-" + value["kind"] + "-" + digest({k: v for k, v in value.items() if k != "id"})[:32]
            self.check(value.get("id") == identifier == expected_id, "Record content address mismatch", record_id=identifier)
            self.check(value.get("workspace_id") == self.workspace_id, "Record workspace mismatch", record_id=identifier)
            self.check(value.get("source_version") == self.source_version, "Record source version mismatch", record_id=identifier)
            self.records[identifier] = value
        value = self.records[identifier]
        self.check(kind is None or value.get("kind") == kind, "Record kind mismatch", record_id=identifier, expected=kind)
        return value["payload"]

    def receipt(self, output):
        prov = output.get("_provenance", {})
        path = self.local(prov["record_path"])
        self.check(path.parent == (self.path / "workspace" / "records").resolve(), "Receipt record outside records")
        self.check(file_sha(path) == prov.get("record_sha256"), "Receipt file hash mismatch", record_path=str(path))
        record = read(path)
        self.record(record["id"])
        self.check(record.get("authorized_tools") == prov.get("authorized_tools"), "Receipt authorization mismatch")
        self.check(prov.get("workspace_id") == self.workspace_id and prov.get("study_sha256") == self.source_version
                   and prov.get("data_sha256") == self.source_hashes.get("data.csv"), "Receipt input/workspace mismatch")
        self.check(output.get("source_version") == self.source_version, "Output source version mismatch")
        return record

    def normalize_runtime(self, value):
        """Only explicit per-run identifiers/paths; never redact arbitrary text."""
        replacements = [(self.original_run, "<RUN_ROOT>"),
                        (self.manifest.get("session_id", ""), "<SESSION_ID>"),
                        (self.manifest.get("run_id", ""), "<RUN_ID>")]
        if isinstance(value, str):
            for original, replacement in replacements:
                if original:
                    value = value.replace(original, replacement)
            return value
        if isinstance(value, list):
            return [self.normalize_runtime(v) for v in value]
        if isinstance(value, dict):
            return {k: self.normalize_runtime(v) for k, v in value.items()}
        return value

    def run(self):
        try:
            self._run()
        except Exception as error:
            self.check(False, "Cannot finish run evidence audit", error=f"{type(error).__name__}: {error}")
        self.result.update(evidence_passed=not self.errors, checks=self.check_count)
        return self.result

    def _run(self):
        self.manifest = read(self.path / "manifest.json")
        self.metrics = read(self.path / "metrics.json")
        m, metrics = self.manifest, self.metrics
        self.original_run = str(m["intake"]["data_root"]).replace("\\", "/").removesuffix("/sources")
        self.workspace_id = "workspace-" + hashlib.sha256((self.original_run + "/workspace").encode()).hexdigest()[:24]
        # For native Windows evidence, use the actual original workspace spelling.
        scenario = read(self.path / "scenario.json")
        workspace = scenario["servers"][0]["env"]["RRA_RUN_ROOT"]
        self.workspace_id = "workspace-" + hashlib.sha256(workspace.encode()).hexdigest()[:24]
        self.result["scenario_scoped_paths"] = self.normalize_runtime(scenario)
        self.source_hashes = {}
        for source in m["source_files"]:
            source_path = self.local(source["path"])
            self.source_hashes[source_path.name] = file_sha(source_path)
            self.check(self.source_hashes[source_path.name] == source["sha256"], "Frozen input byte hash mismatch", file=source_path.name)
        self.source_version = digest(self.source_hashes)
        self.check(self.source_version == m.get("input_content_digest"), "Input content digest mismatch")
        self.check(digest(m["source_files"]) == m.get("input_sha256"), "Path-sensitive input manifest digest mismatch")
        self.check(m.get("mode") == self.job.get("mode", "baseline"), "Matrix/manifest mode mismatch")
        self.check(self.job.get("case", m.get("case_id")) == m.get("case_id"), "Matrix/manifest case mismatch")
        self.study = read(self.path / "sources" / "cases" / m["case_id"] / "study.json")
        frozen = self.study.get("benchmark_frozen_decisions")
        self.result.update(run_id=m["run_id"], case_id=m["case_id"], mode=m["mode"],
                           manifest=m, source_sha256=self.source_hashes,
                           frozen_decisions=frozen, reported_metrics=metrics,
                           event_file_sha256=file_sha(self.path / "agent-events.jsonl"))
        if self.group == "evaluation":
            self.check(bool(frozen) and m.get("comparison_protocol") == "frozen_semantic_decisions",
                       "Formal matched run is not explicitly frozen-semantic protocol")
        if frozen:
            self.check(frozen.get("decision_sha256") == m.get("frozen_decisions_sha256"), "Frozen decision/manifest hash mismatch")
            self.check(digest({k: frozen[k] for k in ("plan", "commentary") if k in frozen}) == frozen.get("decision_sha256"),
                       "Frozen decision content hash mismatch")
        self.rows = tool_rows(jsonlines(self.path / "agent-events.jsonl"))
        self.check(len({r["call_id"] for r in self.rows}) == len(self.rows), "Duplicate MCP call IDs")
        self.audit_rows = jsonlines(self.path / "motif-audit.jsonl")
        self.result["motif_audit"] = self.audit_rows
        self._requests()
        self._calls()
        self._layouts()
        deliveries = [r for r in self.rows if r["tool"] == PREFIX + "deliver_report"]
        successful = [r for r in deliveries if r["success"] and (r["output"] or {}).get("delivered") is True]
        final_delivery = successful[-1] if successful else None
        self.result["delivery_attempts"] = [{"step": r["step"], "success": r["success"], "output": r["output"]} for r in deliveries]
        self.result["business_delivered"] = bool(final_delivery and deliveries[-1] is final_delivery
                                                 and metrics.get("status") == "done" and metrics.get("delivered") is True
                                                 and metrics.get("report_quality_passed") is True)
        if final_delivery:
            self.check(final_delivery["output"] == metrics.get("delivery"), "Final event delivery differs from metrics")
            self._final(final_delivery)
        else:
            self.result["final"] = None
        # A real business failure can have intact evidence. Keep the two distinct.
        self.result["business_failure"] = None if self.result["business_delivered"] else {
            "status": metrics.get("status"), "reason": "No final accepted delivery", "finish_reason": metrics.get("finish_reason")}

    def _requests(self):
        costs = jsonlines(self.path / "cost-ledger.jsonl")
        self.costs = costs
        costs_by_id = {r["request_id"]: r for r in costs}
        paths = {p.name.removesuffix(".request.json"): p for p in (self.path / "model-requests").glob("*.request.json")}
        self.check(len(costs) == len(costs_by_id) and set(paths) == set(costs_by_id), "API request files/ledger IDs differ")
        ordered = sorted(costs, key=lambda r: r.get("request_sequence", 0))
        totals, charges, cloud, requests = Counter(), Counter(), {}, []
        schemas, systems, configs = {}, {}, {}
        for cost in ordered:
            rid = cost["request_id"]
            try:
                req = read(paths[rid])
                usage, calls = response_data(paths[rid].with_name(rid + ".response.txt"))
                self.check(hashlib.sha256(json.dumps(req, ensure_ascii=False).encode()).hexdigest() == cost.get("request_sha256"),
                           "Saved API request hash differs from metered request", request_id=rid)
                self.check(isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in USAGE),
                           "Missing/incomplete actual provider usage", request_id=rid)
                if not isinstance(usage, dict):
                    usage = {}
                self.check(all(usage.get(k) == cost.get("usage", {}).get(k) for k in USAGE), "Raw API/ledger usage mismatch", request_id=rid)
                self.check(usage.get("prompt_tokens") == usage.get("prompt_cache_hit_tokens", 0) + usage.get("prompt_cache_miss_tokens", 0)
                           and usage.get("total_tokens") == usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
                           "Provider token sum mismatch", request_id=rid)
                estimates = {}
                for period in ("peak", "offpeak"):
                    prices = self.manifest["pricing"][period]
                    estimates[period] = (usage.get("prompt_cache_miss_tokens", 0) * prices["input_miss"]
                                         + usage.get("prompt_cache_hit_tokens", 0) * prices["input_hit"]
                                         + usage.get("completion_tokens", 0) * prices["output"]) / 1e6
                    self.check(cost.get(period + "_estimate_cny") is not None and math.isclose(
                        cost[period + "_estimate_cny"], estimates[period], abs_tol=1e-12), "Token price recomputation differs", request_id=rid, period=period)
                    charges[period] += estimates[period]
                totals.update({k: usage.get(k, 0) for k in USAGE})
                system = [msg for msg in req.get("messages", []) if msg.get("role") == "system"]
                config = {k: v for k, v in req.items() if k not in {"messages", "tools", "dsh_plugin_packages"}}
                schemas[digest(req.get("tools", []))] = req.get("tools", [])
                systems[digest(system)] = {"raw": system, "normalized": self.normalize_runtime(system)}
                configs[digest(config)] = config
                self.check(req.get("model") == self.manifest.get("model"), "Actual request model differs from manifest", request_id=rid)
                for call in calls:
                    self.check(call["id"] not in cloud, "Duplicate cloud tool call ID", call_id=call["id"])
                    cloud[call["id"]] = {**call, "request_id": rid, "request_sequence": cost.get("request_sequence")}
                requests.append({"request_id": rid, "sequence": cost.get("request_sequence"), "status": cost.get("status"),
                                 "usage": usage, "peak_estimate_cny": estimates["peak"], "offpeak_estimate_cny": estimates["offpeak"],
                                 "tool_call_ids": [c["id"] for c in calls], "tool_names": [c["name"] for c in calls],
                                 "phase": ("semantic" if any(c["name"].removeprefix(PREFIX) in SEMANTIC for c in calls)
                                           else "execution" if calls else "no_tool_response"),
                                 "schema_sha256": digest(req.get("tools", [])), "system_sha256": digest(system),
                                 "model_config_sha256": digest(config), "dsh_plugin_packages": req.get("dsh_plugin_packages"),
                                 "elapsed_seconds": cost.get("elapsed_seconds")})
                if len(requests) == 1:
                    initial = [msg for msg in req.get("messages", []) if msg.get("role") != "system"]
                    self.result["initial_non_system_messages"] = initial
                    self.result["initial_context_normalized"] = self.normalize_runtime(initial)
            except Exception as error:
                self.check(False, "Cannot audit recorded API request", request_id=rid, error=f"{type(error).__name__}: {error}")
        self.cloud = cloud
        self.result.update(requests=requests, systems=systems, model_configs=configs,
                           tool_schemas=schemas,
                           runtime_patch=read(self.path / "runtime.patch.yml"),
                           normalization={"allowed": ["recorded absolute run root", "manifest session_id", "manifest run_id"],
                                          "note": "Only these explicit values are replaced; unknown nonce differences remain visible. No report text is normalized."})
        self.check(len(paths) == self.metrics.get("upstream_requests"), "API count differs from metrics")
        self.check(dict(totals) == self.metrics.get("usage"), "Aggregate usage differs from metrics")
        for period in ("peak", "offpeak"):
            self.check(math.isclose(charges[period], self.metrics.get(period + "_estimate_cny", -1), abs_tol=1e-10), "Aggregate cost differs from metrics", period=period)
        self.check(self.metrics.get("unknown_cost_requests", 0) == 0, "Unknown cost requests remain")
        self.check(len(schemas) == 1, "Tool schemas/order/descriptions changed within run or absent")
        self.result["accounting"] = {"llm_requests": len(paths), "mcp_calls": len(self.rows),
            "usage": dict(totals), "peak_estimate_cny": charges["peak"], "offpeak_estimate_cny": charges["offpeak"],
            "failed_http_requests": sum(r.get("status") != 200 for r in costs),
            "unknown_cost_requests": self.metrics.get("unknown_cost_requests"),
            "elapsed_seconds": self.metrics.get("elapsed_seconds"),
            "phases": {phase: {"requests": sum(r["phase"] == phase for r in requests),
                       "peak_estimate_cny": sum(r["peak_estimate_cny"] for r in requests if r["phase"] == phase)}
                       for phase in ("semantic", "execution", "no_tool_response")}}

    def _calls(self):
        attempts = {r["call_id"]: r for r in self.audit_rows if r.get("kind") == "motif_bypass_attempt"}
        verified = [r for r in self.audit_rows if r.get("kind") == "model_request_skipped_verified"]
        verified_ids = {r["call_id"] for r in verified}
        by_id = {r["call_id"]: r for r in self.rows}
        self.check(len(verified_ids) == len(verified), "Duplicate verified bypass count")
        seen = {}
        for row in self.rows:
            cid = row["call_id"]
            cloud, motif = self.cloud.get(cid), attempts.get(cid)
            self.check(bool(cloud) != bool(motif), "MCP call has missing or ambiguous origin", call_id=cid)
            row["origin"] = "llm" if cloud else "motif" if motif else "unknown"
            row["verified_bypass"] = cid in verified_ids
            if cloud:
                row["request_id"] = cloud["request_id"]
                self.check(row["tool"] == cloud["name"] and row["arguments"] == parse_args(cloud["arguments"]),
                           "MCP call differs from cloud function call", call_id=cid)
            frozen = self.result.get("frozen_decisions")
            decision = {PREFIX + "approve_workflow": "plan", PREFIX + "approve_interpretation": "commentary"}.get(row["tool"])
            if frozen and decision and row["success"]:
                self.check(row["origin"] == "llm" and isinstance(row["arguments"], dict)
                           and digest(row["arguments"].get(decision)) == digest(frozen.get(decision)),
                           "Accepted semantic decision differs from frozen input or is not a real LLM call", call_id=cid)
            if motif:
                self.check(row["tool"] == motif["tool"] and row["arguments"] == motif["arguments"], "MCP call differs from bypass audit", call_id=cid)
                previous = by_id.get(motif.get("after_call_id"))
                self.check(previous is not None and previous["success"] and previous["step"] < row["step"],
                           "Motif lacks successful earlier receipt", call_id=cid)
                if previous:
                    self.check((previous["output"] or {}).get("_provenance", {}).get("record_sha256") == motif.get("record_sha256"),
                               "Motif source receipt hash differs", call_id=cid)
            key = digest([row["tool"], row["arguments"]])
            row["repeat_of_step"] = seen.get(key)
            seen.setdefault(key, row["step"])
            if row["output"] and row["output"].get("_provenance"):
                try:
                    self.receipt(row["output"])
                except Exception as error:
                    self.check(False, "Cannot verify MCP output receipt", call_id=cid, error=f"{type(error).__name__}: {error}")
        for event in verified:
            row = by_id.get(event["call_id"])
            self.check(row is not None and row["success"] and row["origin"] == "motif" and row["tool"] == event.get("tool"),
                       "Verified bypass lacks actual successful MCP result", call_id=event["call_id"])
        self.check(set(self.cloud).issubset(by_id), "Cloud function calls missing from MCP events")
        self.check(set(attempts).issubset(by_id), "Bypass attempts missing from MCP events")
        self.check(len(self.rows) == self.metrics.get("tool_calls"), "MCP count differs from metrics")
        self.check(len(verified) == self.metrics.get("verified_motif_bypasses"), "Bypass count differs from metrics")
        self.result["accounting"].update(verified_bypasses=len(verified), bypass_attempts=len(attempts),
            tool_failures=sum(not r["success"] for r in self.rows), repeated_identical_calls=sum(r["repeat_of_step"] is not None for r in self.rows))
        self.result["tool_sequence"] = self.rows
        self.result["successful_tool_order"] = [r["tool"].removeprefix(PREFIX) for r in self.rows if r["success"]]
        self.result["complete_tool_order"] = [r["tool"].removeprefix(PREFIX) for r in self.rows]

    def _layouts(self):
        layouts, seen_ids, unique_candidates = [], set(), 0
        for row in self.rows:
            if row["tool"] != PREFIX + "layout_report":
                continue
            output = row["output"] or {}
            item = {"step": row["step"], "call_id": row["call_id"], "origin": row["origin"],
                    "draft_id": (row["arguments"] or {}).get("draft_id") if isinstance(row["arguments"], dict) else None,
                    "success": row["success"], "cache_reused": output.get("cache_reused"),
                    "warnings": output.get("warnings"), "failed_checks": output.get("failed_checks"),
                    "repeat_of_step": row["repeat_of_step"]}
            try:
                if output.get("layout_id"):
                    layout = self.record(output["layout_id"], "report_layout")
                    engine = layout["engine"]
                    item.update(layout_id=output["layout_id"], engine_version=layout.get("engine_version", engine.get("engine_version")),
                                selected_attempt=engine.get("selected_attempt"), selected_config=engine.get("selected_config"),
                                candidates=engine.get("attempts", []), candidate_count=len(engine.get("attempts", [])),
                                audit=engine.get("audit"), page_count=engine.get("page_count"))
                    if output["layout_id"] not in seen_ids:
                        unique_candidates += len(engine.get("attempts", []))
                    seen_ids.add(output["layout_id"])
                    if layout.get("engine_result_path"):
                        p = self.local(layout["engine_result_path"])
                        self.check(file_sha(p) == layout["engine_result_sha256"], "Saved layout engine result hash mismatch", step=row["step"])
                        self.check(read(p) == engine, "Saved layout engine result differs from record", step=row["step"])
                    for candidate in engine.get("attempts", []):
                        if candidate.get("path") and candidate.get("sha256"):
                            self.check(file_sha(self.local(candidate["path"])) == candidate["sha256"], "Layout candidate file hash mismatch", step=row["step"], attempt=candidate.get("attempt"))
            except Exception as error:
                self.check(False, "Cannot audit layout attempt", step=row["step"], error=f"{type(error).__name__}: {error}")
            layouts.append(item)
        drafts = {r["draft_id"] for r in layouts if r["draft_id"]}
        approvals = Counter(r["tool"].removeprefix(PREFIX) for r in self.rows if r["success"] and r["tool"].removeprefix(PREFIX) in SEMANTIC)
        self.result["layout"] = {"calls": layouts, "layout_calls": len(layouts), "distinct_drafts": len(drafts),
            "distinct_layout_receipts": len(seen_ids), "internal_candidates_per_call": sum(r.get("candidate_count", 0) for r in layouts),
            "unique_recorded_candidates": unique_candidates,
            "rendered_candidates_excluding_explicit_cache_hits": sum(r.get("candidate_count", 0) for r in layouts if r["cache_reused"] is not True),
            "cache_hits": sum(r["cache_reused"] is True for r in layouts),
            "agent_rework": {"same_draft_layout_repeats": sum(r["repeat_of_step"] is not None for r in layouts),
                             "additional_drafts": max(0, len(drafts) - 1), "successful_semantic_approvals": dict(approvals)},
            "note": "Tool-internal layout candidates and additional agent calls are different quantities; cache hits do not mean new rendering."}

    def _final(self, delivery_row):
        output = delivery_row["output"]
        receipt = self.receipt(output)
        self.check(receipt["id"] == output.get("delivery_id") and receipt["kind"] == "delivery", "Final delivery receipt mismatch")
        delivery = self.record(output["delivery_id"], "delivery")
        verification = self.record(delivery["verification_id"], "report_verification")
        report = self.record(delivery["report_id"], "report")
        layout = self.record(report["layout_id"], "report_layout")
        draft = self.record(report["draft_id"], "report_draft")
        packet = self.record(draft["packet_id"], "evidence_packet")
        evidence = self.record(packet["evidence_id"], "evidence")
        plan = self.record(draft["plan_id"], "analysis_plan")
        analysis = self.record(draft["analysis_id"], "analysis")
        bundle = self.record(packet["figure_bundle_id"], "figure_bundle")
        final_ids = [output["delivery_id"], delivery["verification_id"], delivery["report_id"], report["layout_id"],
                     report["draft_id"], draft["packet_id"], packet["evidence_id"], draft["plan_id"],
                     draft["analysis_id"], packet["figure_bundle_id"]]
        returned_ids = {PurePosixPath(str((r["output"] or {}).get("_provenance", {}).get("record_path", "")).replace("\\", "/")).stem
                        for r in self.rows if r["success"]}
        self.check(set(final_ids).issubset(returned_ids), "Final chain has a record absent from successful MCP receipts")
        self.check(delivery["verification_id"] == delivery_row["arguments"].get("verification_id"), "Delivery argument lineage mismatch")
        self.check(verification["report_id"] == delivery["report_id"] and layout["draft_id"] == report["draft_id"], "Report/draft lineage mismatch")
        self.check(all(p.get("plan_id") == draft["plan_id"] for p in (delivery, verification, report, layout, packet, evidence, analysis, bundle)),
                   "Final artifact chain uses different plans")
        self.check(all(p.get("analysis_id") == draft["analysis_id"] for p in (packet, evidence, bundle)), "Final artifact chain uses different analyses")
        self.check(bundle["evidence_id"] == packet["evidence_id"] and evidence["workflow"] == plan["workflow"], "Final evidence/workflow lineage mismatch")
        self.check(all(p.get("quality_passed") is True for p in (delivery, verification, report, layout["engine"], packet)), "Final artifact chain contains failed quality gate")
        pdf = self.local(delivery["path"])
        actual_sha = file_sha(pdf)
        self.check(all(p.get("path") == delivery["path"] and p.get("sha256") == actual_sha for p in (output, delivery, verification, report, layout["engine"])), "Final PDF hash/path binding mismatch")
        doc = deepcopy(draft["document"])
        figures = []
        from PIL import Image
        for index, figure in enumerate(doc["figures"]):
            p = self.local(figure["path"])
            with Image.open(p) as image:
                rgba = image.convert("RGBA")
                pixels = hashlib.sha256(canonical({"size": list(rgba.size), "mode": "RGBA"}) + rgba.tobytes()).hexdigest()
                size = list(rgba.size)
            figures.append({"index": index, "path": str(p), "original_path": figure["path"], "file_sha256": file_sha(p),
                            "rgba_sha256": pixels, "size": size, "kind": figure.get("kind"), "caption": figure.get("caption")})
            figure["path"] = {"png_file_sha256": file_sha(p), "decoded_rgba_sha256": pixels, "size": size}
            self.check(index < len(bundle["figures"]) and bundle["figures"][index]["paths"]["png"] == figures[-1]["original_path"]
                       and bundle["figures"][index]["sha256"]["png"] == file_sha(p), "Draft PNG differs from verified figure bundle", index=index)
        self.check(len(doc["figures"]) == len(bundle["figures"]), "Final document figure count differs from verified bundle")
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        with fitz.open(pdf) as pdf_document:
            texts = [page.get_text("text") for page in pdf_document]
            pdf_info = {"file_sha256": actual_sha, "page_count": len(pdf_document), "text_by_page": texts,
                        "text_sha256": digest(texts), "metadata": pdf_document.metadata,
                        "page_sizes": [[page.rect.width, page.rect.height] for page in pdf_document]}
        self.check(pdf_info["page_count"] == delivery["page_count"] == output["page_count"] == layout["engine"]["page_count"], "Actual PDF page count differs from delivery")
        commentary = {key: evidence.get(key) for key in ("custom_commentary_template", "custom_commentary",
                      "research_options_template", "research_options", "comparison_summary_template", "comparison_summary", "interpretation_approved")}
        final = {"delivery_id": output["delivery_id"], "report_id": delivery["report_id"], "layout_id": report["layout_id"],
                 "draft_id": report["draft_id"], "plan_id": draft["plan_id"], "analysis_id": draft["analysis_id"],
                 "evidence_id": packet["evidence_id"], "figure_bundle_id": packet["figure_bundle_id"],
                 "delivery_event_step": delivery_row["step"], "pdf_path": str(pdf), "workflow": plan["workflow"],
                 "workflow_sha256": digest(plan["workflow"]), "commentary": commentary, "commentary_sha256": digest(commentary),
                 "document": doc, "document_sha256": digest(doc), "figures": figures, "pdf": pdf_info,
                 "statistics": analysis.get("statistics"), "diagnostics": analysis.get("diagnostics"),
                 "warnings": delivery.get("warnings", verification.get("audit", {}).get("soft_warnings", [])),
                 "audit": verification.get("audit"),
                 "record_chain": [{"id": record["id"], "kind": record["kind"], "source_version": record["source_version"],
                                   "record_sha256": file_sha(self.path / "workspace" / "records" / (record["id"] + ".json"))}
                                  for record in (self.records[identifier] for identifier in final_ids)]}
        self.result["final"] = final


def compare_pair(case, baseline, execute, controlled=True):
    pair = {"case_id": case, "baseline": baseline.get("name") if baseline else None,
            "execute": execute.get("name") if execute else None, "controlled": controlled, "checks": {}, "mismatches": []}
    if baseline is None or execute is None:
        pair.update(passed=False, error="Pair must contain exactly one baseline and one execute run")
        return pair
    checks = pair["checks"]

    def compare(label, left, right, required=True):
        equal = left is not None and right is not None and left == right
        checks[label] = {"equal": equal, "required": required, "baseline_sha256": digest(left), "execute_sha256": digest(right)}
        if not equal:
            pair["mismatches"].append({"field": label, "required": required, "differences": differences(left, right)})
    bm, em = baseline.get("manifest", {}), execute.get("manifest", {})
    compare("input_file_bytes", baseline.get("source_sha256"), execute.get("source_sha256"))
    for key in ("input_content_digest", "prompt_sha256", "question", "contracts_digest", "tool_order", "model", "provider", "thinking",
                "reasoning_effort", "max_requests", "max_output", "compression", "automatic_retries", "benchmark_code_sha256", "budget_implementation_sha256",
                "pricing", "python", "node", "dsh", "python_sdk"):
        compare(key, bm.get(key), em.get(key))
    compare("runtime_patch", baseline.get("runtime_patch"), execute.get("runtime_patch"))
    compare("scenario_scoped_paths", baseline.get("scenario_scoped_paths"), execute.get("scenario_scoped_paths"))
    compare("runtime_tool_schemas_and_order", baseline.get("tool_schemas"), execute.get("tool_schemas"))
    compare("actual_model_configuration", baseline.get("model_configs"), execute.get("model_configs"))
    compare("raw_system_messages", sorted(baseline.get("systems", {})), sorted(execute.get("systems", {})), False)
    compare("scoped_system_messages", sorted({digest(s["normalized"]) for s in baseline.get("systems", {}).values()}),
            sorted({digest(s["normalized"]) for s in execute.get("systems", {}).values()}))
    compare("initial_context_scoped_paths", baseline.get("initial_context_normalized"), execute.get("initial_context_normalized"))
    compare("frozen_decisions", baseline.get("frozen_decisions"), execute.get("frozen_decisions"), controlled)
    bf, ef = baseline.get("final"), execute.get("final")
    pair["both_delivered"] = baseline.get("business_delivered") is True and execute.get("business_delivered") is True
    pair["both_evidence_passed"] = baseline.get("evidence_passed") is True and execute.get("evidence_passed") is True
    if bf and ef:
        for key in ("workflow", "commentary", "document", "statistics", "diagnostics"):
            compare(key, bf.get(key), ef.get(key), controlled)
        for label, field in (("PNG_file_bytes", "file_sha256"), ("PNG_decoded_pixels", "rgba_sha256")):
            compare(label, [f[field] for f in bf["figures"]], [f[field] for f in ef["figures"]], controlled)
        compare("PDF_text_exact_by_page", bf["pdf"]["text_by_page"], ef["pdf"]["text_by_page"], controlled)
        compare("PDF_page_count", bf["pdf"]["page_count"], ef["pdf"]["page_count"], controlled)
        compare("PDF_bytes", bf["pdf"]["file_sha256"], ef["pdf"]["file_sha256"], False)
        pair["PDF_metadata"] = {"baseline": bf["pdf"]["metadata"], "execute": ef["pdf"]["metadata"]}
    else:
        checks["final_artifacts_available"] = {"equal": False, "required": True}
    compare("complete_tool_order", baseline.get("complete_tool_order"), execute.get("complete_tool_order"), False)
    compare("successful_tool_order", baseline.get("successful_tool_order"), execute.get("successful_tool_order"), False)
    pair["accounting"] = {"baseline": baseline.get("accounting"), "execute": execute.get("accounting")}
    if baseline.get("accounting") and execute.get("accounting"):
        pair["execute_minus_baseline"] = {key: execute["accounting"][key] - baseline["accounting"][key]
            for key in ("llm_requests", "mcp_calls", "verified_bypasses", "tool_failures", "peak_estimate_cny", "offpeak_estimate_cny", "elapsed_seconds")}
    pair["passed"] = bool(pair["both_delivered"] and pair["both_evidence_passed"]
                          and all(item["equal"] for item in checks.values() if item["required"]))
    return pair


def audit_library(path, objects, formal_names):
    issues, witness_rows = [], []
    if not Path(path).is_file():
        return {"passed": False, "issues": ["Library file missing"], "path": str(path)}
    library = read(path)
    by_run_id = {obj.manifest.get("run_id"): obj for obj in objects.values()}
    if digest({k: v for k, v in library.items() if k != "library_digest"}) != library.get("library_digest"):
        issues.append("Library content digest mismatch")
    for field in ("contracts", "tool_schemas"):
        if digest(library.get(field)) != library.get(field + "_digest"):
            issues.append(field + " digest mismatch")
    for edge in library.get("artifacts", []):
        row = {"motif_id": edge["motif_id"], "from_tool": edge["from_tool"], "to_tool": edge["to_tool"], "witnesses": []}
        train_csv, cert_csv = set(), set()
        for phase, evidence in [("training", e) for e in edge["training_evidence"]] + [("certification", edge["certification_evidence"])]:
            obj = by_run_id.get(evidence["run_id"])
            valid = obj is not None and obj.path.name not in formal_names
            if obj:
                valid &= obj.result.get("business_delivered") is True and obj.manifest.get("mode") == "baseline"
                valid &= evidence["events_sha256"] == file_sha(obj.path / "agent-events.jsonl")
                (train_csv if phase == "training" else cert_csv).add(obj.source_hashes.get("data.csv"))
                by_call = {r["call_id"]: r for r in obj.rows}
                for witness in evidence.get("witnesses", []):
                    a, b = by_call.get(witness["from_call_id"]), by_call.get(witness["to_call_id"])
                    valid &= bool(a and b and a["success"] and b["success"] and a["origin"] == b["origin"] == "llm")
                    if a and b:
                        valid &= (a["tool"] == edge["from_tool"] and b["tool"] == edge["to_tool"] and b["step"] == a["step"] + 1
                                  and digest(a["output"]) == witness["from_output_sha256"] and digest(b["arguments"]) == witness["to_arguments_sha256"]
                                  and b["arguments"] == {edge["to_param"]: a["output"].get(edge["from_field"])}
                                  and edge["to_tool"].removeprefix(PREFIX) in a["output"].get("_provenance", {}).get("authorized_tools", []))
            row["witnesses"].append({"phase": phase, "run_id": evidence["run_id"], "valid": bool(valid)})
            if not valid:
                issues.append(f"Invalid/missing {phase} witness: {edge['motif_id']} {evidence['run_id']}")
        if len(train_csv) < 2 or len(cert_csv) != 1 or train_csv & cert_csv or None in train_csv | cert_csv:
            issues.append("Need two independent training CSVs and independent confirmation: " + edge["motif_id"])
        witness_rows.append(row)
    used_csv = set(library.get("training_csv_sha256", [])) | {library.get("certification_csv_sha256")}
    motif_by_id = {edge["motif_id"]: edge for edge in library.get("artifacts", [])}
    for name in formal_names:
        obj = objects.get(name)
        if not obj or not hasattr(obj, "source_hashes"):
            continue
        if obj.source_hashes.get("data.csv") in used_csv:
            issues.append("Formal input reused training/cert CSV: " + name)
        if obj.manifest.get("mode") == "execute":
            if obj.manifest.get("library_digest") != library.get("library_digest"):
                issues.append("Formal execute library differs: " + name)
            by_call = {r["call_id"]: r for r in obj.rows}
            for attempt in getattr(obj, "audit_rows", []):
                if attempt.get("kind") != "motif_bypass_attempt":
                    continue
                edge, before = motif_by_id.get(attempt.get("motif_id")), by_call.get(attempt.get("after_call_id"))
                if not edge or not before or (attempt.get("certified_digest") != edge["certified_digest"]
                    or before["tool"] != edge["from_tool"] or attempt["tool"] != edge["to_tool"]
                    or attempt["arguments"] != {edge["to_param"]: (before["output"] or {}).get(edge["from_field"])}):
                    issues.append("Actual bypass is not a learned witnessed edge: " + name + "/" + attempt.get("call_id", "?"))
    return {"path": str(path), "file_sha256": file_sha(path), "library_digest": library.get("library_digest"),
            "passed": not issues, "issues": issues, "edge_count": len(witness_rows), "edges": witness_rows,
            "meaning": "Tools and authorized successors are manually designed; the compiler records independently witnessed receipt transfers, not autonomous workflow discovery or formal proof."}


def summarize(rows):
    by_mode = {}
    for mode in sorted({r.get("mode", r["job"].get("mode", "baseline")) for r in rows}):
        selected = [r for r in rows if r.get("mode", r["job"].get("mode", "baseline")) == mode]
        by_mode[mode] = {"runs": len(selected), "delivered": sum(r.get("business_delivered") is True for r in selected),
            "evidence_passed": sum(r.get("evidence_passed") is True for r in selected),
            **{key: sum(r.get("accounting", {}).get(key, 0) or 0 for r in selected)
               for key in ("llm_requests", "mcp_calls", "verified_bypasses", "tool_failures", "peak_estimate_cny", "offpeak_estimate_cny", "elapsed_seconds")}}
    return by_mode


def audit(experiment, evaluation, natural, training, library, expected_pairs=4):
    experiment = Path(experiment)
    groups, issues, objects, results = {}, [], {}, {}
    for group, path in (("evaluation", evaluation), ("natural", natural), ("training", training)):
        try:
            jobs = read(path)
            if not isinstance(jobs, list) or not jobs:
                raise ValueError("Matrix must be a nonempty list")
        except Exception as error:
            issues.append({"issue": "Cannot read explicit matrix", "group": group, "path": str(path), "error": str(error)})
            jobs = []
        groups[group] = []
        for job in jobs:
            name = job.get("name")
            if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]{1,100}", name) or name in objects:
                issues.append({"issue": "Unsafe/duplicate matrix run name", "name": name, "group": group})
                continue
            obj = RunAudit(experiment / "runs" / name, job, group)
            objects[name], results[name] = obj, obj.run()
            groups[group].append(name)
    unlisted = sorted(p.name for p in (experiment / "runs").iterdir() if p.is_dir() and p.name not in objects) if (experiment / "runs").exists() else []
    unlisted_details = []
    for name in unlisted:
        p = experiment / "runs" / name / "metrics.json"
        unlisted_details.append({"name": name, "metrics": read(p) if p.is_file() else None,
                                 "note": "Not in the predeclared matrices; preserved separately and excluded from pair totals."})
    pairs_by_group = {}
    for group in ("evaluation", "natural"):
        cases = defaultdict(lambda: defaultdict(list))
        for name in groups[group]:
            row = results[name]
            # Optional pair_id/repetition avoids ever selecting the 'best' repeat.
            key = row["job"].get("pair_id") or row["job"].get("case") or row.get("case_id") or name
            if row["job"].get("repetition") is not None:
                key += ":" + str(row["job"]["repetition"])
            cases[key][row["job"].get("mode", "baseline")].append(row)
        pairs = []
        for case, arms in sorted(cases.items()):
            valid = set(arms) == {"baseline", "execute"} and all(len(arm) == 1 for arm in arms.values())
            if not valid:
                pairs.append({"case_id": case, "passed": False, "error": "Need exactly one run per arm; no selection among duplicates",
                              "runs": {mode: [r["name"] for r in rows] for mode, rows in arms.items()}})
            else:
                pairs.append(compare_pair(case, arms["baseline"][0], arms["execute"][0], group == "evaluation"))
        pairs_by_group[group] = pairs
    if len(pairs_by_group["evaluation"]) != expected_pairs or len(groups["evaluation"]) != 2 * expected_pairs:
        issues.append({"issue": "Formal matrix cardinality mismatch", "expected_pairs": expected_pairs,
                       "actual_pairs": len(pairs_by_group["evaluation"]), "actual_runs": len(groups["evaluation"])})
    try:
        library_audit = audit_library(library, objects, set(groups["evaluation"]))
    except Exception as error:
        library_audit = {"passed": False, "issues": [f"Cannot audit library: {type(error).__name__}: {error}"]}
    return {"audit_version": 1, "experiment": str(experiment.resolve()), "auditor_sha256": file_sha(__file__),
        "passed": not issues and library_audit["passed"] and all(r["evidence_passed"] for r in results.values())
                  and all(pair["passed"] for pair in pairs_by_group["evaluation"]),
        "issues": issues, "matrices": {"evaluation": str(evaluation), "natural": str(natural), "training": str(training)},
        "groups": groups, "group_totals": {group: summarize([results[n] for n in names]) for group, names in groups.items()},
        "formal_pairs": pairs_by_group["evaluation"], "natural_diagnostic_pairs": pairs_by_group["natural"],
        "library": library_audit, "runs": results, "unlisted_runs": unlisted_details,
        "limitations": [
            "Frozen semantic decisions isolate deterministic continuation; they do not measure autonomous scientific planning or writing ability.",
            "All actual API calls, failed tools, repeats and unsuccessful runs are retained. No best-run selection or rerun is performed.",
            "Costs are independently recomputed token estimates from recorded prices, not provider invoices. Semantic/execution phases label actual request contents; mixed requests count as semantic.",
            "Only exact document figure paths are replaced by verified image-content hashes. Scientific text, figures, numbers, order and source provenance remain intact.",
            "PDF byte inequality alone is not a content failure: creation metadata or document IDs can differ. Actual per-page extracted text, page count, PNG bytes and decoded pixels are compared separately without deleting substantive content.",
            "Known run root/session/run identifiers may differ in initial runtime context. Raw system messages remain recorded; unknown nonce differences are not silently normalized.",
            "Automatic byte/lineage/layout checks are not independent expert review of scientific claims or visual aesthetics."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve()
    repo_default = next((p for p in here.parents if (p / "benchmarks" / "research_report_agent_v2").is_dir()),
                        here.parents[1] / "data-analysis-agent-reference")
    parser.add_argument("--repo", type=Path, default=repo_default)
    parser.add_argument("--experiment", type=Path, default=Path(".local/research-report-agent-v22-20261010"))
    for name in ("evaluation", "natural", "training", "library", "output"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--expected-pairs", type=int, default=4)
    args = parser.parse_args()
    if not args.experiment.is_absolute():
        args.experiment = args.repo / args.experiment
    paths = {name: getattr(args, name) or args.experiment / (name + ".json") for name in ("evaluation", "natural", "training", "library")}
    output = args.output or args.experiment / "review" / "matched-summary.json"
    result = audit(args.experiment, **paths, expected_pairs=args.expected_pairs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "formal_pairs": len(result["formal_pairs"]),
                      "matched_pairs_passed": sum(p["passed"] for p in result["formal_pairs"]),
                      "runs": len(result["runs"]), "output": str(output.resolve()),
                      "group_totals": result["group_totals"]}, ensure_ascii=False))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
