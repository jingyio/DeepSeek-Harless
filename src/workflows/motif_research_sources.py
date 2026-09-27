"""Incremental, hash-bound source collection using the migrated Motif state core.

This is the source/read stage of the research workflow. Later retrieval and
answer gates still use the existing SSS graph runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import asdict
from decimal import Decimal, InvalidOperation, localcontext
from io import BytesIO
from pathlib import Path
from typing import Any

from src.motif_core import MotifContextManager, resolve_dependencies
from src.motif_core.context_manager import SlotState
from src.motif_core.failure_feedback import dependency_failure_witness
from src.motif_core.controller import MotifController
from src.motif_core.offline.library_builder import library_from_certified
from src.workflows.research_source_tools import (
    ResearchSourceToolClient, SOURCE_TOOL_CONTRACTS, SUPPORTED_SOURCE_SUFFIXES,
)


MOTIF_ID = "research_sources"
PARSER_VERSION = 5
READ_METADATA = {
    "required_evidence": ["read_source"],
    "operators": {"read_source": {"read_only": True, "required_params": ["source", "sha256"]}},
}


class SourceReadBlocked(ValueError):
    """A failed Motif read with evidence safe to retain for later revision."""

    def __init__(self, source: str, witness: dict[str, Any]) -> None:
        super().__init__(f"source read failed: {source}: {witness['reason']}")
        self.witness = witness


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_numeric_profile(value: list[Any], *, first_page: int,
                          source: str, digest: str) -> list[dict[str, Any]]:
    """Derive small, auditable numeric summaries from a JSON record array.

    These are explicitly derived passages. Each names the exact source record
    range and is invalidated by the same source hash as the original records.
    """
    if not value or len(value) > 2000 or not all(isinstance(row, dict) for row in value):
        return []
    fields: dict[str, list[Decimal]] = defaultdict(list)
    unsupported_number = False

    def visit(prefix: str, item: Any) -> None:
        nonlocal unsupported_number
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(key, str):
                    visit(f"{prefix}.{key}" if prefix else key, child)
        elif isinstance(item, (int, float, Decimal)) and not isinstance(item, bool):
            try:
                number = Decimal(str(item))
                if (number.is_finite() and len(prefix) <= 120
                        and abs(number.adjusted()) <= 100
                        and len(number.as_tuple().digits) <= 120
                        and number.as_tuple().exponent >= -120):
                    fields[prefix].append(number)
                else:
                    unsupported_number = True
            except InvalidOperation:
                unsupported_number = True

    for row in value:
        visit("", row)
    if unsupported_number or not fields or len(fields) > 128:
        return []

    def render(number: Decimal) -> str:
        result = format(number, "f")
        return result.rstrip("0").rstrip(".") if "." in result else result

    lines = []
    numeric_fields: dict[str, dict[str, str | int]] = {}
    for name, values in sorted(fields.items()):
        if not name or len(values) != len(value):
            # Partial fields need a semantic decision about the denominator.
            continue
        # Default Decimal precision (28) could silently round a large sum.
        # Preserve every supplied decimal digit; only the displayed mean may
        # round when the quotient repeats.
        precision = max(value.adjusted() for value in values) - min(
            value.as_tuple().exponent for value in values) + len(str(len(values))) + 4
        with localcontext() as context:
            context.prec = max(28, precision)
            total = sum(values, Decimal(0))
            mean = total / len(values)
        numeric_fields[name] = {"count": len(values), "sum": render(total),
                                "mean": render(mean)}
        lines.append(f"{name}: count={len(values)}, sum={render(total)}, "
                     f"mean={render(mean)}")
    if not lines:
        return []
    text = (f"DERIVED NUMERIC SUMMARY from JSON records 1-{len(value)}; "
            "each listed field occurs in every record; booleans are excluded; "
            "sum/count are exact and means are rounded.\n" + "\n".join(lines))
    if len(text) > 6000:
        return []
    return [{"source": source, "page": first_page, "text": text,
             "source_sha256": digest, "evidence_kind": "derived_numeric_summary",
             "derived_from_pages": [1, len(value)], "numeric_fields": numeric_fields}]


def _parse(path: Path, raw: bytes, digest: str) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        texts = [(index, page.extract_text() or "")
                 for index, page in enumerate(PdfReader(BytesIO(raw)).pages, 1)]
    elif path.suffix.lower() == ".json":
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            texts = [(index, json.dumps(value, ensure_ascii=False, sort_keys=True))
                     for index, value in enumerate(parsed, 1)]
            exact_numbers = json.loads(raw, parse_float=Decimal)
            derived = _json_numeric_profile(exact_numbers, first_page=len(texts) + 1,
                                            source=path.name, digest=digest)
        elif isinstance(parsed, dict):
            texts = [(index, json.dumps({key: value}, ensure_ascii=False, sort_keys=True))
                     for index, (key, value) in enumerate(parsed.items(), 1)]
        else:
            texts = [(1, json.dumps(parsed, ensure_ascii=False))]
    else:
        texts = [(1, raw.decode("utf-8"))]
    pages = [{"source": path.name, "page": number, "text": text, "source_sha256": digest}
             for number, text in texts if text.strip()]
    return pages + (derived if path.suffix.lower() == ".json"
                    and isinstance(parsed, list) else [])


def _restore(previous: dict[str, Any]) -> MotifContextManager:
    if (previous.get("schema_version") != 1 or previous.get("motif_id") != MOTIF_ID
            or previous.get("parser_version") != PARSER_VERSION):
        raise ValueError("unsupported Motif research source state")
    manager = MotifContextManager()
    for record in previous["evidence"]:
        manager.evidence.record(record["type"], record["binding"], record["value"],
                                version=record.get("version"))
    frame = manager.suspend_motif(
        motif_id=MOTIF_ID, execution_plan=["read_source", "dedupe"], plan_step=2,
        motif_tools={"read_source", "dedupe"}, completed_tools={"read_source", "dedupe"},
        revision=int(previous["revision"]),
    )
    frame.slots = {
        key: SlotState(**{**row, "dependency_signatures": tuple(row["dependency_signatures"])})
        for key, row in previous["slots"].items()
    }
    frame.resume_count = int(previous["resume_count"])
    return manager


def verify_source_snapshot(source_dir: Path, state: dict[str, Any]) -> None:
    """Reject additions, removals, or edits after the evidence snapshot was made."""
    root = source_dir.resolve(strict=True)
    if state.get("source_dir") != str(root):
        raise ValueError("source snapshot belongs to a different directory")
    expected = {row["binding"]["source"]: row["binding"]["sha256"]
                for row in state["evidence"]}
    paths = sorted(path for path in root.iterdir()
                   if path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES)
    if set(expected) != {path.name for path in paths}:
        raise ValueError("source snapshot changed after collection")
    for path in paths:
        if (path.is_symlink() or not path.is_file() or path.stat().st_size > 10_000_000
                or _digest(path.read_bytes()) != expected[path.name]):
            raise ValueError("source snapshot changed after collection")


def collect(source_dir: Path, previous: dict[str, Any] | None = None,
            *, read_motif_artifact: dict[str, Any] | None = None
            ) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    root = source_dir.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("source path must be a directory")
    if previous and previous.get("source_dir") != str(root):
        raise ValueError("previous source state belongs to a different directory")
    expected_motif_digest = (read_motif_artifact or {}).get("certified_digest")
    if previous and previous.get("read_motif_digest") != expected_motif_digest:
        raise ValueError("previous source state used a different Motif artifact")
    paths = sorted(path for path in root.iterdir() if path.suffix.lower() in SUPPORTED_SOURCE_SUFFIXES)
    if len(paths) > 20:
        raise ValueError("select at most 20 sources")
    if not paths:
        raise ValueError("no supported source files")
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 10_000_000:
            raise ValueError(f"source requires review: {path.name}")

    manager = _restore(previous) if previous else MotifContextManager()
    revision = int(previous["revision"]) + 1 if previous else 1
    frame = (manager.mark_resumed(MOTIF_ID, revision) if previous else
             manager.activate_motif(MOTIF_ID, execution_plan=["read_source", "dedupe"],
                                    plan_step=0, motif_tools={"read_source", "dedupe"}))
    if frame is None:
        raise RuntimeError("Motif source frame did not resume")
    events: list[dict[str, Any]] = []
    inputs = [(path, path.read_bytes()) for path in paths]
    signatures = {
        "source_" + _digest(path.name.encode("utf-8"))[:16]:
            (f"{path.name}:{_digest(raw)}",)
        for path, raw in inputs
    }
    old_slots = previous["slots"] if previous else {}
    stale = frame.stale_changed_dependencies(signatures)
    for kind, tool_name, _ in stale:
        if kind == "slot":
            old = old_slots[f"{tool_name}.sha256"]["dependency_signatures"][0]
            events.append({"event": "source_invalidated", "source": old.split(":", 1)[0],
                           "reason": "removed_or_changed"})
    pages: list[dict[str, Any]] = []
    current_bindings: set[str] = set()
    for path, raw in inputs:
        digest = _digest(raw)
        binding = {"source": path.name, "sha256": digest}
        current_bindings.add(manager.evidence.key("read_source", binding))
        cached = manager.evidence.lookup("read_source", binding)

        def execute(tool: str, params: dict[str, str]) -> dict[str, Any]:
            if tool != "read_source" or params != binding:
                raise ValueError("unverified source binding")
            # Recheck after parsing so an edit during the read cannot enter the cache.
            parsed = _parse(path, raw, digest)
            if _digest(path.read_bytes()) != digest:
                raise ValueError(f"source changed during read: {path.name}")
            return {"pages": parsed}

        if read_motif_artifact is None:
            result = resolve_dependencies(
                READ_METADATA, manager.evidence, {"read_source": binding}, execute,
                lambda tool: tool == "read_source", lambda *_args, **_kwargs: None,
            )
            if result.status != "SUCCESS":
                raise SourceReadBlocked(path.name, dependency_failure_witness(
                    motif_id=MOTIF_ID, result=result, metadata=READ_METADATA,
                    binding=binding, input_version=digest))
        else:
            client = ResearchSourceToolClient(root, path.name, digest)
            controller = MotifController(
                library_from_certified([read_motif_artifact]),
                contracts=SOURCE_TOOL_CONTRACTS,
                execute_tool=client.execute,
                verify_current=client.verify_current,
                is_read_only=lambda tool: tool in SOURCE_TOOL_CONTRACTS,
                manager=manager)
            decision = controller.execute_goal(
                required_output="read_source",
                bindings={"hash_source": {"source": path.name},
                          "read_source": {"source": path.name}},
                input_version=digest)
            run = decision.run
            if run is None:
                raise ValueError(f"source Motif selection stopped: {decision.status}")
            events.append({"event": "compiled_motif_execution", "source": path.name,
                           "motif_id": run.motif_id, "status": run.status,
                           "model_requests": 0})
            if run.status != "completed":
                if run.failure_witness is not None:
                    raise SourceReadBlocked(path.name, run.failure_witness)
                raise ValueError(f"compiled source Motif blocked: {path.name}")
        record = manager.evidence.lookup("read_source", binding)
        if record is None:
            raise RuntimeError("bound source evidence missing")
        pages.extend(record["value"]["pages"])
        events.append({"event": "source_reused" if cached else "source_read", "source": path.name,
                       "sha256": digest})
        tool_name = "source_" + _digest(path.name.encode("utf-8"))[:16]
        frame.validate_slot(tool_name, "sha256", digest, dependency_signatures=signatures[tool_name])

    if not pages:
        raise ValueError("no readable source text")
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in pages:
        normalized = re.sub(r"\s+", " ", page["text"]).strip()
        page_hash = _digest(normalized.encode("utf-8"))
        if page_hash not in seen:
            seen.add(page_hash)
            unique.append({**page, "page_sha256": page_hash})
    # Persist current bindings only; prior revisions cannot be mistaken for live evidence.
    evidence = [record for key, record in manager.evidence.records.items() if key in current_bindings]
    manager.suspend_motif(
        motif_id=MOTIF_ID, execution_plan=["read_source", "dedupe"], plan_step=2,
        motif_tools={"read_source", "dedupe"}, completed_tools={"read_source", "dedupe"},
        revision=revision,
    )
    state = {"schema_version": 1, "parser_version": PARSER_VERSION,
             "motif_id": MOTIF_ID, "source_dir": str(root),
             "read_motif_digest": expected_motif_digest,
             "revision": revision, "resume_count": frame.resume_count,
             "slots": {key: asdict(slot) for key, slot in frame.slots.items()
                       if slot.resolution_status == "VALIDATED"},
             "evidence": evidence}
    return unique, state, events
