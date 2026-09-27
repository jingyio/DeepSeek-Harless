"""Office research adapter on the migrated MotifAgent state/evidence runtime.

The parser is deliberately narrow: it accepts the structured synthetic records
used by office_research_v0. This is a mechanism run, not a research quality claim.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.motif_core import MotifContextManager, StructureHandoffRequest, resolve_dependencies
from src.motif_core.context_manager import SlotState


READ_METADATA = {
    "required_evidence": ["read_document"],
    "operators": {
        "read_document": {
            "read_only": True,
            "required_params": ["file", "sha256"],
        }
    },
}
RECORD_ID = re.compile(r"^Record ID:\s*(\S+)\s*$", re.MULTILINE)
VERSION = re.compile(r"^Version:\s*(\d+)\s*$", re.MULTILINE)
STATUS = re.compile(r"^Status:\s*(.+)$", re.MULTILINE)
SUITE = re.compile(r"^Evaluation suite:\s*(.+)$", re.MULTILINE)
PASSED = re.compile(r"\bpassed (\d+) of (\d+) tasks\b")


class OfficeHandoffError(ValueError):
    def __init__(self, request: StructureHandoffRequest) -> None:
        super().__init__(request.reason or request.source)
        self.request = request


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record(text: str, filename: str, digest: str) -> dict[str, Any]:
    rid = RECORD_ID.search(text)
    status = STATUS.search(text)
    if not rid or not status:
        raise ValueError(f"missing record metadata: {filename}")
    version = VERSION.search(text)
    suite = SUITE.search(text)
    return {
        "file": filename,
        "sha256": digest,
        "record_id": rid.group(1),
        "version": int(version.group(1)) if version else None,
        "official": status.group(1).lower().startswith("official"),
        "correction": "correction" in status.group(1).lower(),
        "suite": suite.group(1) if suite else None,
        "text": text,
    }


def _sentence(text: str, anchor: str) -> str:
    for line in text.splitlines():
        for sentence in re.split(r"(?<=\.)\s+", line):
            if anchor in sentence:
                return sentence.strip()
    raise ValueError(f"support anchor absent: {anchor}")


def _archive(records: list[dict[str, Any]]) -> tuple[list[dict[str, str]], dict[str, dict[str, Any]]]:
    seen_hashes: set[str] = set()
    unique: list[dict[str, Any]] = []
    duplicates: set[str] = set()
    for record in records:
        if record["sha256"] in seen_hashes:
            duplicates.add(record["file"])
        else:
            seen_hashes.add(record["sha256"])
            unique.append(record)
    canonical: dict[str, dict[str, Any]] = {}
    for record in unique:
        if not record["official"] or record["version"] is None:
            continue
        rid = record["record_id"]
        old = canonical.get(rid)
        if old is None or record["version"] > old["version"]:
            canonical[rid] = record
        elif record["version"] == old["version"] and record["sha256"] != old["sha256"]:
            raise OfficeHandoffError(StructureHandoffRequest(
                handoff_type="need_user_clarification",
                source="official_revision_conflict",
                motif_id="office_research",
                available_state={"record_id": rid, "version": record["version"],
                                 "candidate_files": [old["file"], record["file"]]},
                allowed_reentry={"mode": "same_motif", "candidates": [old["file"], record["file"]]},
                reason="two different official files claim the same record and version",
            ))
    archive = []
    for record in records:
        if record["file"] in duplicates:
            state = "duplicate"
        elif not record["official"]:
            state = "needs_review"
        elif canonical[record["record_id"]]["file"] == record["file"]:
            state = "canonical"
        else:
            state = "superseded"
        archive.append({"file": record["file"], "record_id": record["record_id"], "status": state})
    return archive, canonical


def _facts(canonical: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Task-specific answer adapter; all values and quotes come from source text."""
    facts = []
    answer_ids = {"MF-24": "mf_success", "GP-25": "gp_success", "RF-26": "rf_success"}
    for rid, answer_id in answer_ids.items():
        if rid not in canonical:
            continue
        record = canonical[rid]
        match = PASSED.search(record["text"])
        if match is None:
            raise ValueError(f"missing measured pass count: {record['file']}")
        anchor = match.group(0).removeprefix("passed ")
        facts.append({
            "id": answer_id,
            "value": f"{match.group(1)}/{match.group(2)}",
            "source_file": record["file"],
            "support_quote": _sentence(record["text"], anchor),
        })
    corrected = canonical.get("MF-24")
    if corrected and corrected["correction"] and "not 32 of 40" in corrected["text"]:
        facts.append({
            "id": "mf_previous_invalid", "value": True,
            "source_file": corrected["file"],
            "support_quote": _sentence(corrected["text"], "not 32 of 40"),
        })
    route = canonical.get("TR-25")
    if route and "not directly comparable" in route["text"]:
        facts.append({
            "id": "tr_not_comparable", "value": True,
            "source_file": route["file"],
            "support_quote": _sentence(route["text"], "not directly comparable"),
        })
    return sorted(facts, key=lambda row: row["id"])


