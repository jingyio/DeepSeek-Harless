"""Check version-labelled raw-record claims against bound tool observations.

This guard verifies only explicit seed series in a finished draft. It neither
judges the scientific conclusion nor treats the absence of a detectable claim
as proof that the whole draft is correct.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from itertools import combinations
from typing import Any

from .dsh_event_projection import is_original_tool_result


def _tool_payloads(events: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    calls = {event["data"]["callId"]: event["data"]["name"]
             for event in events if event.get("type") == "tool/call"}
    found = []
    for event in events:
        if not is_original_tool_result(event):
            continue
        for block in event.get("data", {}).get("message", {}).get("content", []):
            if block.get("type") != "tool-result" or block.get("isError"):
                continue
            name = calls.get(block.get("toolCallId"), "").rsplit("__", 1)[-1]
            for item in block.get("content", []):
                if item.get("type") != "text":
                    continue
                try:
                    value = json.loads(item["text"])
                except (KeyError, TypeError, ValueError):
                    continue
                if isinstance(value, dict):
                    found.append((name, value))
    return found


def _version_label(object_id: str) -> str | None:
    match = re.search(r"run_\d{4}(w\d{2})$", object_id)
    return match.group(1) if match else None


def _series_by_group(rows: list[dict[str, Any]], dimensions: list[str],
                     changed: str) -> dict[tuple[Any, ...], tuple[int, ...]] | None:
    buckets: dict[tuple[Any, ...], list[tuple[int, int]]] = defaultdict(list)
    for row in rows:
        seed, value = row.get("seed"), row.get(changed)
        if type(seed) is not int or type(value) is not int:
            return None
        buckets[tuple(row.get(name) for name in dimensions)].append((seed, value))
    answer = {}
    for group, values in buckets.items():
        seeds = [seed for seed, _ in values]
        if len(values) < 2 or len(set(seeds)) != len(seeds):
            return None
        answer[group] = tuple(value for _, value in sorted(values))
    return answer


def _sequence_pattern(values: tuple[int, ...]) -> re.Pattern[str]:
    separator = r"\s*[/、，,]\s*"
    return re.compile(r"(?<!\d)" + separator.join(map(str, values)) + r"(?!\d)")


def _formal_simpson_reversal(rows: list[dict[str, Any]], contract: dict,
                             dimensions: list[str]) -> bool | None:
    """Test the strict pooled-versus-every-stratum sign reversal."""
    strata = [name for name in dimensions if name != "variant"]
    if len(strata) != 1:
        return None
    numerator, denominator = contract.get("numerator"), contract.get("denominator")
    if not isinstance(numerator, str) or not isinstance(denominator, str):
        return None
    pooled: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    grouped: dict[tuple[Any, str], list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        variant, stratum = row.get("variant"), row.get(strata[0])
        top, bottom = row.get(numerator), row.get(denominator)
        if (variant not in ("baseline", "candidate") or stratum is None or
                type(top) is not int or type(bottom) is not int or bottom <= 0):
            return None
        pooled[variant][0] += top
        pooled[variant][1] += bottom
        grouped[(stratum, variant)][0] += top
        grouped[(stratum, variant)][1] += bottom
    if set(pooled) != {"baseline", "candidate"}:
        return None
    strata_values = {key[0] for key in grouped}
    if len(strata_values) < 2 or any((stratum, variant) not in grouped
                                     for stratum in strata_values
                                     for variant in ("baseline", "candidate")):
        return None
    def sign(delta: float) -> int:
        return (delta > 0) - (delta < 0)
    pooled_sign = sign(pooled["candidate"][0] / pooled["candidate"][1] -
                       pooled["baseline"][0] / pooled["baseline"][1])
    subgroup_signs = {sign(grouped[(stratum, "candidate")][0] /
                           grouped[(stratum, "candidate")][1] -
                           grouped[(stratum, "baseline")][0] /
                           grouped[(stratum, "baseline")][1])
                      for stratum in strata_values}
    return pooled_sign != 0 and len(subgroup_signs) == 1 and subgroup_signs == {-pooled_sign}


def _observed_fractions(rows_by_object: dict[str, list[dict[str, Any]]],
                        contract: dict, dimensions: list[str]) -> tuple[set[tuple[int, int]], set[int]]:
    """Enumerate row and declared-group fractions; infer no scientific meaning."""
    numerator, denominator = contract.get("numerator"), contract.get("denominator")
    if not isinstance(numerator, str) or not isinstance(denominator, str):
        return set(), set()
    valid: set[tuple[int, int]] = set()
    denominators: set[int] = set()
    for rows in rows_by_object.values():
        for width in range(len(dimensions) + 1):
            for grouping in combinations(dimensions, width):
                totals: dict[tuple[Any, ...], list[int]] = defaultdict(lambda: [0, 0])
                for row in rows:
                    top, bottom = row.get(numerator), row.get(denominator)
                    if type(top) is not int or type(bottom) is not int or bottom <= 0:
                        return set(), set()
                    bucket = totals[tuple(row.get(field) for field in grouping)]
                    bucket[0] += top
                    bucket[1] += bottom
                    valid.add((top, bottom))
                    denominators.add(bottom)
                for top, bottom in totals.values():
                    valid.add((top, bottom))
                    denominators.add(bottom)
    return valid, denominators


def audit_versioned_seed_claims(events: list[dict[str, Any]],
                                draft: str) -> dict[str, Any]:
    """Return explicit contradictions; incomplete evidence yields no clearance."""
    payloads = _tool_payloads(events)
    changes = [row for name, row in payloads if name == "read_change"]
    if not changes or any(row != changes[0] for row in changes[1:]):
        return {"status": "insufficient_evidence", "reason": "change_event_missing"}
    change = changes[0]
    current_id = change.get("experiment_id")
    previous_id = change.get("previous_experiment_id")
    changed_fields = change.get("changed_fields")
    current_label = _version_label(current_id or "")
    previous_label = _version_label(previous_id or "")
    if (not current_label or not previous_label or current_label == previous_label or
            not isinstance(changed_fields, list) or len(changed_fields) != 1 or
            not isinstance(changed_fields[0], str)):
        return {"status": "insufficient_evidence", "reason": "version_pair_not_bounded"}
    source_objects = {}
    source_versions = {}
    dimensions = None
    metric_contract = None
    for name, row in payloads:
        if name != "read_pinned_object":
            continue
        source_objects[row.get("source_id")] = row.get("object_id")
        source_versions[row.get("source_id")] = row.get("version_sha256")
        value = row.get("value")
        if (row.get("object_id") == current_id and isinstance(value, dict) and
                isinstance(value.get("metric_contract"), dict)):
            metric_contract = value["metric_contract"]
            allowed = metric_contract.get("allowed_groups")
            if isinstance(allowed, list) and all(isinstance(x, str) for x in allowed):
                dimensions = allowed
    if dimensions is None:
        return {"status": "insufficient_evidence", "reason": "metric_contract_missing"}
    prior_versions = {source_versions[source] for source, object_id in source_objects.items()
                      if object_id == previous_id}
    if (len(prior_versions) != 1 or
            next(iter(prior_versions)) != change.get("previous_version_sha256")):
        return {"status": "insufficient_evidence", "reason": "previous_version_mismatch"}
    rows_by_object = {}
    for name, row in payloads:
        if name != "read_dataset_rows":
            continue
        object_id = source_objects.get(row.get("source_id"))
        if object_id not in (current_id, previous_id):
            continue
        if row.get("version_sha256") != source_versions.get(row.get("source_id")):
            return {"status": "insufficient_evidence", "reason": "row_version_mismatch"}
        data = row.get("rows")
        if row.get("offset") != 0 or not isinstance(data, list) or len(data) != row.get("total"):
            continue
        if object_id in rows_by_object and rows_by_object[object_id] != data:
            return {"status": "insufficient_evidence", "reason": "row_observations_disagree"}
        rows_by_object[object_id] = data
    if set(rows_by_object) != {current_id, previous_id}:
        return {"status": "insufficient_evidence", "reason": "full_row_pair_missing"}
    changed = changed_fields[0]
    old = _series_by_group(rows_by_object[previous_id], dimensions, changed)
    new = _series_by_group(rows_by_object[current_id], dimensions, changed)
    if old is None or new is None or old.keys() != new.keys():
        return {"status": "insufficient_evidence", "reason": "row_keys_changed"}
    candidates = [(group, old[group], new[group]) for group in old
                  if old[group] != new[group]]
    # Identical series in different groups are ambiguous in free text; defer.
    all_series = [series for _, prior, current in candidates
                  for series in (prior, current)]
    candidates = [(group, prior, current) for group, prior, current in candidates
                  if all_series.count(prior) == all_series.count(current) == 1]
    label_re = re.compile(rf"(?<![\w])(?:{re.escape(previous_label)}|"
                          rf"{re.escape(current_label)})(?!\w)", re.IGNORECASE)
    markers = list(label_re.finditer(draft))
    conflicts = []
    checked = 0
    fractions, observed_denominators = _observed_fractions(
        rows_by_object, metric_contract, dimensions)
    if fractions:
        for match in re.finditer(r"(?<![\d.\-])(\d{1,6})\s*/\s*(\d{1,6})(?![\d.])", draft):
            top, bottom = int(match.group(1)), int(match.group(2))
            if bottom in observed_denominators and (top, bottom) not in fractions:
                conflicts.append({"kind": "unobserved_fraction", "message":
                                  f"报告中的 {top}/{bottom} 不属于已读取原始行或声明分组的聚合结果"})
    denominator_field = metric_contract.get("denominator")
    if isinstance(denominator_field, str):
        full_table_denominators = {
            sum(row[denominator_field] for row in rows)
            for rows in rows_by_object.values()
            if all(type(row.get(denominator_field)) is int for row in rows)
        }
        if full_table_denominators:
            for match in re.finditer(
                    r"(?:分母|denominator)[^。；\n]{0,80}?"
                    r"(?:全表|整表|全数据集|whole\s+table)\s*(?:为|是|共|=|:|：)?\s*(\d{1,8})",
                    draft, re.IGNORECASE):
                claimed = int(match.group(1))
                if claimed not in full_table_denominators:
                    conflicts.append({"kind": "full_table_denominator", "message":
                                      f"声称全表分母为 {claimed}，已读取版本的全表分母为"
                                      f" {sorted(full_table_denominators)}"})
    if len(rows_by_object[current_id]) == len(rows_by_object[previous_id]):
        for match in re.finditer(r"新增[^。；，、\n]{0,18}行", draft):
            prefix = draft[max(0, match.start() - 6):match.start()]
            if not re.search(r"(?:没|没有|未|无|非|不是)$", prefix):
                conflicts.append({"kind": "row_count", "message":
                                  "两版逐行记录数相同，不能声称新增了记录行"})
                break
    simpson_claims = []
    for match in re.finditer(r"辛普森|Simpson", draft, re.IGNORECASE):
        start = max(draft.rfind(mark, 0, match.start()) for mark in "。！？；\n") + 1
        end_candidates = [draft.find(mark, match.end()) for mark in "。！？；\n"]
        end = min((index for index in end_candidates if index >= 0), default=len(draft))
        sentence = draft[start:end]
        before = draft[start:match.start()]
        after = draft[match.end():end]
        if ("是否" in before or re.search(r"[?？]\s*$", sentence) or
                re.search(r"(?:并非|不是|不构成|不能|不得|不属于|不满足|未|无)"
                          r"[^。；\n]{0,24}$", before) or
                re.search(r"^(?:悖论)?(?:要求|定义|须|需)", after)):
            continue
        if (re.search(r"(?:存在|构成|呈现|出现|属于|可称为|是)\s*[^。；\n]{0,12}$",
                      before) or re.search(r"^(?:式|型)", after)):
            simpson_claims.append(match)
    if simpson_claims:
        reversal = _formal_simpson_reversal(rows_by_object[current_id],
                                            metric_contract, dimensions)
        if reversal is not True:
            conflicts.append({"kind": "statistical_label", "message":
                              "当前分层与总体差值不满足严格的辛普森悖论方向反转"})
    for index, marker in enumerate(markers):
        next_marker = markers[index + 1].start() if index + 1 < len(markers) else len(draft)
        segment = draft[marker.end():min(marker.end() + 120, next_marker)].split("\n", 1)[0]
        line_start = draft.rfind("\n", 0, marker.start()) + 1
        line_end = draft.find("\n", marker.end())
        line = draft[line_start:line_end if line_end >= 0 else len(draft)]
        if not re.search(r"seed|种子", line, re.IGNORECASE):
            continue
        labelled = marker.group().lower()
        for group, prior, current in candidates:
            wrong = prior if labelled == current_label.lower() else current
            right = current if labelled == current_label.lower() else prior
            wrong_match = _sequence_pattern(wrong).search(segment)
            right_match = _sequence_pattern(right).search(segment)
            if wrong_match and not right_match:
                conflicts.append({"kind": "seed_series", "version": labelled,
                                  "group": dict(zip(dimensions, group)),
                                  "observed": list(wrong), "expected": list(right)})
            if wrong_match or right_match:
                checked += 1
    return {"status": "conflict" if conflicts else "checked",
            "checked_versioned_series": checked, "changed_groups": len(candidates),
            "conflicts": conflicts,
            "scope": "version-labelled seed series, unchanged row counts and formal Simpson labels"}
