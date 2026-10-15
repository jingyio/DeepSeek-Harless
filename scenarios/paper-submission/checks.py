"""Read-only, versioned views of already prepared paper evidence.

This is a bounded static LaTeX diagnostic, not a full TeX interpreter, a venue
checker or a compiler. It never executes paper source or model-generated code.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
import platform
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4
from src.adapters.paper_bibliography import bib_records
from src.adapters.arxiv_metadata import fetch_metadata
from src.adapters.crossref_metadata import fetch_crossref, literal_field, DOI
from src.adapters.paper_query_recovery import recover_queries


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


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
        key = str(file.relative_to(source))
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


def probe(binary: str, pdf: Path) -> dict:
    executable = shutil.which(binary)
    if not executable: return {'status': 'unavailable'}
    p = subprocess.run([executable, str(pdf)], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=30)
    return {'status': 'ok' if p.returncode == 0 else 'failed', 'exit_code': p.returncode,
            'stdout': p.stdout[:16000], 'stderr': p.stderr[:4000]}


class PaperEvidence:
    def __init__(self, inputs: dict, trusted_root: Path):
        self.inputs, self.trusted_root, self.handles = inputs, trusted_root.resolve(), {}
        self.citation_batches = {}
        self.preprint_packets = {}
        for case, row in inputs.items():
            if not re.fullmatch(r'[a-z][a-z0-9_]{1,39}', case): raise ValueError('invalid case ID')
            root = Path(row['root']).resolve(strict=True)
            if not root.is_relative_to(self.trusted_root): raise ValueError('case must be private')
            self.paths(case)

    def paths(self, case):
        if case not in self.inputs: raise ValueError('case not authorised')
        row = self.inputs[case]; root = Path(row['root']).resolve(strict=True)
        return row, root, {key: safe_path(root, row[key]) for key in
                           ('source_dir', 'pdf', 'log', 'bbl', 'build_record') if row.get(key)}

    def version(self, case):
        row, root, paths = self.paths(case)
        files = sorted(p for p in root.rglob('*') if p.is_file())
        if len(files) > 256 or sum(p.stat().st_size for p in files) > 50000000:
            raise ValueError('paper snapshot exceeds size limit')
        # Include diagnostics code, source and derived bytes; changes invalidate handles.
        hashes = {}
        for file in files:
            relative = str(file.relative_to(root))
            safe_path(root, relative)
            hashes[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
        binaries = {name: hashlib.sha256(Path(shutil.which(name)).read_bytes()).hexdigest()
                    if shutil.which(name) else None for name in ('pdfinfo', 'pdffonts')}
        return digest({'files': hashes, 'config': row,
                       'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                       'bib_parser_sha256': hashlib.sha256(
                           Path(__file__).resolve().parents[2].joinpath('src/adapters/paper_bibliography.py').read_bytes()).hexdigest(),
                       'arxiv_metadata_sha256': hashlib.sha256(
                           Path(__file__).resolve().parents[2].joinpath('src/adapters/arxiv_metadata.py').read_bytes()).hexdigest(),
                       'crossref_metadata_sha256': hashlib.sha256(
                           Path(__file__).resolve().parents[2].joinpath('src/adapters/crossref_metadata.py').read_bytes()).hexdigest(),
                       'query_recovery_sha256': hashlib.sha256(
                           Path(__file__).resolve().parents[2].joinpath('src/adapters/paper_query_recovery.py').read_bytes()).hexdigest(),
                       'python': platform.python_version(), 'binaries': binaries})

    def pin(self, case: str, kind: str):
        if kind not in {'sources', 'build', 'pdf'}: raise ValueError('unsupported view')
        version = self.version(case)
        source_id = 'source-' + uuid4().hex
        self.handles[source_id] = (case, kind, version)
        return {'case_id': case, 'kind': kind, 'source_id': source_id, 'version_sha256': version}

    def inspect_citations(self, source_id: str):
        """Create a session-owned batch from the active manuscript, not model text."""
        result = self.read(source_id, 'sources')
        diag = result['diagnostic']
        if diag['unsupported_inputs']:
            raise ValueError('dynamic LaTeX inputs need model review')
        keys = diag['cited_keys']
        if len(keys) > 64:
            raise ValueError('citation scope exceeds one batch; explicit partition required')
        citation_id = 'source-' + uuid4().hex
        self.citation_batches[citation_id] = (source_id, tuple(keys), result['version_sha256'])
        return {**result, 'source_id': source_id, 'case_id': self.handles[source_id][0], 'citation_id': citation_id,
                'scope': 'active_manuscript_literal_cite_keys_only',
                'nocite_included': False, 'authenticity_checked': False}

    def read_citation_records(self, citation_id: str):
        if citation_id not in self.citation_batches:
            raise ValueError('unknown or expired citation batch')
        source_id, keys, version = self.citation_batches[citation_id]
        case, kind, current = self.handles[source_id]
        if kind != 'sources' or current != version or self.version(case) != version:
            raise ValueError('citation batch source version changed')
        if keys:
            result = self.read_references(source_id, list(keys))
        else:
            result = {'source_id': source_id, 'version_sha256': version,
                      'coverage': 'active_literal_bibliography_brace_entries_only',
                      'requested_keys': [], 'records': [], 'missing_keys': [], 'duplicate_keys': {},
                      'reference_authenticity_checked': False, 'rendered_numbering_checked': False}
        pairs = sorted({(r['key'], identifier) for r in result['records']
                        for identifier in re.findall(r'(?<!\d)(\d{4}\.\d{4,5})(?!\d)', r['raw_bibtex'])})
        return {**result, 'citation_id': citation_id,
                'scope': 'active_manuscript_literal_cite_keys_only',
                'required_reference_pairs': [{'key': key, 'arxiv_id': identifier} for key, identifier in pairs],
                'identifier_detection': 'literal_arxiv_syntax_candidates_not_authenticity_confirmation'}

    def read_preprints(self, citation_id: str):
        records = self.read_citation_records(citation_id)
        return self._fetch_preprints(citation_id, records)

    def _fetch_preprints(self, citation_id: str, records: dict):
        pairs = records['required_reference_pairs']
        identifiers = list(dict.fromkeys(p['arxiv_id'] for p in pairs))
        metadata = fetch_metadata(identifiers)
        source_id, _, version = self.citation_batches[citation_id]
        case = self.handles[source_id][0]
        if self.version(case) != version: raise ValueError('source changed during metadata fetch')
        result = {'citation_id': citation_id, 'version_sha256': version,
                'required_reference_pairs': pairs, 'metadata': metadata,
                'formal_publication_confirmed': False, 'bibliography_match_confirmed': False}
        self.preprint_packets[citation_id] = result
        return result

    def read_formal_metadata(self, citation_id: str):
        """Use literal identifiers/titles from source-bound records, not model URLs."""
        records = self.read_citation_records(citation_id)
        preprints = self.preprint_packets.get(citation_id)
        if not preprints or preprints['version_sha256'] != records['version_sha256']:
            raise ValueError('current preprint metadata must be obtained before formal lookup')
        by_id = {r['requested_id']: r for r in preprints['metadata']['items']}
        grouped = {}
        for row in records['records']:
            grouped.setdefault(row['key'], []).append(row)
        rows=[]; queried={}
        for pair in records['required_reference_pairs']:
            originals=grouped.get(pair['key'], [])
            base={**pair,'record_sha256':[r['record_sha256'] for r in originals],
                  'work_identity_confirmed':False,'formal_version_selected':False}
            if len(originals)!=1:
                rows.append({**base,'status':'ambiguous_original_records','lookups':[]});continue
            raw=originals[0]['raw_bibtex']; meta=by_id.get(pair['arxiv_id'],{})
            literal_doi=literal_field(raw,'doi')
            identifiers=list(dict.fromkeys(d for d in [literal_doi,meta.get('doi')]
                                           if isinstance(d,str) and DOI.fullmatch(d)))
            title=literal_field(raw,'title')
            queries=[('doi',d) for d in identifiers] or ([('title',title)] if title else [])
            results=[]
            for field, value in queries:
                key=(field,value)
                if key not in queried:queried[key]=fetch_crossref(**{field:value})
                results.append({'source_field':'original_or_arxiv_doi' if field=='doi' else 'literal_original_title',
                                **queried[key]})
            rows.append({**base,'status':'evidence_candidates' if results else 'no_literal_lookup_input',
                         'lookups':results,'arxiv_comments':meta.get('comments'),
                         'arxiv_journal_reference':meta.get('journal_reference')})
        source_id,_,version=self.citation_batches[citation_id];case=self.handles[source_id][0]
        if self.version(case)!=version:raise ValueError('source changed during formal metadata lookup')
        result={'citation_id':citation_id,'version_sha256':version,'items':rows,
                'coverage':'deposited_metadata_candidates_not_identity_or_publication_confirmation',
                'formal_publication_confirmed':False,'bibliography_match_confirmed':False}
        if len(json.dumps(result,ensure_ascii=False).encode())>1500000:
            raise ValueError('formal evidence exceeds size limit')
        return result

    def recover_formal_queries(self, citation_id: str, library: dict):
        records=self.read_citation_records(citation_id)
        if citation_id not in self.preprint_packets:raise ValueError('source-bound preprint evidence required')
        result=recover_queries(records,library)
        source_id,_,version=self.citation_batches[citation_id];case=self.handles[source_id][0]
        if self.version(case)!=version:raise ValueError('source changed during recovery query')
        if len(json.dumps(result,ensure_ascii=False).encode())>1500000:raise ValueError('recovery evidence exceeds limit')
        return result

    def collect_citation_evidence(self, case_id: str):
        """One bounded tool body, preserving the existing steps and source guards.

        This is an engineered composite capability, not a newly mined Motif.
        No model judgment, generated code or manuscript write occurs here.
        """
        pin = self.pin(case_id, 'sources')
        inspected = self.inspect_citations(pin['source_id'])
        records = self.read_citation_records(inspected['citation_id'])
        preprints = self._fetch_preprints(inspected['citation_id'], records)
        if self.version(case_id) != pin['version_sha256']:
            raise ValueError('source changed during composite evidence collection')
        result = {'schema_version': 1, 'case_id': case_id,
                  'source_id': pin['source_id'], 'citation_id': inspected['citation_id'],
                  'version_sha256': pin['version_sha256'],
                  'scope': 'active_manuscript_literal_cite_keys_only',
                  'diagnostic': inspected['diagnostic'],
                  'references': records,
                  'required_reference_pairs': records['required_reference_pairs'],
                  'metadata': preprints['metadata'],
                  'internal_steps': ['pin_sources', 'inspect_active_citations',
                                     'read_original_bibliography', 'fetch_arxiv_metadata'],
                  'formal_publication_confirmed': False,
                  'bibliography_match_confirmed': False}
        if len(json.dumps(result, ensure_ascii=False).encode()) > 1500000:
            raise ValueError('composite evidence exceeds size limit')
        return result

    def read_references(self, source_id: str, keys: list[str]):
        """Complete requested records with provenance, no shell/network or inference."""
        if (not isinstance(keys, list) or not 1 <= len(keys) <= 64 or
                any(not isinstance(k, str) or not k or len(k) > 256 or
                    any(ord(c) < 32 for c in k) for k in keys) or len(set(keys)) != len(keys)):
            raise ValueError('keys must be 1..64 unique literal citation keys')
        if source_id not in self.handles: raise ValueError('unknown or expired source handle')
        case, kind, version = self.handles[source_id]
        if kind != 'sources' or self.version(case) != version:
            raise ValueError('view or source version changed')
        row, _, paths = self.paths(case)
        source = paths['source_dir']
        diag = source_diagnostics(source, row['main'], None)
        if diag['unsupported_inputs']:
            raise ValueError('dynamic LaTeX inputs need model review')
        # Active literal declarations only; dormant drafts do not change scope.
        bibfiles = []
        for name in diag['active_files']:
            text = strip_comments(safe_path(source, name).read_text(encoding='utf-8'))
            for match in re.finditer(r'\\bibliography\s*\{([^}]*)\}', text):
                for value in match.group(1).split(','):
                    value = value.strip()
                    file = safe_path(source, value if value.endswith('.bib') else value + '.bib')
                    if file not in bibfiles: bibfiles.append(file)
        records = []
        for file in bibfiles:
            raw = file.read_bytes(); text = raw.decode('utf-8')
            if re.search(r'(?m)^\s*@(?!comment\b|string\b|preamble\b)[A-Za-z]+\s*\(', text, re.I):
                raise ValueError('parenthesized BibTeX entries need parser support')
            for index, item in enumerate(bib_records(text)):
                if item['key'] not in keys: continue
                records.append({'key': item['key'], 'kind': item['kind'],
                                'bib_file': str(file.relative_to(source)),
                                'entry_index_in_bib': index,
                                'bib_file_sha256': hashlib.sha256(raw).hexdigest(),
                                'record_sha256': hashlib.sha256(item['raw'].encode('utf-8')).hexdigest(),
                                'raw_bibtex': item['raw']})
        counts = Counter(r['key'] for r in records)
        result = {'source_id': source_id, 'version_sha256': version,
                  'coverage': 'active_literal_bibliography_brace_entries_only',
                  'requested_keys': keys, 'records': records,
                  'missing_keys': [k for k in keys if not counts[k]],
                  'duplicate_keys': {k: n for k, n in counts.items() if n > 1},
                  'reference_authenticity_checked': False, 'rendered_numbering_checked': False}
        if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > 1000000:
            raise ValueError('record batch exceeds size limit; choose fewer keys')
        if self.version(case) != version: raise ValueError('source changed during read')
        return result

    def read(self, source_id: str, kind: str):
        if source_id not in self.handles: raise ValueError('unknown or expired source handle')
        case, selected, version = self.handles[source_id]
        if selected != kind or self.version(case) != version: raise ValueError('view or source version changed')
        row, root, paths = self.paths(case)
        if kind == 'sources':
            value = source_diagnostics(paths['source_dir'], row['main'],
                                       paths['bbl'].read_text() if 'bbl' in paths else None)
        elif kind == 'build':
            value = build_diagnostics(paths['log'].read_text(errors='replace'),
                                      json.loads(paths['build_record'].read_text()) if 'build_record' in paths else None)
        else:
            info, fonts = probe('pdfinfo', paths['pdf']), probe('pdffonts', paths['pdf'])
            match = re.search(r'(?m)^Pages:\s*(\d+)', info.get('stdout', ''))
            font_rows = [line.split() for line in fonts.get('stdout', '').splitlines()[2:] if line.strip()]
            value = {'coverage': 'pdf_metadata_and_font_embedding_only',
                     'pages': int(match.group(1)) if match else None,
                     'fonts_embedded': bool(font_rows) and all(len(r) >= 7 and r[-5] == 'yes' for r in font_rows),
                     'font_count': len(font_rows), 'pdfinfo': info, 'pdffonts': fonts,
                     'visual_checked': False, 'venue_compliance_checked': False}
        if self.version(case) != version: raise ValueError('source changed during read')
        return {'kind': kind, 'version_sha256': version, 'diagnostic': value}
