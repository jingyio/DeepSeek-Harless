"""Lossless structural table extraction; never infer observations from prose."""
from __future__ import annotations
import csv
import io
import json
import math
import re
from contextlib import redirect_stdout


def _table(rows):
    if not isinstance(rows, list) or len(rows) < 2 or any(not isinstance(r, (list, tuple)) for r in rows):
        return None
    if len(rows[0]) < 2 or any(len(r) != len(rows[0]) for r in rows): return None
    if any(not isinstance(v, str) or not v.strip() for v in rows[0]) or len(set(rows[0])) != len(rows[0]): return None
    if any(isinstance(v, (dict, list, tuple, bool)) for row in rows for v in row): return None
    normalized = [[str(v) if v is not None else '' for v in row] for row in rows]
    # A table used for statistics needs at least one actual numeric data cell.
    def numeric(v):
        try: return bool(v.strip()) and math.isfinite(float(v))
        except ValueError: return False
    if not any(numeric(v) for row in normalized[1:] for v in row): return None
    output = io.StringIO(newline=''); csv.writer(output, lineterminator='\n').writerows(normalized)
    return output.getvalue()


def _json_table(value):
    if isinstance(value, dict):
        if isinstance(value.get('columns'), list) and isinstance(value.get('rows'), list):
            return _table([value['columns'], *value['rows']])
        value = value.get('data')
    if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
        keys = list(value[0])
        if keys and all(set(row) == set(keys) for row in value):
            return _table([keys, *[[row[k] for k in keys] for row in value]])
    return None


def extract_tables(path, document):
    """Return distinct explicit tables. Multiple tables require user selection.

    PDF detection uses cell boundaries, Word uses the extractor's table markers,
    and text uses delimiters. No whitespace-separated prose is promoted to data.
    """
    suffix = path.suffix.lower(); text = document.get('text', '')
    candidates = []
    if suffix == '.json':
        try:
            found = _json_table(json.loads(text))
            if found: candidates.append(found)
        except (ValueError, TypeError): pass
    elif suffix == '.pdf':
        try:
            import fitz
            with fitz.open(path) as pdf, redirect_stdout(io.StringIO()):
                for page in pdf:
                    for table in page.find_tables().tables:
                        found = _table(table.extract())
                        if found: candidates.append(found)
        except (ImportError, RuntimeError, ValueError, AttributeError):
            pass
    elif suffix in {'.docx', '.doc', '.txt', '.md', '.markdown'}:
        blocks = re.split(r'\n\s*\n|\[Table\]', text)
        for block in blocks:
            lines = block.strip().splitlines()
            for delimiter in ('\t', ',', '|'):
                if len(lines) < 2 or not all(delimiter in line for line in lines): continue
                source = '\n'.join(line.strip().strip('|').strip() for line in lines) if delimiter == '|' else block.strip()
                rows = list(csv.reader(io.StringIO(source), delimiter=delimiter))
                if delimiter == '|':
                    rows = [[v.strip() for v in row] for row in rows]
                    if len(rows) > 1 and all(re.fullmatch(r':?-{3,}:?', v) for v in rows[1]): rows.pop(1)
                found = _table(rows)
                if found:
                    candidates.append(found); break
    return candidates
