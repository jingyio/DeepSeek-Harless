"""Independent raw-log/hash/accounting primitives for the v3 reviewer.

Adapted from our independently tested v2.2 review script, not from benchmark
runner/tools/compiler/evaluator code. No model or network calls, no file writes.
Semantic and report-specific checks live in audit_runs.py.
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


SEMANTIC = {"inspect_study", "approve_analysis", "approve_presentation", "submit_report_text"}


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


class EvidenceRun:
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
                       "peak_estimate_cny": sum(r["peak_estimate_cny"] for r in requests if r["phase"] == phase),
                       "offpeak_estimate_cny": sum(r["offpeak_estimate_cny"] for r in requests if r["phase"] == phase),
                       "usage": dict(sum((Counter({k: r["usage"].get(k, 0) for k in USAGE}) for r in requests if r["phase"] == phase), Counter()))}
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
            if row["tool"].removeprefix(PREFIX) in SEMANTIC:
                self.check(row["origin"] == "llm", "Semantic call must originate in an actual model response", call_id=cid)
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


