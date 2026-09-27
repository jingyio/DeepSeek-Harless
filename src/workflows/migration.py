"""Guarded Python 3.10+ migration for selected collections ABC aliases.

Repeated, verified import/attribute rewrites run as structural operations.
Uncertain bindings and mixed imports remain semantic gaps.
"""

from __future__ import annotations

import ast
import collections.abc
import difflib
import os
import re
import shutil
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from src.graph.runtime import Evidence, Motif, Node, SemanticGap, execute


SKIP_DIRS = {".git", ".venv", ".local", "node_modules", "__pycache__", "build", "dist"}
ABCS = {"Callable", "Mapping", "MutableMapping", "MutableSet", "MutableSequence"}
MODULE_LINE = re.compile(r"^[ \t]*import[ \t]+collections[ \t]*(?:#.*)?$")
ABC_MODULE_LINE = re.compile(r"^[ \t]*import[ \t]+collections\.abc[ \t]*(?:#.*)?$")
PATTERN_BINDINGS = tuple(getattr(ast, name) for name in ("MatchAs", "MatchStar") if hasattr(ast, name))
MATCH_MAPPING = getattr(ast, "MatchMapping", None)


def _binding_is_safe(tree: ast.Module, import_node: ast.Import) -> bool:
    """Require one top-level binding with no competing assignment or import."""
    bindings = [
        node for node in tree.body
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.name == "collections" and alias.asname is None
    ]
    if bindings != [import_node]:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "collections" and isinstance(node.ctx, (ast.Store, ast.Del)):
            return False
        if isinstance(node, ast.arg) and node.arg == "collections":
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == "collections":
            return False
        if isinstance(node, (ast.ExceptHandler,) + PATTERN_BINDINGS) and getattr(node, "name", None) == "collections":
            return False
        if MATCH_MAPPING is not None and isinstance(node, MATCH_MAPPING) and node.rest == "collections":
            return False
        if isinstance(node, ast.Import) and node is not import_node:
            if any((alias.asname or alias.name.split(".")[0]) == "collections"
                   and not (alias.name == "collections.abc" and alias.asname is None)
                   for alias in node.names):
                return False
        if isinstance(node, ast.ImportFrom):
            if any((alias.asname or alias.name) == "collections" for alias in node.names):
                return False
    return True


def _verify_site(state: Mapping[str, Evidence]) -> dict[str, Any]:
    source = state["source_text"].value
    line = state["line"].value
    before = state["before"].value
    after = state["after"].value
    if sha256(source.encode("utf-8")).hexdigest() != state["source_sha256"].value:
        raise SemanticGap("stale_source", "Site source hash no longer matches")
    lines = source.splitlines(keepends=True)
    if not isinstance(line, int) or line < 1 or line > len(lines) or lines[line - 1] != before:
        raise SemanticGap("stale_source", "Site source line no longer matches")
    if not state["binding_verified"].value:
        raise SemanticGap("ambiguous_binding", "Site binding was not verified")
    if before == after or state["operation"].value not in {
        "rewrite_import_abc", "rewrite_combined_abc", "bind_collections_abc", "rewrite_qualified_abc"
    }:
        raise SemanticGap("invalid_site", "Site edit is empty or unknown")
    return {"site_checked": True}


def _emit_site(state: Mapping[str, Evidence]) -> dict[str, Any]:
    return {"proposal": {
        "file": state["file"].value, "line": state["line"].value,
        "before": state["before"].value, "after": state["after"].value,
        "source_sha256": state["source_sha256"].value,
        "operation": state["operation"].value,
    }}


SITE_MOTIF = Motif(
    id="python310-abc-site-v1",
    nodes=(
        Node("verify_source_and_binding", (),
             ("source_text", "source_sha256", "line", "before", "after", "operation", "binding_verified"),
             ("site_checked",), _verify_site),
        Node("emit_change", ("verify_source_and_binding",),
             ("file", "line", "before", "after", "source_sha256", "operation", "site_checked"),
             ("proposal",), _emit_site),
    ),
)


