"""Incremental evidence guards; synthetic fixtures never certify scientific quality."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import corpus, POPPLER, task, draft, make_pdf, module

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'scenarios/literature-notes'
sys.path.insert(0, str(HERE))
from pdf_tools import PdfScene, digest, save_private, FIELDS
from pdf_dependencies import compile_graph, evaluate, inputs
from pdf_incremental_tools import IncrementalScene
from bibliography_tools import preview_bibliography
RUN = module(HERE / 'run-incremental.py', 'incremental_test_entry')


@pytest.fixture
def dependency_fixture(corpus):
    directory, cache = corpus
    source = PdfScene(directory, cache, task(directory))
    value = draft(source)
    for p in value['papers']:
        for f in p['fields']:
            f['citations'] = [{'source_id': f['citations'][0]['source_id'], 'quote_id': 'q0'}]
    evidence = source.preview_research_notes(value)
    evidence.update(research_quality='codex_source_checked_expert_blind_review_pending', reviewer_kind='Codex')
    base = directory.parent / 'baseline'; base.mkdir()
    decisions = [{'paper_id': p['paper_id'], 'field': f['name'], 'source_checked_statement': f['statement'],
                  'semantic_verdict_by': 'Codex',
                  'source_locators': [{'physical_page': c['page'], 'window_start': c['start'], 'quote_id': c['quote_id']}
                                     for c in evidence['citation_checks'] if c['paper_id'] == p['paper_id'] and c['field'] == f['name']]}
                 for p in value['papers'] for f in p['fields']]
    save_private(base / 'evidence.json', evidence)
    save_private(base / 'audit.json', {'source_checked_by': 'Codex',
                 'source_checked_evidence_sha256': digest(evidence), 'decisions': decisions,
                 'scope': 'synthetic protocol fixture; no scientific quality claim'})
    save_private(base / 'snapshot.json', {'task': source.task})
    envelope = compile_graph(base / 'evidence.json', base / 'audit.json', base / 'snapshot.json')
    save_private(base / 'dependencies.json', envelope)
    return directory, base, envelope


def scene(fixture, *, revoked=None):
    directory, base, _ = fixture
    return IncrementalScene(base / 'dependencies.json', directory, task(directory),
                            base / 'output', revoked_path=revoked)


def update_for(s):
    plan = s.read_update_plan(); papers = []
    for w in plan['work']:
        pin = s.pin_pdf_context(w['paper_id'], '1')
        context = s.read_pinned_pdf_context(pin['source_id'])
        papers.append({'paper_id': w['paper_id'], 'fields': [
            {'name': name, 'verdict': 'revised', 'reason': 'Synthetic protocol review only.',
             'statement': 'Protocol fixture update.', 'citations': [{'source_id': pin['source_id'],
                         'quote_id': context['quote_spans'][0]['quote_id']}]} for name in w['fields_to_review']]})
    return {'papers': papers, 'synthesis_hypothesis': 'A test hypothesis, not scientific evidence.'
            if plan['synthesis_requires_review'] else ''}


@POPPLER
def test_unchanged_reuses_source_checked_fields_without_certifying_truth(dependency_fixture):
    s = scene(dependency_fixture); plan = s.read_update_plan()
    assert len(plan['retained_claim_ids']) == 10 and not plan['work']
    receipt = s.publish({'papers': [], 'synthesis_hypothesis': ''}, automatic=True)
    payload = json.loads(Path(receipt['artifact']).read_text())
    assert payload['draft']['synthesis'] == s.graph['synthesis']
    assert receipt['reviewed_field_count'] == 0 and receipt['retained_field_count'] == 10
    assert not payload['incremental_audit']['scientific_truth_certified']
    assert payload['incremental_audit']['verified_motif_model_requests_skipped'] == 0


@POPPLER
def test_one_changed_pdf_invalidates_only_its_claims_and_synthesis(dependency_fixture):
    directory, base, envelope = dependency_fixture
    original = (base / 'evidence.json').read_bytes()
    make_pdf(directory / 'B.pdf', ['A revised experiment with independent evaluation and new limitations.'])
    s = scene(dependency_fixture); plan = s.read_update_plan()
    assert len(plan['retained_claim_ids']) == len(plan['invalidated_claim_ids']) == 5
    assert len(plan['work']) == 1 and plan['synthesis_requires_review']
    result = s.submit_incremental_update(update_for(s))
    payload = json.loads(Path(result['artifact']).read_text())
    for cid in plan['retained_claim_ids']:
        old = envelope['graph']['fields'][cid]
        new = next(p for p in payload['draft']['papers'] if p['paper_id'] == old['paper_id'])
        assert old['field'] == next(f for f in new['fields'] if f['name'] == old['field']['name'])
    assert (base / 'evidence.json').read_bytes() == original
    assert result['reviewed_field_count'] == 5 and result['research_quality'].startswith('model_draft')


@POPPLER
def test_incremental_length_feedback_identifies_all_overlong_fields_and_preserves_limits(dependency_fixture):
    directory, base, _ = dependency_fixture
    make_pdf(directory / 'B.pdf', ['A changed paper with a new method and measurable limitations.'])
    s = scene(dependency_fixture)
    value = update_for(s)
    value['papers'][0]['fields'][0]['statement'] = '界' * 121
    value['papers'][0]['fields'][1]['statement'] = '界' * 125
    with pytest.raises(ToolError, match='invalid bounded') as error:
        s.submit_incremental_update(value)
    feedback = json.loads(str(error.value).split(': ', 1)[1])
    assert [issue['actual_characters'] for issue in feedback['issues']] == [121, 125]
    assert all(issue['allowed_characters'] == [1, 120] for issue in feedback['issues'])
    assert not (base / 'output/incremental-evidence.json').exists()
    assert len(s.read_update_plan()['work'][0]['fields_to_review']) == 5
    for f in value['papers'][0]['fields']:
        f['statement'] = 'Protocol fixture update.'
    assert s.submit_incremental_update(value)['reviewed_field_count'] == 5


@POPPLER
@pytest.mark.parametrize('dependency', ['question', 'parser', 'contract', 'review_attestation', 'selection'])
def test_global_dependency_changes_invalidate_all_claims(dependency_fixture, dependency):
    s = scene(dependency_fixture)
    current = {'inputs': inputs(s, s.graph['review_attestation_sha256']), 'revoked_claim_ids': []}
    current['inputs'][dependency] = 'a' * 64
    result = evaluate(s.envelope, current)
    assert not result['retained_claim_ids'] and len(result['invalidated_claim_ids']) == 10


@POPPLER
def test_revocation_only_invalidates_named_claim_and_its_consumers(dependency_fixture):
    _, base, envelope = dependency_fixture
    cid = next(iter(envelope['graph']['fields']))
    revoked = base / 'revoked.json'; save_private(revoked, {'revoked_claim_ids': [cid]})
    s = scene(dependency_fixture, revoked=revoked); plan = s.read_update_plan()
    assert plan['invalidated_claim_ids'] == [cid] and len(plan['retained_claim_ids']) == 9
    assert plan['synthesis_requires_review']
    s.submit_incremental_update(update_for(s))


@POPPLER
def test_question_change_is_actual_full_review_handoff(dependency_fixture):
    directory, base, _ = dependency_fixture
    s = IncrementalScene(base / 'dependencies.json', directory, task(directory, 'A new question'), base / 'output')
    assert len(s.read_update_plan()['retained_claim_ids']) == 0
    with pytest.raises(ToolError, match='fully unchanged'):
        s.publish({'papers': [], 'synthesis_hypothesis': ''}, automatic=True)


@POPPLER
@pytest.mark.parametrize('mutation', ['add', 'remove'])
def test_selection_change_requires_review_and_covers_current_papers(dependency_fixture, mutation):
    directory, _, _ = dependency_fixture
    if mutation == 'add': make_pdf(directory / 'new.pdf', ['A new research paper with a limited experimental evaluation.'])
    else: (directory / 'B.pdf').unlink()
    s = scene(dependency_fixture); plan = s.read_update_plan()
    assert not plan['retained_claim_ids'] and len(plan['work']) == len(s.rows)
    receipt = s.submit_incremental_update(update_for(s))
    assert receipt['reviewed_field_count'] == 5 * len(s.rows)


@POPPLER
def test_unreviewed_or_forged_baseline_is_rejected(dependency_fixture):
    _, base, envelope = dependency_fixture
    forged = copy.deepcopy(envelope)
    next(iter(forged['graph']['fields'].values()))['field']['statement'] = 'Invented approval.'
    forged['graph_sha256'] = digest(forged['graph']); save_private(base / 'dependencies.json', forged)
    with pytest.raises(ValueError, match='changed; recompile'): scene(dependency_fixture)
    evidence = json.loads((base / 'evidence.json').read_text()); evidence['reviewer_kind'] = 'model'
    save_private(base / 'evidence.json', evidence)
    with pytest.raises(ValueError, match='explicit review'):
        compile_graph(base / 'evidence.json', base / 'audit.json', base / 'snapshot.json')


@POPPLER
def test_changed_claim_cannot_use_stale_unread_or_cross_paper_citation(dependency_fixture):
    directory, _, envelope = dependency_fixture
    make_pdf(directory / 'B.pdf', ['A changed method and new experimental results, requiring fresh evidence.'])
    s = scene(dependency_fixture); value = update_for(s)
    changed_pid = value['papers'][0]['paper_id']
    old = next(v for v in envelope['graph']['fields'].values() if v['paper_id'] == changed_pid)
    value['papers'][0]['fields'][0]['citations'] = copy.deepcopy(old['field']['citations'])
    with pytest.raises(ToolError, match='current evidence read'): s.submit_incremental_update(value)
    other = next(pid for pid in s.rows if pid != changed_pid)
    pin = s.pin_pdf_context(other, '1'); s.read_pinned_pdf_context(pin['source_id'])
    value['papers'][0]['fields'][0]['citations'] = [{'source_id': pin['source_id'], 'quote_id': 'q0'}]
    with pytest.raises(ToolError, match='cross-paper'): s.submit_incremental_update(value)


@POPPLER
def test_model_cannot_overwrite_retained_field_or_omit_affected_field(dependency_fixture):
    directory, _, _ = dependency_fixture
    make_pdf(directory / 'B.pdf', ['A changed source needing a revised evidence review.'])
    s = scene(dependency_fixture); value = update_for(s)
    value['papers'][0]['fields'].pop()
    with pytest.raises(ToolError, match='every invalidated'): s.submit_incremental_update(value)
    value = update_for(s); value['papers'][0]['paper_id'] = next(pid for pid in s.rows if pid != value['papers'][0]['paper_id'])
    with pytest.raises(ToolError, match='retained'): s.submit_incremental_update(value)


@POPPLER
@pytest.mark.parametrize('mutation', ['pdf', 'audit', 'graph', 'revocation'])
def test_midrun_changes_cannot_publish_stale_plan(dependency_fixture, mutation):
    directory, base, _ = dependency_fixture
    revoked = base / 'revoked.json'; save_private(revoked, {'revoked_claim_ids': []})
    s = scene(dependency_fixture, revoked=revoked); s.read_update_plan()
    if mutation == 'pdf': make_pdf(directory / 'B.pdf', ['Changed during execution.'])
    elif mutation == 'audit':
        audit = json.loads((base / 'audit.json').read_text()); audit['new_counterevidence'] = True
        save_private(base / 'audit.json', audit)
    elif mutation == 'graph': save_private(base / 'dependencies.json', {})
    else: save_private(revoked, {'revoked_claim_ids': [next(iter(s.graph['fields']))]})
    with pytest.raises((ToolError, ValueError)):
        s.publish({'papers': [], 'synthesis_hypothesis': ''}, automatic=True)
    assert not (base / 'output/incremental-evidence.json').exists()


def test_ts_rejects_cycles_missing_dependencies_and_bad_digest():
    graph = {'schema_version': 1, 'nodes': [{'id': 'claim:a', 'kind': 'claim', 'reviewed': True, 'deps': ['claim:a']}]}
    envelope = {'graph': graph, 'graph_sha256': digest(graph)}
    current = {'inputs': {}, 'revoked_claim_ids': []}
    with pytest.raises(ValueError, match='cycle'): evaluate(envelope, current)
    graph['nodes'][0]['deps'] = ['missing']; envelope['graph_sha256'] = digest(graph)
    with pytest.raises(ValueError, match='missing'): evaluate(envelope, current)
    envelope['graph_sha256'] = 'a' * 64
    with pytest.raises(ValueError, match='digest'): evaluate(envelope, current)


@POPPLER
def test_collector_requires_witnessed_receipt_and_rechecks_artifact(dependency_fixture, monkeypatch):
    directory, base, _ = dependency_fixture
    make_pdf(directory / 'B.pdf', ['A revised scientific method with distinct experimental conditions.'])
    s = scene(dependency_fixture); receipt = s.submit_incremental_update(update_for(s))
    rows = []
    monkeypatch.setattr('src.adapters.dsh_trajectory.extract_dsh_trace',
                        lambda *a, **k: SimpleNamespace(records=rows))
    (base / 'agent-events.jsonl').write_text('')
    assert RUN.collect_incremental(base, s) is None
    rows.append(SimpleNamespace(name=RUN.TOOL, observation=receipt))
    assert RUN.collect_incremental(base, s) == receipt
    Path(receipt['artifact']).write_text('{}')
    with pytest.raises(ValueError, match='receipt or dependencies'): RUN.collect_incremental(base, s)


@POPPLER
def test_unchanged_entry_has_zero_paid_requests_and_does_not_load_key(dependency_fixture, monkeypatch, capsys):
    directory, base, _ = dependency_fixture
    original = RUN.load_entry
    def load(name, filename):
        assert filename != 'run-live.py'
        return original(name, filename)
    monkeypatch.setattr(RUN, 'load_entry', load)
    monkeypatch.delenv('DEEPSEEK_API_KEY', raising=False)
    assert RUN.main(['--dependencies', str(base / 'dependencies.json'), '--papers-dir', str(directory), '--call-model']) == 0
    assert '"model_requests": 0' in capsys.readouterr().out


def test_pinned_bibtex_helper_preserves_nested_braces_and_conflicting_duplicates():
    text = '@article{a,title={A {Nested} Title},author={Smith},year={2024},doi={https://doi.org/10.1/x}}\n' \
           '@article{b,title={Conflicting Title},author={Jones},year={2025},doi={10.1/x}}'
    result = preview_bibliography(text); payload = json.loads(Path(result['artifact']).read_text())
    assert result['entry_count'] == 2 and result['possible_duplicate_count'] == 1
    assert '{Nested}' in payload['formatted_bibtex'] and 'Conflicting Title' in payload['formatted_bibtex']
    assert not payload['claim_support_assessed'] and not payload['metadata_verified_online']
    malformed = preview_bibliography(text + '\n@article{broken, title={Missing brace')
    assert malformed['unparsed_remainder_present']


@POPPLER
def test_changed_entry_supplies_all_required_environment_before_paid_launch(dependency_fixture, monkeypatch):
    directory, base, _ = dependency_fixture
    make_pdf(directory / 'B.pdf', ['Changed fixture requiring evidence review.'])
    launched = []
    original = RUN.subprocess.run
    def launch(command, **kwargs):
        if 'run-scenario.py' not in str(command[1]): return original(command, **kwargs)
        launched.append(kwargs['env'])
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(RUN.subprocess, 'run', launch)
    assert RUN.main(['--dependencies', str(base / 'dependencies.json'), '--papers-dir', str(directory)]) == 0
    config = json.loads((HERE / 'pdf-incremental-scenario.json').read_text())
    assert all(launched[0].get(value['from_env']) for value in config['servers'][0]['env'].values())
    assert json.loads(Path(launched[0]['SSS_PDF_REVOKED']).read_text()) == {'revoked_claim_ids': []}


@POPPLER
def test_real_incremental_mcp_harness_budget_protocol(dependency_fixture):
    directory, base, _ = dependency_fixture
    make_pdf(directory / 'B.pdf', ['Changed source for a protocol fixture, not a scientific conclusion.'])
    checker = module(HERE / 'check-incremental.py', 'incremental_protocol_test')
    report = checker.check(base / 'dependencies.json', directory)
    assert report['paid_api_requests'] == 0 and report['mcp']['tool_count'] == 10
    assert report['mcp']['retained_field_count'] == report['mcp']['fields_to_review'] == 5
    assert report['harness']['model_requests'] == report['harness']['budget_ledger_rows'] == 6

@POPPLER
def test_incremental_unquoted_technical_name_requires_source_or_narrower_claim(dependency_fixture):
    directory, _, _ = dependency_fixture
    make_pdf(directory / 'B.pdf', ['Changed fixture with a new evaluation.'])
    s = scene(dependency_fixture); update = update_for(s)
    update['papers'][0]['fields'][0]['statement'] = '采用CIPS算法。'
    with pytest.raises(ToolError, match='missing_technical_names.*CIPS'):
        s.submit_incremental_update(update)
    assert not (s.output / 'incremental-evidence.json').exists()
