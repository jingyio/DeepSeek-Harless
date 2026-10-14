"""Mechanical execution of model-selected PDF windows, never semantic certification."""
import re
from mcp.server.mcpserver.exceptions import ToolError

PLAN_POLICY = 'exact-selected-coverage-v2'


def normalize_windows(pages, windows, *, maximum=8, total_chars=36000, window_chars=12000, allow_empty=False):
    """Union selected offsets only: no ranking, extra text, or silent truncation.

    Clip requests at the physical page end, merge overlap, and split a merged
    range only at the existing per-window bound. Preserve first-selection order.
    Validate the entire input before any caller issues source/citation handles.
    """
    if not isinstance(windows, list) or not 1 <= len(windows) <= maximum:
        raise ToolError(f'choose 1–{maximum} explicit windows')
    requested = []
    for index, window in enumerate(windows):
        if not isinstance(window, dict) or set(window) != {'page', 'start', 'length'}:
            raise ToolError('each window requires page/start/length')
        page, start, length = (window[k] for k in ('page', 'start', 'length'))
        if (not isinstance(page, str) or re.fullmatch(r'[1-9][0-9]{0,5}', page) is None
                or not 1 <= int(page) <= len(pages) or type(start) is not int
                or not (0 <= start < len(pages[int(page) - 1])
                        or allow_empty and start == 0 and not pages[int(page) - 1]) or type(length) is not int
                or not 1 <= length <= window_chars):
            raise ToolError('invalid physical page/start/length; low-text pages require inspection')
        requested.append((page, start, min(start + length, len(pages[int(page) - 1])), index))
    groups = {}
    for page, start, end, index in requested:
        groups.setdefault(page, []).append((start, end, index))
    chunks = []
    for page, ranges in groups.items():
        components = []
        for start, end, index in sorted(ranges):
            if components and (start < components[-1][1] or start == end == components[-1][0] == components[-1][1]):
                a, b, owner = components[-1]
                components[-1] = (a, max(b, end), min(owner, index))
            else:
                components.append((start, end, index))
        for start, end, owner in components:
            if start == end:
                # Keep the selected empty page visible to the existing low-text
                # inspection guard, rather than dropping it and certifying others.
                chunks.append((owner, page, start, 1))
            for offset in range(start, end, window_chars):
                chunks.append((owner, page, offset, min(offset + window_chars, end) - offset))
    keys = [(page, start, length) for _, page, start, length in sorted(chunks)]
    actual = sum(min(length, len(pages[int(page) - 1]) - start) for page, start, length in keys)
    if actual > total_chars:
        raise ToolError(f'plan exceeds {total_chars} actual characters: selected coverage is {actual}; '
                        'choose narrower windows; no selected text was read or silently dropped')
    mapping = [[i for i, (p, s, n) in enumerate(keys) if p == page and
                (s < end and s + n > start or start == end == s)]
               for page, start, end, _ in requested]
    report = {'policy': PLAN_POLICY, 'requested_windows': len(windows), 'executed_windows': len(keys),
              'requested_chars': sum(w['length'] for w in windows),
              'selected_chars_with_repeats': sum(end - start for _, start, end, _ in requested),
              'unique_chars': actual, 'budget_chars': total_chars,
              'requested_to_contexts': mapping, 'selected_coverage_preserved': True,
              'semantic_selection_performed': False}
    return keys, report


def validate_windows(scene, paper_id, version, windows, *, maximum=8, total_chars=36000, window_chars=12000):
    if version != scene.document_version(paper_id):
        raise ToolError('document version changed; prepare current PDF and choose a new plan')
    pages = scene._document(paper_id)['pages']
    return normalize_windows(pages, windows, maximum=maximum, total_chars=total_chars,
                             window_chars=window_chars)[0]


def section_navigation(pages):
    """Literal headings only. No heuristic relevance or support verdict."""
    result = []
    for page, text in enumerate(pages, 1):
        for match in re.finditer(r'(?m)^\s*(?:\d+(?:\.\d+)*[.\s]+[^\n]{3,100}|Abstract|References|Limitations|Conclusion[^\n]*)\s*$', text):
            result.append({'page': str(page), 'start': max(0, match.start() - 150),
                           'heading': match.group().strip()[:120]})
    return result[:100]
