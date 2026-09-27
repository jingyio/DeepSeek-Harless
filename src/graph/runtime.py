"""Small executable motif runtime with explicit evidence and safe stopping.

This is deliberately independent of a particular model provider. Semantic
gaps are surfaced as typed requests instead of being guessed by the runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from json import dumps
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class Evidence:
    value: Any
    source: str
    verified: bool = True

    @property
    def digest(self) -> str:
        data = dumps(self.value, sort_keys=True, ensure_ascii=False, default=str)
        return sha256(data.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SemanticGap(Exception):
    kind: str
    question: str
    allowed_answers: tuple[str, ...] = ()
    evidence_keys: tuple[str, ...] = ()


Action = Callable[[Mapping[str, Evidence]], Mapping[str, Any]]
Guard = Callable[[Mapping[str, Evidence]], bool]


@dataclass(frozen=True)
class Node:
    id: str
    deps: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    action: Action
    guard: Guard = lambda _state: True


@dataclass(frozen=True)
class Motif:
    id: str
    nodes: tuple[Node, ...]

    def validate(self) -> None:
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"duplicate node: {node.id}")
            if not set(node.deps) <= seen:
                raise ValueError(f"{node.id}: dependencies must precede node")
            seen.add(node.id)


@dataclass
class Run:
    motif_id: str
    state: dict[str, Evidence]
    events: list[dict[str, Any]] = field(default_factory=list)
    status: str = "running"
    gap: SemanticGap | None = None

    def report(self) -> dict[str, Any]:
        return {
            "motif": self.motif_id,
            "status": self.status,
            "events": self.events,
            "gap": None if self.gap is None else {
                "kind": self.gap.kind,
                "question": self.gap.question,
                "allowed_answers": self.gap.allowed_answers,
                "evidence_keys": self.gap.evidence_keys,
            },
            "evidence": {
                key: {"source": item.source, "digest": item.digest}
                for key, item in self.state.items()
            },
        }


def execute(motif: Motif, initial: Mapping[str, Evidence]) -> Run:
    motif.validate()
    run = Run(motif.id, dict(initial))
    completed: set[str] = set()
    for node in motif.nodes:
        if not set(node.deps) <= completed:
            raise AssertionError("motif validation failed")
        missing = [key for key in node.inputs if key not in run.state or not run.state[key].verified]
        if missing:
            run.status = "needs_mediation"
            run.gap = SemanticGap("missing_evidence", f"{node.id}: missing verified inputs: {', '.join(missing)}", evidence_keys=tuple(missing))
            run.events.append({"node": node.id, "status": "mediation", "kind": run.gap.kind})
            break
        try:
            if not node.guard(run.state):
                raise SemanticGap("guard_failed", f"{node.id}: evidence guard did not pass", evidence_keys=node.inputs)
            produced = dict(node.action(run.state))
            if set(produced) != set(node.outputs):
                raise ValueError(f"{node.id}: output schema mismatch")
            for key, value in produced.items():
                if key in run.state:
                    raise ValueError(f"{node.id}: duplicate evidence key {key}")
                run.state[key] = Evidence(value, source=f"{motif.id}/{node.id}")
            completed.add(node.id)
            run.events.append({"node": node.id, "status": "verified", "inputs": list(node.inputs), "outputs": list(node.outputs)})
        except SemanticGap as gap:
            run.status = "needs_mediation"
            run.gap = gap
            run.events.append({"node": node.id, "status": "mediation", "kind": gap.kind})
            break
        except Exception as exc:
            run.status = "stopped"
            run.events.append({"node": node.id, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            break
    else:
        run.status = "completed"
    return run