def _site(name: str, record: dict[str, str], line: int, before: str, after: str,
          operation: str, binding_verified: bool) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    inputs = {
        "file": Evidence(name, "ast_scan"),
        "source_text": Evidence(record["text"], "scan"),
        "source_sha256": Evidence(record["sha256"], "scan"),
        "line": Evidence(line, "ast_scan"),
        "before": Evidence(before, "ast_scan"),
        "after": Evidence(after, "ast_rewrite"),
        "operation": Evidence(operation, "recipe"),
        "binding_verified": Evidence(binding_verified, "ast_binding_check"),
    }
    run = execute(SITE_MOTIF, inputs)
    report = {"file": name, "line": line, "operation": operation,
              "status": run.status, "events": run.events,
              "gap": run.gap.kind if run.gap else None}
    return (run.state["proposal"].value if run.status == "completed" else None), report


def _scan(state: Mapping[str, Evidence]) -> dict[str, Any]:
    root = Path(state["root"].value).resolve(strict=True)
    if not root.is_dir():
        raise SemanticGap("invalid_root", "Migration target must be a directory")
    raw_includes = state.get("includes", Evidence([], "default_scope")).value
    if not isinstance(raw_includes, list) or any(not isinstance(item, str) or not item for item in raw_includes):
        raise SemanticGap("invalid_scope", "Includes must be relative file or directory paths")
    includes: list[Path] = []
    for item in raw_includes:
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts or "." in relative.parts:
            raise SemanticGap("invalid_scope", f"Unsafe include path: {item}")
        selected = root / relative
        if selected.is_symlink() or not selected.exists() or not selected.resolve().is_relative_to(root):
            raise SemanticGap("invalid_scope", f"Include path is absent or escapes target: {item}")
        includes.append(relative)
    files: dict[str, dict[str, str]] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if includes and not any(relative == item or item in relative.parents for item in includes):
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        if len(files) >= 200:
            raise SemanticGap("scope_limit", "More than 200 Python files; select a smaller directory")
        if path.stat().st_size > 1_000_000:
            raise SemanticGap("scope_limit", f"File exceeds 1 MB: {relative}")
        raw = path.read_bytes()
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise SemanticGap("encoding", f"Non-UTF-8 file requires review: {relative}")
        files[str(relative)] = {"text": content, "sha256": sha256(raw).hexdigest()}
    return {"files": files}


