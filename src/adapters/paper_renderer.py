"""Freeze a trace-generated PDF program; replay only its reviewed current input.

This host does not generate a new layout algorithm or certify scientific claims.
The historical program contains paper-specific prose, so publication as a general
MCP renderer remains blocked until a model removes those embedded conclusions.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import re
import unicodedata


SCHEMA = "paper-renderer-preparation-v1"
PUBLISHED_SCHEMA = "paper-renderer-generated-v1"
SOURCE_PATH = "work/make_pdf.py"
FONT_PATH = "fonts/NotoSansSC-VF.ttf"
PDF_PATH = "reference-check-report.pdf"
# Reviewed source from a real DeepSeek write followed by two successful edits.
# Admission is deliberately exact: a new source needs a new independent review.
REVIEWED_SOURCE_SHA256 = "c54400836357cd3bdb7386349ee2bf178a9ddbddf918c3c562995a5f15686c87"
BASE_LINE = "BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))"
BOUND_BASE_LINE = "BASE = os.environ['SSS_PAPER_RENDER_WORK']"


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, limit: int = 2_000_000) -> bytes:
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("renderer_symlink_rejected")
    if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > limit:
        raise ValueError("renderer_regular_bounded_file_required")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise ValueError("renderer_file_size_changed")
    return raw


def _json_write(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _trace_path(path: str) -> str:
    return str(PurePosixPath(path.replace("\\", "/")))


def reconstruct_renderer(run_dir: Path, source_relative: str = SOURCE_PATH) -> dict:
    """Replay successful write/edit *text*, never historical shell or Python."""
    run_dir = Path(run_dir)
    manifest_raw = _read(run_dir / "manifest.json", 8_000_000)
    manifest = json.loads(manifest_raw)
    if PurePosixPath(source_relative).is_absolute() or ".." in PurePosixPath(source_relative).parts:
        raise ValueError("renderer_invalid_source_relative")
    target = _trace_path(manifest["work"].rstrip("/\\") + "/" + source_relative)
    raw_events = _read(run_dir / "session-events.jsonl", 100_000_000)
    current = None
    pending = {}
    provenance = []
    for number, line in enumerate(raw_events.splitlines(), 1):
        record = json.loads(line)
        if record.get("session_id") != manifest["session_id"]:
            continue
        event = record.get("event", {})
        data = event.get("data", {})
        if event.get("type") == "tool/call" and data.get("name") in ("write", "edit"):
            args = data.get("arguments", {})
            args = json.loads(args) if isinstance(args, str) else args
            if _trace_path(args.get("file_path", "")) == target:
                call_id = data["callId"]
                if call_id in pending or any(p["call_id"] == call_id for p in provenance):
                    raise ValueError("renderer_duplicate_call_id")
                pending[call_id] = (data, args, number)
        elif event.get("type") == "tool/result":
            for item in data.get("message", {}).get("content", []):
                call_id = item.get("toolCallId")
                if item.get("type") != "tool-result" or call_id not in pending:
                    continue
                call, args, call_line = pending.pop(call_id)
                if item.get("isError") is not False:
                    continue
                if call["name"] == "write":
                    current = args["content"]
                else:
                    old, new = args["old_string"], args["new_string"]
                    if current is None or not old or current.count(old) != 1:
                        raise ValueError("renderer_edit_not_unique_or_missing_source")
                    if args.get("replace_all", False):
                        raise ValueError("renderer_replace_all_not_supported")
                    current = current.replace(old, new, 1)
                provenance.append({"call_id": call_id, "tool": call["name"],
                                   "step": call.get("step"), "call_line": call_line,
                                   "result_line": number, "source_sha256": sha256(current.encode())})
    if pending or current is None:
        raise ValueError("renderer_incomplete_write_edit_provenance")
    actual = _read(run_dir / "work" / source_relative)
    if current.encode() != actual:
        raise ValueError("renderer_final_source_not_reconstructed")
    return {"source": current, "source_sha256": sha256(actual),
            "session_id": manifest["session_id"], "model": manifest.get("model"),
            "provider": manifest.get("provider"), "run_id": manifest.get("run_id"),
            "manifest_sha256": sha256(manifest_raw), "events_sha256": sha256(raw_events),
            "mutations": provenance}


INPUT_SCHEMA = {
    "schema": "paper-audit-render-input-v1",
    "required_root": ["schema_version", "scope", "reference_count", "references", "sources", "issues", "citation_checks", "notes"],
    "reference_required": ["number", "key", "short_title", "status", "priority", "source_ids", "explanation", "evidence_files"],
    "source_required": ["id", "platform", "url"],
    "issue_required": ["priority", "number_or_location", "problem", "finding", "recommended_fix"],
    "citation_checks_required": ["list_without_citation", "citation_without_entry", "duplicate_entries", "numbering_anomaly", "unresolved_or_abnormal_citations", "non_citation_brackets"],
    "citation_result_required": ["result", "evidence", "limitation"],
    "status_enum": ["已确认", "已确认，但需修正", "存疑", "未找到"],
    "priority_enum": ["—", "P0", "P1", "P2", "P3"],
    "bounds": {"max_references": 1000, "max_sources": 2000, "max_issues": 2000, "max_input_bytes": 2000000},
    "unknown_fields": "preserved_in_input; renderer_must_not_infer_new_claims",
}


def validate_audit(audit: dict) -> None:
    """Data shape/identity admission only; does not decide reference truth."""
    if not isinstance(audit, dict) or not set(INPUT_SCHEMA["required_root"]) <= audit.keys():
        raise ValueError("renderer_input_missing_root_fields")
    refs, sources, issues = (audit[k] for k in ("references", "sources", "issues"))
    for rows, key, maximum in ((refs, "reference_required", 1000), (sources, "source_required", 2000), (issues, "issue_required", 2000)):
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ValueError("renderer_input_array_limit")
        for row in rows:
            if not isinstance(row, dict) or not set(INPUT_SCHEMA[key]) <= row.keys():
                raise ValueError("renderer_input_missing_record_fields")
    if type(audit["reference_count"]) is not int or audit["reference_count"] != len(refs):
        raise ValueError("renderer_input_count_mismatch")
    if [r["number"] for r in refs] != list(range(1, len(refs) + 1)) or any(type(r["number"]) is not int for r in refs):
        raise ValueError("renderer_input_numbering_mismatch")
    if any(not isinstance(r["key"], str) for r in refs) or len({r["key"] for r in refs}) != len(refs):
        raise ValueError("renderer_input_duplicate_keys")
    for rows, fields in ((refs, ("key", "short_title", "status", "priority", "explanation")),
                         (sources, ("id", "platform", "url")),
                         (issues, tuple(INPUT_SCHEMA["issue_required"]))):
        for row in rows:
            if any(not isinstance(row[f], str) for f in fields):
                raise ValueError("renderer_input_text_required")
    ids = [s["id"] for s in sources]
    if len(ids) != len(set(ids)):
        raise ValueError("renderer_input_duplicate_source_ids")
    for r in refs:
        if r["status"] not in INPUT_SCHEMA["status_enum"] or r["priority"] not in INPUT_SCHEMA["priority_enum"]:
            raise ValueError("renderer_input_invalid_status_priority")
        for field in ("source_ids", "evidence_files"):
            if not isinstance(r[field], list) or not all(isinstance(v, str) for v in r[field]):
                raise ValueError("renderer_input_text_list_required")
        if not set(r["source_ids"]) <= set(ids):
            raise ValueError("renderer_input_missing_source")
    checks = audit["citation_checks"]
    if not isinstance(checks, dict) or not set(INPUT_SCHEMA["citation_checks_required"]) <= checks.keys():
        raise ValueError("renderer_input_missing_citation_checks")
    for field in INPUT_SCHEMA["citation_checks_required"]:
        value = checks[field]
        if not isinstance(value, dict) or any(not isinstance(value.get(k), str) for k in INPUT_SCHEMA["citation_result_required"]):
            raise ValueError("renderer_input_invalid_citation_result")


def audit_pdf_content_coverage(pdf_path: Path, audit: dict) -> dict:
    """Check literal report fields in the produced PDF text and link objects.

    This checks preservation, not the truth of any reference or visual quality.
    """
    from pypdf import PdfReader

    validate_audit(audit)
    reader = PdfReader(pdf_path)
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 200:
        raise ValueError("renderer_pdf_pages_invalid")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    links = []
    for page in reader.pages:
        for annotation in page.get("/Annots", []):
            action = annotation.get_object().get("/A", {})
            if action.get("/URI"):
                links.append(str(action["/URI"]))

    def normalized(value: str) -> str:
        return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)
                      .replace("\u00ad", "").replace("\u200b", ""))

    body = normalized(text)
    linked = normalized(text + "\n" + "\n".join(links))
    checks = []

    def check(value, *, link=False):
        if isinstance(value, str) and value.strip():
            checks.append(normalized(value) in (linked if link else body))

    for row in audit["references"]:
        for field in ("short_title", "status", "priority", "explanation"):
            check(row[field])
    for row in audit["sources"]:
        for field in ("id", "platform", "url"):
            check(row[field], link=field == "url")
    for row in audit["issues"]:
        for value in row.values():
            check(value)
    for row in audit["citation_checks"].values():
        for value in row.values():
            check(value)
    for note in audit.get("notes", []) if isinstance(audit.get("notes"), list) else []:
        check(note)
    return {"pdf_pages": len(reader.pages), "checked_fields": len(checks),
            "present_fields": sum(checks), "all_fields_present": all(checks),
            "has_text_layer": bool(body), "has_replacement_character": "\ufffd" in text,
            "source_link_objects": len(links), "semantic_quality_accepted": False,
            "visual_quality_reviewed": False}


def _capability_audit(source: str) -> dict:
    tree = ast.parse(source)
    calls, blocked = [], []
    forbidden = {"exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars"}
    allowed_roots = {"json", "os", "collections", "reportlab", "html", "re", "math"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if any(n.split(".")[0] not in allowed_roots for n in names):
                blocked.append({"line": node.lineno, "kind": "unreviewed_import"})
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            calls.append({"line": node.lineno, "call": name})
            if name in forbidden or name.startswith(("os.system", "os.popen", "os.exec", "os.spawn", "os.remove", "os.unlink", "os.rename", "os.rmdir", "os.mkdir")):
                blocked.append({"line": node.lineno, "kind": "dynamic_or_extra_effect", "call": name})
    return {"origin": "engineering_static_inventory_not_sandbox_or_semantic_certification",
            "calls": calls, "blocked": blocked, "manual_source_review_required": True}


def publish_generated_renderer(package_dir: Path, generation_run: Path, output_dir: Path | None = None,
                               source_relative: str = SOURCE_PATH) -> dict:
    """Freeze a newly generated version as pending review; never executes it.

    The caller must separately review source and pin manifest/source/schema hashes
    in a trusted review record before render_renderer can run new report inputs.
    """
    package_dir = Path(package_dir)
    parent_raw = _read(package_dir / "manifest.json")
    parent = json.loads(parent_raw)
    if parent.get("schema") != SCHEMA:
        raise ValueError("renderer_preparation_required")
    evidence = reconstruct_renderer(generation_run, source_relative)
    source = evidence.pop("source")
    if evidence["source_sha256"] == parent["source"]["source_sha256"]:
        raise ValueError("renderer_revision_unchanged")
    capability = _capability_audit(source)
    bound = bind_workspace(source).encode()
    font = _read(package_dir / "font.ttf", 25_000_000)
    if sha256(font) != parent["files"]["font.ttf"]:
        raise ValueError("renderer_parent_font_changed")
    output_dir = Path(output_dir) if output_dir else package_dir.parent / ("generated-" + evidence["source_sha256"][:16])
    schema_raw = (json.dumps(INPUT_SCHEMA, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    manifest = {"schema": PUBLISHED_SCHEMA, "state": "pending_manual_source_review_and_diagnostics",
                "parent_manifest_sha256": sha256(parent_raw), "source": evidence,
                "files": {"generated-original.py": sha256(source.encode()), "generated-bound.py": sha256(bound),
                          "font.ttf": sha256(font), "input-schema.json": sha256(schema_raw)},
                "input": {"path": "audit.json", "schema": INPUT_SCHEMA["schema"], "schema_sha256": sha256(schema_raw)},
                "output": {"path": PDF_PATH, "effect": "new_private_task_pdf_only"},
                "parameterization": {"origin": "engineering_workspace_binding_only", "layout_algorithm_changed": False},
                "capability_audit": capability, "automatic_runtime_execution_enabled": False,
                "required_diagnostics": ["changed_reference_count", "changed_status_priority", "changed_sources",
                                         "all_current_reference_rows_and_source_ids_in_pdf", "per_page_visual_review"],
                "limitations": ["Model generation provenance is verified; scientific conclusions are not certified.",
                                "Static inventory alone never authorizes executing generated code."]}
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, raw in (("generated-original.py", source.encode()), ("generated-bound.py", bound),
                      ("font.ttf", font), ("input-schema.json", schema_raw)):
        with (output_dir / name).open("xb") as stream:
            stream.write(raw)
    _json_write(output_dir / "manifest.json", manifest)
    return {"package": str(output_dir), "manifest_sha256": sha256((output_dir / "manifest.json").read_bytes()),
            "source_sha256": evidence["source_sha256"], "state": manifest["state"],
            "static_blockers": capability["blocked"]}


def inspect_renderer(source: str) -> dict:
    """Expose constants for model-led revision; flags are not semantic proof."""
    tree = ast.parse(source)
    imports = sorted({node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
                     | {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names})
    # Long strings and reference/identifier-looking literals are review candidates.
    # Preserve exact text privately so a model can edit only affected statements.
    literals = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if len(text) > 45 or "Paper #" in text or "doi.org/" in text:
                literals.append({"line": node.lineno, "end_line": node.end_lineno,
                                 "text": text, "sha256": sha256(text.encode())})
    return {"imports": imports, "embedded_text_review_candidates": literals,
            "review_candidate_count": len(literals), "general_publication_ready": False,
            "blocking_reason": "embedded_paper_identity_counts_citation_claims_and_replacement_bibliography",
            "required_model_revision": [
                "Move paper identity, date, scope and all conclusions out of renderer source into versioned report data.",
                "Read replacements, summary counts and minimum fix list from current audit data; preserve source-backed judgments.",
                "Keep generated page/table/layout functions; change only data bindings and reject missing semantic fields.",
                "Do not infer findings from static strings or silently reuse old paper conclusions."]}


def bind_workspace(source: str) -> str:
    if source.count(BASE_LINE) != 1:
        raise ValueError("renderer_unrecognized_workspace_binding")
    return source.replace(BASE_LINE, BOUND_BASE_LINE, 1)


def prepare_renderer(run_dir: Path, output_dir: Path) -> dict:
    """Create immutable private preparation package, without executing its code."""
    run_dir, output_dir = Path(run_dir), Path(output_dir)
    evidence = reconstruct_renderer(run_dir)
    original = evidence.pop("source")
    audit = _read(run_dir / "work/audit.json")
    json.loads(audit)
    font = _read(run_dir / "work" / FONT_PATH, 25_000_000)
    bound = bind_workspace(original).encode()
    review = inspect_renderer(original)
    manifest = {"schema": SCHEMA, "source": evidence,
                "files": {"generated-original.py": sha256(original.encode()),
                          "generated-bound.py": sha256(bound), "font.ttf": sha256(font)},
                "parameterization": {"origin": "engineering_workspace_binding_only",
                                     "replacement_count": 1, "layout_algorithm_changed": False},
                "input": {"path": "audit.json", "sha256": sha256(audit),
                          "reuse_scope": "same_report_bytes_only_due_to_embedded_claims"},
                "output": {"path": PDF_PATH, "effect": "new_private_diagnostic_pdf_only"},
                "review": review, "automatic_runtime_execution_enabled": False,
                "reviewed_replay_source": evidence["source_sha256"] == REVIEWED_SOURCE_SHA256,
                "limitations": ["Historical report quality is not certified.",
                                "Trace extraction and host binding are engineering; layout source was generated by DeepSeek.",
                                "Preparation is not a general renderer, learned Motif, new training task or saving claim."]}
    output_dir.mkdir(parents=True, exist_ok=False)
    for name, raw in (("generated-original.py", original.encode()), ("generated-bound.py", bound),
                      ("font.ttf", font), ("audit.original.json", audit)):
        with (output_dir / name).open("xb") as stream:
            stream.write(raw)
    _json_write(output_dir / "manifest.json", manifest)
    return {"package": str(output_dir), "manifest_sha256": sha256((output_dir / "manifest.json").read_bytes()),
            "source_sha256": evidence["source_sha256"], "mutations": len(evidence["mutations"]),
            "general_publication_ready": False, "embedded_text_review_candidates": review["review_candidate_count"]}


def render_renderer(package_dir: Path, expected_manifest_sha256: str, task_dir: Path,
                    expected_audit_sha256: str, python_executable: Path, timeout: int = 60,
                    review_path: Path | None = None, expected_review_sha256: str | None = None) -> dict:
    """Explicit diagnostic only, executing the reviewed source and unchanged audit.

    No arbitrary source or output argument is accepted. The hash comes from trusted
    host configuration, not from a model tool call. This is process control plus
    exact reviewed-code admission, not an OS sandbox for untrusted Python.
    """
    package_dir, task_dir = Path(package_dir), Path(task_dir)
    manifest_raw = _read(package_dir / "manifest.json")
    if sha256(manifest_raw) != expected_manifest_sha256:
        raise ValueError("renderer_manifest_version_mismatch")
    manifest = json.loads(manifest_raw)
    if manifest.get("schema") not in (SCHEMA, PUBLISHED_SCHEMA):
        raise ValueError("renderer_schema_mismatch")
    original = _read(package_dir / "generated-original.py")
    if manifest["schema"] == SCHEMA:
        if sha256(original) != REVIEWED_SOURCE_SHA256:
            raise ValueError("renderer_source_not_reviewed")
    else:
        if review_path is None or expected_review_sha256 is None:
            raise ValueError("renderer_generated_source_review_required")
        review_raw = _read(review_path)
        review = json.loads(review_raw)
        schema_raw = _read(package_dir / "input-schema.json")
        if (sha256(review_raw) != expected_review_sha256 or review.get("schema") != "paper-renderer-source-review-v1"
                or review.get("approved") is not True or review.get("manifest_sha256") != expected_manifest_sha256
                or review.get("source_sha256") != sha256(original)
                or review.get("input_schema_sha256") != sha256(schema_raw)
                or review.get("embedded_claims_removed") is not True
                or review.get("fixed_input_output_only") is not True
                or json.loads(schema_raw) != INPUT_SCHEMA
                or sha256(schema_raw) != manifest["files"].get("input-schema.json")
                or _capability_audit(original.decode())["blocked"]):
            raise ValueError("renderer_generated_source_review_mismatch")
    source = _read(package_dir / "generated-bound.py")
    font = _read(package_dir / "font.ttf", 25_000_000)
    if source != bind_workspace(original.decode()).encode():
        raise ValueError("renderer_parameterization_mismatch")
    for name, raw in (("generated-original.py", original), ("generated-bound.py", source), ("font.ttf", font)):
        if manifest["files"].get(name) != sha256(raw):
            raise ValueError("renderer_package_file_version_mismatch")
    audit = _read(task_dir / "audit.json")
    if sha256(audit) != expected_audit_sha256:
        raise ValueError("renderer_input_version_mismatch")
    if manifest["schema"] == SCHEMA and sha256(audit) != manifest["input"]["sha256"]:
        raise ValueError("renderer_embedded_claims_require_same_audit")
    validate_audit(json.loads(audit))
    output = task_dir / PDF_PATH
    if output.exists() or output.is_symlink():
        raise ValueError("renderer_existing_output_rejected")
    # Keep a venv's executable path: resolving its symlink would select the base
    # interpreter and lose the pinned document dependencies.
    python_executable = Path(os.path.abspath(python_executable))
    if not python_executable.is_file() or not os.access(python_executable, os.X_OK) or not 1 <= timeout <= 120:
        raise ValueError("renderer_invalid_host_configuration")
    with tempfile.TemporaryDirectory(prefix=".renderer-", dir=task_dir) as tmp:
        stage = Path(tmp).resolve()
        (stage / "fonts").mkdir()
        (stage / "audit.json").write_bytes(audit)
        (stage / FONT_PATH).write_bytes(font)
        (stage / "renderer.py").write_bytes(source)
        env = {key: os.environ[key] for key in ("PATH", "SYSTEMROOT", "WINDIR") if key in os.environ}
        env.update({"SSS_PAPER_RENDER_WORK": str(stage.resolve()), "PYTHONIOENCODING": "utf-8"})
        result = subprocess.run([str(python_executable), "-I", "-B", str(stage / "renderer.py")],
                                cwd=stage, env=env, capture_output=True, timeout=timeout, check=False)
        if result.returncode:
            raise ValueError("renderer_process_failed:" + result.stderr.decode(errors="replace")[-2000:])
        pdf = _read(stage / PDF_PATH, 20_000_000)
        if not pdf.startswith(b"%PDF-") or b"%%EOF" not in pdf[-1024:]:
            raise ValueError("renderer_invalid_pdf")
        if sha256(_read(task_dir / "audit.json")) != expected_audit_sha256:
            raise ValueError("renderer_input_changed_during_render")
        if _read(package_dir / "manifest.json") != manifest_raw or _read(package_dir / "generated-bound.py") != source:
            raise ValueError("renderer_package_changed_during_render")
        with output.open("xb") as stream:
            stream.write(pdf)
    return {"schema": "paper-renderer-receipt-v1", "manifest_sha256": expected_manifest_sha256,
            "source_sha256": sha256(original), "input_sha256": expected_audit_sha256,
            "output_path": str(output), "output_sha256": sha256(pdf), "output_bytes": len(pdf),
            "mode": "same_input_diagnostic" if manifest["schema"] == SCHEMA else "reviewed_generated_renderer_diagnostic",
            "semantic_quality_accepted": False,
            "requires_per_page_visual_review": True, "model_calls": 0}
