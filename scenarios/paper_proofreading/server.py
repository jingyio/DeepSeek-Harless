"""Session-scoped paper evidence, reusing the existing static checker."""
from pathlib import Path
import hashlib
import io
import json
import os
import re
import stat
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.session_files import SessionFiles
from src.adapters.file_lock import exclusive_lock
from src.adapters import paper_static_checks
from src.adapters.paper_archive import materialize_approved_archive
from src.adapters.paper_query_recovery import validate_queries
from src.adapters.paper_renderer import INPUT_SCHEMA, audit_pdf_content_coverage, render_renderer, validate_audit
from mcp.server import MCPServer
from mcp.types import ToolAnnotations

# Reuse the paper-submission evidence implementation, with a Web task's
# approved input directory as its only case root.
sys.path.insert(0, str(ROOT / 'scenarios' / 'paper-submission'))
from checks import PaperEvidence as CitationEvidence


class PaperEvidence(SessionFiles):
    def __init__(self, directory):
        super().__init__(directory, max_files=16)

    def paper_tree(self):
        rows = self.list_files()['files']
        tex = [row['name'] for row in rows if Path(row['name']).suffix.lower() == '.tex']
        has_archive = any(Path(row['name']).suffix.lower() == '.zip' for row in rows)
        if tex and has_archive: raise ValueError('paper_source_scope_ambiguous')
        main = 'main.tex' if 'main.tex' in tex else tex[0] if len(tex) == 1 else None
        if main is not None:
            return {'root': self.root, 'main': main, 'files': rows}
        if has_archive:
            return materialize_approved_archive(self)
        return None

    def scope_version(self):
        rows = self.list_files()['files']
        return hashlib.sha256(json.dumps({'files': rows, 'checker': hashlib.sha256(
            Path(paper_static_checks.__file__).read_bytes()).hexdigest()}, sort_keys=True).encode()).hexdigest()

    def pin_sources(self, main):
        if Path(main).suffix.lower() != '.tex': raise ValueError('latex_main_required')
        tree = self.paper_tree()
        if tree is None or main != tree['main']: raise ValueError('paper_main_tex_not_unambiguous')
        if next(row for row in tree['files'] if row['name'] == main)['bytes'] > 256*1024:
            raise ValueError('paper_text_limit')
        version = self.scope_version()
        handle = 'source-' + uuid4().hex
        self.handles[handle] = (main, version, 'latex')
        return {'source_id': handle, 'main': main, 'version_sha256': version}

    def read_sources(self, source_id):
        row = self.handles.get(source_id)
        if not row or len(row) != 3 or row[2] != 'latex': raise ValueError('wrong_or_unknown_source_view')
        main, version, _ = row
        if self.scope_version() != version: raise ValueError('paper_scope_version_changed')
        tree = self.paper_tree()
        if tree is None or tree['main'] != main: raise ValueError('paper_scope_version_changed')
        for entry in tree['files']:
            if Path(entry['name']).suffix.lower() in ('.tex','.bib','.bbl','.log') and entry['bytes']>256*1024:
                raise ValueError('paper_text_limit')
        bbl_name = str(Path(main).with_suffix('.bbl'))
        bbl_path = tree['root'] / bbl_name
        bbl = ((self.read(bbl_name, limit=256*1024)[0].decode('utf-8')
                if tree['root'] == self.root else
                paper_static_checks.safe_path(tree['root'], bbl_name).read_text(encoding='utf-8'))
               if bbl_path.exists() else None)
        diagnostic = paper_static_checks.source_diagnostics(tree['root'], main, bbl)
        logs = []
        for entry in tree['files']:
            if Path(entry['name']).suffix.lower() == '.log':
                text = (self.read(entry['name'], entry['sha256'], limit=256*1024)[0].decode('utf-8')
                        if tree['root'] == self.root else
                        paper_static_checks.safe_path(tree['root'], entry['name']).read_text(encoding='utf-8'))
                logs.append({'name': entry['name'], 'diagnostic': paper_static_checks.build_diagnostics(text, None)})
        if self.scope_version() != version: raise ValueError('paper_scope_version_changed')
        return {'source_id': source_id, 'version_sha256': version, 'diagnostic': diagnostic,
                'existing_logs': logs, 'compiled_by_this_task': False}

    def document(self, source_id, page):
        row = self.handles.get(source_id)
        if not row or len(row) != 2: raise ValueError('wrong_or_unknown_source_view')
        name, data, version = self.pinned(source_id)
        if type(page) is not int or page < 1: raise ValueError('positive_page_required')
        if Path(name).suffix.lower() == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted: raise ValueError('encrypted_pdf_unsupported')
            if len(reader.pages) > 200: raise ValueError('paper_page_limit')
            if page > len(reader.pages): raise ValueError('page_not_in_document')
            text = reader.pages[page - 1].extract_text() or ''
            count = len(reader.pages)
        else:
            if len(data) > 256*1024: raise ValueError('paper_text_limit')
            whole = data.decode('utf-8')
            count = max(1, (len(whole) + 79999) // 80000)
            if page > count: raise ValueError('page_not_in_document')
            text = whole[(page - 1) * 80000:page * 80000]
        if len(text) > 100000: raise ValueError('paper_page_text_limit')
        self.pinned(source_id)
        return {'source_id': source_id, 'version_sha256': version, 'name': name, 'page': page,
                'page_count': count, 'text': text, 'visual_checked': False,
                'coverage': 'extracted_text_for_model_review_not_fact_or_venue_certification'}


def create_server(directory, renderer_root=None):
    files = PaperEvidence(directory)
    output = PaperOutput(files, renderer_root)
    citation_state = {'epoch': None, 'service': None}
    def citations():
        # The preset may start before task admission. Read the live admission
        # manifest on each call and discard handles at every task boundary.
        workspace = files.root.parent
        approved = json.loads((workspace / 'approved-inputs.json').read_text())['files']
        grant = json.loads((workspace / 'paper-output-grant.json').read_text())
        rows = files.list_files()['files']
        if {row['name']: row['sha256'] for row in rows} != approved:
            raise ValueError('paper_citation_approval_changed')
        # Recheck the ZIP-derived bytes on every call, including after pinning.
        files.paper_tree()
        epoch = (grant.get('task_id'), tuple(sorted(approved.items())))
        if not isinstance(epoch[0], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', epoch[0]):
            raise ValueError('paper_citation_task_invalid')
        if epoch != citation_state['epoch']:
            citation_state.update(epoch=epoch, service=create_citation_evidence(files))
        return citation_state['service']
    server = MCPServer('Harless uploaded paper evidence')
    annotation = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)

    @server.tool(annotations=annotation)
    def list_inputs() -> dict:
        """List only the approved files in this Session, with exact SHA256."""
        return files.list_files()

    @server.tool(annotations=annotation)
    def pin_document(name: str, sha256: str) -> dict:
        """Pin a listed PDF or UTF-8 paper file to a fresh Session-local handle; no host paths."""
        if Path(name).suffix.lower() not in ('.pdf', '.tex', '.bib', '.bbl', '.log', '.md', '.txt'):
            raise ValueError('paper_document_format_unsupported')
        return files.pin(name, sha256)

    @server.tool(annotations=annotation)
    def read_pinned_document(source_id: str, page: int = 1) -> dict:
        """Read one exact PDF page or one bounded 80k-character text page; follow page_count, not guessed page numbers."""
        return files.document(source_id, page)

    @server.tool(annotations=annotation)
    def pin_paper_sources(main: str) -> dict:
        """Pin the uploaded literal LaTeX main and all current source files to a versioned scope."""
        return files.pin_sources(main)

    @server.tool(annotations=annotation)
    def read_pinned_paper_sources(source_id: str) -> dict:
        """Use the existing static checker for literal citations, duplicate labels, floats and supplied logs; no compilation or authenticity claim."""
        return files.read_sources(source_id)

    @server.tool(annotations=annotation)
    def pin_paper_citations(case_id: str) -> dict:
        """Pin the approved current manuscript's active citations to a versioned Session handle."""
        if case_id != 'current': raise ValueError('paper_case_not_approved')
        return citations().pin(case_id, 'sources')

    @server.tool(annotations=annotation)
    def read_pinned_paper_citations(source_id: str) -> dict:
        """Inspect active literal citations and bind a fresh citation batch; no factual judgment."""
        return citations().inspect_citations(source_id)

    @server.tool(annotations=annotation)
    def read_pinned_citation_records(citation_id: str) -> dict:
        """Read original BibTeX entries for the bound active citation batch."""
        return citations().read_citation_records(citation_id)

    @server.tool(annotations=annotation)
    def read_pinned_bibliography_page(source_id: str, page: int) -> dict:
        """Read page two or later with a source_id from collect_current_local_citation_evidence or pin_paper_citations; never use pin_paper_sources' different handle."""
        if type(page) is not int or page < 2:
            raise ValueError('bibliography_later_page_required_use_first_page_tool')
        return citations().read_bibliography_page(source_id, page)

    @server.tool(annotations=annotation)
    def read_pinned_bibliography_first_page(source_id: str) -> dict:
        """Read fixed page one using only the source_id from collect_current_local_citation_evidence or pin_paper_citations, not pin_paper_sources."""
        return citations().read_bibliography_page(source_id, 1)

    @server.tool(annotations=annotation)
    def collect_current_local_citation_evidence() -> dict:
        """Collect current LaTeX checks and active original BibTeX records in one bounded, versioned local read; no network or authenticity claim."""
        return citations().collect_local_citation_evidence('current')

    @server.tool(annotations=annotation)
    def fetch_pinned_cited_preprint_metadata(citation_id: str) -> dict:
        """Fetch official arXiv metadata for the bound citations; it does not certify publication."""
        return citations().read_preprints(citation_id)

    @server.tool(annotations=annotation)
    def fetch_pinned_formal_reference_metadata(citation_id: str) -> dict:
        """Fetch Crossref candidates for bound source identifiers or titles; model reviews identity."""
        return citations().read_formal_metadata(citation_id)

    @server.tool(annotations=annotation)
    def recover_pinned_formal_reference_queries(citation_id: str) -> dict:
        """Use only an administrator-registered bounded query library for this citation batch."""
        path = os.environ.get('HARLESS_PAPER_QUERY_LIBRARY')
        if not path: raise ValueError('paper_query_library_not_deployed')
        path_ref = Path(path)
        candidate = path_ref.resolve(strict=True)
        if (not candidate.is_relative_to((ROOT / '.local').resolve()) or
            path_ref.is_symlink() or candidate.stat().st_size > 1000000):
            raise ValueError('paper_query_library_scope_invalid')
        library = json.loads(candidate.read_text(encoding='utf-8'))
        validate_queries(library)
        return citations().recover_formal_queries(citation_id, library)

    @server.tool(annotations=annotation)
    def read_current_audit() -> dict:
        """Read the task's approved or model-finalized audit report with its exact SHA256."""
        return output.read_audit()

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def stage_current_audit(scope: str | None = None, references: list[dict] | None = None,
                            sources: list[dict] | None = None, issues: list[dict] | None = None,
                            citation_checks: dict[str, dict[str, str]] | None = None,
                            notes: list[str] | None = None,
                            remove_reference_number: int | None = None,
                            expected_draft_sha256: str = '') -> dict:
        """Append typed fields or remove one draft reference; use returned SHA for the next call.

        scope is text; notes is a list of strings. Each references/sources/issues field is
        a list of report rows (at most eight per call). citation_checks is an object keyed
        by check name, each value having result/evidence/limitation strings. A reference's
        source_ids must name rows in sources; uploaded names belong in evidence_files.
        Missing required fields return staged=false and exact field names without writing.
        Duplicate reference keys return staged=false without writing. To repair an older
        draft, pass only remove_reference_number and the current draft SHA; later rows
        are renumbered. This cannot change a finalized report or uploaded original.
        """
        patch = {name: value for name, value in {
            'scope': scope, 'references': references, 'sources': sources,
            'issues': issues, 'citation_checks': citation_checks, 'notes': notes,
            'remove_reference_number': remove_reference_number,
        }.items() if value is not None}
        return output.stage(patch, expected_draft_sha256)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def finalize_current_audit(expected_draft_sha256: str) -> dict:
        """Validate and freeze the report; invalid draft content returns a repair reason."""
        return output.finalize(expected_draft_sha256)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False))
    def export_current_audit_pdf(report_sha256: str) -> dict:
        """Export a new task PDF from the approved or finalized report SHA and reviewed renderer."""
        return output.export(report_sha256)

    return server


