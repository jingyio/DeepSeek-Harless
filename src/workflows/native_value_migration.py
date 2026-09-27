"""Guarded Python 3.12 migration for a legacy native-value concatenation shape.

The recipe is executable only when AST bindings and the exact source region
match. It preserves a single non-text result before calling literal_eval.
"""

from __future__ import annotations

import ast
import difflib
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping

from src.graph.runtime import Evidence, Motif, Node, SemanticGap


def _read_target(state: Mapping[str, Evidence]) -> dict[str, Any]:
    root = Path(state["root"].value).resolve(strict=True)
    relative = Path(state["file"].value)
    if (not root.is_dir() or relative.is_absolute() or ".." in relative.parts
            or len(relative.parts) < 2 or relative.suffix != ".py"
            or relative.parts[0] == "tests"):
        raise SemanticGap("invalid_scope", "Select one package Python file outside tests")
    path = root / relative
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
        raise SemanticGap("invalid_scope", "Target file is missing or outside repository")
    raw = path.read_bytes()
    if len(raw) > 1_000_000:
        raise SemanticGap("scope_limit", "Target file exceeds 1 MB")
    try:
        source = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise SemanticGap("encoding", "Target file is not UTF-8") from None
    return {"files": {str(relative): {"text": source, "sha256": sha256(raw).hexdigest()}}}


def _recognize(state: Mapping[str, Evidence]) -> dict[str, Any]:
    name = state["file"].value
    source = state["files"].value[name]["text"]
    try:
        tree = ast.parse(source, filename=name)
    except SyntaxError:
        raise SemanticGap("unparseable_source", "Target source does not parse") from None
    imports_text_type = any(
        isinstance(node, ast.ImportFrom) and node.module == "jinja2._compat"
        and any(alias.name == "text_type" and alias.asname is None for alias in node.names)
        for node in tree.body
    )
    imports_literal_eval = any(
        isinstance(node, ast.ImportFrom) and node.module == "ast"
        and any(alias.name == "literal_eval" and alias.asname is None for alias in node.names)
        for node in tree.body
    )
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef) and node.name == "native_concat"]
    if not imports_text_type or not imports_literal_eval or len(functions) != 1:
        raise SemanticGap("unsupported_shape", "Required imports or native_concat function are absent")
    function = functions[0]
    def is_single_head(node: ast.stmt) -> bool:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
            return False
        test = node.test
        call = test.left
        return (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                and call.func.id == "len" and len(call.args) == 1 and not call.keywords
                and isinstance(call.args[0], ast.Name) and call.args[0].id == "head"
                and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)
                and len(test.comparators) == 1
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value == 1)

    single = [node for node in function.body if is_single_head(node)]
    if len(single) != 1 or len(single[0].body) != 1:
        raise SemanticGap("unsupported_shape", "Single-node branch has a different form")
    assign = single[0].body[0]
    if (not isinstance(assign, ast.Assign) or len(assign.targets) != 1
            or not isinstance(assign.targets[0], ast.Name) or assign.targets[0].id != "out"
            or not isinstance(assign.value, ast.Subscript)
            or not isinstance(assign.value.value, ast.Name) or assign.value.value.id != "head"
            or not isinstance(assign.value.slice, ast.Constant) or assign.value.slice.value != 0):
        raise SemanticGap("unsupported_shape", "Single-node branch does not bind out=head[0]")
    if (len(single[0].orelse) != 1 or not isinstance(single[0].orelse[0], ast.Assign)
            or len(single[0].orelse[0].targets) != 1
            or not isinstance(single[0].orelse[0].targets[0], ast.Name)
            or single[0].orelse[0].targets[0].id != "out"
            or not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                       and node.func.id == "text_type"
                       for node in ast.walk(single[0].orelse[0].value))):
        raise SemanticGap("unsupported_shape", "Other branch does not assemble text into out")
    tries = [node for node in function.body if isinstance(node, ast.Try)]
    if len(tries) != 1 or len(tries[0].body) != 1:
        raise SemanticGap("unsupported_shape", "literal_eval try block has a different form")
    returned = tries[0].body[0]
    if (not isinstance(returned, ast.Return) or not isinstance(returned.value, ast.Call)
            or not isinstance(returned.value.func, ast.Name)
            or returned.value.func.id != "literal_eval" or len(returned.value.args) != 1
            or not isinstance(returned.value.args[0], ast.Name)
            or returned.value.args[0].id != "out" or returned.value.keywords):
        raise SemanticGap("unsupported_shape", "Try block does not return literal_eval(out)")
    if any(isinstance(node, ast.Name) and node.id in {"text_type", "literal_eval", "len"}
           and isinstance(node.ctx, (ast.Store, ast.Del)) for node in ast.walk(tree)):
        raise SemanticGap("ambiguous_binding", "Required names are rebound inside native_concat")
    line = tries[0].lineno
    lines = source.splitlines(keepends=True)
    if "if len(head) == 1 and not isinstance(out, text_type):" in source:
        raise SemanticGap("already_migrated", "Native single-value guard is already present")
    if lines[line - 1] != "    try:\n":
        raise SemanticGap("unsupported_shape", "Try indentation or line endings need review")
    return {"insertion_line": line, "recognized_shape": True}


def _preview(state: Mapping[str, Evidence]) -> dict[str, Any]:
    root = Path(state["root"].value).resolve(strict=True)
    name = state["file"].value
    record = state["files"].value[name]
    path = root / name
    if path.is_symlink() or sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise SemanticGap("stale_source", "Target changed since recognition")
    source = record["text"]
    lines = source.splitlines(keepends=True)
    insertion = state["insertion_line"].value - 1
    guard = ["    if len(head) == 1 and not isinstance(out, text_type):\n",
             "        return out\n", "\n"]
    changed = "".join(lines[:insertion] + guard + lines[insertion:])
    try:
        compile(changed, name, "exec")
    except SyntaxError:
        raise SemanticGap("invalid_patch", "Generated guard does not parse") from None
    diff = "".join(difflib.unified_diff(source.splitlines(keepends=True), changed.splitlines(keepends=True),
                                        fromfile=f"a/{name}", tofile=f"b/{name}"))
    return {"updated": {name: changed}, "diff": diff}


NATIVE_VALUE_MOTIF = Motif(
    id="native-single-value-guard-v1",
    nodes=(
        Node("read", (), ("root", "file"), ("files",), _read_target),
        Node("recognize", ("read",), ("file", "files"), ("insertion_line", "recognized_shape"), _recognize),
        Node("preview", ("recognize",), ("root", "file", "files", "insertion_line", "recognized_shape"),
             ("updated", "diff"), _preview),
        Node("ready", ("preview",), ("updated", "diff"), ("ready",), lambda _: {"ready": True}),
    ),
)
