"""Offline diagnostic inputs; never fabricate Harness events or scientific approval."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import sys
from uuid import uuid4
from pdf_dependencies import private_file
from pdf_tools import ROOT, PdfScene, digest, save_private

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('phase_one_agent_support', HERE / 'agent-support.py')
support = importlib.util.module_from_spec(spec)
spec.loader.exec_module(support)


def gap_draft(evidence):
    """Remove exactly one already extracted method fact in a separately marked copy."""
    draft = copy.deepcopy(evidence['draft'])
    candidates = sorted((p['paper_id'], f['name']) for p in draft['papers'] for f in p['fields']
                        if f['name'] == 'method' and f['status'] == 'evidence' and f['citations'])
    if not candidates:
        raise ValueError('controlled gap requires an extracted method with actual citations')
    pid, name = candidates[0]
    field = next(f for p in draft['papers'] if p['paper_id'] == pid for f in p['fields'] if f['name'] == name)
    original = copy.deepcopy(field)
    field.update(status='not_extracted', statement='当前未提取到足够证据。', citations=[])
    return draft, {'claim_id': 'claim:' + pid + ':' + name, 'original_field': original,
                   'transformation': 'remove one extracted method and its citations; controlled missing-data diagnostic'}


def diagnostic_parent(parent_id):
    # All input and output paths pass existing private-file validation.
    directory = ROOT / '.local/literature-notes/agent-jobs' / parent_id
    parent = support.read(directory / 'job.json')
    if parent.get('id') != parent_id or parent.get('status') not in ('delivered', 'delivered_with_gaps'):
        raise ValueError('diagnostic parent requires a complete real delivery')
    evidence = support.read(directory / 'evidence.json')
    snapshot = support.read(directory / 'source-snapshot.json')
    support.validate(evidence, snapshot)
    draft, change = gap_draft(evidence)
    scene = PdfScene(Path(snapshot['task']['sources']['root']), ROOT / '.local/literature-notes/pdf-cache', snapshot['task'])
    for citation in evidence['citation_checks']:
        pin = scene.pin_pdf_context(citation['paper_id'], str(citation['page']), citation['start'], citation['end'] - citation['start'])
        if pin['source_id'] != citation['source_id'] or pin['version_sha256'] != citation['version_sha256']:
            raise ValueError('diagnostic source replay failed')
        scene.read_pinned_pdf_context(pin['source_id'])
    modified = scene.preview_research_notes(draft)
    identifier = str(uuid4())
    output = directory.parent / identifier
    output.mkdir(mode=0o700)
    save_private(output / 'diagnostic-evidence.json', modified)
    metadata = support.package(output, output / 'diagnostic-evidence.json', directory / 'source-snapshot.json')
    # Previous source-bound windows are navigation data, not an answer key.
    origin = output / 'repair-input-1'
    save_private(origin / 'evidence.json', evidence)
    save_private(origin / 'pdf-input-snapshot.json', snapshot)
    save_private(origin / 'repair-targets.json', {'input_sha256': digest(evidence), 'claim_ids': [change['claim_id']]})
    provenance = {'kind': 'controlled_missing_data_diagnostic', 'original_job': parent_id,
                  'original_evidence_sha256': digest(evidence), 'derived_evidence_sha256': digest(modified),
                  'target_claim_id': change['claim_id'], 'synthetic_native_events': False,
                  'model_calls_during_preparation': 0, 'not_a_natural_failure': True}
    save_private(output / 'diagnostic-provenance.json', provenance)
    save_private(output / 'diagnostic-reference.json', {**change, 'gold_visible_to_model': False,
                 'scope': 'known source-bound method; not an expert truth reference'})
    job = {'schema_version': 1, 'id': identifier, 'status': 'delivered_with_gaps',
           'options': parent['options'], 'frame': parent['frame'], 'parent_job': parent_id,
           'source_run': parent['source_run'], 'stages': [], 'model_requests': 0,
           'accounted_usd': 0, 'cost_complete': True, 'verified_skips': 0,
           'quality': 'controlled_diagnostic_source_validated_unverified',
           'human_review_required': False, 'user_pdf_writes': False,
           'diagnostic_provenance': provenance, **metadata}
    save_private(output / 'job.json', job)
    return {'diagnostic_parent_job': identifier, 'target_claim_id': change['claim_id'], 'provenance': provenance}


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(diagnostic_parent(request['parent_job']), ensure_ascii=False))