def _report(canonical: dict[str, dict[str, Any]], facts: list[dict[str, Any]]) -> str:
    by_id = {row["id"]: row for row in facts}
    comparable = []
    for rid, fid in (("MF-24", "mf_success"), ("GP-25", "gp_success"), ("RF-26", "rf_success")):
        row = by_id.get(fid)
        if row:
            comparable.append(f"{rid} {row['value']}（{row['source_file']}）")
    lines = ["# 组会资料简报（合成任务）", "", "LabSuite-40、2024-06 快照中的可比记录：" + "；".join(comparable) + "。"]
    if "mf_previous_invalid" in by_id:
        corrected_file = by_id["mf_previous_invalid"]["source_file"]
        lines.append(f"MF-24 的正式更正版替代旧版 32/40；旧数值失效，参见 {corrected_file}。")
    if "tr_not_comparable" in by_id:
        route = canonical["TR-25"]
        lines.append(f"TR-25 使用 {route['suite']}，与 LabSuite-40 的通过数不能直接排名（{route['file']}）。")
    lines.append("未核实笔记保留待人工复核，不作为正式结果。")
    return "\n".join(lines)


def _restore(state: dict[str, Any]) -> MotifContextManager:
    manager = MotifContextManager()
    for entry in state["evidence"]:
        manager.evidence.record(entry["type"], entry["binding"], entry["value"],
                                version=entry.get("version"))
    frame_data = state["frame"]
    frame = manager.suspend_motif(
        motif_id=frame_data["motif_id"],
        execution_plan=frame_data["execution_plan"],
        plan_step=frame_data["plan_step"],
        motif_tools=set(frame_data["motif_tools"]),
        completed_tools=set(frame_data["completed_tools"]),
        revision=frame_data["suspended_revision"],
    )
    frame.slots = {
        key: SlotState(**{**row, "dependency_signatures": tuple(row["dependency_signatures"])})
        for key, row in frame_data["slots"].items()
    }
    frame.resume_count = frame_data["resume_count"]
    return manager


def _persist(manager: MotifContextManager, input_hashes: dict[str, str], stage: str) -> dict[str, Any]:
    frame = manager.active_frame("office_research")
    if frame is None:
        raise RuntimeError("motif frame missing")
    frame_data = asdict(frame)
    frame_data["motif_tools"] = sorted(frame.motif_tools)
    frame_data["completed_tools"] = sorted(frame.completed_tools)
    return {
        "schema_version": 1,
        "stage": stage,
        "input_hashes": input_hashes,
        "frame": frame_data,
        "evidence": list(manager.evidence.records.values()),
    }


