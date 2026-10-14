"""Review provenance, publication guards and explicit model-verdict limits."""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import corpus, POPPLER, task, draft, make_pdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scenarios/literature-notes'))
from pdf_tools import PdfScene, save_private
from pdf_review_tools import ReviewScene, numeric_gaps


@pytest.fixture
def review_scene(corpus):
    directory, cache = corpus
    source = PdfScene(directory, cache, task(directory))
    original = draft(source)
    for paper in original['papers']:
        for field in paper['fields']:
            field['citations'] = [{'source_id': field['citations'][0]['source_id'], 'quote_id': 'q0'}]
    run = directory.parent / 'run'
    save_private(run / 'evidence.json', source.preview_research_notes(original))
    save_private(run / 'pdf-input-snapshot.json', {'task': source.task})
    scene = ReviewScene(run, directory.parent / 'review')
    yield scene, directory


def report(scene):
    papers = []
    for paper in scene.evidence['draft']['papers']:
        scene.read_review_packet(paper['paper_id'])
        papers.append({'paper_id': paper['paper_id'], 'fields': [
            {'name': f['name'], 'verdict': 'supported', 'reason': 'Protocol fixture; no semantic quality claim.',
             'statement': f['statement'], 'citations': copy.deepcopy(f['citations'])} for f in paper['fields']]})
    return {'papers': papers, 'synthesis_hypothesis': 'Protocol fixture hypothesis; not a paper finding.'}


@POPPLER
def test_model_review_preserves_original_and_does_not_certify_human_quality(review_scene):
    scene, _ = review_scene
    before = (scene.run / 'evidence.json').read_bytes()
    receipt = scene.submit_claim_review(report(scene))
    revised = json.loads(Path(receipt['artifact']).read_text())
    audit = json.loads((scene.output / 'claim-review.json').read_text())
    assert (scene.run / 'evidence.json').read_bytes() == before
    assert revised['research_quality'] == 'model_reviewed_human_unverified'
    assert audit['human_blind_review_completed'] is False
    assert audit['quality_equivalence_established'] is False


@POPPLER
def test_changed_claim_cannot_be_reported_as_supported(review_scene):
    scene, _ = review_scene
    value = report(scene); value['papers'][0]['fields'][0]['statement'] = 'Changed claim.'
    with pytest.raises(ToolError, match='changes require revised'):
        scene.submit_claim_review(value)


@POPPLER
def test_reviewer_cannot_use_unread_or_cross_paper_evidence(review_scene):
    scene, _ = review_scene
    value = report(scene); first = value['papers'][0]['fields'][0]
    first.update(verdict='revised', citations=copy.deepcopy(value['papers'][1]['fields'][0]['citations']))
    with pytest.raises(ToolError, match='cross-paper'):
        scene.submit_claim_review(value)
    first['citations'][0]['quote_id'] = 'q_not_issued'
    with pytest.raises(ToolError, match='has not read'):
        scene.submit_claim_review(value)


@POPPLER
def test_numeric_precheck_is_fail_closed_but_not_semantic_approval(review_scene):
    scene, _ = review_scene
    value = report(scene); first = value['papers'][0]['fields'][0]
    first.update(verdict='revised', statement='Accuracy is 99.9%.')
    with pytest.raises(ToolError, match='numbers absent'):
        scene.submit_claim_review(value)
    assert numeric_gaps('Accuracy 84.2%', ['There were 84.2 trials.']) == []  # Same number, different meaning.


def test_chinese_decimal_cannot_bypass_selected_quote_numeric_check():
    assert numeric_gaps('提高三点七与三点六分。', ['An unrelated 12.4 gain.']) == ['3.6', '3.7']
    assert numeric_gaps('判别准确率八十四点二%。', ['Detection accuracy was 84.2%.']) == []
    assert numeric_gaps('增益十二点五，差值零点六。', ['12.5 and 0.6']) == []
    assert numeric_gaps('提高三点七分。', ['提高三点七分。']) == []
    assert numeric_gaps('一致比较，一并核验。', ['No numeric fact.']) == []


