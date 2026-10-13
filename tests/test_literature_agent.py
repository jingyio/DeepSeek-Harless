"""Local app protocol checks; synthetic statements do not certify paper quality."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest
from test_literature_pdf import corpus, POPPLER, task, draft, make_pdf, module
from pdf_tools import PdfScene, digest, save_private
from pdf_incremental_tools import IncrementalScene

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = module(ROOT / 'scenarios/literature-notes/agent-support.py', 'agent_support_test')
PHASE_ONE = module(ROOT / 'scenarios/literature-notes/phase_one_tasks.py', 'phase_one_tasks_test')


def test_controlled_gap_changes_only_one_method_and_preserves_original():
    evidence = {'draft': {'papers': [
        {'paper_id': pid, 'fields': [{'name': name, 'status': 'evidence', 'statement': pid + name,
                                    'citations': [{'source_id': pid, 'quote_id': 'q0'}]}
                                   for name in ('method', 'findings')]}
        for pid in ('z', 'a')], 'synthesis': 'unchanged hypothesis'}}
    original = copy.deepcopy(evidence)
    value, change = PHASE_ONE.gap_draft(evidence)
    assert evidence == original and change['claim_id'] == 'claim:a:method'
    assert value['synthesis'] == original['draft']['synthesis']
    for p, old in zip(value['papers'], original['draft']['papers']):
        for f, previous in zip(p['fields'], old['fields']):
            if p['paper_id'] == 'a' and f['name'] == 'method':
                assert f['status'] == 'not_extracted' and f['citations'] == []
            else:
                assert f == previous


def test_controlled_gap_requires_real_extracted_citations():
    with pytest.raises(ValueError, match='extracted method'):
        PHASE_ONE.gap_draft({'draft': {'papers': [{'paper_id': 'p', 'fields': [
            {'name': 'method', 'status': 'not_extracted', 'citations': []}]}]}})


@pytest.fixture
def candidate(corpus):
    directory, cache = corpus
    scene = PdfScene(directory, cache, task(directory))
    value = draft(scene)
    for paper in value['papers']:
        for field in paper['fields']:
            field['citations'] = [{'source_id': field['citations'][0]['source_id'], 'quote_id': 'q0'}]
    evidence = scene.preview_research_notes(value)
    base = directory.parent
    save_private(base / 'evidence.json', evidence)
    save_private(base / 'snapshot.json', {'task': scene.task})
    job = ROOT / '.local/literature-notes/agent-jobs' / str(uuid4())
    job.mkdir(parents=True)
    result = SUPPORT.package(job, base / 'evidence.json', base / 'snapshot.json')
    cards = json.loads((job / 'review-cards.json').read_text())
    yield directory, job, result, cards
    shutil.rmtree(job)


@POPPLER
def test_controlled_gap_parent_replays_sources_without_editing_native_history(candidate):
    directory, job, result, _ = candidate
    originals = {name: (job / name).read_bytes() for name in ('evidence.json', 'source-snapshot.json')}
    save_private(job / 'job.json', {'id': job.name, 'status': 'delivered', 'options': {},
        'frame': SUPPORT.capture(directory, 'synthetic fixture'), 'source_run': 'synthetic-fixture-no-native-run', **result})
    created = PHASE_ONE.diagnostic_parent(job.name)
    derived = job.parent / created['diagnostic_parent_job']
    resumed = job.parent / str(uuid4())
    resumed.mkdir()
    try:
        for name, original in originals.items():
            assert (job / name).read_bytes() == original
        value = SUPPORT.read(derived / 'evidence.json')
        snapshot = SUPPORT.read(derived / 'source-snapshot.json')
        assert SUPPORT.validate(value, snapshot)['gaps'] == value['gaps']
        assert len(value['gaps']) == 1
        assert not (derived / 'agent-events.jsonl').exists()
        assert created['provenance']['not_a_natural_failure']
        assert not created['provenance']['synthetic_native_events']
        assert SUPPORT.read(derived / 'diagnostic-reference.json')['gold_visible_to_model'] is False
        SUPPORT.package(resumed, derived / 'evidence.json', derived / 'source-snapshot.json')
        plan = SUPPORT.repair_plan(resumed, 1, 'unresolved_claims_only', parent_job=derived)
        assert plan['claim_ids'] == [created['target_claim_id']]
    finally:
        shutil.rmtree(resumed)
        shutil.rmtree(derived)


@POPPLER
@pytest.mark.parametrize('mutation', ['digest', 'target', 'duplicate'])
def test_source_feedback_rejects_unbound_diagnostics_before_key_load(candidate, mutation, monkeypatch):
    _, job, _, _ = candidate
    plan = SUPPORT.repair_plan(job, 1, 'support_audit')
    feedback = {'schema_version': 1, 'origin': 'independent_source_check',
        'input_sha256': plan['input_sha256'], 'issues': [{'claim_id': plan['claim_ids'][0], 'issue': 'Synthetic check.'}]}
    if mutation == 'digest': feedback['input_sha256'] = '0' * 64
    if mutation == 'target': feedback['issues'][0]['claim_id'] = 'out-of-scope'
    if mutation == 'duplicate': feedback['issues'].append(dict(feedback['issues'][0]))
    path = job / 'feedback-fixture.json'
    save_private(path, feedback)
    entry = module(ROOT / 'scenarios/literature-notes/repair-pdf.py', 'repair_feedback_test_' + mutation)
    monkeypatch.setattr(entry, 'module', lambda *args: pytest.fail('key/runtime loader reached before feedback validation'))
    with pytest.raises(ValueError, match='source feedback must bind'):
        entry.main(['--run', plan['input_directory'], '--source-feedback', str(path), '--call-model'])


@POPPLER
@pytest.mark.parametrize('mutation', ['edit', 'add', 'remove', 'question', 'workflow'])
def test_automatic_source_bound_cache_updates_only_dependent_fields_without_human(candidate, mutation, monkeypatch):
    directory, job, _, _ = candidate
    result = SUPPORT.index_automatic(job)
    assert result['index_model_requests'] == 0 and not result['scientific_truth_certified']
    envelope = SUPPORT.read(job / 'automatic-dependencies.json')
    graph = envelope['graph']
    assert graph['reuse_policy'] == 'automatic_source_bound_unverified'
    assert all('reviewed' not in n for n in graph['nodes'] if n['kind'] == 'claim')
    baseline = IncrementalScene(job / 'automatic-dependencies.json', directory, task(directory), job / 'baseline')
    assert len(baseline.read_update_plan()['retained_claim_ids']) == 10
    if mutation == 'edit': make_pdf(directory / 'B.pdf', ['Changed experiment with fresh evidence.'])
    if mutation == 'add': make_pdf(directory / 'new.pdf', ['A new paper with different evidence.'])
    if mutation == 'remove': (directory / 'B.pdf').unlink()
    current = task(directory)
    if mutation == 'question': current['question'] = 'Another research question'
    if mutation == 'workflow': monkeypatch.setattr('pdf_dependencies.automatic_workflow_version', lambda: '0' * 64)
    changed = IncrementalScene(job / 'automatic-dependencies.json', directory, current, job / 'changed')
    plan = changed.read_update_plan()
    assert plan['synthesis_requires_review'] and not plan['scientific_truth_certified']
    assert len(plan['retained_claim_ids']) == {'edit': 5, 'add': 10, 'remove': 5, 'question': 0, 'workflow': 0}[mutation]
    assert sum(len(w['fields_to_review']) for w in plan['work']) == {'edit': 5, 'add': 5, 'remove': 0, 'question': 10, 'workflow': 10}[mutation]


@POPPLER
def test_human_approval_compiles_current_source_and_incremental_dependencies(candidate):
    directory, job, result, cards = candidate
    assert result['research_quality'] == 'automatic_source_validated_unverified'
    assert result['human_review_required'] is False
    assert cards['delivery_policy'] == 'automatic_v1'
    assert '待人工核对' not in (job / 'research-notes.md').read_text()
    assert not cards['human_review_completed']
    ids = [r['id'] for r in cards['rows']]
    for ids_bad, synth, sha in [(ids[:-1], True, result['evidence_sha256']),
                               (ids, False, result['evidence_sha256']), (ids, True, 'a' * 64)]:
        with pytest.raises(ValueError): SUPPORT.approve(job, sha, ids_bad, synth)
    approval = SUPPORT.approve(job, result['evidence_sha256'], ids, True)
    assert approval['reviewer_kind'] == 'Human' and not approval['expert_blind_review_completed']
    assert json.loads((job / 'review-cards.json').read_text())['human_review_completed']
    baseline = IncrementalScene(job / 'dependencies.json', directory, task(directory), job / 'unchanged')
    assert len(baseline.read_update_plan()['retained_claim_ids']) == 10
    make_pdf(directory / 'B.pdf', ['A changed method and evaluation requiring new evidence.'])
    changed = IncrementalScene(job / 'dependencies.json', directory, task(directory), job / 'changed')
    plan = changed.read_update_plan()
    assert len(plan['retained_claim_ids']) == len(plan['invalidated_claim_ids']) == 5
    assert plan['synthesis_requires_review']


@POPPLER
@pytest.mark.parametrize('mutation', ['duplicate_card', 'statement', 'number', 'source'])
def test_approval_rejects_stale_or_tampered_sources(candidate, mutation):
    directory, job, result, cards = candidate
    ids = [r['id'] for r in cards['rows']]
    if mutation == 'duplicate_card': cards['rows'][-1] = copy.deepcopy(cards['rows'][0])
    elif mutation == 'statement': cards['rows'][0]['statement'] = 'Invented claim.'
    elif mutation == 'number': cards['rows'][0]['missing_literal_numbers'] = ['999']
    else: make_pdf(directory / 'B.pdf', ['Changed source after review.'])
    save_private(job / 'review-cards.json', cards)
    with pytest.raises(ValueError): SUPPORT.approve(job, result['evidence_sha256'], ids, True)
    assert not (job / 'dependencies.json').exists()


@POPPLER
def test_edit_changes_digest_retains_history_and_requires_reapproval(candidate):
    _, job, result, cards = candidate
    statements = {r['id']: 'A narrower synthetic protocol statement.' for r in cards['rows']}
    save_private(job / 'model-review.json', {'old_review': True})
    edited = SUPPORT.revise(job, result['evidence_sha256'], statements, 'A revised hypothesis.')
    assert edited['evidence_sha256'] != result['evidence_sha256']
    assert (job / ('candidate-before-edit-' + result['evidence_sha256'] + '.json')).exists()
    assert not (job / 'model-review.json').exists()
    assert not json.loads((job / 'review-cards.json').read_text())['human_review_completed']
    with pytest.raises(ValueError):
        SUPPORT.approve(job, result['evidence_sha256'], list(statements), True)


def test_typescript_application_guards():
    node = shutil.which('node')
    if not node: pytest.skip('Node required')
    version = subprocess.check_output([node, '-p', 'process.versions.node'], text=True).strip()
    major, minor = map(int, version.split('.')[:2])
    if (major, minor) < (22, 18): pytest.skip('Application requires Node >=22.18 native TypeScript')
    result = subprocess.run([node, '--test', 'tests/test_literature_agent.mjs'], cwd=ROOT,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


@POPPLER
def test_automatic_package_delivers_gaps_without_forging_review(candidate):
    _, job, _, cards = candidate
    evidence = json.loads((job / 'evidence.json').read_text())
    field = evidence['draft']['papers'][0]['fields'][0]
    field.update(status='not_extracted', statement='Not enough evidence.', citations=[])
    snapshot = json.loads((job / 'source-snapshot.json').read_text())
    scene = PdfScene(Path(snapshot['task']['sources']['root']), job / 'gap-cache', snapshot['task'])
    for c in evidence['citation_checks']:
        pin = scene.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
        scene.read_pinned_pdf_context(pin['source_id'])
    evidence = scene.preview_research_notes(evidence['draft'])
    save_private(job / 'gap-evidence.json', evidence)
    result = SUPPORT.package(job, job / 'gap-evidence.json', job / 'source-snapshot.json')
    assert result['gap_count'] > 0 and result['human_review_required'] is False
    assert not (job / 'dependencies.json').exists()
    assert not json.loads((job / 'review-cards.json').read_text())['human_review_completed']


@POPPLER
def test_automatic_review_binding_is_still_required(candidate):
    _, job, result, cards = candidate
    audit = {'revised_evidence_sha256': 'a' * 64, 'decisions': []}
    save_private(job / 'review-fixture.json', audit)
    with pytest.raises(ValueError, match='候选稿不一致'):
        SUPPORT.package(job, job / 'evidence.json', job / 'source-snapshot.json',
                        review_path=job / 'review-fixture.json')
    audit['revised_evidence_sha256'] = result['evidence_sha256']
    save_private(job / 'review-fixture.json', audit)
    delivered = SUPPORT.package(job, job / 'evidence.json', job / 'source-snapshot.json',
                                review_path=job / 'review-fixture.json')
    assert delivered['research_quality'] == 'automatic_model_reviewed_unverified'
    assert delivered['human_review_required'] is False


@POPPLER
def test_repair_plan_audits_all_once_then_selects_only_unresolved_numeric_claim(candidate):
    _, job, _, cards = candidate
    first = SUPPORT.repair_plan(job, 1)
    assert len(first['claim_ids']) == 10 and first['scope'] == 'all_claim_audit'
    assert not SUPPORT.repair_plan(job, 2)['claim_ids']
    statements = {r['id']: r['statement'] for r in cards['rows']}
    statements[cards['rows'][0]['id']] = 'Accuracy 99.9%.'
    SUPPORT.revise(job, cards['evidence_sha256'], statements, cards['synthesis'])
    second = SUPPORT.repair_plan(job, 2)
    assert second['claim_ids'] == [cards['rows'][0]['id']]
    assert second['scope'] == 'unresolved_claims_only'
    frozen = json.loads((Path(second['input_directory']) / 'repair-targets.json').read_text())
    assert frozen['input_sha256'] == second['input_sha256']


@POPPLER
def test_resume_plan_selects_only_gaps_and_keeps_source_bound_original_navigation(candidate):
    _, parent, _, cards = candidate
    original = SUPPORT.repair_plan(parent, 1)
    evidence = SUPPORT.read(parent / 'evidence.json')
    cid = cards['rows'][0]['id']
    evidence['draft']['papers'][0]['fields'][0].update(status='not_extracted',
        statement='当前未提取到足够证据。', citations=[])
    snapshot = SUPPORT.read(parent / 'source-snapshot.json')
    scene = PdfScene(Path(snapshot['task']['sources']['root']), ROOT / '.local/literature-notes/pdf-cache', snapshot['task'])
    for c in SUPPORT.read(parent / 'evidence.json')['citation_checks']:
        pin = scene.pin_pdf_context(c['paper_id'], str(c['page']), c['start'], c['end'] - c['start'])
        scene.read_pinned_pdf_context(pin['source_id'])
    evidence = scene.preview_research_notes(evidence['draft'])
    save_private(parent / 'evidence.json', evidence)
    audit = {'input_sha256': original['input_sha256'], 'repair_request_sha256': digest(SUPPORT.read(Path(original['input_directory']) / 'repair-targets.json')),
        'revised_evidence_sha256': digest(evidence), 'rejected_proposals': {cid: {'proposal': {'claim_id': cid, 'statement': 'Untrusted hypothesis'}, 'validation_error': 'unread citation'}}}
    save_private(parent / 'model-review.json', audit)
    save_private(parent / 'job.json', {'parent_job': None})
    child = parent.parent / str(uuid4())
    child.mkdir()
    try:
        SUPPORT.package(child, parent / 'evidence.json', parent / 'source-snapshot.json')
        plan = SUPPORT.repair_plan(child, 1, scope='unresolved_claims_only', parent_job=parent)
        assert plan['claim_ids'] == [cid] and plan['review_mode'] == 'compare_existing_claim'
        assert plan['prior_proposals'][cid]['validation_error'] == 'unread citation'
        assert SUPPORT.read(Path(plan['history_input_directory']) / 'evidence.json')['draft']['papers'][0]['fields'][0]['citations']
        audit['revised_evidence_sha256'] = 'a' * 64
        save_private(parent / 'model-review.json', audit)
        with pytest.raises(ValueError, match='当前稿不一致'):
            SUPPORT.repair_plan(child, 1, scope='unresolved_claims_only', parent_job=parent)
    finally:
        shutil.rmtree(child)

@POPPLER
def test_support_audit_checks_existing_facts_without_blind_reextract_or_widening(candidate):
    from pdf_repair_tools import RepairScene
    _, job, _, cards = candidate
    plan = SUPPORT.repair_plan(job, 1, scope='support_audit', target_claim_ids=[cards['rows'][0]['id']])
    assert plan['scope'] == 'claim_support_audit' and plan['review_mode'] == 'compare_existing_claim'
    assert plan['claim_ids'] == [cards['rows'][0]['id']]
    scene = RepairScene(Path(plan['input_directory']), job / 'support-output')
    packet = scene.read_claim_repair_packet(plan['claim_ids'][0])
    assert packet['field']['statement'] == cards['rows'][0]['statement']
    assert packet['policy']['max_statement_characters'] == 80
    value = {'claim_id': plan['claim_ids'][0], 'verdict': 'revised', 'reason': 'Protocol check.',
             'statement': '字' * 81, 'citations': packet['field']['citations']}
    result = scene.submit_claim_repair([value], 'Protocol hypothesis.')
    assert '1–80' in result['issues'][0]['error'] and not scene.completed

@POPPLER
def test_support_anchor_cannot_borrow_unselected_context_and_is_not_entailment(candidate):
    from pdf_repair_tools import RepairScene
    _, job, _, cards = candidate
    cid = cards['rows'][0]['id']; plan = SUPPORT.repair_plan(job, 1, scope='support_audit', target_claim_ids=[cid])
    scene = RepairScene(Path(plan['input_directory']), job / 'anchor-output')
    packet = scene.read_claim_repair_packet(cid)
    bad = {'claim_id': cid, 'verdict': 'supported', 'reason': 'Protocol fixture.',
           'support_anchor': 'This sentence was not selected as source evidence.'}
    response = scene.submit_claim_repair([bad], 'Protocol hypothesis.')
    assert 'outside FINAL selected' in response['issues'][0]['error']
    assert not scene.completed
    quote = packet['quotes'][0]['quote']
    # A real prefix inside the selected quote can still cut a sentence short.
    bad['support_anchor'] = quote.rstrip().rstrip('.')
    response = scene.submit_claim_repair([bad], 'Protocol hypothesis.')
    assert 'ends mid-sentence' in response['issues'][0]['error']
    bad['support_anchor'] = quote
    receipt = scene.submit_claim_repair([bad], 'Protocol hypothesis.')
    assert 'artifact' in receipt
    value = json.loads(Path(receipt['artifact']).read_text())
    # A valid literal anchor still cannot certify this deliberately generic fixture statement.
    assert value['research_quality'] == 'model_repaired_unverified'
