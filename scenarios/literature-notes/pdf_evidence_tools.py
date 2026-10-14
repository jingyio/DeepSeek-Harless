"""Bounded evidence preparation MCP tools; no Agent loop or Motif controller.

The model selects the windows. These tools preserve that decision, validate
mechanical provenance, and stop before relevance or claim-support judgments.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from pdf_tools import PdfScene, ROOT, digest, inventory, normalized, save_private

HERE = Path(__file__).resolve().parent
PREFIX = 'mcp__literature_evidence__'
MAX_WINDOWS = 6
MAX_TOTAL_CHARS = 12000


def continuation_policy():
    return json.loads((HERE / 'pdf-evidence-contracts.json').read_text())[
        PREFIX + 'extract_evidence_windows']['continuation_policy']


def implementation_version():
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in
            ('pdf_tools.py', 'pdf_read_plan.py', 'pdf_evidence_tools.py', 'pdf-evidence-contracts.json')}


class EvidenceScene(PdfScene):
    def __init__(self, directory, cache, task, *, delivery, cache_policy='reuse', script_chain=False):
        super().__init__(directory, cache, task, delivery=delivery, cache_policy=cache_policy)
        if self.delivery is None:
            raise ValueError('evidence preparation requires private delivery storage')
        self.script_chain = script_chain
        self.initial_task = digest(self.task)
        self.initial_profile = digest(self.profile)
        self.initial_implementation = implementation_version()
        self.execution_version = digest({'task': self.task, 'parser_profile': self.initial_profile,
                                         'implementation': self.initial_implementation})
        self.receipts = {}

    def _assert_current(self):
        if (digest(self.task) != self.initial_task or inventory(self.root) != self.task['sources']
                or digest(self.profile) != self.initial_profile
                or implementation_version() != self.initial_implementation):
            raise ToolError('source selection, parser or implementation changed; create a new task')
        for name, executable in self.executables.items():
            try:
                result = subprocess.run([executable, '-v'], capture_output=True, timeout=10, check=True)
                version = (result.stdout + result.stderr).decode('utf-8', errors='replace').splitlines()[0]
            except (subprocess.SubprocessError, OSError, IndexError):
                raise ToolError('parser unavailable; stop the current preparation') from None
            if shutil.which(name) != executable or version != self.profile['versions'][name]:
                raise ToolError('parser executable changed; create a new task')

    def list_pdfs(self) -> dict:
        """List frozen task sources and the version required by the reading plan; no relevance ranking."""
        self._assert_current()
        return {**super().list_pdfs(), 'execution_version_sha256': self.execution_version,
                'reading_budget': {'max_windows': MAX_WINDOWS, 'max_window_chars': 6000,
                                   'max_actual_chars': MAX_TOTAL_CHARS,
                                   'rule': 'actual page text; same-purpose overlap normalized; never silently truncate selection'}}

    def _plan(self, serialized):
        if not isinstance(serialized, str) or len(serialized) > 16000:
            raise ToolError('reading plan must be a bounded JSON string')
        if serialized.startswith('source-'):
            # A long semantic decision is frozen before the bounded runtime
            # sees it. Only this service may issue the opaque plan receipt.
            return self._load(serialized, 'plan')['plan']
        try:
            plan = json.loads(serialized)
        except ValueError:
            raise ToolError('reading plan is not valid JSON') from None
        if (not isinstance(plan, dict) or set(plan) != {'schema_version', 'task_sha256',
                'allow_deterministic_continuation', 'windows'} or plan['schema_version'] != 1
                or type(plan['schema_version']) is not int
                or plan['task_sha256'] != digest(self.task)
                or type(plan['allow_deterministic_continuation']) is not bool
                or not isinstance(plan['windows'], list) or not 1 <= len(plan['windows']) <= MAX_WINDOWS):
            raise ToolError('plan must bind this task, explicit permission and 1–6 selected windows')
        for w in plan['windows']:
            if not isinstance(w, dict) or set(w) != {'paper_id', 'page', 'start', 'length', 'purpose'}:
                raise ToolError('each window requires paper_id, page, start, length and purpose')
            self._current(w['paper_id'])
            if (not isinstance(w['page'], str) or not w['page'].isascii()
                    or not w['page'].isdigit() or not 1 <= len(w['page']) <= 3
                    or w['page'].startswith('0') or type(w['start']) is not int or w['start'] < 0
                    or type(w['length']) is not int or not 1 <= w['length'] <= 6000
                    or not isinstance(w['purpose'], str) or not 1 <= len(w['purpose'].strip()) <= 300):
                raise ToolError('invalid canonical page, window bounds or reading purpose')
        if plan['allow_deterministic_continuation'] is False:
            return plan  # Declining execution must not parse/read selected sources.
        from pdf_read_plan import normalize_windows
        # Different purposes remain separate semantic selections; never combine
        # their rationale or invent a new research objective. Only same-purpose
        # overlap can be replaced by the exact union of selected offsets.
        groups = {}
        for w in plan['windows']:
            groups.setdefault((w['paper_id'], w['purpose']), []).append(
                {k: w[k] for k in ('page', 'start', 'length')})
        normalized_windows = []
        total = 0
        for (pid, purpose), windows in groups.items():
            keys, report = normalize_windows(self._document(pid)['pages'], windows,
                maximum=MAX_WINDOWS, total_chars=MAX_TOTAL_CHARS, window_chars=6000, allow_empty=True)
            total += report['unique_chars']
            normalized_windows.extend({'paper_id': pid, 'page': page, 'start': start,
                                       'length': length, 'purpose': purpose} for page, start, length in keys)
        if total > MAX_TOTAL_CHARS:
            raise ToolError(f'selected windows exceed the 12000-character preparation bound: {total} actual characters; '
                            'choose narrower windows; no selected text was silently dropped')
        return {**plan, 'windows': normalized_windows}

    def _save(self, kind, payload):
        sha = digest(payload)
        # Existing provenance inference recognizes these opaque 128-bit handles.
        # Keep the full content digest in storage; do not widen the shared IR.
        prefix = {'plan': 'source', 'extraction': 'source', 'verification': 'dataset', 'packet': 'result'}[kind]
        handle = prefix + '-' + sha[:32]
        if handle in self.receipts and self.receipts[handle][2] != sha:
            raise ToolError('receipt handle collision')
        path = self.delivery / (kind + '-' + sha + '.json')
        save_private(path, payload)
        self.receipts[handle] = (kind, path, sha)
        return handle

    def _load(self, handle, kind):
        self._assert_current()
        if not isinstance(handle, str) or handle not in self.receipts:
            raise ToolError('unknown or other-session receipt')
        actual_kind, path, sha = self.receipts[handle]
        if actual_kind != kind or path.is_symlink() or not path.is_file() or path.stat().st_size > 200000:
            raise ToolError('receipt kind or artifact location is invalid')
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except ValueError:
            raise ToolError('receipt artifact is unreadable') from None
        if (digest(payload) != sha or payload.get('task_sha256') != digest(self.task)
                or payload.get('execution_version_sha256') != self.execution_version):
            raise ToolError('receipt artifact changed or has a stale version')
        return payload

    def _envelope(self, **values):
        return {'schema_version': 1, 'task_sha256': digest(self.task),
                'execution_version_sha256': self.execution_version, **values}

    def _grant(self, plan_id, completed_steps, receipt):
        if plan_id is None:
            return {}  # Legacy inline plans remain callable, never auto-authorize.
        self._load(plan_id, 'plan')  # Current service receipt, source and approval revalidation.
        return {'continuation_grant': {'schema_version': 1,
                'policy_sha256': digest(continuation_policy()),
                'task_input_version': self.initial_task, 'execution_version': self.execution_version,
                'plan_id': plan_id, 'completed_steps': completed_steps, 'receipt': receipt}}

    def register_reading_plan(self, plan: str) -> dict:
        """Freeze an explicitly approved reading plan into a short, versioned receipt; no automatic relevance judgment."""
        self._assert_current()
        value = self._plan(plan)
        if value['allow_deterministic_continuation'] is not True:
            return self._envelope(status='needs_review', reason='continuation_not_approved')
        plan_id = self._save('plan', self._envelope(kind='plan', plan=value))
        return self._envelope(status='plan_approved', plan_id=plan_id, plan_sha256=digest(value),
                              requested_plan_sha256=digest(value if plan.startswith('source-') else json.loads(plan)),
                              window_count=len(value['windows']), relevance_assessed=False,
                              normalization_policy='exact-selected-coverage-v2; same-purpose-only',
                              selected_coverage_preserved=True)

    def extract_evidence_windows(self, plan: str) -> dict:
        """Extract only the model-selected, explicitly approved reading plan; return a bounded source receipt."""
        self._assert_current()
        value = self._plan(plan)
        if value['allow_deterministic_continuation'] is not True:
            return self._envelope(status='needs_review', reason='continuation_not_approved',
                                  next_step='return to model; do not change false to true automatically')
        contexts = []
        for w in value['windows']:
            pinned = self.pin_pdf_context(w['paper_id'], w['page'], w['start'], w['length'])
            context = self.read_pinned_pdf_context(pinned['source_id'])
            contexts.append({'purpose': w['purpose'], 'source_id': pinned['source_id'], **context})
        self._assert_current()
        plan_id = plan if plan.startswith('source-') else None
        extraction = self._envelope(kind='extraction', plan=value, windows=contexts, plan_id=plan_id)
        extraction_id = self._save('extraction', extraction)
        result = self._envelope(status='extracted', extraction_id=extraction_id,
                                window_count=len(contexts), interpretation_performed=False,
                                **self._grant(plan_id, 1, extraction_id))
        if self.script_chain:
            verified = self.verify_evidence_windows(extraction_id)
            if verified['status'] == 'verified':
                result['script_packet'] = self.build_evidence_packet(verified['verification_id'])
            else:
                result['script_verification'] = verified
        return result

    def _replay(self, extraction):
        plan = self._plan(json.dumps(extraction['plan'], ensure_ascii=False))
        if plan['allow_deterministic_continuation'] is not True:
            raise ToolError('continuation permission missing')
        if len(extraction['windows']) != len(plan['windows']):
            raise ToolError('extraction coverage changed')
        for w, stored in zip(plan['windows'], extraction['windows']):
            pinned = self.pin_pdf_context(w['paper_id'], w['page'], w['start'], w['length'])
            current = {'purpose': w['purpose'], 'source_id': pinned['source_id'],
                       **self.read_pinned_pdf_context(pinned['source_id'])}
            if current != stored:
                raise ToolError('extracted window no longer matches its source')
        self._assert_current()

    def verify_evidence_windows(self, extraction_id: str) -> dict:
        """Replay exact source windows and check basic text availability; do not certify relevance or entailment."""
        extraction = self._load(extraction_id, 'extraction')
        self._replay(extraction)
        issues = [{'window_index': i, 'paper_id': w['paper_id'], 'page': w['page'],
                   'reason': 'low_text_or_empty_window_needs_inspection'}
                  for i, w in enumerate(extraction['windows'])
                  if w['status'] != 'text_available' or len(normalized(w['text'])) < 40]
        if issues:
            return self._envelope(status='needs_review', issues=issues,
                                  next_step='inspect PDF or choose new windows; OCR is not installed')
        verification = self._envelope(kind='verification', extraction_id=extraction_id,
                                      extraction_sha256=digest(extraction),
                                      check='exact_source_replay_and_basic_text_availability')
        verification_id = self._save('verification', verification)
        return self._envelope(status='verified', verification_id=verification_id,
                              window_count=len(extraction['windows']), claim_support_assessed=False,
                              **self._grant(extraction.get('plan_id'), 2, verification_id))

    def build_evidence_packet(self, verification_id: str) -> dict:
        """Assemble mechanically verified windows for the model; stop before scientific interpretation."""
        verification = self._load(verification_id, 'verification')
        extraction = self._load(verification['extraction_id'], 'extraction')
        if digest(extraction) != verification['extraction_sha256']:
            raise ToolError('verification no longer binds the extraction')
        self._replay(extraction)
        packet = self._envelope(kind='evidence_packet', question=self.task['question'],
                                plan=extraction['plan'], windows=extraction['windows'],
                                claim_support_assessed=False, research_quality='unreviewed',
                                coverage='selected windows only; no completeness, relevance, OCR or figure guarantee')
        self._assert_current()
        packet_id = self._save('packet', packet)
        _, path, sha = self.receipts[packet_id]
        return self._envelope(status='packet_ready', packet_id=packet_id, artifact=str(path),
                              artifact_sha256=sha, packet=packet,
                              **self._grant(extraction.get('plan_id'), 3, packet_id),
                              next_step='return to model for paper understanding and claim generation')

    def validate_packet(self, packet):
        """Offline delivery collection also rechecks current sources; no model loop."""
        self._assert_current()
        if (not isinstance(packet, dict) or packet.get('kind') != 'evidence_packet'
                or packet.get('execution_version_sha256') != self.execution_version
                or packet.get('task_sha256') != digest(self.task)
                or packet.get('question') != self.task['question']
                or packet.get('claim_support_assessed') is not False
                or packet.get('research_quality') != 'unreviewed'):
            raise ToolError('packet task, version or interpretation scope is invalid')
        self._replay(packet)
        if any(w['status'] != 'text_available' or len(normalized(w['text'])) < 40 for w in packet['windows']):
            raise ToolError('packet contains windows requiring inspection')


def make_server(scene):
    server = MCPServer('Bounded PDF evidence preparation')
    for fn in (scene.list_pdfs, scene.prepare_pdf, scene.search_pdf_text, scene.register_reading_plan,
               scene.extract_evidence_windows, scene.verify_evidence_windows, scene.build_evidence_packet):
        server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))(fn)
    return server


if __name__ == '__main__':
    os.environ.pop('SSS_PDF_SCRIPT_READ', None)  # Do not inherit the other scene's composition mode.
    task = json.loads(Path(os.environ['SSS_PDF_TASK_FILE']).read_text(encoding='utf-8'))
    make_server(EvidenceScene(Path(os.environ['SSS_PDF_ROOT']), Path(os.environ['SSS_PDF_CACHE']), task,
                delivery=Path(os.environ['SSS_PDF_DELIVERY']),
                cache_policy=os.environ.get('SSS_PDF_CACHE_POLICY', 'reuse'),
                script_chain=os.environ.get('SSS_EVIDENCE_SCRIPT_CHAIN') == '1')).run(transport='stdio')
