"""Static checks reused from feature/paper-submission@9479edf; no compiler or network.

Original: scenarios/paper-submission/checks.py. Checks are preserved; source-relative paths use POSIX separators on every platform.
"""
from pathlib import Path
from collections import Counter, defaultdict
import re


def safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts:
        raise ValueError('path escapes the paper case')
    target = path.resolve(strict=True)
    if not target.is_relative_to(root.resolve()) or any(
            part.is_symlink() for part in [path, *path.parents] if part != root.parent):
        raise ValueError('symlink or external paper path')
    return target


def strip_comments(text: str) -> str:
    # A percent preceded by an odd number of backslashes is escaped.
    result = []
    for line in text.splitlines():
        for index, char in enumerate(line):
            if char == '%':
                count, pos = 0, index - 1
                while pos >= 0 and line[pos] == '\\':
                    count += 1; pos -= 1
                if count % 2 == 0:
                    line = line[:index]; break
        result.append(line)
    return '\n'.join(result)


def source_diagnostics(source: Path, main: str, bbl: str | None) -> dict:
    active, visiting, unknown = {}, set(), []

    def visit(relative):
        file = safe_path(source, relative)
        key = file.relative_to(source).as_posix()
        if key in visiting: raise ValueError('cyclic LaTeX input')
        if key in active: return
        visiting.add(key)
        text = strip_comments(file.read_text(encoding='utf-8'))
        active[key] = text
        for match in re.finditer(r'\\(?:input|include)\s*\{([^}]*)\}', text):
            name = match.group(1)
            if not re.fullmatch(r'[A-Za-z0-9_./-]+', name):
                unknown.append({'file': key, 'input': name}); continue
            if not name.endswith('.tex'): name += '.tex'
            visit(name)
        visiting.remove(key)

    visit(main)
    cite, nocite, labels, bad_floats = set(), set(), defaultdict(list), []
    for file, text in active.items():
        for m in re.finditer(r'\\(nocite|cite[a-zA-Z]*)(?:\*)?\s*(?:\[[^\]]*\]\s*)*\{([^}]*)\}', text):
            keys = {k.strip() for k in m.group(2).split(',') if k.strip()}
            (nocite if m.group(1) == 'nocite' else cite).update(keys)
        for m in re.finditer(r'\\label\s*\{([^}]*)\}', text):
            labels[m.group(1)].append({'file': file, 'line': text.count('\n', 0, m.start()) + 1})
        for m in re.finditer(r'\\begin\{(?:figure|table)\*?\}\[([^\]]*)\]', text):
            if '!' in m.group(1) and not any(c in m.group(1) for c in 'htbpH'):
                bad_floats.append({'file': file, 'line': text.count('\n', 0, m.start()) + 1,
                                   'specifier': m.group(1), 'reason': 'modifier_without_position'})
    entries = []
    for text in active.values():
        for match in re.finditer(r'\\bibliography\s*\{([^}]*)\}', text):
            for name in match.group(1).split(','):
                name = name.strip()
                if not name.endswith('.bib'): name += '.bib'
                bib = strip_comments(safe_path(source, name).read_text())
                entries.extend((m.group(2), name, bib.count('\n', 0, m.start()) + 1)
                               for m in re.finditer(r'(?m)^\s*@([A-Za-z]+)\s*[({]\s*([^,\s]+)\s*,', bib)
                               if m.group(1).lower() not in {'string', 'comment', 'preamble'})
    key_counts = Counter(key for key, _, _ in entries)
    rendered = set(re.findall(r'\\bibitem(?:\[[\s\S]*?\])?\s*\{([^}]*)\}',
                              strip_comments(bbl or '')))
    return {'coverage': 'static_literal_inputs_and_bibtex_keys_only',
            'unsupported_inputs': unknown, 'active_files': sorted(active),
            'cited_keys': sorted(cite), 'nocite_keys': sorted(nocite),
            'missing_cited_keys': sorted(cite - key_counts.keys()),
            'missing_nocite_keys': sorted(nocite - key_counts.keys() - {'*'}),
            'bib_entry_count': len(entries), 'bib_unique_key_count': len(key_counts),
            'duplicate_bib_keys': [{'key': k, 'is_cited': k in cite,
                                    'is_rendered': k in rendered,
                                    'locations': [{'file': f, 'line': n} for key, f, n in entries if key == k]}
                                   for k, count in key_counts.items() if count > 1],
            'rendered_keys': sorted(rendered), 'duplicate_labels':
                [{'label': k, 'locations': v} for k, v in labels.items() if len(v) > 1],
            'invalid_float_positions': bad_floats,
            'nocite_places_inline_marker': False, 'reference_authenticity_checked': False}


def build_diagnostics(log: str, record: dict | None) -> dict:
    patterns = {'undefined_citation': r'Citation .* undefined',
                'undefined_reference': r'(?:Hyper reference|Reference) .* undefined',
                'duplicate_label': r'Label .* multiply defined',
                'overfull_hbox': r'Overfull \\hbox', 'underfull_hbox': r'Underfull \\hbox',
                'underfull_vbox': r'Underfull \\vbox',
                'invalid_float_position': 'No positions in optional float specifier'}
    steps = (record or {}).get('steps', [])
    return {'coverage': 'recorded_build_and_log_only',
            'counts': {k: len(re.findall(pattern, log)) for k, pattern in patterns.items()},
            'tex_errors': [line for line in log.splitlines() if line.startswith('!')][:20],
            'output_written': bool(re.search(r'Output written on .*\.pdf', log)),
            'steps': steps, 'exit_codes_known': bool(steps) and all(type(s.get('exit_code')) is int for s in steps),
            'all_exit_codes_zero': bool(steps) and all(s.get('exit_code') == 0 for s in steps),
            'shell_escape_disabled': (all('-no-shell-escape' in s.get('command', [])
                                          for s in steps if s.get('engine') != 'bibtex')
                                      if any(s.get('engine') != 'bibtex' and s.get('command')
                                             for s in steps) else None),
            'visual_checked': False}