def _analyze(state: Mapping[str, Evidence]) -> dict[str, Any]:
    files = state["files"].value
    requested = state.get("aliases", Evidence([], "default_recipe")).value
    if not isinstance(requested, list) or any(not isinstance(alias, str) or alias not in vars(collections.abc)
                                                  or not alias.isidentifier() or not alias[0].isupper()
                                                  for alias in requested):
        raise SemanticGap("invalid_alias_scope", "Additional aliases must be named collections.abc classes")
    active_abcs = ABCS | set(requested)
    selected_sites = state.get("selected_sites", Evidence(None, "default_recipe")).value
    if selected_sites is not None and (not isinstance(selected_sites, list)
                                       or any(not isinstance(item, dict)
                                              or set(item) != {"file", "line", "alias"}
                                              or not isinstance(item["file"], str)
                                              or not isinstance(item["line"], int)
                                              or not isinstance(item["alias"], str)
                                              for item in selected_sites)):
        raise SemanticGap("invalid_site_scope", "Selected sites must have file, line and alias")
    selected_keys = None if selected_sites is None else {
        (item["file"], item["line"], item["alias"]) for item in selected_sites
    }
    import_line = re.compile(
        r"^(?P<prefix>[ \t]*from[ \t]+)collections(?P<suffix>[ \t]+import[ \t]+(?:"
        + "|".join(re.escape(alias) for alias in sorted(active_abcs))
        + r")(?:[ \t]+as[ \t]+[A-Za-z_]\w*)?[ \t]*(?:#.*)?)$"
    )
    proposals: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    site_runs: list[dict[str, Any]] = []

    def add_site(name: str, record: dict[str, str], line: int, before: str, after: str,
                 operation: str, binding_verified: bool) -> None:
        proposal, report = _site(name, record, line, before, after, operation, binding_verified)
        site_runs.append(report)
        if proposal is None:
            gaps.append({"file": name, "line": line, "reason": report["gap"] or "site verification stopped"})
        else:
            proposals.append(proposal)

    for name, record in files.items():
        source = record["text"]
        try:
            tree = ast.parse(source, filename=name)
        except SyntaxError as exc:
            gaps.append({"file": name, "line": exc.lineno, "reason": "source does not parse"})
            continue
        lines = source.splitlines(keepends=True)
        qualified: list[ast.Attribute] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "collections" and any(
                alias.name in active_abcs and (alias.name in ABCS or selected_keys is None
                                                or (name, node.lineno, alias.name) in selected_keys)
                for alias in node.names
            ):
                if node.end_lineno != node.lineno:
                    gaps.append({"file": name, "line": node.lineno, "reason": "multiline import"})
                    continue
                original = lines[node.lineno - 1]
                body = original.rstrip("\r\n")
                if len(node.names) > 1:
                    if not all(alias.name in ABCS and alias.name in vars(collections.abc) for alias in node.names):
                        gaps.append({"file": name, "line": node.lineno, "reason": "mixed ABC/non-ABC import"})
                        continue
                    names_pattern = r"[ \t]*,[ \t]*".join(
                        re.escape(alias.name) + (r"[ \t]+as[ \t]+" + re.escape(alias.asname) if alias.asname else "")
                        for alias in node.names
                    )
                    combined_line = re.compile(
                        r"^(?P<prefix>[ \t]*from[ \t]+)collections"
                        r"(?P<suffix>[ \t]+import[ \t]+" + names_pattern + r"[ \t]*(?:#.*)?)$"
                    )
                    combined = combined_line.fullmatch(body)
                    if not combined:
                        gaps.append({"file": name, "line": node.lineno, "reason": "combined import syntax needs review"})
                        continue
                    replacement = f"{combined['prefix']}collections.abc{combined['suffix']}" + original[len(body):]
                    add_site(name, record, node.lineno, original, replacement,
                             "rewrite_combined_abc", True)
                    continue
                match = import_line.fullmatch(body)
                if not match:
                    gaps.append({"file": name, "line": node.lineno, "reason": "import syntax needs review"})
                    continue
                replacement = f"{match['prefix']}collections.abc{match['suffix']}" + original[len(body):]
                add_site(name, record, node.lineno, original, replacement,
                         "rewrite_import_abc", match is not None)
            elif (isinstance(node, ast.Attribute) and node.attr in active_abcs
                  and (node.attr in ABCS or selected_keys is None
                       or (name, node.lineno, node.attr) in selected_keys)
                  and isinstance(node.value, ast.Name) and node.value.id == "collections"):
                qualified.append(node)
        if not qualified:
            continue
        imports = [
            node for node in tree.body
            if isinstance(node, ast.Import) and len(node.names) == 1
            and node.names[0].name == "collections" and node.names[0].asname is None
            and node.lineno == node.end_lineno
            and MODULE_LINE.fullmatch(lines[node.lineno - 1].rstrip("\r\n"))
        ]
        abc_import_present = any(
            isinstance(node, ast.Import) and len(node.names) == 1
            and node.names[0].name == "collections.abc" and node.names[0].asname is None
            and node.lineno == node.end_lineno
            and ABC_MODULE_LINE.fullmatch(lines[node.lineno - 1].rstrip("\r\n"))
            for node in tree.body
        )
        binding_safe = len(imports) == 1 and _binding_is_safe(tree, imports[0])
        if not binding_safe or any(node.lineno <= imports[0].lineno for node in qualified):
            gaps.extend({"file": name, "line": node.lineno, "reason": "qualified collections binding needs review"} for node in qualified)
            continue
        import_node = imports[0]
        original_import = lines[import_node.lineno - 1]
        newline = "\r\n" if original_import.endswith("\r\n") else "\n"
        import_prefix = original_import if original_import.endswith(("\r", "\n")) else original_import + newline
        if not abc_import_present:
            add_site(name, record, import_node.lineno, original_import,
                     import_prefix + "import collections.abc" + newline,
                     "bind_collections_abc", binding_safe)
        for node in qualified:
            original = lines[node.lineno - 1]
            old = f"collections.{node.attr}".encode("utf-8")
            encoded = original.encode("utf-8")
            if node.end_lineno != node.lineno or encoded[node.col_offset:node.end_col_offset] != old:
                gaps.append({"file": name, "line": node.lineno, "reason": "qualified expression syntax needs review"})
                continue
            replacement = encoded[:node.col_offset] + f"collections.abc.{node.attr}".encode("utf-8") + encoded[node.end_col_offset:]
            add_site(name, record, node.lineno, original, replacement.decode("utf-8"),
                     "rewrite_qualified_abc", binding_safe)
        file_proposals = [item for item in proposals if item["file"] == name]
        conflicting_lines = {line for line in {item["line"] for item in file_proposals}
                             if sum(item["line"] == line for item in file_proposals) > 1}
        for line in sorted(conflicting_lines):
            gaps.append({"file": name, "line": line, "reason": "multiple edits on one line need review"})
        if conflicting_lines:
            proposals = [item for item in proposals if item["file"] != name or item["line"] not in conflicting_lines]
    return {"proposals": proposals, "gaps": gaps, "site_runs": site_runs}


