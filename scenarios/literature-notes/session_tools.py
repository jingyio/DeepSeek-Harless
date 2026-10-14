"""Lazy, uploaded-PDF-only binding for the existing literature MCP workflow.

Private operation replay restores this same frozen task after a process restart;
it is recovery, not a learned Motif or a scientific support decision.
"""
from __future__ import annotations
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
from mcp.server.mcpserver.exceptions import ToolError
from pdf_tools import ROOT, PdfScene, digest, inventory, save_private
from web_pdf_tools import WebPdfScene, make_server

READ_METHODS = ('list_pdfs', 'prepare_pdf', 'search_pdf_text', 'pin_pdf_context',
                'read_pinned_pdf_context', 'read_pdf_evidence_plan')
WEB_METHODS = ('preview_research_notes', 'read_claim_repair_packet', 'search_claim_evidence',
               'read_claim_evidence_plan', 'submit_claim_repair', 'read_final_synthesis',
               'deliver_research_notes')
CODE_FILES = ('session_tools.py', 'web_pdf_tools.py', 'pdf_tools.py', 'pdf_layout.py',
              'pdf_read_plan.py', 'pdf_review_tools.py', 'pdf_repair_tools.py',
              'pdf_dependencies.py', 'claim_coverage.py')


def stable_result(value):
    # Parser cache counters are observability, never evidence or authority.
    if isinstance(value, dict):
        return {key: stable_result(item) for key, item in value.items() if key != 'cache_stats'}
    if isinstance(value, list):
        return [stable_result(item) for item in value]
    return value


class ReadingProxy:
    def __init__(self, owner):
        self.owner = owner


