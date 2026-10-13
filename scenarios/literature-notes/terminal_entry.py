"""Frozen claim-repair terminal frame; no model or user-file writes."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from pdf_tools import ROOT, digest
from pdf_dependencies import private_file
from pdf_repair_tools import POLICY

TOOL = 'mcp__literature_pdf_repair__submit_claim_repair'
VERSION_PATHS = ['scenarios/literature-notes/' + n for n in
    ['pdf_tools.py', 'pdf_layout.py', 'pdf_read_plan.py', 'pdf_review_tools.py', 'pdf_repair_tools.py', 'claim_coverage.py', 'pdf_dependencies.py',
     'pdf-repair-task.md', 'repair-pdf.py', 'terminal_entry.py']]
VERSION_PATHS += ['src/motif_core/terminal_receipt_policy.ts', 'src/adapters/dsh_entry_motif.ts', 'scripts/run-scenario.py']


def version_files():
    return [{'path': p, 'sha256': hashlib.sha256((ROOT / p).read_bytes()).hexdigest()} for p in sorted(VERSION_PATHS)]


def execution_version():
    return digest(version_files())


def entry_task(scene, task_id):
    if scene.synthesis_only:
        raise ValueError('synthesis-only terminal frontier has not been certified')
    return {'schema_version': 1, 'task_id': task_id, 'session_id': 'terminal-' + uuid4().hex,
        'input_version': scene.input_digest, 'task_sha256': digest(scene.task), 'request_version': scene.request_digest,
        'policy_sha256': digest({**POLICY, 'max_statement_characters': scene.statement_limit,
                               'support_anchor_required': scene.statement_limit == 80}),
        'target_ids': scene.targets, 'target_ids_sha256': digest(scene.targets), 'pdf_inventory': scene.task['sources'],
        'artifact_root': str(scene.output), 'execution_version_sha256': execution_version(), 'version_files': version_files(),
        'input_files': [{'path': str(private_file(scene.run / n)),
                         'sha256': hashlib.sha256((scene.run / n).read_bytes()).hexdigest()}
                        for n in ['evidence.json', 'pdf-input-snapshot.json', 'repair-targets.json']]}


def private_policy(path):
    p = json.loads(private_file(path).read_text())
    if (p.get('format') != 'sss-terminal-receipt-v1' or p.get('execution_version_sha256') != execution_version()
            or p.get('policy_digest') != digest({k: v for k, v in p.items() if k != 'policy_digest'})):
        raise ValueError('terminal policy or producer/executor version changed; recertify')
    return p
