"""Bounded, side-effect-free expression evaluator for Motif code nodes.

Expressions see only JSON input ``x``. They are interpreted, never passed to
Python eval/exec. The command-line worker is also used by the online adapter.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


MAX_CODE = 500
MAX_INPUT = 8_000
MAX_INTERMEDIATE = 8_000
MAX_NODES = 64
PURE_CALLS = frozenset({"strip", "lower", "upper", "replace",
                        "regex_capture", "str", "int", "len"})


def validate_expression(expression: str) -> None:
    if not isinstance(expression, str) or not 1 <= len(expression) <= MAX_CODE:
        raise ValueError("code expression length is invalid")
    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("invalid pure code expression") from exc
    nodes = list(ast.walk(parsed))
    if len(nodes) > MAX_NODES:
        raise ValueError("code expression has too many nodes")
    allowed = (ast.Expression, ast.Load, ast.Constant, ast.Name, ast.Subscript,
               ast.Call, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.IfExp,
               ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt,
               ast.GtE)
    for node in nodes:
        if not isinstance(node, allowed):
            raise ValueError("unsupported pure code expression")
        if isinstance(node, ast.Name) and node.id not in PURE_CALLS | {"x"}:
            raise ValueError("unsupported pure code name")
        if (isinstance(node, ast.Call)
                and (not isinstance(node.func, ast.Name)
                     or node.func.id not in PURE_CALLS
                     or node.keywords or len(node.args) > 3)):
            raise ValueError("unsupported pure code call")
        if isinstance(node, ast.Constant) and type(node.value) not in (
                str, int, float, bool, type(None)):
            raise ValueError("unsupported pure code constant")


def _bounded(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_INTERMEDIATE:
        raise ValueError("code value exceeds size limit")
    if isinstance(value, (list, dict)) and len(value) > 100:
        raise ValueError("code collection exceeds size limit")
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and abs(value) > 1_000_000_000):
        raise ValueError("code number exceeds size limit")
    return value


def _regex_capture(pattern: Any, value: Any, group: Any = 1) -> str:
    if (not isinstance(pattern, str) or len(pattern) > 120
            or not isinstance(value, str) or len(value) > 2_000
            or type(group) is not int or not 0 <= group <= 9):
        raise ValueError("regex_capture needs bounded text, pattern and group")
    found = re.search(pattern, value)
    if found is None:
        raise ValueError("regex_capture found no match")
    try:
        return found.group(group)
    except IndexError as exc:
        raise ValueError("regex_capture group is unavailable") from exc


def _call(name: str, args: list[Any]) -> Any:
    if name == "strip" and len(args) == 1 and isinstance(args[0], str):
        return args[0].strip()
    if name == "lower" and len(args) == 1 and isinstance(args[0], str):
        return args[0].lower()
    if name == "upper" and len(args) == 1 and isinstance(args[0], str):
        return args[0].upper()
    if (name == "replace" and len(args) == 3
            and all(isinstance(item, str) for item in args)):
        return args[0].replace(args[1], args[2])
    if name == "regex_capture" and 2 <= len(args) <= 3:
        return _regex_capture(*args)
    if name == "str" and len(args) == 1 and type(args[0]) in (str, int, float, bool):
        return str(args[0])
    if name == "int" and len(args) == 1 and type(args[0]) in (str, int, float):
        return int(args[0])
    if name == "len" and len(args) == 1 and type(args[0]) in (str, list, dict):
        return len(args[0])
    raise ValueError("code call is not in the pure allowlist")


def _interpret(node: ast.AST, x: Any, depth: int = 0) -> Any:
    if depth > 16:
        raise ValueError("code expression is too deep")
    child = lambda part: _interpret(part, x, depth + 1)
    if isinstance(node, ast.Constant) and type(node.value) in (str, int, float, bool, type(None)):
        return _bounded(node.value)
    if isinstance(node, ast.Name) and node.id == "x":
        return x
    if isinstance(node, ast.Subscript):
        value, key = child(node.value), child(node.slice)
        if type(value) is dict and type(key) is str and key in value:
            return _bounded(value[key])
        if type(value) is list and type(key) is int and 0 <= key < len(value):
            return _bounded(value[key])
        raise ValueError("code subscript is unavailable")
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and not node.keywords and len(node.args) <= 3):
        return _bounded(_call(node.func.id, [child(arg) for arg in node.args]))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = child(node.left), child(node.right)
        if type(left) is type(right) and type(left) in (str, int, float):
            return _bounded(left + right)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Sub, ast.Mult)):
        left, right = child(node.left), child(node.right)
        if type(left) in (int, float) and type(right) in (int, float):
            result = left - right if isinstance(node.op, ast.Sub) else left * right
            return _bounded(result)
    if isinstance(node, ast.IfExp):
        return child(node.body if child(node.test) else node.orelse)
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left, right = child(node.left), child(node.comparators[0])
        if type(left) is type(right) and type(left) in (str, int, float, bool):
            op = node.ops[0]
            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            if isinstance(op, ast.Lt):
                return left < right
            if isinstance(op, ast.LtE):
                return left <= right
            if isinstance(op, ast.Gt):
                return left > right
            if isinstance(op, ast.GtE):
                return left >= right
    raise ValueError("unsupported pure code expression")


def evaluate(expression: str, value: Any) -> str:
    validate_expression(expression)
    payload = json.dumps(value, ensure_ascii=False)
    if len(payload) > MAX_INPUT:
        raise ValueError("code input exceeds size limit")
    parsed = ast.parse(expression, mode="eval")
    result = _interpret(parsed.body, value)
    if (not isinstance(result, str) or not 1 <= len(result) <= 500
            or any(ord(char) < 32 for char in result)):
        raise ValueError("code node must return one bounded string")
    return result


def run_isolated(expression: str, value: Any) -> str:
    """Use the same bounded worker as the online JS runtime."""
    request = json.dumps({"expression": expression, "input": value},
                         ensure_ascii=False)
    if len(request) > MAX_INPUT + MAX_CODE + 200:
        raise ValueError("code request exceeds size limit")
    try:
        process = subprocess.run(
            [sys.executable, "-I", "-S", str(Path(__file__).resolve())],
            input=request, capture_output=True, text=True, timeout=1.5,
            env={"PYTHONIOENCODING": "utf-8"}, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("pure code timed out") from exc
    if process.returncode != 0 or len(process.stdout) > 2_000:
        raise ValueError("pure code failed its bounded worker")
    try:
        output = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("pure code returned invalid JSON") from exc
    if not isinstance(output, dict) or not isinstance(output.get("output"), str):
        raise ValueError("pure code returned no output")
    return output["output"]


def main() -> None:
    try:
        request = json.loads(sys.stdin.read(MAX_INPUT + MAX_CODE + 200))
        result = evaluate(request["expression"], request["input"])
        print(json.dumps({"output": result}, ensure_ascii=False))
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
