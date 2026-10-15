"""Bounded literal BibTeX parsing shared by preparation and read-only MCP tools.

Keeps raw entries and duplicate keys; does not expand macros or infer publications.
"""
from __future__ import annotations
import re


def title_query(raw):
    match = re.search(r'(?is)\btitle\s*=\s*([{\"])', raw)
    if not match: return None
    start = match.end(); opener = match.group(1); depth = 1; escaped = False; end = None
    for i in range(start, len(raw)):
        ch = raw[i]
        if escaped: escaped = False; continue
        if ch == '\\': escaped = True; continue
        if opener == '"' and ch == '"': end = i; break
        if opener == '{':
            depth += (ch == '{') - (ch == '}')
            if depth == 0: end = i; break
    if end is None: return None
    value = re.sub(r'\s+', ' ', raw[start:end].replace('{', '').replace('}', '')).strip()
    # TeX commands need interpretation; leave them to the model instead of guessing.
    return value if 1 <= len(value) <= 512 and '\\' not in value else None


def bib_records(text):
    """Literal brace-delimited BibTeX entries; reject unsupported/unbalanced syntax."""
    rows, consumed = [], 0
    for m in re.finditer(r'(?m)^\s*@([A-Za-z]+)\s*([{(])', text):
        if m.start() < consumed: continue  # No entries inside a title or @comment.
        if m.group(2) != '{': raise ValueError('unsupported parenthesized BibTeX block')
        kind = m.group(1)
        metadata = kind.lower() in {'comment', 'string', 'preamble'}
        key = None if metadata else re.match(r'\s*([^,\s{}]+)\s*,', text[m.end():])
        if not metadata and not key: raise ValueError('unsupported BibTeX key')
        depth, quoted, escaped, end = 1, False, False, None
        for i in range(m.end(), len(text)):
            ch = text[i]
            if escaped: escaped = False; continue
            if ch == '\\': escaped = True; continue
            if ch == '"' and depth == 1: quoted = not quoted
            if not quoted:
                depth += (ch == '{') - (ch == '}')
                if depth == 0: end = i + 1; break
        if end is None: raise ValueError('unbalanced BibTeX')
        consumed = end
        if not metadata:
            rows.append({'key': key.group(1), 'kind': kind, 'raw': text[m.start():end].strip()})
    return rows
