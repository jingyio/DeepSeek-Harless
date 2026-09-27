"""Structure Engine 与 Semantic Engine 之间的显式交接协议。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


HandoffType = str
HandoffSource = str
ResolutionType = str


def normalize_runtime_error_type(error_type: Any) -> str:
    """兼容旧日志命名；运行时边界统一把 path_error 归入 tool_error。"""
    text = str(error_type or "").strip()
    if text == "path_error":
        return "tool_error"
    return text


def missing_slots_from_params(missing_params: dict[str, list[str]] | None) -> list[str]:
    slots: set[str] = set()
    for params in (missing_params or {}).values():
        for param in params or []:
            text = str(param).strip()
            if text:
                slots.add(text)
    return sorted(slots)


def _clean_missing_params(missing_params: dict[str, list[str]] | None) -> dict[str, list[str]]:
    cleaned: dict[str, list[str]] = {}
    for tool_name, params in (missing_params or {}).items():
        tool = str(tool_name).strip()
        if not tool:
            continue
        values = [str(param).strip() for param in (params or []) if str(param).strip()]
        if values:
            cleaned[tool] = values
    return cleaned


def _allowed_reentry(mode: str, candidates: list[str] | None = None) -> dict[str, Any]:
    return {
        "mode": mode,
        "candidates": [str(item) for item in (candidates or []) if str(item).strip()],
    }


@dataclass(frozen=True)
class StructureHandoffRequest:
    """结构引擎无法继续时，交给语义引擎的唯一入口对象。

    这里不承载开放语义判断，只描述结构上已经确定的阻塞点、可用状态和
    语义引擎被允许返回后重新进入的范围。
    """

    handoff_type: HandoffType
    source: HandoffSource
    motif_id: str | None = None
    missing_slots: list[str] = field(default_factory=list)
    missing_params: dict[str, list[str]] = field(default_factory=dict)
    available_state: dict[str, Any] = field(default_factory=dict)
    allowed_reentry: dict[str, Any] = field(default_factory=lambda: _allowed_reentry("none"))
    error_type: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_type": self.handoff_type,
            "source": self.source,
            "motif_id": self.motif_id,
            "missing_slots": list(self.missing_slots),
            "missing_params": {tool: list(params) for tool, params in self.missing_params.items()},
            "available_state": dict(self.available_state),
            "allowed_reentry": dict(self.allowed_reentry),
            "error_type": self.error_type,
            "reason": self.reason,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SemanticResolution:
    """语义引擎处理 handoff 后返回给结构引擎的结果。"""

    resolution_type: ResolutionType
    slot_values: dict[str, Any] = field(default_factory=dict)
    action: dict[str, Any] | None = None
    updated_user_intent: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_type": self.resolution_type,
            "slot_values": dict(self.slot_values),
            "action": self.action,
            "updated_user_intent": self.updated_user_intent,
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }


def build_blocking_precheck_handoff(
    *,
    motif_id: str | None,
    missing_params: dict[str, list[str]] | None,
    available_state: dict[str, Any] | None = None,
    candidates: list[str] | None = None,
) -> StructureHandoffRequest:
    cleaned_missing = _clean_missing_params(missing_params)
    reentry_mode = "frontier_candidate" if candidates else "same_motif"
    return StructureHandoffRequest(
        handoff_type="need_user_clarification",
        source="blocking_precheck",
        motif_id=str(motif_id) if motif_id is not None else None,
        missing_slots=missing_slots_from_params(cleaned_missing),
        missing_params=cleaned_missing,
        available_state=dict(available_state or {}),
        allowed_reentry=_allowed_reentry(reentry_mode, candidates),
        error_type="param_error",
    )


def build_runtime_failure_handoff(
    *,
    motif_id: str | None,
    error_type: str,
    missing_params: dict[str, list[str]] | None = None,
    available_state: dict[str, Any] | None = None,
    candidates: list[str] | None = None,
    reason: str | None = None,
) -> StructureHandoffRequest:
    normalized = normalize_runtime_error_type(error_type)
    cleaned_missing = _clean_missing_params(missing_params)
    if normalized == "param_error":
        handoff_type = "need_user_clarification"
        reentry = _allowed_reentry("frontier_candidate" if candidates else "same_motif", candidates)
    else:
        handoff_type = "need_open_world_action"
        reentry = _allowed_reentry("none")
    return StructureHandoffRequest(
        handoff_type=handoff_type,
        source=normalized or "unknown",
        motif_id=str(motif_id) if motif_id is not None else None,
        missing_slots=missing_slots_from_params(cleaned_missing),
        missing_params=cleaned_missing,
        available_state=dict(available_state or {}),
        allowed_reentry=reentry,
        error_type=normalized or None,
        reason=reason,
    )


def build_write_gate_handoff(
    *,
    motif_id: str | None,
    reason: str,
    available_state: dict[str, Any] | None = None,
) -> StructureHandoffRequest:
    return StructureHandoffRequest(
        handoff_type="need_open_world_action",
        source="write_gate",
        motif_id=str(motif_id) if motif_id is not None else None,
        available_state=dict(available_state or {}),
        allowed_reentry=_allowed_reentry("none"),
        reason=reason,
    )


def build_no_motif_handoff(
    *,
    available_state: dict[str, Any] | None = None,
    reason: str = "no_motif_selected",
) -> StructureHandoffRequest:
    return StructureHandoffRequest(
        handoff_type="need_open_world_action",
        source="no_motif",
        available_state=dict(available_state or {}),
        allowed_reentry=_allowed_reentry("none"),
        reason=reason,
    )


def fallback_mode_for_handoff(
    request: StructureHandoffRequest,
    *,
    has_clarification_bundle: bool = False,
    unanchored_write_bundle_skipped: bool = False,
) -> str:
    """把正式 handoff 映射回当前 loop 的 legacy fallback_mode。

    第一阶段仍保留旧 loop 变量；这个函数让后续删除 fallback_mode 分支时有
    单一替换点。
    """
    if request.source in {"no_motif", "write_gate"} or unanchored_write_bundle_skipped:
        return "no_motif"
    if request.handoff_type == "need_user_clarification" and has_clarification_bundle:
        return "motif_failed"
    if request.handoff_type == "need_open_world_action":
        return "motif_failed"
    return "no_motif"
