"""Acceptance cannot mistake verdict changes, corrupted receipts or blanket gaps for scientific quality."""
import copy
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scenarios/literature-notes'))
from pdf_tools import digest
from pdf_acceptance import score_calibration, check_revocation, freeze_calibration


def calibration():
    originals = [{'name': 'method', 'status': 'evidence', 'statement': 'Unsupported expansion.',
                  'citations': [{'source_id': 's', 'quote_id': 'q'}]},
                 {'name': 'findings', 'status': 'evidence', 'statement': 'A supported control.',
                  'citations': [{'source_id': 's', 'quote_id': 'q'}]}]
    manifest = {'input_sha256': 'input', 'scope': 'known-error calibration', 'cases': [
        {'paper_id': 'p', 'field': f['name'], 'original': f, 'expected_issue': i == 0}
        for i, f in enumerate(originals)]}
    revised = {'original_evidence_sha256': 'input', 'draft': {'papers': [{'paper_id': 'p', 'fields': copy.deepcopy(originals)}]}}
    audit = {'input_sha256': 'input', 'revised_evidence_sha256': digest(revised), 'decisions': [
        {'paper_id': 'p', 'name': f['name'], 'original_statement': f['statement'], 'statement': f['statement'],
         'citations': copy.deepcopy(f['citations']), 'verdict': 'revised' if i == 0 else 'supported'}
        for i, f in enumerate(originals)]}
    return manifest, audit, revised


def test_verdict_change_is_not_an_entailment_pass():
    manifest, audit, revised = calibration()
    report = score_calibration(manifest, audit, revised)
    assert report['issues_flagged_by_verdict'] == 1 and report['controls_preserved'] == 1
    assert report['quality_passed'] is False
    adjudication = {'calibration_sha256': digest(manifest), 'review_sha256': digest(audit),
                    'revised_evidence_sha256': digest(revised), 'synthesis_supported': True,
                    'synthesis_reason': 'Bounded hypothesis only.', 'decisions': [
                        {'paper_id': 'p', 'field': f, 'supported_after_review': f != 'method',
                         'original_issue_addressed': f != 'method', 'reason': 'Independent comparison.'}
                        for f in ('method', 'findings')]}
    report = score_calibration(manifest, audit, revised, adjudication)
    assert report['unsupported_after_review'] == 1 and not report['quality_passed']
    for d in adjudication['decisions']:
        d.update(supported_after_review=True, original_issue_addressed=True)
    adjudication['synthesis_supported'] = False
    assert not score_calibration(manifest, audit, revised, adjudication)['quality_passed']
    adjudication['synthesis_supported'] = True
    assert score_calibration(manifest, audit, revised, adjudication)['quality_passed']


def test_blanket_gaps_do_not_pass_quality_or_preserve_controls():
    manifest, audit, revised = calibration()
    for d, f in zip(audit['decisions'], revised['draft']['papers'][0]['fields']):
        d['verdict'] = f['status'] = 'not_extracted'
        d['citations'] = f['citations'] = []
    audit['revised_evidence_sha256'] = digest(revised)
    report = score_calibration(manifest, audit, revised)
    assert report['delivered_gap_count'] == 2 and report['controls_preserved'] == 0
    assert not report['quality_passed']


def test_adjudication_must_bind_exact_output_and_cover_all_cases():
    manifest, audit, revised = calibration()
    bad = {'calibration_sha256': digest(manifest), 'review_sha256': digest(audit),
           'revised_evidence_sha256': 'wrong', 'decisions': []}
    with pytest.raises(ValueError, match='different artifacts'):
        score_calibration(manifest, audit, revised, bad)
    bad['revised_evidence_sha256'] = digest(revised)
    with pytest.raises(ValueError, match='all cases'):
        score_calibration(manifest, audit, revised, bad)


def test_duplicate_or_modified_supported_decisions_are_rejected():
    manifest, audit, revised = calibration()
    audit['decisions'].append(copy.deepcopy(audit['decisions'][0]))
    with pytest.raises(ValueError, match='exactly once'):
        score_calibration(manifest, audit, revised)
    audit['decisions'].pop()
    audit['decisions'][1]['statement'] = revised['draft']['papers'][0]['fields'][1]['statement'] = 'Changed.'
    audit['revised_evidence_sha256'] = digest(revised)
    with pytest.raises(ValueError, match='changed original'):
        score_calibration(manifest, audit, revised)


def test_calibration_reference_must_bind_original_and_cover_cases(tmp_path, monkeypatch):
    import json
    import pdf_acceptance
    monkeypatch.setattr(pdf_acceptance, 'private_file', lambda p: Path(p))
    evidence = {'draft': {'papers': [{'paper_id': 'p', 'fields': [{'name': 'method', 'statement': 'Original.'}]}]}}
    (tmp_path / 'evidence.json').write_text(json.dumps(evidence))
    ref = tmp_path / 'reference.json'
    reference = {'original_evidence_sha256': 'wrong', 'decisions': []}
    ref.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match='not bound'):
        freeze_calibration(tmp_path, ref)
    reference['original_evidence_sha256'] = digest(evidence)
    ref.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match='every original field'):
        freeze_calibration(tmp_path, ref)
    reference['decisions'] = [{'paper_id': 'p', 'field': 'method', 'original_statement': 'Original.',
                                'support_issue': 'Missing condition.'}]
    ref.write_text(json.dumps(reference))
    assert freeze_calibration(tmp_path, ref)['cases'][0]['expected_issue'] is True


def test_revocation_requires_exact_retention_not_only_counts(monkeypatch):
    import pdf_acceptance
    old = {'name': 'method', 'status': 'evidence', 'statement': 'Retained.', 'citations': []}
    changed = {'name': 'findings', 'status': 'needs_review', 'statement': 'Needs evidence.', 'citations': []}
    graph = {'task': {'question': 'q'}, 'fields': {'claim:p:method': {'paper_id': 'p', 'field': old, 'citation_checks': []},
                                                   'claim:p:findings': {'paper_id': 'p', 'field': changed}}}
    monkeypatch.setattr(pdf_acceptance, 'validate_envelope', lambda e: graph)
    envelope = {'graph_sha256': 'graph'}
    plan = {'invalidated_claim_ids': ['claim:p:findings'], 'retained_claim_ids': ['claim:p:method'],
            'synthesis_requires_review': True, 'plan_sha256': 'plan'}
    payload = {'task_sha256': digest(graph['task']), 'citation_checks': [],
               'draft': {'papers': [{'paper_id': 'p', 'fields': [copy.deepcopy(old), changed]}]},
               'incremental_audit': {'graph_sha256': 'graph', 'plan_sha256': 'plan', 'task_sha256': digest(graph['task']),
                   'retained_claim_ids': ['claim:p:method'], 'reviewed_field_count': 1,
                   'decisions': [{'paper_id': 'p', 'name': 'findings'}],
                   'update_quality': 'model_draft_pending_independent_support_review'}}
    revoked = {'revoked_claim_ids': ['claim:p:findings']}
    assert check_revocation(envelope, revoked, plan, payload)['retained_fields'] == 1
    payload['draft']['papers'][0]['fields'][0]['statement'] = 'Illegally rewritten.'
    with pytest.raises(ValueError, match='retained field'):
        check_revocation(envelope, revoked, plan, payload)
