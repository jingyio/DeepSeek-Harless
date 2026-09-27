from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from .evidence import BoundEvidence


UNRESOLVED = "UNRESOLVED"
VALIDATED = "VALIDATED"
INVALID = "INVALID"
STALE = "STALE"


@dataclass(slots=True)
class SlotState:
    """一个 motif invocation 内的局部参数状态。

    ``dependency_signatures`` 只保存签名，不复制 evidence/tool payload，避免
    Frame 随上下文增长。
    """

    value: Any = None
    resolution_status: str = UNRESOLVED
    dependency_signatures: tuple[str, ...] = ()
    invalid_reason: str = ""


@dataclass(slots=True)
class DecisionState:
    values: dict[str, Any] = field(default_factory=dict)
    resolution_status: str = UNRESOLVED
    member_slots: tuple[str, ...] = ()
    dependency_signatures: tuple[str, ...] = ()
    invalid_reason: str = ""


@dataclass(slots=True)
class ConfirmationState:
    candidate_signature: str = ""
    status: str = "NONE"

    def token(self) -> dict[str, str] | None:
        if self.status != "CONFIRMED" or not self.candidate_signature:
            return None
        return {"status": "confirmed", "candidate_signature": self.candidate_signature}


@dataclass(slots=True)
class MotifFrame:
    motif_id: str
    execution_plan: list[str]
    plan_step: int
    motif_instance_id: str = ""
    lifecycle_status: str = "ACTIVE"
    motif_tools: set[str] = field(default_factory=set)
    completed_tools: set[str] = field(default_factory=set)
    tool_results: dict[str, Any] = field(default_factory=dict)
    missing_params: dict[str, list[str]] = field(default_factory=dict)
    slots: dict[str, SlotState] = field(default_factory=dict)
    decisions: dict[str, DecisionState] = field(default_factory=dict)
    # 检查集合不是业务目标；只在读取执行器中投影，不进入语义参数槽。
    read_authorizations: dict[str, dict[str, Any]] = field(default_factory=dict)
    read_set_semantic_owner: bool = False
    pending_read_actions: list[dict[str, Any]] = field(default_factory=list)
    executing_read_set: bool = False
    confirmation: ConfirmationState = field(default_factory=ConfirmationState)
    suspended_revision: int = 0
    resume_count: int = 0

    @staticmethod
    def slot_key(tool_name: str, param: str) -> str:
        return f"{str(tool_name).rstrip('+')}.{param}"

    def validate_slot(
        self,
        tool_name: str,
        param: str,
        value: Any,
        *,
        dependency_signatures: tuple[str, ...] = (),
    ) -> bool:
        key = self.slot_key(tool_name, param)
        previous = self.slots.get(key)
        unchanged = bool(
            previous
            and previous.resolution_status == VALIDATED
            and previous.value == value
            and previous.dependency_signatures == dependency_signatures
        )
        self.slots[key] = SlotState(
            value=value,
            resolution_status=VALIDATED,
            dependency_signatures=tuple(dependency_signatures),
        )
        return not unchanged

    def invalidate_slot(self, tool_name: str, param: str, *, reason: str) -> bool:
        key = self.slot_key(tool_name, param)
        state = self.slots.get(key) or SlotState()
        changed = state.resolution_status != INVALID or state.invalid_reason != str(reason)
        state.resolution_status = INVALID
        state.invalid_reason = str(reason or "")
        self.slots[key] = state
        return changed

    def project_semantic_prefill(self) -> dict[str, dict[str, Any]]:
        projection: dict[str, dict[str, Any]] = {}
        # A validated joint decision is authoritative for all of its members.
        # Project the members atomically instead of copying them into independent
        # SlotState records that can later be recombined across revisions.
        for name, decision in self.decisions.items():
            if decision.resolution_status != VALIDATED or "." not in name:
                continue
            tool_name = name.split(".", 1)[0]
            member_projection = {
                param: decision.values.get(param)
                for param in decision.member_slots
                if decision.values.get(param) not in (None, "", [])
            }
            if member_projection:
                projection.setdefault(tool_name, {}).update(member_projection)
        for key, state in self.slots.items():
            if state.resolution_status != VALIDATED or "." not in key:
                continue
            tool_name, param = key.split(".", 1)
            if param in projection.get(tool_name, {}):
                continue
            if state.value not in (None, "", []):
                projection.setdefault(tool_name, {})[param] = state.value
        return projection

    def project_read_bindings(self) -> dict[str, dict[str, Any]]:
        projection = self.project_semantic_prefill()
        for authorization in self.read_authorizations.values():
            projection.setdefault(authorization["tool"], {})[authorization["param"]] = authorization["values"]
        return projection

    def stale_changed_dependencies(
        self,
        signatures_by_tool: dict[str, tuple[str, ...]],
    ) -> list[tuple[str, str, str]]:
        stale: list[tuple[str, str, str]] = []
        for key, state in self.slots.items():
            if state.resolution_status != VALIDATED or not state.dependency_signatures or "." not in key:
                continue
            tool_name, param = key.split(".", 1)
            current = signatures_by_tool.get(tool_name, ())
            if current != state.dependency_signatures:
                state.resolution_status = STALE
                state.invalid_reason = "dependency_signature_changed"
                stale.append(("slot", tool_name, param))
        for name, decision in self.decisions.items():
            if decision.resolution_status != VALIDATED or not decision.dependency_signatures:
                continue
            tool_name = name.split(".", 1)[0]
            current = signatures_by_tool.get(tool_name, ())
            if current != decision.dependency_signatures:
                decision.resolution_status = STALE
                decision.invalid_reason = "dependency_signature_changed"
                stale.append(("decision", tool_name, name.split(".", 1)[-1]))
        return stale

    def validate_decision(
        self,
        name: str,
        *,
        values: dict[str, Any],
        member_slots: tuple[str, ...],
        dependency_signatures: tuple[str, ...] = (),
    ) -> bool:
        previous = self.decisions.get(str(name))
        unchanged = bool(
            previous
            and previous.resolution_status == VALIDATED
            and previous.values == values
            and previous.dependency_signatures == dependency_signatures
        )
        self.decisions[str(name)] = DecisionState(
            values=dict(values),
            resolution_status=VALIDATED,
            member_slots=tuple(member_slots),
            dependency_signatures=tuple(dependency_signatures),
        )
        return not unchanged

    def invalidate_decision(self, name: str, *, member_slots: tuple[str, ...], reason: str) -> bool:
        state = self.decisions.get(str(name)) or DecisionState(member_slots=tuple(member_slots))
        changed = state.resolution_status != INVALID or state.invalid_reason != str(reason)
        state.resolution_status = INVALID
        state.invalid_reason = str(reason or "")
        self.decisions[str(name)] = state
        return changed

    def observe_confirmation_candidate(self, candidate_signature: str) -> str:
        signature = str(candidate_signature or "")
        if self.confirmation.candidate_signature == signature:
            return "reused" if self.confirmation.status == "CONFIRMED" else "unchanged"
        had_previous = bool(self.confirmation.candidate_signature)
        self.confirmation = ConfirmationState(candidate_signature=signature, status="PENDING")
        return "stale" if had_previous else "new"

    def confirm(self, candidate_signature: str) -> bool:
        signature = str(candidate_signature or "")
        if not signature:
            return False
        self.confirmation = ConfirmationState(candidate_signature=signature, status="CONFIRMED")
        return True

    def confirmation_token(self) -> dict[str, str] | None:
        return self.confirmation.token()

    def deny_confirmation(self, candidate_signature: str) -> None:
        signature = str(candidate_signature or "")
        if signature and self.confirmation.candidate_signature == signature:
            self.confirmation.status = "DENIED"


