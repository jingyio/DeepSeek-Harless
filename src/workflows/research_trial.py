"""Fail-closed comparison of method-blind research reviews and run costs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


DEEPSEEK_OFFPEAK_USD_PER_MILLION = {
    "inputTokens": 0.15, "cacheReadTokens": 0.003, "outputTokens": 0.6,
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _nonnegative_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{name} must be a nonnegative number")
    return float(value)


def inventory_digest(rows: list[dict[str, Any]]) -> str:
    if not isinstance(rows, list) or not rows:
        raise ValueError("source inventory must be nonempty")
    normalized = sorted((row["filename"], row["sha256"]) for row in rows)
    if len({name for name, _ in normalized}) != len(normalized):
        raise ValueError("source inventory contains duplicate filenames")
    if any(not isinstance(name, str) or not name or not isinstance(digest, str)
           or len(digest) != 64 for name, digest in normalized):
        raise ValueError("invalid source inventory entry")
    return hashlib.sha256(json.dumps(normalized, separators=(",", ":")).encode()).hexdigest()


def review_template(label: str, points: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": 1, "label": label, "reviewer_id": "",
            "points": [{"id": point["id"], "support": None, "coverage": None,
                        "critical_error": None, "notes": ""} for point in points],
            "overall_usable": None, "practical_usable": None,
            "comparison_accuracy": None,
            "correction_minutes": None, "notes": ""}


def validate_review(review: dict[str, Any], *, label: str,
                    points: list[dict[str, Any]]) -> dict[str, Any]:
    if (review.get("schema_version") != 1 or review.get("label") != label or
            not isinstance(review.get("reviewer_id"), str) or
            not review["reviewer_id"].strip()):
        raise ValueError("review identity or schema is invalid")
    rows = review.get("points")
    if (not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
            or [row.get("id") for row in rows] != [p["id"] for p in points]):
        raise ValueError("review must score every answer point in order")
    for row in rows:
        if (type(row.get("support")) is not int or row["support"] not in {0, 1, 2}
                or type(row.get("coverage")) is not int or row["coverage"] not in {0, 1, 2}
                or type(row.get("critical_error")) is not bool
                or not isinstance(row.get("notes"), str)):
            raise ValueError(f"invalid point review: {row.get('id')}")
    if type(review.get("overall_usable")) is not bool:
        raise ValueError("overall_usable must be true or false")
    practical_usable = review.get("practical_usable")
    if practical_usable is not None and type(practical_usable) is not bool:
        raise ValueError("practical_usable must be true or false")
    comparison = review.get("comparison_accuracy")
    if comparison not in {"yes", "partial", "no", "not_applicable"}:
        raise ValueError("comparison_accuracy is invalid")
    requires_comparison = any(point.get("min_sources", 1) > 1 for point in points)
    if requires_comparison and comparison == "not_applicable":
        raise ValueError("comparison accuracy must be scored for this task")
    if not requires_comparison and comparison != "not_applicable":
        raise ValueError("this task has no comparison requirement")
    minutes = _nonnegative_number(review.get("correction_minutes"), "correction_minutes")
    if not isinstance(review.get("notes"), str):
        raise ValueError("review notes must be text")
    qualified = (review["overall_usable"] and
                 all(row["support"] == 2 and row["coverage"] == 2 and
                     not row["critical_error"] for row in rows) and
                 (comparison == "yes" if requires_comparison else True))
    # A separate, explicitly reviewed tier permits one partially covered point.
    # Every stated fact must still be fully supported; no critical error is waived.
    partial_points = sum(row["coverage"] == 1 for row in rows)
    practical_qualified = (qualified or
                           (practical_usable is True and partial_points <= 1 and
                            all(row["support"] == 2 and row["coverage"] >= 1 and
                                not row["critical_error"] for row in rows) and
                            (comparison == "yes" if requires_comparison else True)))
    return {"qualified": qualified, "practical_qualified": practical_qualified,
            "correction_minutes": minutes,
            "point_scores": [{"id": row["id"], "support": row["support"],
                              "coverage": row["coverage"],
                              "critical_error": row["critical_error"]} for row in rows],
            "overall_usable": review["overall_usable"],
            "practical_usable": practical_usable,
            "comparison_accuracy": comparison, "reviewer_id": review["reviewer_id"]}


def _metrics(run: Path) -> dict[str, Any] | None:
    for name in ("total-metrics.json", "metrics.json"):
        path = run / name
        if path.is_file():
            value = _read_json(path)
            if not isinstance(value, dict):
                raise ValueError("run metrics must be an object")
            return value
    return None


def _api_cost(run_info: dict[str, Any], metrics: dict[str, Any] | None) -> dict[str, Any]:
    if run_info.get("api_cost_usd") is not None:
        cost = _nonnegative_number(run_info["api_cost_usd"], "api_cost_usd")
        if not run_info.get("api_cost_evidence"):
            raise ValueError("actual API cost needs an evidence reference")
        return {"kind": "actual", "usd": cost,
                "evidence": run_info["api_cost_evidence"]}
    if run_info.get("model") != "deepseek-flash" or metrics is None:
        return {"kind": "unavailable"}
    tokens = {}
    for key in DEEPSEEK_OFFPEAK_USD_PER_MILLION:
        value = metrics.get(key)
        if type(value) is not int or value < 0:
            return {"kind": "unavailable"}
        tokens[key] = value
    offpeak = sum(tokens[key] * rate / 1_000_000
                  for key, rate in DEEPSEEK_OFFPEAK_USD_PER_MILLION.items())
    return {"kind": "pinned_price_estimate", "offpeak_usd": round(offpeak, 8),
            "peak_usd": round(offpeak * 2, 8),
            "pricing_checked": "2026-09-25",
            "scope": "visible API tokens only"}


def score_trial(manifest: dict[str, Any]) -> dict[str, Any]:
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("task_id"), str):
        raise ValueError("invalid trial manifest")
    points = _read_json(Path(manifest["answer_points"]).resolve(strict=True))
    if not isinstance(points, list) or not points:
        raise ValueError("trial answer points are empty")
    runs = manifest.get("runs")
    if not isinstance(runs, list) or not runs or any(not isinstance(item, dict) for item in runs):
        raise ValueError("trial has no runs")
    labels = [item.get("label") for item in runs]
    if (any(not isinstance(label, str) or not label for label in labels)
            or len(set(labels)) != len(labels)):
        raise ValueError("trial labels must be unique")
    hourly_rate = manifest.get("human_rate_usd_per_hour")
    if hourly_rate is not None:
        hourly_rate = _nonnegative_number(hourly_rate, "human_rate_usd_per_hour")
    reference_question = None
    reference_inventory = None
    outcomes = []
    for item in runs:
        label = item["label"]
        run = Path(item["run_dir"]).resolve(strict=True)
        answer = run / "answer.md"
        if not answer.is_file() or not answer.read_text(encoding="utf-8").strip():
            raise ValueError(f"{label}: missing answer")
        status_path = run / "status.json"
        if status_path.is_file() and _read_json(status_path).get("fixture_only"):
            raise ValueError(f"{label}: synthetic fixture cannot be scored as a real run")
        question = (run / "question.txt").read_text(encoding="utf-8").strip()
        run_points = _read_json(run / "answer-points.json")
        if run_points != points:
            raise ValueError(f"{label}: answer points differ from the trial")
        digest = inventory_digest(_read_json(run / "sources.json"))
        if reference_question is None:
            reference_question = question
            reference_inventory = digest
        elif question != reference_question or digest != reference_inventory:
            raise ValueError(f"{label}: task question or source inventory differs")
        review = validate_review(_read_json(Path(item["review_file"]).resolve(strict=True)),
                                 label=label, points=points)
        metrics = _metrics(run)
        api_cost = _api_cost(item, metrics)
        if "setup_minutes" not in item:
            raise ValueError(f"{label}: setup_minutes must be recorded, including zero")
        setup_minutes = _nonnegative_number(item["setup_minutes"], "setup_minutes")
        human_minutes = setup_minutes + review["correction_minutes"]
        local_cost = item.get("local_cost_usd")
        if local_cost is not None:
            local_cost = _nonnegative_number(local_cost, "local_cost_usd")
        total_cost = None
        if api_cost["kind"] == "actual" and local_cost is not None and hourly_rate is not None:
            total_cost = round(api_cost["usd"] + local_cost +
                               human_minutes * hourly_rate / 60, 8)
        outcomes.append({
            "label": label, "method": item["method"], "run_dir": str(run),
            "model": item.get("model"), "qualified": review["qualified"],
            "practical_qualified": review["practical_qualified"],
            "quality": review, "model_requests": metrics.get("model_requests") if metrics else None,
            "token_usage": {key: metrics.get(key) for key in DEEPSEEK_OFFPEAK_USD_PER_MILLION}
                           if metrics else None,
            "api_cost": api_cost, "local_cost_usd": local_cost,
            "human_minutes": human_minutes, "setup_minutes": setup_minutes,
            "total_cost_usd": total_cost,
            "qualified_total_cost_usd": total_cost if review["qualified"] else None,
            "practical_total_cost_usd": total_cost if review["practical_qualified"] else None,
            "elapsed_seconds": metrics.get("elapsed_seconds") if metrics else None,
        })
    return {"schema_version": 1, "task_id": manifest["task_id"],
            "question": reference_question, "source_inventory_sha256": reference_inventory,
            "answer_points": [point["id"] for point in points],
            "human_rate_usd_per_hour": hourly_rate, "runs": outcomes,
            "cost_comparison_ready": all(row["total_cost_usd"] is not None for row in outcomes),
            "qualified_cost_comparison_ready": all(row["qualified"] and
                                                    row["qualified_total_cost_usd"] is not None
                                                    for row in outcomes),
            "practical_cost_comparison_ready": all(row["practical_qualified"] and
                                                    row["practical_total_cost_usd"] is not None
                                                    for row in outcomes)}