def _preview(state: Mapping[str, Evidence]) -> dict[str, Any]:
    root = Path(state["root"].value).resolve(strict=True)
    files = state["files"].value
    proposals = state["proposals"].value
    by_file: dict[str, list[dict[str, Any]]] = {}
    for proposal in proposals:
        by_file.setdefault(proposal["file"], []).append(proposal)
    patches: list[str] = []
    updated: dict[str, str] = {}
    for name, items in by_file.items():
        live = root / name
        if live.is_symlink() or not live.is_file() or sha256(live.read_bytes()).hexdigest() != files[name]["sha256"]:
            raise SemanticGap("stale_source", f"Source changed during preview: {name}")
        original = files[name]["text"]
        lines = original.splitlines(keepends=True)
        for item in items:
            if lines[item["line"] - 1] != item["before"]:
                raise SemanticGap("stale_source", f"Source changed during preview: {name}")
            lines[item["line"] - 1] = item["after"]
        changed = "".join(lines)
        try:
            compile(changed, name, "exec")
        except SyntaxError:
            raise SemanticGap("invalid_patch", f"Generated code does not parse: {name}")
        updated[name] = changed
        patches.extend(difflib.unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True), fromfile=f"a/{name}", tofile=f"b/{name}"))
    return {"diff": "".join(patches), "updated": updated}


def _gate(state: Mapping[str, Evidence]) -> dict[str, Any]:
    gaps = state["gaps"].value
    if gaps:
        raise SemanticGap(
            "ambiguous_migration",
            f"{len(gaps)} source locations need semantic review before applying a complete migration",
            allowed_answers=("review_each", "restrict_scope", "stop"),
            evidence_keys=("gaps", "proposals", "diff"),
        )
    return {"ready": True}


MIGRATION_MOTIF = Motif(
    id="python310-collections-abc-v4",
    nodes=(
        Node("scan", (), ("root",), ("files",), _scan),
        Node("analyze", ("scan",), ("files",), ("proposals", "gaps", "site_runs"), _analyze),
        Node("preview", ("analyze",), ("root", "files", "proposals"), ("diff", "updated"), _preview),
        Node("review_gate", ("preview",), ("gaps", "diff"), ("ready",), _gate),
    ),
)


def _stage_copy(state: Mapping[str, Evidence]) -> dict[str, Any]:
    root = Path(state["root"].value).resolve(strict=True)
    sandbox_root = Path(state["sandbox_root"].value).resolve()
    sandbox_root.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    total_files = 0
    for folder, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS and not name.startswith(".") and not (Path(folder) / name).is_symlink()]
        for name in names:
            path = Path(folder) / name
            if name.startswith(".") or path.is_symlink() or not path.is_file():
                continue
            total_files += 1
            total_bytes += path.stat().st_size
            if total_files > 5000 or total_bytes > 50_000_000:
                raise SemanticGap("scope_limit", "Repository copy exceeds 5,000 files or 50 MB; narrow the target")
    for name, record in state["files"].value.items():
        live = root / name
        if live.is_symlink() or not live.is_file() or sha256(live.read_bytes()).hexdigest() != record["sha256"]:
            raise SemanticGap("stale_source", f"Source changed before isolated test: {name}")
    def ignore(folder: str, names: list[str]) -> set[str]:
        return {
            name for name in names
            if name in SKIP_DIRS or name.startswith(".") or (Path(folder) / name).is_symlink()
        }
    run_dir = Path(tempfile.mkdtemp(prefix="migration-", dir=sandbox_root))
    checkout = run_dir / "repo"
    shutil.copytree(root, checkout, ignore=ignore)
    for name, content in state["updated"].value.items():
        target = checkout / name
        if not target.is_file() or target.is_symlink():
            raise SemanticGap("staging_mismatch", f"Changed file is absent in isolated copy: {name}")
        target.write_text(content, encoding="utf-8")
    return {"staged_path": str(checkout)}


