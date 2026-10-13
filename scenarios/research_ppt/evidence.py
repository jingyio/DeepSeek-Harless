"""核验直接结果元组；字面摘录存在不等于科学主张得到支持。

``sources`` 必须来自宿主已获授权且重核版本的解析结果，``trusted_facts``
必须由宿主从独立人工审阅侧表加载，不能从 Agent 提交的 plan/sidecar 取得。
本模块不执行 PDF 解析、模糊检索、单位换算、图读数或语义支持推断。
pass 只表示给定直接元组与独立已审侧表一致，不认证全份 PPT 科学质量。
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("evidence.schema.json")
SCOPE = "reviewed_direct_result_tuple_consistency_not_semantic_support_or_deck_quality"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_RESULT_FIELDS = ("value", "method", "metric", "unit", "condition")
_CLAIM_FIELDS = {"claim_id", "source_id", "version_sha256", "page", "span", "panel", "result", "fact_id"}


def _diagnostic(code: str, message: str, field: str = "") -> dict:
    return {"code": code, "message": message, "field": field}


def _text(value: Any, maximum: int = 4096) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _shape(claim: Any) -> list[dict]:
    errors: list[dict] = []
    if not isinstance(claim, dict):
        return [_diagnostic("claim_schema_invalid", "结果声明必须是对象")]
    required = _CLAIM_FIELDS - {"panel", "fact_id"}
    if set(claim) - _CLAIM_FIELDS or required - set(claim):
        errors.append(_diagnostic("claim_schema_invalid", "结果声明有未知或缺失字段"))
    for field in ("claim_id", "source_id"):
        if not _text(claim.get(field), 256):
            errors.append(_diagnostic("claim_schema_invalid", "标识必须是非空字符串", field))
    sha = claim.get("version_sha256")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        errors.append(_diagnostic("claim_schema_invalid", "来源版本须为小写SHA256", "version_sha256"))
    if type(claim.get("page")) is not int or not 1 <= claim["page"] <= 200:
        errors.append(_diagnostic("claim_schema_invalid", "来源页码须为1–200的整数", "page"))
    for field in ("panel", "fact_id"):
        if field in claim and not _text(claim[field], 256):
            errors.append(_diagnostic("claim_schema_invalid", "可选标识若提供须为非空字符串", field))
    span = claim.get("span")
    if (not isinstance(span, dict) or set(span) != {"start", "end", "quote"}
            or type(span.get("start")) is not int or type(span.get("end")) is not int
            or span["start"] < 0 or span["end"] <= span["start"]
            or not _text(span.get("quote"), 8192)):
        errors.append(_diagnostic("claim_schema_invalid", "span须为Unicode码点start/end及原样quote", "span"))
    result = claim.get("result")
    if not isinstance(result, dict) or set(result) != set(_RESULT_FIELDS):
        errors.append(_diagnostic("result_tuple_incomplete", "结果须有value/method/metric/unit/condition", "result"))
    else:
        for field in _RESULT_FIELDS[:-1]:
            if not _text(result[field], 256):
                errors.append(_diagnostic("result_tuple_incomplete", "结果字段须明确给出，不做隐式补全", "result." + field))
        condition = result["condition"]
        if (not isinstance(condition, dict) or not condition or len(condition) > 32
                or any(not _text(key, 128) or not _text(value, 256) for key, value in condition.items())):
            errors.append(_diagnostic("result_tuple_incomplete", "condition须显式列出条件；不适用也须明示", "result.condition"))
    return errors


def _canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _checked_anchor(claim: dict, sources: Mapping[str, dict]) -> tuple[list[dict], list[dict]]:
    """只核宿主原文的定位及版本；不将词或数字的存在转成支持结论。"""
    errors: list[dict] = []
    unknown: list[dict] = []
    source = sources.get(claim["source_id"])
    if not isinstance(source, dict):
        return [_diagnostic("source_not_authorized", "声明来源不在宿主当前授权集合", "source_id")], []
    if source.get("version_sha256") != claim["version_sha256"]:
        return [_diagnostic("source_version_changed", "声明绑定的来源版本与当前版本不同", "version_sha256")], []
    pages = source.get("pages")
    matches = [row for row in pages if isinstance(row, dict) and type(row.get("page")) is int
               and row["page"] == claim["page"]] if isinstance(pages, list) else []
    if len(matches) != 1 or not isinstance(matches[0].get("text"), str):
        return [_diagnostic("source_page_unavailable", "声明页缺失、重复或不是已解析文本", "page")], []
    text, span = matches[0]["text"], claim["span"]
    if span["end"] > len(text) or text[span["start"]:span["end"]] != span["quote"]:
        errors.append(_diagnostic("source_span_mismatch", "声明摘录与当前页Unicode码点区间不一致", "span"))
    if "panel" in claim:
        panels = source.get("panels", [])
        entries = [p for p in panels if isinstance(p, dict) and p.get("panel") == claim["panel"]
                   and p.get("page") == claim["page"]] if isinstance(panels, list) else []
        if len(entries) != 1:
            unknown.append(_diagnostic("panel_not_independently_bound", "panel没有唯一的独立来源绑定，须核原图", "panel"))
        elif entries[0].get("complete") is False:
            errors.append(_diagnostic("panel_incomplete", "绑定图件记录显示panel不完整", "panel"))
        elif entries[0].get("complete") is not True:
            unknown.append(_diagnostic("panel_completeness_unknown", "panel完整性未经核验", "panel"))
    return errors, unknown


def _trusted_tuple(claim: dict, facts: Mapping[str, dict] | None) -> tuple[list[dict], list[dict]]:
    """可信性来自独立调用通道，不来自模型自填的review/verified字段。"""
    fact = facts.get(claim.get("fact_id")) if isinstance(facts, Mapping) else None
    if not isinstance(fact, dict):
        return [], [_diagnostic("independent_fact_missing", "仅核到原文摘录，缺少独立已审结果元组；科学支持未知", "fact_id")]
    review = fact.get("review")
    if (not isinstance(review, dict) or review.get("kind") != "human_direct_result"
            or not _text(review.get("reviewed_by"), 256) or not _text(review.get("reviewed_at"), 128)):
        return [], [_diagnostic("independent_review_missing", "宿主侧表未记录独立直接结果审阅，科学支持未知", "fact_id")]
    expected = {key: fact.get(key) for key in _CLAIM_FIELDS - {"claim_id", "fact_id", "panel"}}
    expected["claim_id"] = claim["claim_id"]
    if "panel" in fact:
        expected["panel"] = fact["panel"]
    if _shape(expected):
        return [], [_diagnostic("independent_fact_invalid", "独立侧表自身不完整，禁止拿声明补全", "fact_id")]
    errors: list[dict] = []
    for field in ("source_id", "version_sha256", "page", "span", "panel"):
        if claim.get(field) != expected.get(field):
            errors.append(_diagnostic("reviewed_source_binding_mismatch", "声明与已审结果的来源定位不同", field))
    for field in _RESULT_FIELDS:
        if claim["result"][field] != expected["result"][field]:
            errors.append(_diagnostic("reviewed_result_mismatch", "声明与独立已审结果字段不同，不做隐式归一化或条件省略", "result." + field))
    return errors, []


def validate_scientific_evidence(sidecar: Any, sources: Mapping[str, dict], *,
                                 trusted_facts: Mapping[str, dict] | None = None) -> dict:
    """返回pass/fail/unknown；没有可信侧表时即使逐字匹配仍为unknown。

    每条claim的span为已解析页文本的Python Unicode码点区间[start, end)，
    ``value`` 保持原样字符串，单位和条件不自动推断/换算。
    调用者必须另核claim与实际Slide/PPT/PDF是否保持；此函数不会验渲染。
    """
    base = {"schema_version": SCHEMA_VERSION, "scope": SCOPE,
            "scientific_quality_certified": False, "checks": [], "diagnostics": []}
    if sidecar is None:
        return {**base, "status": "unknown", "passed": False, "mechanical_passed": False,
                "evidence_present": False, "needs_review": [],
                "diagnostics": [_diagnostic("evidence_missing", "没有科学结果侧表，科学正确性未验证")]}
    if (not isinstance(sidecar, dict) or set(sidecar) != {"schema_version", "claims"}
            or type(sidecar.get("schema_version")) is not int or sidecar["schema_version"] != SCHEMA_VERSION
            or not isinstance(sidecar.get("claims"), list) or len(sidecar["claims"]) > 300):
        return {**base, "status": "fail", "passed": False, "mechanical_passed": False,
                "evidence_present": True, "needs_review": [],
                "diagnostics": [_diagnostic("evidence_schema_invalid", "科学侧表结构或版本无效")]}
    if not isinstance(sources, Mapping):
        raise TypeError("sources必须由宿主提供授权来源映射")
    try:
        sidecar_hash = _canonical_hash(sidecar)
    except (TypeError, ValueError):
        return {**base, "status": "fail", "passed": False, "mechanical_passed": False,
                "evidence_present": True, "needs_review": [],
                "diagnostics": [_diagnostic("evidence_schema_invalid", "科学侧表必须是有限JSON数据")]}
    if not sidecar["claims"]:
        return {**base, "status": "unknown", "passed": False, "mechanical_passed": False,
                "evidence_present": True, "needs_review": [],
                "diagnostics": [_diagnostic("evidence_empty", "没有直接结果声明，不能据此通过科学核验")]}
    checks, seen = [], set()
    for index, claim in enumerate(sidecar["claims"]):
        errors, unknown = _shape(claim), []
        identifier = claim.get("claim_id", "") if isinstance(claim, dict) else ""
        if not errors:
            if identifier in seen:
                errors.append(_diagnostic("duplicate_claim_id", "重复claim_id会使结果绑定产生歧义", "claim_id"))
            seen.add(identifier)
            anchor_errors, anchor_unknown = _checked_anchor(claim, sources)
            errors.extend(anchor_errors)
            unknown.extend(anchor_unknown)
            if not anchor_errors:
                tuple_errors, tuple_unknown = _trusted_tuple(claim, trusted_facts)
                errors.extend(tuple_errors)
                unknown.extend(tuple_unknown)
        status = "fail" if errors else "unknown" if unknown else "pass"
        checks.append({"claim_index": index, "claim_id": identifier, "status": status,
                       "mechanical_passed": not errors, "diagnostics": errors + unknown})
    status = "fail" if any(c["status"] == "fail" for c in checks) else (
        "unknown" if any(c["status"] == "unknown" for c in checks) else "pass")
    return {**base, "status": status, "passed": status == "pass", "evidence_present": True,
            "mechanical_passed": all(c["mechanical_passed"] for c in checks), "checks": checks,
            "needs_review": [c["claim_id"] for c in checks if c["status"] == "unknown"],
            "sidecar_sha256": sidecar_hash}


def source_snapshot(handles: Mapping[str, dict]) -> dict:
    """把PPTService.handles投影为副本；调用前宿主仍须current()核文件版本。"""
    return {identifier: {"version_sha256": item["row"]["version_sha256"],
                         "pages": copy.deepcopy(item["parsed"]["pages"])}
            for identifier, item in handles.items() if item.get("read") is True}
