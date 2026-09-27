"""Motif-owned selection, execution and reentry for certified read operators.

The host specifies the required output tool, current input version, and tool
adapter. It does not choose an artifact or issue individual tool calls. Model
or human decisions enter only through a signed, bounded handoff.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .context_manager import MotifContextManager
from .evidence import BoundEvidence
from .handoff import SemanticResolution, StructureHandoffRequest, build_no_motif_handoff
from .offline.library_builder import validate_read_motif_library
from .offline.link_compiler import validate_read_link
from .offline.trace_compiler import _field_value
from .offline.failure_evolution import (
    current_active_guards, propose_exact_failure_guard, validate_active_guard,
)
from .read_executor import ReadMotifRun, _validate_artifact, resume_read_motif, run_read_motif


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode()).hexdigest()


@dataclass
class MotifDecision:
    status: str
    motif_id: str | None
    run: ReadMotifRun | None = None
    handoff: StructureHandoffRequest | None = None
    events: tuple[dict[str, Any], ...] = ()


class MotifController:
    """One current-input Motif session with a strictly validated skill library."""

    def __init__(
        self, library: dict[str, Any], *, contracts: Mapping[str, Any],
        execute_tool: Callable[[str, dict[str, Any]], Any],
        verify_current: Callable[[], None], is_read_only: Callable[[str], bool],
        manager: MotifContextManager | None = None,
        active_guards: tuple[dict[str, Any], ...] = (),
        guard_registries: Mapping[str, dict[str, Any]] | None = None,
    ) -> None:
        validate_read_motif_library(library)
        self.artifacts = {}
        for artifact in library["artifacts"]:
            _validate_artifact(artifact, contracts)
            self.artifacts[artifact["motif_id"]] = artifact
        self.library_digest = library["library_digest"]
        self.connectors = library.get("connectors") or {}
        self.links = list(library.get("links") or [])
        for link in self.links:
            validate_read_link(link, self.artifacts, contracts)
        self.active_guards: dict[str, tuple[dict[str, Any], ...]] = {}
        for motif_id, registry in (guard_registries or {}).items():
            if motif_id not in self.artifacts:
                raise ValueError("guard registry names an unknown Motif")
            self.active_guards[motif_id] = current_active_guards(
                registry, self.artifacts[motif_id])
        for guard in active_guards:
            motif_id = guard.get("motif_id") if isinstance(guard, dict) else None
            if motif_id not in self.artifacts:
                raise ValueError("active guard names an unknown Motif")
            validate_active_guard(guard, self.artifacts[motif_id])
            self.active_guards[motif_id] = (*self.active_guards.get(motif_id, ()), guard)
        self.contracts = contracts
        self.execute_tool = execute_tool
        self.verify_current = verify_current
        self.is_read_only = is_read_only
        self.manager = manager or MotifContextManager()
        self.input_version: str | None = None
        self.pending: dict[str, Any] | None = None
        self.pending_plan: dict[str, Any] | None = None
        self.last: MotifDecision | None = None
        self.failure_history: dict[str, list[dict[str, Any]]] = {}

    def _current_version(self, input_version: str,
                         node_versions: Mapping[str, str] | None) -> None:
        if not input_version:
            raise ValueError("current input version is required")
        if node_versions is not None and (
            not isinstance(node_versions, Mapping)
            or any(not isinstance(key, str) or not key
                   or not isinstance(value, str) or not value
                   for key, value in node_versions.items())
        ):
            raise ValueError("node evidence versions must be nonempty strings")
        self.verify_current()
        if self.input_version is not None and input_version != self.input_version:
            # Explicit per-node versions preserve unaffected cached evidence.
            # Without them, the whole input snapshot is the dependency scope.
            if node_versions is None:
                self.manager = MotifContextManager()
            else:
                self.manager = MotifContextManager(evidence=self.manager.evidence)
            self.pending = None
            self.pending_plan = None
            self.last = None
        self.input_version = input_version

    def _run(self, motif_id: str, bindings: dict[str, dict[str, Any]],
             input_version: str,
             node_versions: Mapping[str, str] | None = None) -> MotifDecision:
        artifact = self.artifacts[motif_id]
        if node_versions is not None and any(tool not in node_versions
                                             for tool in artifact["tools"]):
            raise ValueError("selected Motif lacks a node evidence version")
        scoped_versions = ({tool: node_versions[tool] for tool in artifact["tools"]}
                           if node_versions is not None else None)
        result = run_read_motif(
            artifact, contracts=self.contracts, bindings=bindings,
            input_version=input_version, execute_tool=self.execute_tool,
            verify_current=self.verify_current, is_read_only=self.is_read_only,
            manager=self.manager,
            active_guards=self.active_guards.get(motif_id, ()),
            node_versions=scoped_versions)
        decision = MotifDecision(result.status, motif_id, result, result.handoff,
                                 tuple(result.events))
        self.last = decision
        if (result.failure_witness is not None
                and result.failure_witness.get("reason") == "dependency_tool_error"):
            history = self.failure_history.setdefault(motif_id, [])
            history.append(result.failure_witness)
            del history[:-128]
        return decision

    def failure_guard_proposals(self, motif_id: str) -> list[dict[str, Any]]:
        """Return quarantined exact-failure revisions; never activate them."""
        if motif_id not in self.artifacts:
            raise ValueError("unknown Motif")
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in self.failure_history.get(motif_id, []):
            key = tuple(str(row.get(field) or "") for field in (
                "operator", "reason", "error_class", "motif_signature",
                "binding_signature", "input_version"))
            groups.setdefault(key, []).append(row)
        return [propose_exact_failure_guard(self.artifacts[motif_id], rows)
                for rows in groups.values() if len(rows) >= 2]

    def execute_goal(self, *, required_output: str,
                     bindings: dict[str, dict[str, Any]],
                     input_version: str,
                     intent: str = "",
                     node_versions: Mapping[str, str] | None = None) -> MotifDecision:
        """Choose a certified motif ending in the requested observable result."""
        self._current_version(input_version, node_versions)
        self.pending_plan = None
        if (not required_output or not isinstance(bindings, dict)
                or not isinstance(intent, str) or len(intent) > 1000):
            raise ValueError("a required output and tool bindings are needed")
        candidates = [row for row in self.artifacts.values()
                      if row["tools"][-1].rstrip("+") == required_output
                      and set(bindings) <= set(row["tools"])
                      and (node_versions is None
                           or set(row["tools"]) <= set(node_versions))]
        if not candidates:
            return self.execute_graph_goal(
                required_output=required_output, bindings=bindings,
                input_version=input_version, node_versions=node_versions)
        if len(candidates) == 1:
            self.pending = None
            return self._run(candidates[0]["motif_id"], bindings, input_version,
                             node_versions)
        ids = sorted(row["motif_id"] for row in candidates)
        previous = (self.manager.completed_motifs[-1]["motif_id"]
                    if self.manager.completed_motifs else None)
        observed = {
            motif_id: self.connectors.get(f"{previous}|{motif_id}", {})
            for motif_id in ids
        } if previous else {}
        scope = {"library_digest": self.library_digest,
                 "input_version": input_version,
                 "required_output": required_output,
                 "intent": intent,
                 "observed_connectors": observed,
                 "node_version_signature": _digest(dict(node_versions))
                                           if node_versions is not None else None,
                 "binding_signature": _digest(bindings), "candidates": ids}
        handoff = StructureHandoffRequest(
            handoff_type="need_user_clarification", source="motif_match",
            available_state=scope,
            allowed_reentry={"mode": "motif_choice", "candidates": ids})
        self.pending = {"scope": scope, "bindings": bindings,
                        "node_versions": dict(node_versions) if node_versions is not None else None,
                        "handoff_signature": _digest(handoff.to_dict())}
        self.last = MotifDecision("needs_motif_choice", None, handoff=handoff)
        return self.last

    def _graph_plan(self, target: str, bindings: dict[str, dict[str, Any]],
                    node_versions: Mapping[str, str] | None) -> dict[str, Any] | None:
        """Build an acyclic dependency graph from certified parameter edges."""
        order: list[str] = []
        edges: list[dict[str, Any]] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(motif_id: str) -> bool:
            if motif_id in visiting:
                return False
            if motif_id in visited:
                return True
            artifact = self.artifacts[motif_id]
            if node_versions is not None and not set(artifact["tools"]) <= set(node_versions):
                return False
            visiting.add(motif_id)
            entry_tool = artifact["tools"][0]
            for param in self.contracts[entry_tool].required_params:
                if param in bindings.get(entry_tool, {}):
                    continue
                incoming = [link for link in self.links
                            if link["to_motif"] == motif_id
                            and link["to_tool"] == entry_tool
                            and link["to_param"] == param]
                if len(incoming) > 1:
                    return False
                if incoming:
                    link = incoming[0]
                    if not visit(link["from_motif"]):
                        return False
                    edges.append(link)
            visiting.remove(motif_id)
            visited.add(motif_id)
            order.append(motif_id)
            return True

        if not visit(target) or len(order) < 2:
            return None
        tools = [tool for motif_id in order for tool in self.artifacts[motif_id]["tools"]]
        if len(set(tools)) != len(tools) or not set(bindings) <= set(tools):
            return None
        return {"nodes": order, "edges": edges}

    def execute_graph_goal(self, *, required_output: str,
                           bindings: dict[str, dict[str, Any]],
                           input_version: str,
                           node_versions: Mapping[str, str] | None = None) -> MotifDecision:
        """Run a uniquely proven Motif DAG, independent of its path length."""
        self._current_version(input_version, node_versions)
        self.pending_plan = None
        if not required_output or not isinstance(bindings, dict):
            raise ValueError("a required output and tool bindings are needed")
        plans = [plan for row in self.artifacts.values()
                 if row["tools"][-1].rstrip("+") == required_output
                 if (plan := self._graph_plan(row["motif_id"], bindings,
                                              node_versions)) is not None]
        if len(plans) != 1:
            handoff = build_no_motif_handoff(
                available_state={"required_output": required_output,
                                 "library_digest": self.library_digest,
                                 "input_version": input_version},
                reason="no_unique_certified_graph_for_output")
            self.last = MotifDecision("no_motif", None, handoff=handoff)
            return self.last
        plan = plans[0]
        self.pending_plan = {**plan, "index": 0, "outputs": {},
                             "bindings": {tool: dict(params)
                                          for tool, params in bindings.items()},
                             "input_version": input_version,
                             "node_versions": dict(node_versions)
                             if node_versions is not None else None,
                             "events": [], "library_digest": self.library_digest}
        return self._advance_plan()

    def execute_linked_goal(self, *, required_output: str,
                            bindings: dict[str, dict[str, Any]],
                            input_version: str,
                            node_versions: Mapping[str, str] | None = None) -> MotifDecision:
        """Compatibility entry point; graph execution now has no hop limit."""
        return self.execute_graph_goal(required_output=required_output,
                                       bindings=bindings, input_version=input_version,
                                       node_versions=node_versions)

    def _advance_plan(self) -> MotifDecision:
        pending = self.pending_plan
        if (pending is None or pending["input_version"] != self.input_version
                or pending["library_digest"] != self.library_digest):
            raise ValueError("Motif graph execution is stale")
        while pending["index"] < len(pending["nodes"]):
            motif_id = pending["nodes"][pending["index"]]
            artifact = self.artifacts[motif_id]
            scoped = {tool: dict(pending["bindings"].get(tool, {}))
                      for tool in artifact["tools"]
                      if tool in pending["bindings"]}
            for link in pending["edges"]:
                if link["to_motif"] != motif_id:
                    continue
                validate_read_link(link, self.artifacts, self.contracts)
                self.verify_current()
                source = pending["outputs"].get(link["from_motif"], {})
                value = _field_value(source.get(link["from_tool"]), link["from_field"])
                existing = scoped.get(link["to_tool"], {}).get(link["to_param"])
                if value is None or (existing is not None and existing != value):
                    self.pending_plan = None
                    handoff = build_no_motif_handoff(
                        available_state={"link_digest": link["link_digest"],
                                         "input_version": self.input_version},
                        reason="cross_motif_source_evidence_missing_or_conflicting")
                    self.last = MotifDecision("blocked", motif_id, handoff=handoff)
                    return self.last
                scoped.setdefault(link["to_tool"], {})[link["to_param"]] = value
                pending["events"].append({"event": "certified_motif_link_applied",
                                          "link_digest": link["link_digest"]})
            result = self._run(motif_id, scoped, pending["input_version"],
                               pending["node_versions"])
            if result.status != "completed":
                pending["events"].extend(result.events)
                if result.status != "needs_mediation":
                    self.pending_plan = None
                result.events = tuple(pending["events"])
                return result
            pending["outputs"][motif_id] = result.run.outputs
            pending["events"].extend(result.events)
            pending["index"] += 1
        self.pending_plan = None
        result.events = tuple(pending["events"])
        return result

    def resume_selection(self, resolution: SemanticResolution) -> MotifDecision:
        pending = self.pending
        if pending is None or self.last is None or self.last.handoff is None:
            raise ValueError("no Motif selection is suspended")
        scope = pending["scope"]
        action = resolution.action or {}
        motif_id = action.get("motif_id") if isinstance(action, dict) else None
        if (resolution.resolution_type != "motif_choice"
                or set(action) != {"motif_id"}
                or motif_id not in scope["candidates"]
                or resolution.metadata.get("handoff_signature")
                != pending["handoff_signature"]
                or scope["library_digest"] != self.library_digest
                or scope["input_version"] != self.input_version
                or scope["node_version_signature"] != (
                    _digest(pending["node_versions"])
                    if pending["node_versions"] is not None else None)
                or scope["binding_signature"] != _digest(pending["bindings"])):
            raise ValueError("semantic choice is outside the suspended Motif scope")
        self.verify_current()
        self.pending = None
        return self._run(motif_id, pending["bindings"], scope["input_version"],
                         pending["node_versions"])

    def resume_slots(self, resolution: SemanticResolution) -> MotifDecision:
        previous = self.last
        if (previous is None or previous.run is None
                or previous.run.status != "needs_mediation"
                or previous.motif_id not in self.artifacts
                or previous.run.input_version != self.input_version):
            raise ValueError("no current Motif parameter gap is suspended")
        run = resume_read_motif(
            self.artifacts[previous.motif_id], previous.run, resolution,
            contracts=self.contracts, execute_tool=self.execute_tool,
            verify_current=self.verify_current, is_read_only=self.is_read_only,
            active_guards=self.active_guards.get(previous.motif_id, ()))
        self.last = MotifDecision(run.status, run.motif_id, run, run.handoff,
                                  tuple(run.events))
        if (self.pending_plan is not None
                and run.motif_id == self.pending_plan["nodes"][self.pending_plan["index"]]):
            pending = self.pending_plan
            pending["events"].extend(run.events)
            if run.status == "completed":
                pending["outputs"][run.motif_id] = run.outputs
                pending["index"] += 1
                if pending["index"] < len(pending["nodes"]):
                    return self._advance_plan()
                self.pending_plan = None
            if run.status != "needs_mediation":
                self.pending_plan = None
            self.last.events = tuple(pending["events"])
        if (run.failure_witness is not None
                and run.failure_witness.get("reason") == "dependency_tool_error"):
            history = self.failure_history.setdefault(run.motif_id, [])
            history.append(run.failure_witness)
            del history[:-128]
        return self.last

    def export_evidence_snapshot(self) -> dict[str, Any]:
        """Export version-bound successful tool observations for a private host store."""
        if self.input_version is None or self.last is None:
            raise ValueError("no current Motif execution has evidence to export")
        self.verify_current()
        approved = {tool.rstrip("+") for artifact in self.artifacts.values()
                    for tool in artifact["tools"]}
        rows = []
        for key, record in sorted(self.manager.evidence.records.items()):
            tool = record.get("type")
            if tool not in approved or not isinstance(record.get("version"), str):
                continue
            binding = record.get("binding")
            if not isinstance(binding, dict) or key != BoundEvidence.key(tool, binding):
                raise ValueError("Motif evidence has an invalid binding key")
            rows.append({"tool": tool, "binding": deepcopy(binding),
                         "value": deepcopy(record["value"]),
                         "version": record["version"]})
        if not rows or len(rows) > 512:
            raise ValueError("Motif evidence snapshot is empty or exceeds its bound")
        snapshot = {"schema_version": 1, "library_digest": self.library_digest,
                    "input_version": self.input_version, "records": rows}
        if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > 16_000_000:
            raise ValueError("Motif evidence snapshot exceeds 16 MB")
        snapshot["snapshot_digest"] = _digest(snapshot)
        return snapshot

    def restore_evidence_snapshot(self, snapshot: dict[str, Any], *,
                                  current_input_version: str) -> int:
        """Restore only exact-version observations; the host verifies source freshness."""
        if (self.input_version is not None or self.last is not None
                or self.pending is not None or self.pending_plan is not None):
            raise ValueError("Motif evidence can only enter a fresh controller")
        if not isinstance(snapshot, dict):
            raise ValueError("invalid Motif evidence snapshot")
        body = {key: value for key, value in snapshot.items()
                if key != "snapshot_digest"}
        rows = snapshot.get("records")
        if (snapshot.get("schema_version") != 1
                or snapshot.get("library_digest") != self.library_digest
                or not current_input_version
                or snapshot.get("input_version") != current_input_version
                or snapshot.get("snapshot_digest") != _digest(body)
                or not isinstance(rows, list) or not 1 <= len(rows) <= 512
                or len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > 16_000_000):
            raise ValueError("Motif evidence snapshot is stale or invalid")
        self.verify_current()
        approved = {tool.rstrip("+") for artifact in self.artifacts.values()
                    for tool in artifact["tools"]}
        evidence = BoundEvidence()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"tool", "binding", "value", "version"}:
                raise ValueError("Motif evidence snapshot record is invalid")
            tool, binding, version = row["tool"], row["binding"], row["version"]
            contract = self.contracts.get(tool) if isinstance(tool, str) else None
            if (tool not in approved or contract is None
                    or not isinstance(binding, dict)
                    or not set(contract.required_params) <= set(binding)
                    or not set(binding) <= (set(contract.required_params)
                                            | set(dict(contract.default_params)))
                    or not isinstance(version, str) or not version
                    or BoundEvidence.key(tool, binding) in evidence.records
                    or not evidence.record(tool, binding, deepcopy(row["value"]),
                                           version=version)):
                raise ValueError("Motif evidence snapshot record is invalid")
        self.manager = MotifContextManager(evidence=evidence)
        self.input_version = current_input_version
        return len(rows)

    def export_replay_checkpoint(self) -> dict[str, Any]:
        """Save a read or motif-choice handoff for safe process restart.

        Tool results are deliberately omitted. Restoring re-executes the
        certified read operations and checks the same bounded frontier.
        """
        pending = self.pending_plan
        last = self.last
        if last is None or last.handoff is None:
            raise ValueError("no certified read handoff can be checkpointed")
        if pending is not None and last.status == "needs_mediation":
            kind = "read_graph_handoff_replay"
            target = self.artifacts[pending["nodes"][-1]]["tools"][-1].rstrip("+")
            bindings = pending["bindings"]
            input_version = pending["input_version"]
            node_versions = pending["node_versions"]
            plan_nodes = pending["nodes"]
        elif self.pending is not None and last.status == "needs_motif_choice":
            kind = "motif_choice_replay"
            target = self.pending["scope"]["required_output"]
            bindings = self.pending["bindings"]
            input_version = self.pending["scope"]["input_version"]
            node_versions = self.pending["node_versions"]
            plan_nodes = None
        elif last.status == "needs_mediation" and last.run is not None:
            kind = "read_motif_handoff_replay"
            target = self.artifacts[last.motif_id]["tools"][-1].rstrip("+")
            bindings = last.run.bindings
            input_version = last.run.input_version
            node_versions = last.run.node_versions
            plan_nodes = None
        else:
            raise ValueError("no certified read handoff can be checkpointed")
        checkpoint = {
            "schema_version": 1, "kind": kind,
            "library_digest": self.library_digest,
            "required_output": target,
            "bindings": deepcopy(bindings),
            "input_version": input_version,
            "node_versions": deepcopy(node_versions),
            "plan_nodes": list(plan_nodes) if plan_nodes is not None else None,
            "blocked_motif": last.motif_id,
            "handoff_signature": _digest(last.handoff.to_dict()),
        }
        checkpoint["checkpoint_digest"] = _digest(checkpoint)
        return checkpoint

    def replay_checkpoint(self, checkpoint: dict[str, Any], *,
                          current_input_version: str,
                          current_node_versions: Mapping[str, str] | None = None
                          ) -> MotifDecision:
        """Rebuild a paused frontier only if current evidence reaches the same gap."""
        body = {key: value for key, value in checkpoint.items()
                if key != "checkpoint_digest"}
        expected_versions = (dict(current_node_versions)
                             if current_node_versions is not None else None)
        if (expected_versions is None
                and checkpoint.get("kind") == "read_motif_handoff_replay"
                and checkpoint.get("blocked_motif") in self.artifacts):
            # A single Motif run records effective per-node versions even when
            # the caller supplied only one input snapshot. Recreate that
            # implicit map rather than requiring the caller to echo saved data.
            expected_versions = {
                tool: current_input_version
                for tool in self.artifacts[checkpoint["blocked_motif"]]["tools"]}
        if (checkpoint.get("schema_version") != 1
                or checkpoint.get("kind") not in {
                    "read_graph_handoff_replay", "read_motif_handoff_replay",
                    "motif_choice_replay"}
                or checkpoint.get("checkpoint_digest") != _digest(body)
                or checkpoint.get("library_digest") != self.library_digest
                or checkpoint.get("input_version") != current_input_version
                or checkpoint.get("node_versions") != expected_versions
                or self.pending is not None or self.pending_plan is not None
                or self.last is not None):
            raise ValueError("read graph checkpoint is stale or invalid")
        try:
            runner = (self.execute_graph_goal if checkpoint["kind"] == "read_graph_handoff_replay"
                      else self.execute_goal)
            decision = runner(
                required_output=checkpoint["required_output"],
                bindings=checkpoint["bindings"],
                input_version=current_input_version,
                node_versions=current_node_versions)
            expected_status = ("needs_motif_choice" if checkpoint["kind"] == "motif_choice_replay"
                               else "needs_mediation")
            if (decision.status != expected_status or decision.handoff is None
                    or decision.motif_id != checkpoint["blocked_motif"]
                    or (checkpoint["kind"] == "read_graph_handoff_replay"
                        and (self.pending_plan is None
                             or self.pending_plan["nodes"] != checkpoint["plan_nodes"]))
                    or _digest(decision.handoff.to_dict()) != checkpoint["handoff_signature"]):
                raise ValueError("current read Motif no longer reaches the saved handoff")
            return decision
        except Exception:
            # Never leave a partially replayed graph eligible for a stale reentry.
            self.pending = None
            self.pending_plan = None
            self.last = None
            self.manager = MotifContextManager()
            raise