# 兼容旧导入；持久状态的真实类型已经是 MotifFrame。
SuspendedMotif = MotifFrame


@dataclass
class MotifContextManager:
    entity_cache: Any = None
    failed_param_cache: Any = None
    messages: list[dict[str, Any]] = field(default_factory=list)
    dialogue_state: dict[str, Any] = field(default_factory=dict)
    recovery: dict[str, Any] = field(default_factory=dict)
    evidence: BoundEvidence = field(default_factory=BoundEvidence)
    dependency_status: dict[str, Any] = field(default_factory=dict)
    terminal_outcome: Any = None
    completed_motifs: list[dict[str, Any]] = field(default_factory=list)
    current_motif_id: str | None = None
    suspended_motifs: dict[str, MotifFrame] = field(default_factory=dict)
    frames: dict[str, MotifFrame] = field(default_factory=dict)
    active_instance_by_motif: dict[str, str] = field(default_factory=dict)
    invocation_counts: dict[str, int] = field(default_factory=dict)

    def activate_motif(
        self,
        motif_id: str,
        *,
        execution_plan: list[str],
        plan_step: int,
        motif_tools: set[str] | None = None,
    ) -> MotifFrame:
        motif_key = str(motif_id)
        instance_id = self.active_instance_by_motif.get(motif_key)
        frame = self.frames.get(instance_id or "")
        if frame is not None and frame.lifecycle_status in {"ACTIVE", "SUSPENDED"}:
            frame.execution_plan = list(execution_plan or frame.execution_plan)
            frame.plan_step = int(plan_step)
            frame.motif_tools.update(motif_tools or set())
            return frame
        invocation = self.invocation_counts.get(motif_key, 0) + 1
        self.invocation_counts[motif_key] = invocation
        instance_id = f"{motif_key}:{invocation}"
        frame = MotifFrame(
            motif_instance_id=instance_id,
            motif_id=motif_key,
            execution_plan=list(execution_plan or [motif_key]),
            plan_step=int(plan_step),
            motif_tools=set(motif_tools or set()),
        )
        self.frames[instance_id] = frame
        self.active_instance_by_motif[motif_key] = instance_id
        return frame

    def active_frame(self, motif_id: str) -> MotifFrame | None:
        return self.frames.get(self.active_instance_by_motif.get(str(motif_id), ""))

    def add_completed_motif(self, motif_id: str, tool_results: dict[str, Any]) -> None:
        motif_key = str(motif_id)
        frame = self.suspended_motifs.pop(motif_key, None) or self.active_frame(motif_key)
        if frame is not None:
            frame.lifecycle_status = "COMPLETED"
            self.frames.pop(frame.motif_instance_id, None)
            self.dependency_status.pop(frame.motif_instance_id, None)
        self.active_instance_by_motif.pop(motif_key, None)
        summary = self._generate_motif_summary(motif_id, tool_results)
        self.completed_motifs.append(
            {
                "motif_id": motif_id,
                "summary": summary,
                "tool_results": tool_results,
                "evidence_keys": self._completed_evidence_keys(frame, tool_results),
            }
        )

    def _completed_evidence_keys(self, frame, tool_results):
        if frame is None:
            return []
        # 只存绑定证据的索引，避免复制 payload；重复读取保留全部绑定而非最后一个。
        return [key for key, record in self.evidence.records.items()
                if record["type"] in frame.motif_tools and key in tool_results]

    def transfer_completed_bindings(self, source_id: str, target_id: str, skill: dict) -> None:
        """仅由显式计划/编译转移调用，继承前驱已完成的必需读取绑定。"""
        completed = next((item for item in reversed(self.completed_motifs)
                          if item["motif_id"] == source_id), None)
        if completed is None:
            return
        required = set((skill.get("dependencies") or {}).get("required_evidence", []))
        by_tool: dict[str, list[dict]] = {}
        for key in completed.get("evidence_keys", []):
            record = self.evidence.records.get(key)
            if record is not None and record["type"] in required:
                by_tool.setdefault(record["type"], []).append(record["binding"])
        for tool, bindings in by_tool.items():
            if len(bindings) != 1:
                continue
            frame = self.activate_motif(target_id, execution_plan=[target_id], plan_step=0)
            existing = frame.project_semantic_prefill().get(tool, {})
            if existing and existing != bindings[0]:
                continue
            for param, value in bindings[0].items():
                frame.validate_slot(tool, param, value)

    def suspend_motif(
        self,
        *,
        motif_id: str,
        execution_plan: list[str],
        plan_step: int,
        motif_tools: set[str] | None = None,
        completed_tools: set[str] | None = None,
        tool_results: dict[str, Any] | None = None,
        missing_params: dict[str, list[str]] | None = None,
        revision: int,
    ) -> MotifFrame:
        motif_key = str(motif_id)
        state = self.suspended_motifs.get(motif_key) or self.activate_motif(
            motif_key,
            execution_plan=execution_plan,
            plan_step=plan_step,
            motif_tools=motif_tools,
        )
        state.lifecycle_status = "SUSPENDED"
        state.execution_plan = list(execution_plan)
        state.plan_step = int(plan_step)
        state.motif_tools.update(motif_tools or set())
        state.completed_tools.update(completed_tools or set())
        state.tool_results.update(tool_results or {})
        state.missing_params = {str(tool): list(params) for tool, params in (missing_params or {}).items()}
        state.suspended_revision = int(revision)
        self.suspended_motifs[motif_key] = state
        return state

    def next_resumable_motif(self, revision: int) -> SuspendedMotif | None:
        for state in reversed(list(self.suspended_motifs.values())):
            if int(revision) > state.suspended_revision:
                return state
        return None

    def resumable_motif(self, motif_id: str, revision: int) -> SuspendedMotif | None:
        state = self.suspended_motifs.get(str(motif_id))
        if state is not None and int(revision) > state.suspended_revision:
            return state
        return None

    def mark_resumed(self, motif_id: str, revision: int) -> SuspendedMotif | None:
        state = self.suspended_motifs.get(str(motif_id))
        if state is None:
            return None
        state.suspended_revision = int(revision)
        state.resume_count += 1
        state.lifecycle_status = "ACTIVE"
        return state

    def has_suspended_motifs(self) -> bool:
        return bool(self.suspended_motifs) or any(f.lifecycle_status == "SUSPENDED" for f in self.frames.values())

    def has_suspended_motif_waiting_for(self, entity_types: set[str]) -> bool:
        available = {str(entity) for entity in entity_types if str(entity)}
        if not available:
            return False
        return any(
            available
            & {
                str(param)
                for params in state.missing_params.values()
                for param in params
                if str(param)
            }
            for state in self.suspended_motifs.values()
        )

    def record_suspended_tool_result(
        self,
        tool_name: str,
        result: Any,
        *,
        motif_id: str | None = None,
    ) -> list[SuspendedMotif]:
        base_tool = str(tool_name).rstrip("+")
        completed: list[SuspendedMotif] = []
        candidates = [
            (state_motif_id, state)
            for state_motif_id, state in self.suspended_motifs.items()
            if base_tool in {str(tool).rstrip("+") for tool in state.motif_tools}
        ]
        anchored = [item for item in candidates if motif_id is not None and item[0] == str(motif_id)]
        selected = anchored or (candidates if len(candidates) == 1 else [])
        for state_motif_id, state in selected:
            motif_tools = {str(tool).rstrip("+") for tool in state.motif_tools}
            state.completed_tools.add(base_tool)
            state.tool_results[base_tool] = result
            state.missing_params.pop(base_tool, None)
            if motif_tools and motif_tools <= state.completed_tools:
                completed.append(state)
                self.suspended_motifs.pop(state_motif_id, None)
                state.lifecycle_status = "COMPLETED"
                self.frames.pop(state.motif_instance_id, None)
                self.active_instance_by_motif.pop(state.motif_id, None)
                self.completed_motifs.append(
                    {
                        "motif_id": state.motif_id,
                        "summary": self._generate_motif_summary(state.motif_id, state.tool_results),
                        "tool_results": dict(state.tool_results),
                        "evidence_keys": self._completed_evidence_keys(state, state.tool_results),
                    }
                )
        return completed

    def build_context_for_llm(self, current_task: str) -> str:
        summaries = [m["summary"] for m in self.completed_motifs]
        summary_text = "\n".join(summaries) if summaries else "(none)"
        return (
            "Completed motifs:\n"
            f"{summary_text}\n\n"
            f"Current task: {current_task}"
        )

    def _generate_motif_summary(self, motif_id: str, tool_results: dict[str, Any]) -> str:
        snippets: list[str] = []
        for tool_name, result in tool_results.items():
            if isinstance(result, dict):
                important = []
                for key, value in result.items():
                    if isinstance(value, (str, int, float, bool)) and len(important) < 5:
                        important.append(f"{key}={result[key]}")
                if important:
                    snippets.append(f"{tool_name}({', '.join(important)})")
                else:
                    snippets.append(f"{tool_name}(ok)")
            else:
                snippets.append(f"{tool_name}(ok)")
        return f"Completed {motif_id}: " + "; ".join(snippets)
