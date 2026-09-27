"""Conservative, traceable reuse of prior research claims after source changes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.adapters.harness_semantic import _parse_response
from .research_review_gate import require_approved_review


def _read(directory: Path, name: str) -> Any:
    return json.loads((directory / name).read_text(encoding="utf-8"))


def _same_source_page(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return all(before.get(key) == after.get(key) for key in
               ("source", "page", "source_sha256"))


def _remap_claim(claim: dict[str, Any], old_citations: dict[str, dict[str, Any]],
                 current_citations: dict[str, dict[str, Any]],
                 allowed: set[str]) -> dict[str, Any] | None:
    point_id = claim["point_id"]
    supports = []
    for support in claim["supports"]:
        old = old_citations.get(support["evidence_id"])
        if old is None:
            return None
        found = None
        for evidence_id in sorted(allowed, key=lambda key: int(key[1:])):
            current = current_citations[evidence_id]
            if not _same_source_page(old, current):
                continue
            candidate = {"point_id": point_id, "text": claim["text"],
                         "supports": [{"evidence_id": evidence_id,
                                       "quote": support["quote"]}]}
            raw = json.dumps({"claims": [candidate], "uncertainties": []}, ensure_ascii=False)
            try:
                accepted, _, rejected = _parse_response(
                    raw, current_citations, point_ids={point_id},
                    point_citations={point_id: allowed})
            except (ValueError, KeyError, TypeError):
                continue
            if accepted and not rejected:
                found = evidence_id
                break
        if found is None:
            return None
        supports.append({"evidence_id": found, "quote": support["quote"]})
    remapped = {**claim, "supports": supports}
    raw = json.dumps({"claims": [remapped], "uncertainties": []}, ensure_ascii=False)
    accepted, _, rejected = _parse_response(
        raw, current_citations, point_ids={point_id}, point_citations={point_id: allowed})
    return accepted[0] if accepted and not rejected else None


def plan_incremental(prior_run: Path, *, question: str,
                     points: list[dict[str, Any]],
                     current_selection_state: dict[str, Any],
                     current_source_state: dict[str, Any],
                     current_citations: dict[str, dict[str, Any]],
                     point_citations: dict[str, set[str]]) -> dict[str, Any]:
    """Return carry-forward *draft* claims and points requiring new synthesis.

    This checks provenance and literal quotes. It cannot detect a contradiction in
    a newly added source; every carried claim therefore needs human review.
    """
    prior_run = prior_run.resolve(strict=True)
    status = _read(prior_run, "status.json").get("status")
    if status not in {"point_links_present", "incomplete_answer", "incremental_draft"}:
        raise ValueError("prior run has no structurally checked report")
    if (prior_run / "question.txt").read_text(encoding="utf-8").strip() != question.strip():
        raise ValueError("incremental report question changed")
    previous_points = _read(prior_run, "answer-points.json")
    if [point["id"] for point in previous_points] != [point["id"] for point in points]:
        raise ValueError("answer point IDs changed; start a fresh report")
    previous_state = _read(prior_run, "motif-selection-state.json")
    if previous_state["source_dir"] != current_selection_state["source_dir"]:
        raise ValueError("incremental run must use the same source directory")
    previous_source_state = _read(prior_run, "motif-source-state.json")
    if (previous_source_state["source_dir"] != current_source_state["source_dir"] or
            current_source_state["source_dir"] != current_selection_state["source_dir"]):
        raise ValueError("source snapshots belong to different directories")
    previous_sources = {row["binding"]["source"]: row["binding"]["sha256"]
                        for row in previous_source_state["evidence"]}
    current_sources = {row["binding"]["source"]: row["binding"]["sha256"]
                       for row in current_source_state["evidence"]}
    source_changes = {
        "added": sorted(set(current_sources) - set(previous_sources)),
        "removed": sorted(set(previous_sources) - set(current_sources)),
        "modified": sorted(key for key in previous_sources.keys() & current_sources.keys()
                           if previous_sources[key] != current_sources[key]),
    }
    previous_claims = _read(prior_run, "claims.json")
    previous_uncertainties = _read(prior_run, "uncertainties.json")
    old_citations = _read(prior_run, "selected-evidence.json")
    previous_coverage = {row["id"]: row["status"]
                         for row in _read(prior_run, "question-coverage.json")}
    carried: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for previous_point, point in zip(previous_points, points):
        point_id = point["id"]
        reason = None
        before = previous_state["decisions"].get(f"select_{point_id}.choice")
        current = current_selection_state["decisions"].get(f"select_{point_id}.choice")
        if previous_point != point:
            reason = "answer_point_changed"
        elif (before is None or current is None or
              before.get("resolution_status") != "VALIDATED" or
              current.get("resolution_status") != "VALIDATED" or
              tuple(before.get("dependency_signatures", ())) !=
              tuple(current.get("dependency_signatures", ()))):
            reason = "evidence_dependency_changed"
        elif previous_coverage.get(point_id) != "cited_claim":
            reason = "previous_point_incomplete"
        elif any(item.get("point_id") == point_id for item in previous_uncertainties
                 if isinstance(item, dict)):
            reason = "previous_uncertainty"
        prior_point_claims = [claim for claim in previous_claims
                              if claim.get("point_id") == point_id]
        if reason is None and not prior_point_claims:
            reason = "previous_claim_missing"
        remapped_claims = []
        if reason is None:
            allowed = point_citations.get(point_id, set())
            for claim in prior_point_claims:
                remapped = _remap_claim(claim, old_citations, current_citations, allowed)
                if remapped is None:
                    reason = "citation_changed_or_quote_missing"
                    break
                remapped_claims.append(remapped)
        if reason is None:
            carried.extend(remapped_claims)
            decisions.append({"point_id": point_id, "action": "carry_for_review",
                              "claim_count": len(remapped_claims)})
        else:
            decisions.append({"point_id": point_id, "action": "resynthesize", "reason": reason})
    prior_review = {"required": bool(carried and status == "incremental_draft"),
                    "status": "not_required"}
    if prior_review["required"]:
        reviewed = require_approved_review(prior_run)
        prior_review = {"required": True, "status": "verified",
                        "record_sha256": hashlib.sha256(json.dumps(
                            reviewed, sort_keys=True, ensure_ascii=False,
                            separators=(",", ":")).encode("utf-8")).hexdigest()}
    return {"parent_run": prior_run.name, "source_changes": source_changes,
            "prior_review": prior_review,
            "carried_claims": carried,
            "carried_points": [row["point_id"] for row in decisions
                               if row["action"] == "carry_for_review"],
            "dirty_points": [row["point_id"] for row in decisions
                             if row["action"] == "resynthesize"],
            "decisions": decisions,
            "review_required": bool(carried)}


def remap_new_claims(claims: list[dict[str, Any]],
                     local_citations: dict[str, dict[str, Any]],
                     current_citations: dict[str, dict[str, Any]],
                     point_citations: dict[str, set[str]]) -> list[dict[str, Any]]:
    """Translate IDs from a reduced synthesis prompt to the full report ledger."""
    mapped = []
    for claim in claims:
        point_id = claim["point_id"]
        row = _remap_claim(claim, local_citations, current_citations,
                           point_citations[point_id])
        if row is None:
            raise ValueError("new claim cannot be mapped to the full evidence ledger")
        mapped.append(row)
    return mapped


def render_change_log(plan: dict[str, Any]) -> str:
    labels = {"added": "新增", "modified": "修改", "removed": "移除"}
    reasons = {
        "answer_point_changed": "问题要求变化",
        "evidence_dependency_changed": "候选证据或来源变化",
        "previous_point_incomplete": "上版未完整覆盖",
        "previous_uncertainty": "上版仍有待核查事项",
        "previous_claim_missing": "上版缺少可核验结论",
        "citation_changed_or_quote_missing": "旧引文无法在当前资料中重新核对",
    }
    lines = ["# 增量报告变更记录", "", f"基于上版运行：`{plan['parent_run']}`", "",
             "## 资料变化", ""]
    any_change = False
    for key in ("added", "modified", "removed"):
        for source in plan["source_changes"][key]:
            lines.append(f"- {labels[key]}：`{source}`")
            any_change = True
    if not any_change:
        lines.append("- 来源文件内容未变化。")
    lines.extend(["", "## 逐项处理", ""])
    for row in plan["decisions"]:
        if row["action"] == "carry_for_review":
            lines.append(f"- `{row['point_id']}`：沿用 {row['claim_count']} 条结论；需人工复核新资料是否构成冲突。")
        else:
            lines.append(f"- `{row['point_id']}`：重新综合；{reasons.get(row['reason'], row['reason'])}。")
    lines.extend(["", "沿用只表示旧引文与当前来源仍可定位，不代表新资料没有推翻旧结论。", ""])
    return "\n".join(lines)