def run(stage: str, input_dir: Path, previous_state: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    if stage not in {"A", "B"}:
        raise ValueError("stage must be A or B")
    if stage == "B" and (previous_state is None or previous_state.get("stage") != "A"):
        raise ValueError("stage B requires a stage A state file")
    if stage == "A" and previous_state is not None:
        raise ValueError("stage A cannot resume a previous state")
    paths = sorted(input_dir.glob("*.md"))
    if not paths:
        raise ValueError("no Markdown inputs")
    manager = _restore(previous_state) if previous_state else MotifContextManager()
    revision = 2 if stage == "B" else 1
    frame = manager.mark_resumed("office_research", revision) if stage == "B" else manager.activate_motif(
        "office_research", execution_plan=["read_document", "archive", "extract", "report"],
        plan_step=0, motif_tools={"read_document", "archive", "extract", "report"},
    )
    if frame is None:
        raise RuntimeError("cannot resume office research motif")
    events: list[dict[str, Any]] = []
    input_hashes = {path.name: _sha(path.read_bytes()) for path in paths}
    old_hashes = previous_state["input_hashes"] if previous_state else {}
    if stage == "B" and not set(old_hashes) <= set(input_hashes):
        raise ValueError("stage B must retain stage A source files")
    records = []
    reused_sources = []
    for path in paths:
        binding = {"file": path.name, "sha256": input_hashes[path.name]}
        cached = manager.evidence.lookup("read_document", binding)

        def execute(tool: str, params: dict[str, str]) -> dict[str, str]:
            if tool != "read_document" or params != binding:
                raise ValueError("unverified read binding")
            content = path.read_bytes()
            if _sha(content) != params["sha256"]:
                raise ValueError("source changed during read")
            return {"text": content.decode("utf-8"), "sha256": params["sha256"]}

        result = resolve_dependencies(
            READ_METADATA, manager.evidence, {"read_document": binding}, execute,
            lambda tool: tool == "read_document", lambda *_args, **_kwargs: None,
        )
        if result.status != "SUCCESS":
            raise RuntimeError(f"document read blocked: {path.name}: {result.reason}")
        evidence = manager.evidence.lookup("read_document", binding)
        if evidence is None:
            raise RuntimeError("bound evidence absent after read")
        if cached is not None:
            reused_sources.append(path.name)
        events.append({"event": "source_reused" if cached else "source_read", "file": path.name, "sha256": binding["sha256"]})
        records.append(_record(evidence["value"]["text"], path.name, binding["sha256"]))
    archive, canonical = _archive(records)
    signatures = {f"canonical_{rid}": (f"{rid}:{record['sha256']}",) for rid, record in canonical.items()}
    stale = frame.stale_changed_dependencies(signatures)
    invalidated_records = sorted({tool.removeprefix("canonical_") for kind, tool, _ in stale if kind == "slot"})
    for rid in invalidated_records:
        events.append({"event": "record_invalidated", "record_id": rid, "reason": "canonical_source_changed"})
    for rid, record in canonical.items():
        changed = frame.validate_slot(f"canonical_{rid}", "source", record["file"],
                                      dependency_signatures=signatures[f"canonical_{rid}"])
        events.append({"event": "record_validated" if changed else "record_retained", "record_id": rid,
                       "file": record["file"], "signature": signatures[f"canonical_{rid}"][0]})
    facts = _facts(canonical)
    prediction = {
        "stage": stage, "archive": archive, "facts": facts, "report": _report(canonical, facts),
        "trace": {"reused_sources": reused_sources, "invalidated_records": invalidated_records,
                  "model_requests": 0, "motif_instance_id": frame.motif_instance_id,
                  "resume_count": frame.resume_count},
    }
    manager.suspend_motif(
        motif_id="office_research", execution_plan=frame.execution_plan, plan_step=len(frame.execution_plan),
        motif_tools=frame.motif_tools, completed_tools=frame.motif_tools,
        tool_results={"archive": archive, "facts": facts}, revision=revision,
    )
    events.append({"event": "motif_suspended", "motif_instance_id": frame.motif_instance_id,
                   "revision": revision, "resume_count": frame.resume_count})
    return prediction, _persist(manager, input_hashes, stage), events


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
