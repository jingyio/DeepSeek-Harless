#!/usr/bin/env python3
"""Bound model-turn opportunities of safe read edges in one real DSH trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = (ROOT / ".local").resolve()
sys.path.insert(0, str(ROOT))

# Explicit estimate for the frozen 2026-09-27 DeepSeek Flash off-peak runs.
# Changing the model or price requires a new audit, not a reused savings claim.
OFFPEAK_USD_PER_MILLION = {"miss": 0.15, "hit": 0.003, "output": 0.6}

from src.adapters.dsh_trajectory import extract_dsh_trace, infer_dsh_provenance  # noqa: E402
from src.adapters.tool_contract_loader import parse_tool_contracts  # noqa: E402
from src.motif_core.offline.edge_compiler import safe_edge_witnesses  # noqa: E402


def audit(events: list[dict], contracts: dict, *, trace_id: str) -> dict:
    trace = extract_dsh_trace(
        events, contracts, trace_id=trace_id, task_fingerprint=trace_id,
        provenance_by_call_id=infer_dsh_provenance(events, contracts))
    call_steps = {}
    calls_per_step = Counter()
    model_messages = Counter()
    prompt_tokens = Counter()
    usage_by_step = defaultdict(lambda: {"miss": 0, "hit": 0, "output": 0})
    for offset, event in enumerate(events):
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        step = data.get("step")
        if type(step) is not int:
            continue
        if event.get("type") == "tool/call":
            raw_seq = event.get("seq", offset)
            call_steps[raw_seq if isinstance(raw_seq, int) else offset] = step
            calls_per_step[step] += 1
        elif event.get("type") == "assistant/message":
            usage = data.get("usage")
            if isinstance(usage, dict):
                model_messages[step] += 1
                for key, field in (("miss", "inputTokens"), ("hit", "cacheReadTokens"),
                                   ("output", "outputTokens")):
                    value = usage.get(field) or 0
                    if type(value) is not int or value < 0:
                        raise ValueError(f"invalid {field} usage at step {step}")
                    usage_by_step[step][key] += value
                prompt_tokens[step] += int(usage.get("inputTokens") or 0)
                prompt_tokens[step] += int(usage.get("cacheReadTokens") or 0)
    edges = {
        (source["from_tool"], source["from_field"], record.name, param)
        for record in trace.records if record.eligible
        for param, source in (record.parameter_sources or {}).items()
    }
    safe_targets = defaultdict(set)
    safe_bindings = defaultdict(set)
    by_edge = []
    for from_tool, from_field, to_tool, to_param in sorted(edges):
        candidate = {"status": "candidate_only", "from_tool": from_tool,
                     "from_field": from_field, "to_tool": to_tool,
                     "to_param": to_param}
        pairs = safe_edge_witnesses(candidate, trace, contracts)
        cross_step = 0
        same_step = 0
        for source, target in pairs:
            source_step = call_steps.get(source.event_seq)
            target_step = call_steps.get(target.event_seq)
            if source_step is None or target_step is None:
                raise ValueError("safe witness lacks a model step")
            if source_step == target_step:
                same_step += 1
            elif source_step < target_step:
                cross_step += 1
                safe_targets[target_step].add(target.event_seq)
                safe_bindings[target.event_seq].add(to_param)
            else:
                raise ValueError("safe witness steps are out of order")
        by_edge.append({"from_tool": from_tool, "to_tool": to_tool,
                        "safe_pairs": len(pairs), "cross_step_pairs": cross_step,
                        "same_step_pairs": same_step})
    fully_bound = set()
    unresolved_slots = Counter()
    for record in trace.records:
        bound = safe_bindings.get(record.event_seq, set())
        contract = contracts.get(record.name)
        if not bound or contract is None or not isinstance(record.arguments, dict):
            continue
        defaults = dict(contract.default_params)
        optional = set(record.arguments) - set(contract.required_params)
        for param in set(contract.required_params) - bound:
            unresolved_slots[(record.name, param)] += 1
        for param in optional:
            if param not in defaults or record.arguments[param] != defaults[param]:
                unresolved_slots[(record.name, param)] += 1
        if (set(contract.required_params) <= bound
                and optional <= set(defaults)
                and all(record.arguments[key] == defaults[key] for key in optional)):
            fully_bound.add(record.event_seq)
    isolated = sorted(step for step, calls in calls_per_step.items()
                      if safe_targets.get(step)
                      and len(safe_targets[step] & fully_bound) == calls
                      and model_messages[step] > 0)
    isolated_usage = {key: sum(usage_by_step[step][key] for step in isolated)
                      for key in ("miss", "hit", "output")}
    isolated_cost = sum(isolated_usage[key] * rate / 1_000_000
                        for key, rate in OFFPEAK_USD_PER_MILLION.items())
    return {"trace_id": trace_id, "tool_calls": len(trace.records),
            "model_messages": sum(model_messages.values()),
            "safe_edges": by_edge,
            "cross_step_target_steps": sorted(safe_targets),
            "fully_bound_cross_step_targets": len(fully_bound),
            "unresolved_target_slots": [
                {"tool": tool, "parameter": param, "calls": count}
                for (tool, param), count in sorted(unresolved_slots.items())],
            "isolated_safe_target_steps": isolated,
            "isolated_target_model_turn_upper_bound": sum(model_messages[s] for s in isolated),
            "isolated_target_prompt_token_exposure": sum(prompt_tokens[s] for s in isolated),
            "isolated_target_usage_upper_bound": isolated_usage,
            "isolated_target_direct_offpeak_usd_upper_bound": round(isolated_cost, 8),
            "price_basis": "2026-09-27 DeepSeek Flash off-peak estimate; not provider bill",
            "interpretation": (
                "An isolated target step has only fully bound safe read calls and "
                "is still only an upper-bound opportunity. "
                "The model may have made a necessary semantic decision in that step, "
                "and removing it can change later prompts and cache hits. "
                "Neither count nor direct request price is a measured saving."
            )}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace-id", required=True)
    parser.add_argument("--contracts", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("events", type=Path)
    args = parser.parse_args()
    source = args.events.resolve(strict=True)
    output = args.out.resolve()
    if not source.is_relative_to(LOCAL) or not output.is_relative_to(LOCAL):
        parser.error("raw events and audit output must stay under .local")
    raw = source.read_bytes()
    events = [json.loads(line) for line in raw.decode("utf-8").splitlines()
              if line.strip()]
    specs = {}
    for path in args.contracts:
        incoming = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
        if specs.keys() & incoming.keys():
            parser.error("duplicate contract tool names")
        specs.update(incoming)
    result = audit(events, parse_tool_contracts(specs), trace_id=args.trace_id)
    result["events_sha256"] = hashlib.sha256(raw).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    output.chmod(0o600)
    print(json.dumps({"tool_calls": result["tool_calls"],
                      "cross_step_target_steps": len(result["cross_step_target_steps"]),
                      "isolated_target_model_turn_upper_bound":
                      result["isolated_target_model_turn_upper_bound"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
