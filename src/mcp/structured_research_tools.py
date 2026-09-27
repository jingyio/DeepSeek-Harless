"""Generic version-bound, read-only research data operations for MCP.

The handles are opaque and persisted locally so a resumed Harness session can
reuse them. Every consumer re-hashes its source before reading; a changed file
invalidates its old source, dataset, and aggregate handles.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import math
import os
import sqlite3
from collections import defaultdict
from functools import wraps
from itertools import zip_longest
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from mcp.server.mcpserver.exceptions import ToolError

from src.semantic_inputs import SemanticInputRequired


ROOT = Path(__file__).resolve().parents[2]
ALLOWED_ROOTS = (
    ROOT / ".local" / "benchmarks",
    ROOT / ".local" / "python-workspace",
    ROOT / "reference",
    ROOT / "experiments",
)
STORE_PATH = ROOT / ".local" / "structured-research" / "handles.sqlite3"
MAX_SOURCE_BYTES = 48 * 1024 * 1024
MAX_RECORDS = 100_000
MAX_FIELDS = 100
MAX_GROUPS = 200
SOURCE_EXTENSIONS = {".json", ".csv", ".tsv", ".svg", ".txt", ".md", ".py", ".pdf"}
MAX_LISTED_SOURCES = 100


class MeasureSpec(TypedDict):
    name: str
    op: Literal["count", "distinct_count", "sum", "mean", "min", "max",
                "sum_difference", "mean_difference", "pearson_correlation",
                "spearman_correlation"]
    field: NotRequired[str]
    left: NotRequired[str]
    right: NotRequired[str]


class FilterSpec(TypedDict):
    field: str
    op: Literal["eq", "ne", "gt", "gte", "lt", "lte", "in"]
    value: Any


def mcp_safe(function):
    """Expose expected validation failures to the model as MCP tool errors."""
    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except SemanticInputRequired as exc:
            payload = {"error": "semantic_input_required",
                       "parameter": exc.parameter,
                       "candidates": {name: exc.details.get(name, {})
                                      for name in exc.candidates}}
            message = json.dumps(payload, ensure_ascii=False)
            if len(message) > 4000:
                message = json.dumps({
                    "error": "semantic_input_required",
                    "parameter": exc.parameter,
                    "candidate_names_preview": [name[:120]
                                                for name in exc.candidates[:8]],
                    "candidate_count": len(exc.candidates),
                    "instruction": "Provide records_path explicitly",
                }, ensure_ascii=False)
            raise ToolError(message) from exc
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
    return checked


class HandleStore:
    def __init__(self, path: Path = STORE_PATH):
        self.path = path

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        self.path.chmod(0o600)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("CREATE TABLE IF NOT EXISTS handles "
                           "(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL)")
        return connection

    def put(self, kind: str, payload: dict[str, Any]) -> str:
        if not isinstance(kind, str) or not kind or not isinstance(payload, dict):
            raise ValueError("A handle needs a kind and JSON object payload")
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS metadata "
                               "(key TEXT PRIMARY KEY, value BLOB NOT NULL)")
            connection.execute("INSERT OR IGNORE INTO metadata VALUES (?, ?)",
                               ("handle_key_v1", os.urandom(32)))
            secret = connection.execute(
                "SELECT value FROM metadata WHERE key=?", ("handle_key_v1",)).fetchone()[0]
            handle = f"{kind}-" + hmac.new(
                secret, f"{kind}\0{canonical}".encode("utf-8"),
                hashlib.sha256).hexdigest()[:32]
            connection.execute("INSERT OR IGNORE INTO handles VALUES (?, ?, ?)",
                               (handle, kind, canonical))
            saved = connection.execute(
                "SELECT kind, payload FROM handles WHERE id=?", (handle,)).fetchone()
            if saved is None or saved[0] != kind or json.loads(saved[1]) != payload:
                raise ValueError("Handle digest collision or store corruption")
        return handle

    def get(self, handle: str, kind: str) -> dict[str, Any]:
        if not isinstance(handle, str) or not handle.startswith(f"{kind}-"):
            raise ValueError(f"Expected a {kind} handle returned by a prior tool call")
        with self._connect() as connection:
            row = connection.execute("SELECT payload FROM handles WHERE id=? AND kind=?",
                                     (handle, kind)).fetchone()
        if row is None:
            raise ValueError(f"Unknown {kind} handle")
        return json.loads(row[0])


_STORE = HandleStore()


def _source_path(path: str) -> Path:
    if not isinstance(path, str) or not path:
        raise ValueError("A source file path is required")
    target = Path(path).expanduser()
    if target.is_absolute():
        target = target.resolve(strict=True)
    else:
        input_dir = os.environ.get("SSS_RESEARCH_INPUT_DIR")
        # A DSH task may call the tool with a path relative to its isolated
        # workspace, while the stdio MCP process itself runs from the project
        # root. The final approved-root check still applies to either base.
        base = Path(input_dir).expanduser() if input_dir else ROOT
        target = (base / target).resolve(strict=True)
    if not target.is_file() or not any(target.is_relative_to(root.resolve()) for root in ALLOWED_ROOTS):
        raise ValueError("Source must be a file in an approved research input directory")
    if target.suffix.lower() not in SOURCE_EXTENSIONS:
        raise ValueError("Unsupported research source format")
    if target.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds 48 MB; make a bounded research extract first")
    return target


def list_research_sources(directory: str = "sources") -> dict[str, Any]:
    """List bounded supported files in one approved research input directory.

    Returns names and sizes, not file contents. Use pin_source on an exact
    returned path to obtain a version hash before reading or calculating.
    """
    if not isinstance(directory, str) or not directory:
        raise ValueError("A research source directory is required")
    base = Path(os.environ.get("SSS_RESEARCH_INPUT_DIR", str(ROOT))).expanduser().resolve()
    requested = Path(directory).expanduser()
    target = (requested if requested.is_absolute() else base / requested).resolve(strict=True)
    if not target.is_dir() or not any(target.is_relative_to(root.resolve()) for root in ALLOWED_ROOTS):
        raise ValueError("Directory must be inside an approved research input directory")
    files = sorted(p for p in target.iterdir() if p.is_file() and
                   any(p.resolve().is_relative_to(root.resolve()) for root in ALLOWED_ROOTS) and
                   p.suffix.lower() in SOURCE_EXTENSIONS and
                   p.stat().st_size <= MAX_SOURCE_BYTES)
    if len(files) > MAX_LISTED_SOURCES:
        raise ValueError("Directory has more than 100 supported source files; narrow it first")
    return {"directory": str(target), "files": [
        {"path": str(p.relative_to(base)) if p.is_relative_to(base) else str(p),
         "bytes": p.stat().st_size, "format": p.suffix.lower().lstrip(".")}
        for p in files], "file_count": len(files)}


def _read_source(path: Path) -> bytes:
    data = path.read_bytes()
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds 48 MB; make a bounded research extract first")
    return data


def _fresh_source(source_id: str) -> tuple[Path, dict[str, Any], bytes]:
    item = _STORE.get(source_id, "source")
    path = _source_path(item["path"])
    data = _read_source(path)
    if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise ValueError("Source changed; pin the new version before continuing")
    return path, item, data


def pin_source(path: str) -> dict[str, Any]:
    """Pin an approved local research file to its current bytes and return a source_id."""
    target = _source_path(path)
    data = _read_source(target)
    item = {"path": str(target), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    source_id = _STORE.put("source", item)
    return {"source_id": source_id, "sha256": item["sha256"],
            "bytes": item["bytes"], "format": target.suffix.lower().lstrip(".")}


def _records(source_id: str, records_path: str = "") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path, source, data = _fresh_source(source_id)
    suffix = path.suffix.lower()
    if suffix == ".json":
        value = json.loads(data.decode("utf-8"))
        if records_path:
            for part in records_path.split("."):
                if not isinstance(value, dict) or part not in value:
                    raise ValueError("records_path does not name a JSON object field")
                value = value[part]
        elif isinstance(value, dict):
            candidates = [key for key, child in value.items()
                          if isinstance(key, str) and isinstance(child, list)
                          and all(isinstance(row, dict) for row in child)]
            if candidates:
                if len(candidates) > 50:
                    raise ValueError("Too many record arrays; provide records_path explicitly")
                details = {}
                for key in candidates:
                    child = value[key]
                    fields = sorted({field for row in child[:20] for field in row
                                     if isinstance(field, str) and len(field) <= 120})[:30]
                    details[key] = {"record_count": len(child), "fields": fields}
                raise SemanticInputRequired("records_path", candidates, details)
        if not isinstance(value, list):
            raise ValueError("Selected JSON value must be an array of records")
        rows = value
    elif suffix in {".csv", ".tsv"}:
        if records_path:
            raise ValueError("records_path applies only to JSON")
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig")),
                                   delimiter="\t" if suffix == ".tsv" else ","))
    else:
        raise ValueError("Record inspection supports JSON, CSV and TSV only")
    if len(rows) > MAX_RECORDS or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Expected at most 100,000 object records")
    fields = _field_paths(rows)
    if len(fields) > MAX_FIELDS or any(not isinstance(field, str) for field in fields):
        raise ValueError("Too many or invalid record fields")
    return rows, source


def _field_paths(rows: list[dict[str, Any]]) -> set[str]:
    paths: set[str] = set()

    def visit(value: dict[str, Any], prefix: str = "", depth: int = 0) -> None:
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("Record fields must have string names")
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            if isinstance(child, dict) and depth < 3:
                visit(child, path, depth + 1)

    for row in rows:
        visit(row)
        if len(paths) > MAX_FIELDS:
            break
    return paths


def _field(row: dict[str, Any], path: str) -> Any:
    if path in row:
        return row[path]
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


def _has_field(row: dict[str, Any], path: str) -> bool:
    try:
        _field(row, path)
        return True
    except KeyError:
        return False


def inspect_records(source_id: str, records_path: str = "") -> dict[str, Any]:
    """Inspect a pinned JSON array or CSV/TSV table and return a dataset_id."""
    rows, source = _records(source_id, records_path)
    fields = sorted(_field_paths(rows))
    dataset_id = _STORE.put("dataset", {"source_id": source_id, "records_path": records_path})
    return {"dataset_id": dataset_id, "source_sha256": source["sha256"],
            "record_count": len(rows), "fields": fields,
            "note": "This describes record structure; it does not judge scientific meaning."}


def _number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError("Numeric measure contains a null or Boolean value")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Numeric measure contains a non-numeric value") from exc
    if not math.isfinite(number):
        raise ValueError("Numeric measure contains a non-finite value")
    return number


def _passes(row: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    for predicate in filters:
        field, op, target = predicate["field"], predicate["op"], predicate["value"]
        value = _field(row, field)
        if op in {"gt", "gte", "lt", "lte"}:
            left, right = _number(value), _number(target)
            passed = {"gt": left > right, "gte": left >= right,
                      "lt": left < right, "lte": left <= right}[op]
        elif op == "in":
            passed = str(value) in {str(item) for item in target}
        else:
            passed = (str(value) == str(target)) if op == "eq" else (str(value) != str(target))
        if not passed:
            return False
    return True


def _validate_spec(fields: set[str], group_by: list[str], measures: list[dict[str, Any]],
                   filters: list[dict[str, Any]]) -> None:
    if not isinstance(group_by, list) or len(group_by) > 3 or any(field not in fields for field in group_by):
        raise ValueError("group_by must list up to three existing fields")
    if not isinstance(measures, list) or not 1 <= len(measures) <= 8:
        raise ValueError("measures must contain 1–8 calculations")
    names = set()
    for measure in measures:
        if not isinstance(measure, dict) or not isinstance(measure.get("name"), str):
            raise ValueError("Each measure needs a name")
        name, op = measure["name"], measure.get("op")
        if not name or name in names:
            raise ValueError("Measure names must be unique and nonempty")
        names.add(name)
        if op not in {"count", "distinct_count", "sum", "mean", "min", "max",
                      "sum_difference", "mean_difference", "pearson_correlation",
                      "spearman_correlation"}:
            raise ValueError("Unsupported measure operation")
        needed = ("left", "right") if op in {"sum_difference", "mean_difference",
                                            "pearson_correlation", "spearman_correlation"} else (
            ("field",) if op != "count" else ())
        if any(measure.get(key) not in fields for key in needed):
            raise ValueError("Measure references an unknown field")
    if not isinstance(filters, list) or len(filters) > 8:
        raise ValueError("filters must contain at most eight predicates")
    for predicate in filters:
        if not isinstance(predicate, dict) or predicate.get("field") not in fields:
            raise ValueError("Filter references an unknown field")
        if predicate.get("op") not in {"eq", "ne", "gt", "gte", "lt", "lte", "in"}:
            raise ValueError("Unsupported filter operation")
        if "value" not in predicate or (predicate["op"] == "in" and
                                        (not isinstance(predicate["value"], list)
                                         or len(predicate["value"]) > 100)):
            raise ValueError("Invalid filter value")


def _average_ranks(values: list[float]) -> list[float]:
    ranks = [0.0] * len(values)
    order = sorted(range(len(values)), key=values.__getitem__)
    start = 0
    while start < len(order):
        stop = start + 1
        while stop < len(order) and values[order[stop]] == values[order[start]]:
            stop += 1
        rank = (start + 1 + stop) / 2
        for index in order[start:stop]:
            ranks[index] = rank
        start = stop
    return ranks


def _pearson(left: list[float], right: list[float]) -> float:
    if len(left) < 3:
        raise ValueError("Correlation needs at least three matched records")
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    ldev = [value - left_mean for value in left]
    rdev = [value - right_mean for value in right]
    denominator = math.sqrt(math.fsum(value * value for value in ldev)
                            * math.fsum(value * value for value in rdev))
    if denominator == 0:
        raise ValueError("Correlation is undefined for a constant series")
    return math.fsum(a * b for a, b in zip(ldev, rdev)) / denominator


def _calculate(rows: list[dict[str, Any]], measure: dict[str, Any]) -> int | float:
    op = measure["op"]
    if op == "count":
        return len(rows)
    if op == "distinct_count":
        return len({str(_field(row, measure["field"])) for row in rows})
    if op in {"pearson_correlation", "spearman_correlation"}:
        left = [_number(_field(row, measure["left"])) for row in rows]
        right = [_number(_field(row, measure["right"])) for row in rows]
        if op == "spearman_correlation":
            left, right = _average_ranks(left), _average_ranks(right)
        return _pearson(left, right)
    if op in {"sum_difference", "mean_difference"}:
        values = [_number(_field(row, measure["left"])) - _number(_field(row, measure["right"]))
                  for row in rows]
    else:
        values = [_number(_field(row, measure["field"])) for row in rows]
    if not values:
        raise ValueError("Numeric measure has no matching records")
    if op in {"sum", "sum_difference"}:
        return math.fsum(values)
    if op in {"mean", "mean_difference"}:
        return math.fsum(values) / len(values)
    return min(values) if op == "min" else max(values)


def aggregate_records(dataset_id: str, group_by: list[str], measures: list[MeasureSpec],
                      filters: list[FilterSpec] | None = None, order_by: str = "",
                      descending: bool = True, limit: int = 0) -> dict[str, Any]:
    """Compute bounded, explicit grouped statistics from a version-bound dataset_id.

    Every measure needs a unique ``name`` and ``op``. Example:
    ``[{"name":"runs","op":"count"},
    {"name":"mean_goodput","op":"mean","field":"slo_goodput_requests_per_s"}]``.
    For ``sum_difference`` or ``mean_difference``, pass ``left`` and ``right``
    field names. Correlation operations also take ``left`` and ``right`` and
    require at least three matched records with nonconstant values. Spearman
    uses average ranks for ties. ``group_by`` may be empty for a whole-dataset summary.
    Set ``order_by`` to a measure name and ``limit`` to return only the top
    groups; the result_id still stores all calculated groups.
    """
    dataset = _STORE.get(dataset_id, "dataset")
    rows, source = _records(dataset["source_id"], dataset["records_path"])
    filters = [] if filters is None else filters
    fields = _field_paths(rows)
    _validate_spec(fields, group_by, measures, filters)
    if not isinstance(limit, int) or not 0 <= limit <= MAX_GROUPS:
        raise ValueError("limit must be 0 (all) or 1–200 groups")
    if order_by and order_by not in {measure["name"] for measure in measures}:
        raise ValueError("order_by must name one of the measures")
    required_fields = set(group_by)
    for measure in measures:
        required_fields.update(measure.get(key) for key in ("field", "left", "right")
                               if measure.get(key) is not None)
    required_fields.update(predicate["field"] for predicate in filters)
    if any(any(not _has_field(row, field) for field in required_fields) for row in rows):
        raise ValueError("Some records lack fields required by this calculation")
    selected = [row for row in rows if _passes(row, filters)]
    groups = defaultdict(list)
    for row in selected:
        groups[tuple(str(_field(row, field)) for field in group_by)].append(row)
    if not group_by:
        groups[()] = selected
    if len(groups) > MAX_GROUPS:
        raise ValueError("More than 200 groups; narrow the query before aggregating")
    output = []
    for key in sorted(groups):
        subset = groups[key]
        output.append({"group": dict(zip(group_by, key)),
                       "values": {item["name"]: _calculate(subset, item) for item in measures}})
    saved = {"dataset_id": dataset_id, "group_by": group_by,
             "measures": measures, "filters": filters, "groups": output}
    result_id = _STORE.put("result", saved)
    returned = output
    if order_by:
        returned = sorted(output, key=lambda item: (
            -item["values"][order_by] if descending else item["values"][order_by],
            tuple(item["group"].values())))
    if limit:
        returned = returned[:limit]
    return {"result_id": result_id, "source_sha256": source["sha256"],
            "matched_records": len(selected), "group_count": len(output),
            "returned_groups": len(returned), "groups": returned}


def rank_grouped_result(result_id: str, category_field: str, measure_name: str,
                        within: list[str], descending: bool = True) -> dict[str, Any]:
    """Rank categories within each stratum of a saved grouped result.

    Use a result_id from aggregate_records. The category plus ``within`` must
    equal that result's group_by fields, so rankings never silently pool
    different strata. The response includes first/last-place counts.
    """
    saved = _STORE.get(result_id, "result")
    dataset = _STORE.get(saved["dataset_id"], "dataset")
    _, source, _ = _fresh_source(dataset["source_id"])
    group_by = saved["group_by"]
    if (not isinstance(category_field, str) or not isinstance(within, list)
            or not all(isinstance(field, str) for field in within)
            or category_field in within or len(set(within)) != len(within)
            or set(within + [category_field]) != set(group_by)):
        raise ValueError("category_field and within must exactly partition group_by")
    if measure_name not in {item["name"] for item in saved["measures"]}:
        raise ValueError("measure_name must name a saved measure")
    strata: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in saved["groups"]:
        key = tuple(row["group"][field] for field in within)
        strata[key].append(row)
    output = []
    first_counts: dict[str, int] = defaultdict(int)
    last_counts: dict[str, int] = defaultdict(int)
    appearances: dict[str, int] = defaultdict(int)
    for key, rows in sorted(strata.items()):
        ordered = sorted(rows, key=lambda row: (
            -_number(row["values"][measure_name]) if descending
            else _number(row["values"][measure_name]), row["group"][category_field]))
        values = [_number(row["values"][measure_name]) for row in ordered]
        ranked = []
        for index, row in enumerate(ordered):
            category = row["group"][category_field]
            value = values[index]
            ranked.append({"category": category, "value": value,
                           "rank": 1 + sum(other > value if descending else other < value
                                           for other in values)})
            appearances[category] += 1
            if value == values[0]:
                first_counts[category] += 1
            if value == values[-1]:
                last_counts[category] += 1
        output.append({"within": dict(zip(within, key)), "ranked": ranked})
    return {"result_id": result_id, "source_sha256": source["sha256"],
            "strata_count": len(output), "category_appearances": dict(appearances),
            "first_place_counts": dict(first_counts), "last_place_counts": dict(last_counts),
            "strata": output}


def compare_sources(left_source_id: str, right_source_id: str) -> dict[str, Any]:
    """Compare two pinned file versions by bytes and report the first difference."""
    _, left, left_bytes = _fresh_source(left_source_id)
    _, right, right_bytes = _fresh_source(right_source_id)
    same = left["sha256"] == right["sha256"]
    answer = {"byte_identical": same, "left_sha256": left["sha256"],
              "right_sha256": right["sha256"]}
    if not same:
        first = next((index for index, pair in enumerate(zip_longest(
            left_bytes, right_bytes, fillvalue=None))
            if pair[0] != pair[1]), None)
        answer["first_different_byte"] = first
    return answer


def compare_results(left_result_id: str, right_result_id: str) -> dict[str, Any]:
    """Compare two saved aggregate outputs after rechecking both source versions."""
    left = _STORE.get(left_result_id, "result")
    right = _STORE.get(right_result_id, "result")
    for result in (left, right):
        dataset = _STORE.get(result["dataset_id"], "dataset")
        _fresh_source(dataset["source_id"])
    if (left["group_by"] != right["group_by"] or left["measures"] != right["measures"]
            or left["filters"] != right["filters"]):
        raise ValueError("Results need the same grouping, measures and filters")
    def indexed(result):
        return {json.dumps(row["group"], sort_keys=True): row for row in result["groups"]}
    old, new = indexed(left), indexed(right)
    changes = []
    for key in sorted(old.keys() & new.keys()):
        before, after = old[key]["values"], new[key]["values"]
        if before != after:
            changes.append({"group": old[key]["group"],
                            "delta": {name: after[name] - before[name] for name in before}})
    return {"added_groups": len(new.keys() - old.keys()),
            "removed_groups": len(old.keys() - new.keys()),
            "changed_groups": len(changes), "changes_preview": changes[:20],
            "preview_truncated": len(changes) > 20}
