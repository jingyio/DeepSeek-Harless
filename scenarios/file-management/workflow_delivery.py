"""Serialize task-result structure from guarded MCP state, without acceptance answers."""
from __future__ import annotations
import copy
import json
from collections import Counter
from common import digest, save

VERSION = 'sss-current-workflow-report-v1'


def report_facts():
    return {'version': VERSION, 'file_ids_owner': 'current_mcp_state',
            'file_ids_argument': 'legacy nonauthoritative hint; pass []',
            'model_fields': ['summary', 'gaps'], 'summary_max_characters': 2000,
            'report_kind': 'task_result', 'search_receipt_id': 'omit',
            'quality_verified_by': 'independent acceptance; serialization is not acceptance'}


def current_ids(scene):
    scene.active()
    return sorted(scene.files())


def finish_report(scene, receipt, supplied_ids, version_fields):
    """Bind actual identities, snapshot and existing receipts; never invent effects."""
    scene.active()
    body = json.loads((scene.output / 'report.json').read_text())
    ids = current_ids(scene)
    counts = Counter(supplied_ids)
    wanted = set(ids)
    # Raw hints remain in the native trace. Digests/counts keep the artifact compact.
    body.update(version_fields)
    body['file_ids'] = ids
    body['final_snapshot'] = copy.deepcopy(scene.expected)
    body['receipts'] = copy.deepcopy(list(scene.receipts.values()))
    body['structural_provenance'] = {
        'version': VERSION, 'generator': 'current_mcp_state',
        'input_sha256': scene.input_digest,
        'snapshot_sha256': digest(body['final_snapshot']),
        'file_ids_sha256': digest(ids), 'file_count': len(ids),
        'receipts_sha256': digest(body['receipts']),
        'model_fields': ['summary', 'gaps'],
        'legacy_hint': {'sha256': digest(supplied_ids), 'count': len(supplied_ids),
                        'missing_count': len(wanted - set(counts)),
                        'unknown_count': len(set(counts) - wanted),
                        'duplicate_count': sum(n - 1 for n in counts.values())}}
    scene.active()
    save(scene.output / 'report.json', body)
    return {**receipt, 'artifact_sha256': digest(body)}