def create_citation_evidence(files: PaperEvidence):
    tree = files.paper_tree()
    if tree is None:
        # The scene may also be used for PDF/text proofreading. Citation tools
        # remain visible but explicitly reject tasks without an unambiguous main.
        return UnavailableCitationEvidence()
    return CitationEvidence({'current': {'root': str(tree['root']), 'source_dir': '.',
                                          'main': tree['main']}}, files.root.parent)


class UnavailableCitationEvidence:
    def __getattr__(self, _name):
        def unavailable(*_args, **_kwargs): raise ValueError('paper_main_tex_not_unambiguous')
        return unavailable


class PaperOutput:
    def __init__(self, files: PaperEvidence, renderer_root):
        self.files = files
        self.renderer_root = Path(renderer_root).resolve(strict=True) if renderer_root else None

    @staticmethod
    def _private_bytes(path, limit=256*1024):
        if path.is_symlink(): raise ValueError('paper_audit_private_file_required')
        with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > limit:
                raise ValueError('paper_audit_private_file_required')
            data = stream.read(limit + 1)
        if len(data) > limit: raise ValueError('paper_audit_size_limit')
        return data

    @staticmethod
    def _save(path, value):
        if path.exists() and (path.is_symlink() or path.stat().st_nlink != 1):
            raise ValueError('paper_audit_private_file_required')
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        if len(data) > 256*1024: raise ValueError('paper_audit_size_limit')
        temporary = path.with_name(path.name + '-' + uuid4().hex + '.tmp')
        with temporary.open('xb') as stream: stream.write(data)
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def _task(self, writable=False):
        workspace = self.files.root.parent
        approved = json.loads((workspace / 'approved-inputs.json').read_text())
        grant = json.loads((workspace / 'paper-output-grant.json').read_text())
        if (not isinstance(approved.get('files'), dict) or
            grant.get('schema_version') != 1 or
            not isinstance(grant.get('task_id'), str) or
            not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',grant['task_id'])):
            raise ValueError('paper_audit_approval_changed')
        if writable and grant.get('allow_output') is not True:
            raise ValueError('paper_pdf_output_not_authorized')
        listed = {row['name']: row['sha256'] for row in self.files.list_files()['files']}
        if listed != approved['files']: raise ValueError('paper_audit_approval_changed')
        return workspace, grant, listed

    def _draft_dir(self, workspace, grant):
        directory = workspace / 'outputs' / 'paper-audits' / grant['task_id']
        if any(p.is_symlink() for p in (workspace / 'outputs', workspace / 'outputs' / 'paper-audits', directory)):
            raise ValueError('paper_audit_private_directory_required')
        return directory

    @staticmethod
    def _missing_patch_fields(patch):
        missing = []
        for name, schema_key in (('references', 'reference_required'),
                                 ('sources', 'source_required'), ('issues', 'issue_required')):
            rows = patch.get(name, [])
            for index, row in enumerate(rows if isinstance(rows, list) else []):
                if isinstance(row, dict):
                    missing.extend(f'{name}[{index}].{field}' for field in INPUT_SCHEMA[schema_key]
                                   if field not in row)
        checks = patch.get('citation_checks', {})
        for name, row in (checks.items() if isinstance(checks, dict) else []):
            if isinstance(row, dict):
                missing.extend(f'citation_checks.{name}.{field}' for field in INPUT_SCHEMA['citation_result_required']
                               if field not in row)
        return missing

    @staticmethod
    def _extra_patch_fields(patch):
        extra = []
        for name, schema_key in (('references', 'reference_required'),
                                 ('sources', 'source_required'), ('issues', 'issue_required')):
            for index, row in enumerate(patch.get(name, []) if isinstance(patch.get(name, []), list) else []):
                if isinstance(row, dict):
                    extra.extend(f'{name}[{index}].{field}' for field in row
                                 if field not in INPUT_SCHEMA[schema_key])
        checks = patch.get('citation_checks', {})
        for name, row in (checks.items() if isinstance(checks, dict) else []):
            if isinstance(row, dict):
                extra.extend(f'citation_checks.{name}.{field}' for field in row
                             if field not in INPUT_SCHEMA['citation_result_required'])
        return extra

    def stage(self, patch, expected_draft_sha256=''):
        workspace, grant, sources = self._task(writable=True)
        if not sources or sources.get('audit.json') is not None:
            raise ValueError('paper_generated_audit_requires_original_sources')
        if (not isinstance(patch, dict) or not patch or
            set(patch) - {'scope', 'references', 'sources', 'issues', 'citation_checks', 'notes',
                          'remove_reference_number'} or
            len(json.dumps(patch, ensure_ascii=False).encode()) > 16000):
            raise ValueError('paper_audit_patch_invalid')
        directory = self._draft_dir(workspace, grant)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with exclusive_lock(directory / '.lock'):
            draft_path = directory / 'draft.json'
            if (directory / 'audit.json').exists(): raise ValueError('paper_audit_already_finalized')
            if draft_path.exists():
                draft = json.loads(self._private_bytes(draft_path))
                current = hashlib.sha256(self._private_bytes(draft_path)).hexdigest()
                if expected_draft_sha256 != current: raise ValueError('stale_paper_audit_draft')
            else:
                if expected_draft_sha256: raise ValueError('stale_paper_audit_draft')
                draft = {'task_id': grant['task_id'], 'source_versions': sources,
                         'report': {'schema_version': 1, 'scope': '', 'reference_count': 0,
                                    'references': [], 'sources': [], 'issues': [],
                                    'citation_checks': {}, 'notes': []}}
            if draft.get('task_id') != grant['task_id'] or draft.get('source_versions') != sources:
                raise ValueError('paper_audit_source_changed')
            missing = self._missing_patch_fields(patch)
            if missing:
                return {'staged': False, 'draft_sha256': current if draft_path.exists() else None,
                        'validation_error': 'paper_audit_patch_missing_record_fields',
                        'missing_fields': missing[:16], 'missing_field_count': len(missing),
                        'semantic_quality_accepted': False}
            extra = self._extra_patch_fields(patch)
            if extra:
                return {'staged': False, 'draft_sha256': current if draft_path.exists() else None,
                        'validation_error': 'paper_audit_patch_extra_record_fields',
                        'extra_fields': extra[:16], 'extra_field_count': len(extra),
                        'semantic_quality_accepted': False}
            report = draft['report']
            if 'remove_reference_number' in patch:
                number = patch['remove_reference_number']
                if (len(patch) != 1 or type(number) is not int or
                    not 1 <= number <= len(report['references'])):
                    raise ValueError('paper_audit_reference_removal_invalid')
                report['references'].pop(number - 1)
                for index, row in enumerate(report['references'], 1):
                    row['number'] = index
                report['reference_count'] = len(report['references'])
                self._save(draft_path, draft)
                return {'staged': True, 'draft_sha256': hashlib.sha256(
                    self._private_bytes(draft_path)).hexdigest(),
                    'removed_reference_number': number,
                    'reference_count': len(report['references']),
                    'semantic_quality_accepted': False}
            for name in ('references', 'sources', 'issues', 'notes', 'citation_checks'):
                rows = patch.get(name)
                if isinstance(rows, (list, dict)) and len(rows) > 8:
                    return {'staged': False,
                            'draft_sha256': current if draft_path.exists() else None,
                            'validation_error': 'paper_audit_batch_limit',
                            'field': name, 'limit': 8, 'received': len(rows),
                            'semantic_quality_accepted': False}
            if 'references' in patch:
                positions = {}
                for index, row in enumerate(report['references'], 1):
                    if isinstance(row, dict) and isinstance(row.get('key'), str):
                        positions.setdefault(row['key'], index)
                duplicates = []
                for index, row in enumerate(
                        patch['references'] if isinstance(patch['references'], list) else [],
                        len(report['references']) + 1):
                    if isinstance(row, dict) and isinstance(row.get('key'), str):
                        if row['key'] in positions:
                            duplicates.append([positions[row['key']], index])
                        else:
                            positions[row['key']] = index
                if duplicates:
                    return {'staged': False,
                            'draft_sha256': current if draft_path.exists() else None,
                            'validation_error': 'paper_audit_duplicate_keys',
                            'duplicate_reference_numbers': duplicates[:16],
                            'semantic_quality_accepted': False}
            if 'scope' in patch:
                if not isinstance(patch['scope'], str) or not 1 <= len(patch['scope']) <= 2000:
                    raise ValueError('paper_audit_scope_invalid')
                report['scope'] = patch['scope']
            for name in ('references', 'sources', 'issues', 'notes'):
                if name in patch:
                    rows = patch[name]
                    if not isinstance(rows, list) or len(rows) > 8 or any(
                        not isinstance(row, str if name == 'notes' else dict) for row in rows):
                        raise ValueError('paper_audit_rows_invalid')
                    report[name].extend(rows)
            if 'citation_checks' in patch:
                checks = patch['citation_checks']
                if not isinstance(checks, dict) or len(checks) > 8 or any(
                    key in report['citation_checks'] or not isinstance(value, dict)
                    for key, value in checks.items()):
                    raise ValueError('paper_audit_checks_invalid')
                report['citation_checks'].update(checks)
            report['reference_count'] = len(report['references'])
            self._save(draft_path, draft)
            digest = hashlib.sha256(self._private_bytes(draft_path)).hexdigest()
            return {'staged': True, 'draft_sha256': digest, 'reference_count': len(report['references']),
                    'source_count': len(report['sources']), 'issue_count': len(report['issues']),
                    'citation_check_count': len(report['citation_checks']),
                    'semantic_quality_accepted': False}

    def finalize(self, expected_draft_sha256):
        workspace, grant, sources = self._task(writable=True)
        directory = self._draft_dir(workspace, grant)
        if not directory.is_dir() or directory.is_symlink(): raise ValueError('paper_audit_draft_missing')
        with exclusive_lock(directory / '.lock'):
            draft_raw = self._private_bytes(directory / 'draft.json')
            if hashlib.sha256(draft_raw).hexdigest() != expected_draft_sha256:
                raise ValueError('stale_paper_audit_draft')
            draft = json.loads(draft_raw)
            if draft.get('task_id') != grant['task_id'] or draft.get('source_versions') != sources:
                raise ValueError('paper_audit_source_changed')
            report = draft['report']
            extra = self._extra_patch_fields(report)
            if extra:
                return {'finalized': False, 'draft_sha256': expected_draft_sha256,
                        'validation_error': 'paper_audit_patch_extra_record_fields',
                        'extra_fields': extra[:16], 'extra_field_count': len(extra),
                        'semantic_quality_accepted': False}
            try:
                validate_audit(report)
            except ValueError as error:
                result = {'finalized': False, 'draft_sha256': expected_draft_sha256,
                          'validation_error': str(error),
                          'semantic_quality_accepted': False}
                if str(error) == 'renderer_input_duplicate_keys':
                    positions = {}
                    duplicates = []
                    for index, row in enumerate(report['references'], 1):
                        key = row.get('key') if isinstance(row, dict) else None
                        if isinstance(key, str):
                            if key in positions: duplicates.append([positions[key], index])
                            else: positions[key] = index
                    result['duplicate_reference_numbers'] = duplicates[:16]
                return result
            if not report['scope'].strip(): raise ValueError('paper_audit_scope_required')
            if (directory / 'audit.json').exists(): raise ValueError('paper_audit_already_finalized')
            digest = hashlib.sha256(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                               separators=(',', ':')).encode()).hexdigest()
            self._save(directory / 'provenance.json', {'task_id': grant['task_id'],
                'source_versions': sources, 'draft_sha256': expected_draft_sha256,
                'audit_sha256': digest, 'origin': 'model_generated_task_copy'})
            self._save(directory / 'audit.json', report)
            return {'report_sha256': digest, 'reference_count': len(report['references']),
                    'source_count': len(report['sources']),
                    'source_scope': 'model_generated_from_current_task_uploads',
                    'semantic_quality_accepted': False}

    def _audit(self, writable=False):
        workspace, grant, sources = self._task(writable=writable)
        if sources.get('audit.json') is not None:
            raw, digest = self.files.read('audit.json', limit=256*1024)
            if grant.get('audit_sha256') != digest:
                raise ValueError('paper_audit_approval_changed')
            scope = 'current_approved_task_upload'
        else:
            directory = self._draft_dir(workspace, grant)
            if not (directory / 'audit.json').is_file(): raise ValueError('paper_audit_not_ready')
            raw = self._private_bytes(directory / 'audit.json')
            digest = hashlib.sha256(raw).hexdigest()
            provenance = json.loads(self._private_bytes(directory / 'provenance.json', 10000))
            if (grant.get('audit_sha256') is not None or
                provenance.get('task_id') != grant['task_id'] or
                provenance.get('source_versions') != sources or
                provenance.get('audit_sha256') != digest):
                raise ValueError('paper_audit_approval_changed')
            scope = 'model_generated_from_current_task_uploads'
        report = json.loads(raw)
        validate_audit(report)
        return workspace, grant, raw, digest, report, scope

    def read_audit(self):
        _, _, _, digest, report, scope = self._audit()
        return {'report_sha256': digest, 'report': report,
                'semantic_quality_accepted': False, 'source_scope': scope}

    def export(self, report_sha256):
        workspace, grant, raw, digest, report, scope = self._audit(writable=True)
        if report_sha256 != digest: raise ValueError('stale_audit_export')
        if self.renderer_root is None: raise ValueError('paper_renderer_not_deployed')
        cert = json.loads((self.renderer_root / 'deployment.json').read_text())
        package = self.renderer_root / 'package'
        review = self.renderer_root / 'review.json'
        if (cert.get('schema_version') != 1 or
            hashlib.sha256((package / 'manifest.json').read_bytes()).hexdigest() != cert.get('manifest_sha256') or
            hashlib.sha256(review.read_bytes()).hexdigest() != cert.get('review_sha256')):
            raise ValueError('paper_renderer_deployment_changed')
        outputs = workspace / 'outputs'
        outputs.mkdir(mode=0o700, exist_ok=True)
        if sum(1 for p in outputs.glob(grant['task_id'] + '-*') if p.is_dir()) >= 3:
            raise ValueError('paper_export_attempt_limit')
        target = outputs / (grant['task_id'] + '-' + uuid4().hex)
        target.mkdir(mode=0o700)
        with (target / 'audit.json').open('xb') as stream: stream.write(raw)
        receipt = render_renderer(package, cert['manifest_sha256'], target, digest,
                                  Path(sys.executable), review_path=review,
                                  expected_review_sha256=cert['review_sha256'])
        receipt['content_coverage'] = audit_pdf_content_coverage(target / 'reference-check-report.pdf', report)
        if self._audit(writable=True)[3] != digest:
            raise ValueError('paper_audit_changed_during_export')
        receipt['audit_source_scope'] = scope
        receipt['artifact_file'] = str((target / 'reference-check-report.pdf').relative_to(workspace))
        (target / 'export-receipt.json').write_text(json.dumps(receipt, ensure_ascii=False) + '\n')
        return receipt


if __name__ == '__main__': create_server(Path(sys.argv[1]), sys.argv[2] if len(sys.argv)>2 else None).run(transport='stdio')
