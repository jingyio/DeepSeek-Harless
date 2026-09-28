"""Check a narrow class of final-answer claims against version-bound tool results.

This does not decide scientific meaning. It only checks whether a statement about
the *direction* of paired seed results agrees with rows the agent already read.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable


_INCONSISTENT = re.compile(
    r"(?:种子|seed).{0,35}(?:方向.{0,5}不一致|符号.{0,5}(?:相反|不一致)|"
    r"一正一负|方向相反)|(?:方向.{0,5}不一致|符号.{0,5}相反).{0,25}(?:种子|seed)",
    re.IGNORECASE,
)
_CONSISTENT = re.compile(
    r"(?:种子|seed).{0,35}(?:方向.{0,5}一致|同向)|"
    r"(?:方向.{0,5}一致|同向).{0,25}(?:种子|seed)",
    re.IGNORECASE,
)


def _payload(event: dict[str, Any]) -> dict[str, Any] | None:
    """Decode the JSON object inside one DSH tool/result event."""
    message = event.get("data", {}).get("message", {})
    for block in message.get("content", []):
        if block.get("type") != "tool-result":
            continue
        for item in block.get("content", []):
            if item.get("type") == "text":
                try:
                    result = json.loads(item["text"])
                except (ValueError, TypeError):
                    return None
                return result if isinstance(result, dict) else None
    return None


def paired_rate_facts(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive paired directions only from complete, matching-version table reads."""
    calls: dict[str, str] = {}
    tables: dict[str, dict[str, Any]] = {}
    reads: dict[str, dict[str, Any]] = {}
    for event in events:
        data = event.get("data", {})
        if event.get("type") == "tool/call":
            calls[data.get("callId", "")] = data.get("name", "")
            continue
        if event.get("type") != "tool/result":
            continue
        call_id = data.get("message", {}).get("source", {}).get("callId", "")
        name = calls.get(call_id, "")
        value = _payload(event)
        if not value:
            continue
        if name.endswith("__read_pinned") and isinstance(value.get("value"), dict):
            table = value["value"]
            if "dataset_id" in table and "metric" in table:
                tables[table["dataset_id"]] = {
                    "source_id": value.get("source_id"),
                    "version_sha256": value.get("version_sha256"),
                    "metric": table["metric"],
                    "row_count": table.get("row_count"),
                }
        elif name.endswith("__read_rows") and "dataset_id" in value:
            reads[value["dataset_id"]] = value
    facts = []
    for dataset_id, table in tables.items():
        read = reads.get(dataset_id)
        metric = table["metric"]
        if (not read or read.get("source_id") != table["source_id"] or
                read.get("version_sha256") != table["version_sha256"] or
                read.get("offset") != 0 or
                read.get("total") != table["row_count"] or
                not isinstance(read.get("rows"), list) or
                len(read["rows"]) != read["total"] or
                len(metric.get("allowed_groups", [])) != 1):
            continue
        group = metric["allowed_groups"][0]
        top, bottom = metric.get("numerator"), metric.get("denominator")
        paired: dict[Any, dict[str, tuple[int, int]]] = defaultdict(dict)
        valid = True
        for row in read["rows"]:
            if not isinstance(row, dict):
                valid = False
                break
            numerator, denominator = row.get(top), row.get(bottom)
            seed, arm = row.get("seed"), row.get(group)
            if (seed is None or not isinstance(arm, str) or
                    type(numerator) is not int or type(denominator) is not int or
                    denominator <= 0 or not 0 <= numerator <= denominator or
                    arm in paired[seed]):
                valid = False
                break
            paired[seed][arm] = (numerator, denominator)
        if not valid or len(paired) < 2:
            continue
        arms = sorted({arm for pair in paired.values() for arm in pair})
        if len(arms) != 2 or any(set(pair) != set(arms) for pair in paired.values()):
            continue
        signs = []
        rates = []
        for seed, pair in sorted(paired.items(), key=lambda item: str(item[0])):
            left, right = pair[arms[0]], pair[arms[1]]
            delta = left[0] * right[1] - right[0] * left[1]
            signs.append(1 if delta > 0 else -1 if delta < 0 else 0)
            rates.append({"seed": seed, arms[0]: f"{left[0]}/{left[1]}",
                          arms[1]: f"{right[0]}/{right[1]}"})
        if 0 in signs:
            continue  # A tie needs semantic wording; do not infer a direction.
        facts.append({"dataset_id": dataset_id,
                      "source_id": table["source_id"],
                      "version_sha256": table["version_sha256"],
                      "groups": arms, "by_seed": rates,
                      "same_direction": len(set(signs)) == 1,
                      "higher_group": (arms[0] if signs[0] > 0 else arms[1])
                      if len(set(signs)) == 1 else None})
    return facts


def direction_issues(answer: str, facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag answer-wide seed-direction contradictions only when one pair is unique."""
    if len(facts) != 1:
        return []
    fact = facts[0]
    issues = []
    for sentence in re.split(r"[。；;\n]", answer):
        claim = sentence.strip()
        if not claim:
            continue
        if fact["same_direction"] and _INCONSISTENT.search(claim):
            issues.append({"claim": claim, "fact": fact,
                           "reason": "paired seed directions are the same"})
        elif (not fact["same_direction"] and _CONSISTENT.search(claim) and
              not _INCONSISTENT.search(claim)):
            issues.append({"claim": claim, "fact": fact,
                           "reason": "paired seed directions differ"})
    return issues


def issues_from_trace(answer: str, events_file: Path) -> list[dict[str, Any]]:
    if not events_file.is_file():
        return []
    events = (json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines())
    return direction_issues(answer, paired_rate_facts(events))


def repair_prompt(issues: list[dict[str, Any]]) -> str:
    """Ask the semantic model to revise; do not silently rewrite its conclusion."""
    return (
        "交付前数字核对发现你的上一版文字与已读取的表格行冲突。"
        "只根据下列同一来源版本的逐种子数值，重新核对组间方向并完整重写原任务的"
        "Markdown 决定；保留来源、科学不确定性和未执行的外部操作边界。"
        "不要把种子间随时间变化与同一种子内两组比较混为一谈。"
        "若仍不确定，写‘待核实’，不要声称方向一致或相反。\n"
        + json.dumps(issues, ensure_ascii=False)
    )


def repair_result_once(result: Any, events_file: Path,
                       continue_model: Callable[[str], Any]) -> tuple[Any, dict[str, Any]]:
    """Make at most one semantic repair request, then recheck the same trace."""
    initial = (issues_from_trace(result.final_response, events_file)
               if result.final_response.strip() and
               result.finish_reason == "completed" else [])
    repaired = continue_model(repair_prompt(initial)) if initial else result
    remaining = (issues_from_trace(repaired.final_response, events_file)
                 if repaired.final_response.strip() else initial)
    return repaired, {"repair_requests": int(bool(initial)),
                      "initial_issues": initial,
                      "remaining_issues": remaining}