def _run_tests(state: Mapping[str, Evidence]) -> dict[str, Any]:
    command = state["test_argv"].value
    if not isinstance(command, list) or not command or any(not isinstance(item, str) or not item for item in command):
        raise SemanticGap("invalid_test_command", "Provide a nonempty argument list; shell syntax is not supported")
    try:
        result = subprocess.run(command, cwd=state["staged_path"].value, text=True, capture_output=True, timeout=120, check=False)
        payload = {"exit_code": result.returncode, "stdout": result.stdout[-20_000:], "stderr": result.stderr[-20_000:]}
    except subprocess.TimeoutExpired as exc:
        payload = {"exit_code": None, "stdout": str(exc.stdout or "")[-20_000:], "stderr": str(exc.stderr or "")[-20_000:], "timed_out": True}
    return {"test_result": payload}


def _test_gate(state: Mapping[str, Evidence]) -> dict[str, Any]:
    result = state["test_result"].value
    if result["exit_code"] != 0:
        raise SemanticGap("tests_failed", "Isolated target-version tests failed; inspect test_result before applying", evidence_keys=("staged_path", "test_result"))
    return {"verified": True}


VERIFY_MOTIF = Motif(
    id="migration-isolated-verification-v1",
    nodes=(
        Node("stage", (), ("root", "files", "updated", "ready", "sandbox_root"), ("staged_path",), _stage_copy),
        Node("test", ("stage",), ("staged_path", "test_argv"), ("test_result",), _run_tests),
        Node("test_gate", ("test",), ("test_result",), ("verified",), _test_gate),
    ),
)


def discover_extra_abc_candidates(root: Path, *, limit: int = 20) -> list[dict[str, Any]]:
    """List statically safe ABC aliases outside the current automatic recipe."""
    files = _scan({"root": Evidence(str(root), "failed_staged_checkout")})["files"]
    candidates: list[dict[str, Any]] = []
    available = {name for name in vars(collections.abc)
                 if name.isidentifier() and name[0].isupper() and name not in ABCS}
    for name, record in files.items():
        source = record["text"]
        try:
            tree = ast.parse(source, filename=name)
        except SyntaxError:
            continue
        lines = source.splitlines(keepends=True)
        imports = [
            node for node in tree.body
            if isinstance(node, ast.Import) and len(node.names) == 1
            and node.names[0].name == "collections" and node.names[0].asname is None
            and node.lineno == node.end_lineno
            and MODULE_LINE.fullmatch(lines[node.lineno - 1].rstrip("\r\n"))
        ]
        binding_safe = len(imports) == 1 and _binding_is_safe(tree, imports[0])
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "collections" and len(node.names) == 1:
                alias = node.names[0].name
                line = lines[node.lineno - 1].rstrip("\r\n")
                syntax = re.compile(r"^[ \t]*from[ \t]+collections[ \t]+import[ \t]+"
                                    + re.escape(alias)
                                    + r"(?:[ \t]+as[ \t]+[A-Za-z_]\w*)?[ \t]*(?:#.*)?$")
                if alias in available and node.end_lineno == node.lineno and syntax.fullmatch(line):
                    candidates.append({"file": name, "line": node.lineno, "alias": alias, "form": "direct_import"})
            elif (isinstance(node, ast.Attribute) and node.attr in available
                  and isinstance(node.value, ast.Name) and node.value.id == "collections"
                  and binding_safe and node.lineno > imports[0].lineno):
                candidates.append({"file": name, "line": node.lineno, "alias": node.attr, "form": "qualified"})
            if len(candidates) > limit:
                raise SemanticGap("candidate_limit", f"More than {limit} additional ABC sites; narrow the target")
    candidates.sort(key=lambda item: (item["file"], item["line"], item["alias"]))
    for index, item in enumerate(candidates, 1):
        item["id"] = f"C{index}"
    return candidates