@POPPLER
def test_review_rejects_source_mutation_before_publication(review_scene):
    scene, directory = review_scene
    value = report(scene)
    make_pdf(directory / 'B.pdf', ['Mutated document, with a different method.'])
    with pytest.raises(ToolError, match='changed'):
        scene.submit_claim_review(value)
    assert not (scene.output / 'revised-evidence.json').exists()


@POPPLER
def test_missing_information_can_be_delivered_as_explicit_gap(review_scene):
    scene, _ = review_scene
    value = report(scene); first = value['papers'][0]['fields'][0]
    first.update(verdict='not_extracted', reason='Insufficient context.', statement='未从当前引文提取。', citations=[])
    receipt = scene.submit_claim_review(value)
    assert receipt['status'] == 'needs_review' and receipt['gap_count'] == 1


@POPPLER
def test_new_page_evidence_requires_explicit_same_paper_selection_and_read(review_scene):
    scene, _ = review_scene
    pid = next(p['paper_id'] for p in scene.evidence['draft']['papers'] if scene.scene.rows[p['paper_id']]['filename'] == '研究 A.PDF')
    with pytest.raises(ToolError, match='packet first'):
        scene.read_review_evidence(pid, page='2')
    scene.read_review_packet(pid)
    added = scene.read_review_evidence(pid, page='2')
    assert added['page'] == 2 and added['paper_id'] == pid
    assert (added['source_id'], 'q0') in scene.allowed
    with pytest.raises(ToolError, match='exactly one'):
        scene.read_review_evidence(pid, source_id=added['source_id'], page='1')


def test_review_collector_contract_is_validated_before_paid_call():
    import importlib.util
    spec = importlib.util.spec_from_file_location('review_test_launcher', ROOT / 'scenarios/literature-notes/review-pdf.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.review_contracts()[module.REVIEW_TOOL].replay_stable is False


def collector():
    import importlib.util
    spec = importlib.util.spec_from_file_location('review_receipt_test', ROOT / 'scenarios/literature-notes/review-pdf.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@POPPLER
def test_offline_collection_requires_tool_receipt_and_matching_artifact(review_scene, monkeypatch):
    scene, _ = review_scene
    receipt = scene.submit_claim_review(report(scene))
    module = collector()
    import src.adapters.dsh_trajectory as trajectory
    records = []
    monkeypatch.setattr(trajectory, 'extract_dsh_trace', lambda *a, **kw: SimpleNamespace(records=records))
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        model_run = Path(temporary); (model_run / 'agent-events.jsonl').write_text('')
        assert module.collect_review(model_run, scene.output, scene.run, scene.input_digest) is None
        records.append(SimpleNamespace(name=module.REVIEW_TOOL, observation=receipt))
        collected = module.collect_review(model_run, scene.output, scene.run, scene.input_digest)
        assert Path(collected['notes']).read_text() == json.loads(Path(receipt['artifact']).read_text())['markdown']
        Path(receipt['artifact']).write_text('{}')
        with pytest.raises(ValueError, match='receipt or original input changed'):
            module.collect_review(model_run, scene.output, scene.run, scene.input_digest)


@POPPLER
def test_offline_collection_revalidates_sources_after_the_paid_run(review_scene, monkeypatch):
    scene, directory = review_scene
    receipt = scene.submit_claim_review(report(scene))
    module = collector()
    import src.adapters.dsh_trajectory as trajectory
    monkeypatch.setattr(trajectory, 'extract_dsh_trace', lambda *a, **kw:
                        SimpleNamespace(records=[SimpleNamespace(name=module.REVIEW_TOOL, observation=receipt)]))
    make_pdf(directory / 'B.pdf', ['Changed after review publication.'])
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        model_run = Path(temporary); (model_run / 'agent-events.jsonl').write_text('')
        with pytest.raises(ValueError, match='current PDF inventory'):
            module.collect_review(model_run, scene.output, scene.run, scene.input_digest)
    assert not (scene.output / 'revised-research-notes.md').exists()