class SessionLiteratureScene:
    def __init__(self, directory: Path):
        self.directory = directory.resolve(strict=True)
        if (self.directory.name != 'literature' or self.directory.parent.name != 'work'
                or not self.directory.is_relative_to(ROOT / '.local')):
            raise ValueError('literature binding must use a Session task directory')
        self.scene = ReadingProxy(self)
        self.delegate = None
        self.journal = None
        self.code_sha256 = digest({name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in CODE_FILES})

    def _task(self):
        path = self.directory / 'task.json'
        if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size > 100_000:
            raise ToolError('literature task scope changed')
        task = json.loads(path.read_text(encoding='utf-8'))
        source = self.directory.parent / 'inputs'
        if (set(task) != {'schema_version', 'question', 'sources'} or task['schema_version'] != 1
                or not isinstance(task['question'], str) or not 1 <= len(task['question'].strip()) <= 4000
                or Path(task['sources']['root']).resolve() != source.resolve()):
            raise ToolError('literature task is not bound to this Session')
        approved = json.loads((self.directory.parent / 'approved-inputs.json').read_text())['files']
        current = inventory(source)
        if current != task['sources'] or any(approved.get(row['filename']) != row['pdf_sha256']
                                             for row in current['papers']):
            raise ToolError('literature approved sources changed; start a new file task')
        for row in current['papers']:
            if (source / row['filename']).stat().st_nlink != 1:
                raise ToolError('literature source must be an exclusive task copy')
        return task

    def _call(self, name, args, kwargs):
        target = self.delegate.scene if name in READ_METHODS else self.delegate
        return getattr(target, name)(*args, **kwargs)

    def _load(self):
        task = self._task()
        if self.delegate is not None:
            return
        journal_path = self.directory / 'operations.json'
        if journal_path.exists():
            if journal_path.is_symlink() or journal_path.stat().st_nlink != 1 or journal_path.stat().st_size > 8_000_000:
                raise ToolError('literature recovery store is invalid')
            journal = json.loads(journal_path.read_text())
            if (set(journal) != {'version', 'task_sha256', 'code_sha256', 'operations'} or journal['version'] != 1
                    or journal['task_sha256'] != digest(task) or journal['code_sha256'] != self.code_sha256
                    or not isinstance(journal['operations'], list) or len(journal['operations']) > 128):
                raise ToolError('literature recovery version changed; start a new task')
        else:
            journal = {'version': 1, 'task_sha256': digest(task), 'code_sha256': self.code_sha256, 'operations': []}
        snapshot = self.directory / 'input-snapshot.json'
        if not snapshot.exists():
            save_private(snapshot, {'task': task, 'task_sha256': digest(task), 'scope': 'session_uploaded_pdf',
                                    'runtime': {'code_sha256': self.code_sha256}, 'cache_policy': 'session_private'})
        else:
            if snapshot.is_symlink() or snapshot.stat().st_nlink != 1 or snapshot.stat().st_size > 200_000:
                raise ToolError('literature input snapshot is invalid')
            frozen = json.loads(snapshot.read_text())
            if (frozen.get('task') != task or frozen.get('task_sha256') != digest(task)
                    or frozen.get('runtime', {}).get('code_sha256') != self.code_sha256
                    or frozen.get('scope') != 'session_uploaded_pdf'):
                raise ToolError('literature input snapshot changed; start a new task')
        self.delegate = WebPdfScene(self.directory, cache=self.directory / 'cache')
        self.journal = journal
        try:
            for operation in journal['operations']:
                if (set(operation) != {'name', 'args', 'kwargs', 'outcome'}
                        or operation['name'] not in READ_METHODS + WEB_METHODS
                        or not isinstance(operation['args'], list) or not isinstance(operation['kwargs'], dict)):
                    raise ToolError('invalid literature recovery operation')
                try:
                    result = self._call(operation['name'], operation['args'], operation['kwargs'])
                    outcome = {'ok': True, 'sha256': digest(stable_result(result))}
                except ToolError as error:
                    outcome = {'ok': False, 'error': str(error)}
                if operation['outcome'] is not None and operation['outcome'] != outcome:
                    raise ToolError('literature recovery no longer matches the frozen task')
                operation['outcome'] = outcome
            save_private(journal_path, journal)
        except Exception:
            self.delegate = None
            raise

    @property
    def phase(self):
        self._load()
        return self.delegate.phase

    def _require(self, *phases):
        # Follow-up reading can inspect the same sources after delivery, while
        # the original final artifact and semantic decisions remain frozen.
        if self.phase not in phases and not (self.phase == 'delivered' and phases == ('reading',)):
            raise ToolError('task phase is ' + self.phase + '; continue the scoped workflow')

    def _invoke(self, name, args, kwargs):
        self._load()
        if len(self.journal['operations']) >= 128:
            raise ToolError('literature operation limit reached; start a new task')
        operation = {'name': name, 'args': list(args), 'kwargs': kwargs, 'outcome': None}
        if len(json.dumps(operation, ensure_ascii=False)) > 200_000:
            raise ToolError('literature operation is too large')
        self.journal['operations'].append(operation)
        save_private(self.directory / 'operations.json', self.journal)
        try:
            result = self._call(name, args, kwargs)
            operation['outcome'] = {'ok': True, 'sha256': digest(stable_result(result))}
            return result
        except ToolError as error:
            operation['outcome'] = {'ok': False, 'error': str(error)}
            raise
        finally:
            save_private(self.directory / 'operations.json', self.journal)


def delegate_method(original, proxy=False):
    @wraps(original)
    def method(self, *args, **kwargs):
        owner = self.owner if proxy else self
        return owner._invoke(original.__name__, args, kwargs)
    return method


for method_name in READ_METHODS:
    setattr(ReadingProxy, method_name, delegate_method(getattr(PdfScene, method_name), proxy=True))
setattr(SessionLiteratureScene, 'list_pdfs', delegate_method(PdfScene.list_pdfs))
for method_name in WEB_METHODS:
    setattr(SessionLiteratureScene, method_name, delegate_method(getattr(WebPdfScene, method_name)))

if __name__ == '__main__':
    make_server(SessionLiteratureScene(Path(os.environ['SSS_PDF_WEB_TASK']))).run(transport='stdio')
