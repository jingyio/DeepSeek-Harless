"""Claim-scoped repairs, deterministic limits and native receipt bindings; no semantic certification."""
import copy
import asyncio
import json
from pathlib import Path
import tempfile
import sys
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import POPPLER, make_pdf, module, corpus
from test_literature_pdf_review import review_scene
from pdf_repair_tools import RepairScene, WITHDRAWN, NOT_EXTRACTED, claim_id, POLICY
from pdf_tools import ROOT, digest, save_private


def repair(scene, targets=None):
    ids = [claim_id(p['paper_id'], f['name']) for p in scene.evidence['draft']['papers'] for f in p['fields']]
    save_private(scene.run / 'repair-targets.json', {'input_sha256': scene.input_digest,
                                                   'claim_ids': ids if targets is None else targets})
    return RepairScene(scene.run, scene.output)


def decisions(scene):
    values = []
    for cid in scene.targets:
        packet = scene.read_claim_repair_packet(cid)
        field = packet['field']
        values.append({'claim_id': cid, 'verdict': 'supported', 'reason': 'Synthetic protocol fixture.',
                       'statement': field['statement'], 'citations': field['citations']})
    return values


@POPPLER
def test_synthesis_only_requires_full_packet_and_preserves_every_field(review_scene):
    base, _ = review_scene
    save_private(base.run / 'repair-targets.json', {'input_sha256': base.input_digest, 'claim_ids': [], 'synthesis_only': True})
    scene = RepairScene(base.run, base.output)
    with pytest.raises(ToolError): scene.submit_claim_repair([], 'A global project hypothesis.')
    packet = scene.read_claim_repair_packet('synthesis')
    assert packet['draft'] == base.evidence['draft']
    assert packet['quotes'] == base.evidence['citation_checks']
    with pytest.raises(ToolError): scene.read_claim_repair_packet('claim:unknown')
    with pytest.raises(ToolError): scene.submit_claim_repair([{'claim_id': 'claim:unknown'}], 'No field changes.')
    receipt = scene.submit_claim_repair([], 'A global project hypothesis.')
    result = json.loads(Path(receipt['artifact']).read_text())
    assert result['draft']['papers'] == base.evidence['draft']['papers']
    assert receipt['changed_claim_count'] == 0 and not result['claim_support_assessed']
    # A real extractor must retain a successful empty-decisions native receipt.
    launcher = module(ROOT / 'scenarios/literature-notes/repair-pdf.py', 'synthesis_collector_test')
    native = [
        {'type': 'tool/call', 'data': {'step': 1, 'callId': 'synthesis', 'name': launcher.REPAIR_TOOL,
         'arguments': json.dumps({'decisions': [], 'synthesis_hypothesis': 'A global project hypothesis.'})}},
        {'type': 'tool/result', 'data': {'step': 1, 'message': {'source': {'kind': 'tool', 'callId': 'synthesis'}, 'role': 'user', 'content': [
            {'type': 'tool-result', 'toolCallId': 'synthesis', 'isError': False,
             'content': [{'type': 'text', 'text': json.dumps(receipt)}]}]}}}]
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        run = Path(temporary)
        (run / 'agent-events.jsonl').write_text('\n'.join(json.dumps(e) for e in native))
        collected = launcher.collect_repair(run, scene.output, scene.run, scene.input_digest)
        assert collected['receipt'] == receipt


@POPPLER
def test_targeted_repair_preserves_untouched_fields_and_withdraws_instead_of_repeating_fact(review_scene):
    base, _ = review_scene
    ids = [claim_id(base.evidence['draft']['papers'][0]['paper_id'], 'findings')]
    scene = repair(base, ids)
    original = copy.deepcopy(scene.evidence['draft'])
    value = decisions(scene)
    value[0].update(verdict='withdrawn', statement=WITHDRAWN, citations=[])
    receipt = scene.submit_claim_repair(value, 'A project hypothesis without the withdrawn result.')
    revised = json.loads(Path(receipt['artifact']).read_text())
    audit = json.loads(Path(receipt['audit']).read_text())
    assert receipt['target_count'] == receipt['changed_claim_count'] == receipt['withdrawn_claim_count'] == 1
    assert receipt['gap_count'] == 1 and receipt['unresolved_claim_ids'] == ids
    for old, new in zip(original['papers'], revised['draft']['papers']):
        for before, after in zip(old['fields'], new['fields']):
            if claim_id(old['paper_id'], before['name']) not in ids: assert before == after
    assert len(audit['untouched_claim_ids']) == 9 and len(audit['decisions']) == 1
    assert not audit['human_blind_review_completed'] and not audit['quality_equivalence_established']
    assert receipt['audit_sha256'] == digest(audit)
    with pytest.raises(ToolError, match='already published'):
        scene.submit_claim_repair(value, 'No repeated submission.')


@POPPLER
def test_prior_rejected_hypothesis_grants_no_citation_permission_and_error_survives_gap(review_scene):
    base, _ = review_scene
    cid = claim_id(base.evidence['draft']['papers'][0]['paper_id'], 'findings')
    repair(base, [cid])
    request = json.loads((base.run / 'repair-targets.json').read_text())
    proposal = {'claim_id': cid, 'verdict': 'revised', 'reason': 'untrusted',
        'statement': 'Untrusted old hypothesis', 'citations': [{'source_id': 'fake', 'quote_id': 'q0'}]}
    request['prior_proposals'] = {cid: {'proposal': proposal, 'validation_error': 'unread'}}
    save_private(base.run / 'repair-targets.json', request)
    scene = RepairScene(base.run, base.output)
    packet = scene.read_claim_repair_packet(cid)
    assert packet['prior_rejected_proposal']['proposal'] == proposal
    result = scene.submit_claim_repair([proposal], 'A hypothesis.')
    assert 'not read' in result['issues'][0]['error']
    receipt = scene.submit_claim_repair([{'claim_id': cid, 'verdict': 'not_extracted', 'reason': 'technical gap'}], 'A hypothesis.')
    audit = json.loads(Path(receipt['audit']).read_text())
    assert audit['rejected_proposals'][cid]['proposal'] == proposal
    assert 'not read' in audit['rejected_proposals'][cid]['validation_error']


@POPPLER
@pytest.mark.parametrize('kind', ['numeric', 'unread', 'changed_supported', 'fact_as_gap', 'widen_scope'])
def test_repair_rejects_unsupported_or_unbound_changes(review_scene, kind):
    base, _ = review_scene
    scene = repair(base)
    value = decisions(scene)
    first = value[0]
    if kind == 'numeric': first.update(verdict='revised', statement='Accuracy was 99.9%.')
    elif kind == 'unread': first.update(verdict='revised', citations=[{'source_id': 'unknown', 'quote_id': 'q0'}])
    elif kind == 'changed_supported': first['statement'] = 'A different fact.'
    elif kind == 'fact_as_gap': first.update(verdict='withdrawn', citations=[])
    else: first['claim_id'] = 'claim:unknown:findings'
    if kind == 'widen_scope':
        with pytest.raises(ToolError): scene.submit_claim_repair(value, 'A bounded fixture hypothesis.')
    else:
        result = scene.submit_claim_repair(value, 'A bounded fixture hypothesis.')
        assert result['status'] == 'pending_claim_decisions'
        assert result['pending_claim_ids'] == [first['claim_id']]
        assert result['issues'][0]['claim_id'] == first['claim_id']
    assert not (scene.output / 'revised-evidence.json').exists()


@POPPLER
def test_search_is_navigation_and_read_is_claim_scoped(review_scene):
    base, _ = review_scene
    scene = repair(base)
    pid = next(p['paper_id'] for p in scene.evidence['draft']['papers'] if scene.scene.rows[p['paper_id']]['filename'] == '研究 A.PDF')
    cid, other = claim_id(pid, 'findings'), claim_id(pid, 'method')
    with pytest.raises(ToolError, match='packet first'): scene.search_claim_evidence(cid, 'limitations')
    value = decisions(scene)
    result = scene.search_claim_evidence(cid, 'limitations')
    assert not result['absence_claim_supported'] and result['matches'][0]['page'] == 2
    added = scene.read_claim_evidence(cid, '2')
    forged = next(v for v in value if v['claim_id'] == other)
    forged.update(verdict='revised', citations=[{'source_id': added['source_id'], 'quote_id': added['quote_spans'][0]['quote_id']}])
    result = scene.submit_claim_repair(value, 'Do not transfer read permissions between claims.')
    assert result['issues'][0]['claim_id'] == other
    assert 'not read for this claim' in result['issues'][0]['error']


@POPPLER
def test_tool_limits_bound_failed_and_successful_attempts(review_scene):
    base, _ = review_scene
    scene = repair(base)
    cid = scene.targets[0]
    scene.read_claim_repair_packet(cid)
    for _ in range(POLICY['searches_per_claim']):
        assert not scene.search_claim_evidence(cid, 'unmatched phrase')['absence_claim_supported']
    with pytest.raises(ToolError, match='search limit'): scene.search_claim_evidence(cid, 'method')
    for _ in range(POLICY['reads_per_claim']):
        with pytest.raises(ToolError): scene.read_claim_evidence(cid, '9999')
    with pytest.raises(ToolError, match='read limit'): scene.read_claim_evidence(cid, '1')


@POPPLER
def test_changed_pdf_prevents_repair_publication(review_scene):
    base, directory = review_scene
    scene = repair(base)
    value = decisions(scene)
    make_pdf(directory / 'B.pdf', ['Different current source.'])
    with pytest.raises(ToolError, match='changed'): scene.submit_claim_repair(value, 'A fixture hypothesis.')


@POPPLER
@pytest.mark.parametrize('kind', ['digest', 'duplicate', 'unknown', 'invalid_type'])
def test_target_plan_is_frozen_not_model_widenable(review_scene, kind):
    base, _ = review_scene
    scene = repair(base)
    request = {'input_sha256': scene.input_digest, 'claim_ids': scene.targets}
    if kind == 'digest': request['input_sha256'] = 'a' * 64
    elif kind == 'duplicate': request['claim_ids'] = [scene.targets[0], scene.targets[0]]
    elif kind == 'unknown': request['claim_ids'] = ['unknown']
    else: request['claim_ids'] = [{}]
    save_private(scene.run / 'repair-targets.json', request)
    with pytest.raises(ValueError, match='uniquely bind'): RepairScene(scene.run, scene.output)


@POPPLER
def test_collection_requires_native_receipt_and_binds_audit(review_scene, monkeypatch):
    base, _ = review_scene
    scene = repair(base)
    receipt = scene.submit_claim_repair(decisions(scene), 'A fixture hypothesis.')
    launcher = module(ROOT / 'scenarios/literature-notes/repair-pdf.py', 'repair_test_collector')
    import src.adapters.dsh_trajectory as trajectory
    records = []
    monkeypatch.setattr(trajectory, 'extract_dsh_trace', lambda *a, **kw: SimpleNamespace(records=records))
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        run = Path(temporary); (run / 'agent-events.jsonl').write_text('')
        assert launcher.collect_repair(run, scene.output, scene.run, scene.input_digest) is None
        records.append(SimpleNamespace(name=launcher.REPAIR_TOOL, observation={'status': 'pending_claim_decisions'}))
        assert launcher.collect_repair(run, scene.output, scene.run, scene.input_digest) is None
        records.append(SimpleNamespace(name=launcher.REPAIR_TOOL, observation=receipt))
        assert launcher.collect_repair(run, scene.output, scene.run, scene.input_digest)['receipt'] == receipt
        audit = json.loads(Path(receipt['audit']).read_text()); audit['decisions'][0]['reason'] = 'Tampered.'
        save_private(Path(receipt['audit']), audit)
        with pytest.raises(ValueError, match='audit receipt changed'):
            launcher.collect_repair(run, scene.output, scene.run, scene.input_digest)


@POPPLER
def test_real_stdio_mcp_exposes_only_repair_tools_and_publishes_bound_receipt(review_scene):
    base, _ = review_scene
    scene = repair(base)
    from mcp import Client, StdioServerParameters

    async def check():
        env = {'SSS_PDF_REPAIR_RUN': str(scene.run), 'SSS_PDF_REPAIR_OUTPUT': str(scene.output)}
        params = StdioServerParameters(command=sys.executable,
            args=[str(ROOT / 'scenarios/literature-notes/pdf_repair_tools.py')], cwd=ROOT, env=env)
        async with Client(params) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == {'read_claim_repair_packet', 'search_claim_evidence',
                                              'read_claim_evidence', 'read_claim_evidence_plan', 'submit_claim_repair'}
            assert all(t.annotations.read_only_hint for t in tools)
            bad = await client.call_tool('read_claim_evidence', {'claim_id': scene.targets[0], 'page': '1'})
            assert bad.is_error
            values = []
            for cid in scene.targets:
                result = await client.call_tool('read_claim_repair_packet', {'claim_id': cid})
                assert not result.is_error
                packet = json.loads(result.content[0].text)
                values.append({'claim_id': cid, 'verdict': 'supported', 'reason': 'Protocol only.',
                               'statement': packet['field']['statement'], 'citations': packet['field']['citations']})
            found = await client.call_tool('search_claim_evidence', {'claim_id': scene.targets[0], 'query': 'method'})
            assert not found.is_error
            read = await client.call_tool('read_claim_evidence', {'claim_id': scene.targets[0], 'page': '1'})
            assert not read.is_error
            delivered = await client.call_tool('submit_claim_repair', {'decisions': values, 'synthesis_hypothesis': 'Protocol fixture only.'})
            assert not delivered.is_error
            receipt = json.loads(delivered.content[0].text)
            assert receipt['artifact_sha256'] == digest(json.loads(Path(receipt['artifact']).read_text()))
            assert receipt['audit_sha256'] == digest(json.loads(Path(receipt['audit']).read_text()))
    asyncio.run(check())


@POPPLER
def test_partial_admission_keeps_good_claims_and_bounds_invalid_retries(review_scene):
    base, _ = review_scene
    scene = repair(base)
    values = decisions(scene)
    bad = values[0]
    bad.update(verdict='revised', statement='Accuracy 99.9%.')
    for attempt in range(3):
        result = scene.submit_claim_repair(values if not attempt else [bad], 'Only pending claims are retried.')
        assert result['pending_claim_ids'] == [bad['claim_id']]
        assert len(result['accepted_claim_ids']) == len(values) - 1
        assert '99.9' in result['issues'][0]['error']
    result = scene.submit_claim_repair([bad], 'Only pending claims are retried.')
    assert 'limit reached' in result['issues'][0]['error']
    receipt = scene.submit_claim_repair([{'claim_id': bad['claim_id'], 'verdict': 'withdrawn', 'reason': 'No supporting quote.'}], 'A hypothesis.')
    assert receipt['withdrawn_claim_count'] == 1 and receipt['changed_claim_count'] == 1
    audit = json.loads(Path(receipt['audit']).read_text())
    assert all(audit['validation_attempts'][cid] == 1 for cid in scene.targets[1:])


@POPPLER
def test_explicit_supported_uses_exact_runtime_bound_parameters(review_scene):
    base, _ = review_scene
    scene = repair(base)
    for cid in scene.targets: scene.read_claim_repair_packet(cid)
    receipt = scene.submit_claim_repair([{'claim_id': cid, 'verdict': 'supported', 'reason': 'Synthetic fixture.'}
                                         for cid in scene.targets], 'A hypothesis.')
    assert receipt['changed_claim_count'] == 0
    assert json.loads(Path(receipt['artifact']).read_text())['draft']['papers'] == scene.evidence['draft']['papers']


@POPPLER
def test_second_pass_recovers_withdrawn_original_context_and_replays_sources(review_scene):
    base, _ = review_scene
    first = repair(base)
    vals = decisions(first); vals[0].update(verdict='withdrawn', statement=WITHDRAWN, citations=[])
    receipt = first.submit_claim_repair(vals, 'A hypothesis.')
    second_run = base.run / 'second'; second_output = base.output / 'second'
    original = json.loads(Path(receipt['artifact']).read_text())
    save_private(second_run / 'evidence.json', original)
    save_private(second_run / 'pdf-input-snapshot.json', json.loads((base.run / 'pdf-input-snapshot.json').read_text()))
    cid = first.targets[0]
    request = {'input_sha256': digest(original), 'claim_ids': [cid], 'history_input_directory': str(base.run),
               'history_input_sha256': first.input_digest}
    save_private(second_run / 'repair-targets.json', request)
    second = RepairScene(second_run, second_output)
    packet = second.read_claim_repair_packet(cid)
    assert packet['field']['statement'] == WITHDRAWN
    assert packet['previous_claim_context']['field']['statement'] == first.claims[cid][1]['statement']
    assert packet['previous_claim_context']['quotes']
    supported = second.submit_claim_repair([{'claim_id': cid, 'verdict': 'supported', 'reason': 'Wrongly retain gap.'}], 'A hypothesis.')
    assert supported['pending_claim_ids'] == [cid]
    old = packet['previous_claim_context']['field']
    fixed = second.submit_claim_repair([{'claim_id': cid, 'verdict': 'revised', 'reason': 'Rechecked old source fixture.',
                                        'statement': old['statement'], 'citations': old['citations']}], 'A hypothesis.')
    assert fixed['gap_count'] == 0
    request['history_input_sha256'] = '0' * 64
    save_private(second_run / 'repair-targets.json', request)
    with pytest.raises(ValueError, match='history'): RepairScene(second_run, second_output)


@POPPLER
def test_packet_exposes_only_actual_same_claim_neighbour_spans(corpus):
    from test_literature_pdf import task, draft
    from pdf_tools import PdfScene
    from pdf_review_tools import ReviewScene
    directory, cache = corpus
    make_pdf(directory / 'B.pdf', ['Evidence context with subject and condition. ' * 50])
    pdf = directory / 'B.pdf'
    pdf.write_bytes(pdf.read_bytes().replace(b'/F1 11 Tf', b'/F1 .5 Tf'))  # Same byte length/xref; fit long fixture text.
    source = PdfScene(directory, cache, task(directory))
    candidate = draft(source)
    for paper in candidate['papers']:
        for field in paper['fields']:
            field['citations'] = [{'source_id': field['citations'][0]['source_id'], 'quote_id': 'q0'}]
    run = directory.parent / 'adjacent-run'
    save_private(run / 'evidence.json', source.preview_research_notes(candidate))
    save_private(run / 'pdf-input-snapshot.json', {'task': source.task})
    base = ReviewScene(run, directory.parent / 'adjacent-output')
    scene = repair(base)
    cid = next(cid for cid, (pid, _) in scene.claims.items() if scene.scene.rows[pid]['filename'] == 'B.pdf')
    packet = scene.read_claim_repair_packet(cid)
    assert packet['adjacent_quotes']
    for quote in packet['adjacent_quotes']:
        assert (quote['source_id'], quote['quote_id']) in scene.claim_allowed[cid]
        context = scene.sources[quote['source_id']]
        span = next(s for s in context['quote_spans'] if s['quote_id'] == quote['quote_id'])
        assert quote['quote'] == context['text'][span['start']:span['end']]
        assert context['paper_id'] == packet['paper_id']


@POPPLER
def test_evidence_first_mode_hides_old_wording_and_requires_independent_fact(review_scene):
    base, _ = review_scene
    scene = repair(base)
    request = json.loads((scene.run / 'repair-targets.json').read_text())
    request['review_mode'] = 'evidence_first_reextract'
    save_private(scene.run / 'repair-targets.json', request)
    scene = RepairScene(scene.run, scene.output)
    cid = scene.targets[0]
    packet = scene.read_claim_repair_packet(cid)
    assert 'statement' not in packet['field'] and 'status' not in packet['field']
    result = scene.submit_claim_repair([{'claim_id': cid, 'verdict': 'supported', 'reason': 'Copy old answer.'}], 'A hypothesis.')
    assert 'independently written' in result['issues'][0]['error']
    assert cid not in scene.accepted


def proposal_history(scene, values):
    events = []
    for i, cid in enumerate(scene.targets, 1):
        packet = scene.read_claim_repair_packet(cid)
        events.append({'type': 'tool/call', 'data': {'step': i, 'callId': str(i),
            'name': 'mcp__literature_pdf_repair__read_claim_repair_packet',
            'arguments': json.dumps({'claim_id': cid})}})
        events.append({'type': 'tool/result', 'data': {'step': i, 'message': {'content': [
            {'type': 'tool-result', 'toolCallId': str(i), 'isError': False,
             'content': [{'type': 'text', 'text': json.dumps(packet)}]}]}}})
    events.append({'type': 'assistant/message', 'data': {'step': len(scene.targets) + 1,
        'message': {'id': 'fixture-model-output', 'source': {'kind': 'model'},
        'content': [{'type': 'text', 'text': json.dumps({'decisions': values, 'synthesis_hypothesis': 'A fixture hypothesis.'})}]}}})
    return events


@POPPLER
@pytest.mark.parametrize('bad_citation', [False, True])
def test_final_model_proposal_recovery_replays_actual_reads_and_keeps_technical_gaps(review_scene, bad_citation):
    from pdf_repair_recovery import recover_final_proposal
    base, _ = review_scene;scene = repair(base);values = decisions(scene)
    if bad_citation: values[0].update(verdict='revised', citations=[{'source_id': 'not-read', 'quote_id': 'q0'}])
    events = proposal_history(repair(base), values)
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        run = Path(temporary);path = run / 'agent-events.jsonl'
        data = '\n'.join(json.dumps(e) for e in events);path.write_text(data)
        output = scene.output / 'recovered'
        result = recover_final_proposal(run, output, scene.run, scene.input_digest)
        assert result['receipt_origin'] == 'validated_model_final_json_recovery'
        assert result['receipt']['gap_count'] == int(bad_citation)
        assert path.read_text() == data  # No invented native submit event.
        audit = json.loads((output / 'claim-review.json').read_text())
        assert audit['proposal_provenance']['additional_model_requests'] == 0
        assert not audit['proposal_provenance']['synthetic_native_events']
        assert len(audit['proposal_provenance']['replayed_tools']) == len(scene.targets)
        if bad_citation:
            assert audit['runtime_gap_claim_ids'] == [values[0]['claim_id']]
            assert 'Runtime' in audit['decisions'][0]['reason']


@POPPLER
@pytest.mark.parametrize('kind', ['non_json', 'unknown_target', 'tampered_observation', 'source_change'])
def test_proposal_recovery_refuses_unbound_outputs_and_source_changes(review_scene, kind):
    from pdf_repair_recovery import recover_final_proposal
    base, directory = review_scene;scene = repair(base);values = decisions(scene)
    events = proposal_history(repair(base), values)
    if kind == 'non_json': events[-1]['data']['message']['content'][0]['text'] = 'Trust me; already published.'
    elif kind == 'unknown_target':
        values[0]['claim_id'] = 'claim:unknown:findings'
        events[-1]['data']['message']['content'][0]['text'] = json.dumps({'decisions': values, 'synthesis_hypothesis': 'A hypothesis.'})
    elif kind == 'tampered_observation': events[1]['data']['message']['content'][0]['content'][0]['text'] = '{}'
    else: make_pdf(directory / 'B.pdf', ['The source changed.'])
    with tempfile.TemporaryDirectory(dir=ROOT / '.local/runs') as temporary:
        run = Path(temporary);(run / 'agent-events.jsonl').write_text('\n'.join(json.dumps(e) for e in events))
        output = scene.output / 'rejected'
        if kind in ('tampered_observation', 'source_change'):
            with pytest.raises((ValueError, ToolError)): recover_final_proposal(run, output, scene.run, scene.input_digest)
        else: assert recover_final_proposal(run, output, scene.run, scene.input_digest) is None
        assert not (output / 'revised-evidence.json').exists()

@POPPLER
def test_claim_batch_plan_keeps_scope_shared_budget_and_version_guard(review_scene):
    base, _ = review_scene; scene = repair(base)
    cid, other = scene.targets[:2]
    packet = scene.read_claim_repair_packet(cid)
    windows = [{'page': '1', 'start': 0, 'length': 1000}]
    with pytest.raises(ToolError): scene.read_claim_evidence_plan(other, packet['document_version_sha256'], windows)
    bad = windows + [{'page': '999', 'start': 0, 'length': 1000}]
    with pytest.raises(ToolError): scene.read_claim_evidence_plan(cid, packet['document_version_sha256'], bad)
    assert scene.usage[cid]['reads'] == 0
    value = scene.read_claim_evidence_plan(cid, packet['document_version_sha256'], windows)
    assert scene.usage[cid]['reads'] == 1
    repeat = scene.read_claim_evidence_plan(cid, packet['document_version_sha256'], windows)
    assert repeat['reused_windows'] == 1 and repeat['contexts'] == value['contexts']
    with pytest.raises(ToolError): scene.read_claim_evidence_plan(cid, '0' * 64, windows)
    sid = value['contexts'][0]['source_id']
    assert (sid, 'q0') in scene.claim_allowed[cid] and (sid, 'q0') not in scene.claim_allowed[other]
    scene.read_claim_evidence(cid, '1'); scene.read_claim_evidence(cid, '1')
    with pytest.raises(ToolError, match='read limit'):
        scene.read_claim_evidence_plan(cid, packet['document_version_sha256'], [{'page': '1', 'start': 1, 'length': 1100}])


@POPPLER
def test_claim_overlap_preserves_coverage_once_and_keeps_citation_permissions_local(review_scene):
    base, _ = review_scene; scene = repair(base)
    cid, other = scene.targets[:2]; packet = scene.read_claim_repair_packet(cid)
    windows = [{'page': '1', 'start': 0, 'length': 40}, {'page': '1', 'start': 20, 'length': 40},
               {'page': '1', 'start': 0, 'length': 40}]
    result = scene.read_claim_evidence_plan(cid, packet['document_version_sha256'], windows)
    assert len(result['contexts']) == 1 and scene.usage[cid]['reads'] == 1
    context = result['contexts'][0]
    assert context['start'] == 0 and context['end'] == 60
    repeat = scene.read_claim_evidence_plan(cid, packet['document_version_sha256'], windows)
    assert repeat['reused_windows'] == 1 and scene.usage[cid]['reads'] == 1
    assert all((context['source_id'], q['quote_id']) in scene.claim_allowed[cid] for q in context['quote_spans'])
    assert all((context['source_id'], q['quote_id']) not in scene.claim_allowed[other] for q in context['quote_spans'])

@POPPLER
def test_repair_rejects_unquoted_algorithm_baseline_names_without_claiming_entailment(review_scene):
    from claim_coverage import technical_name_gaps
    assert technical_name_gaps('使用CIPS并优于PlanCache。', ['AutoTool is described here.']) == ['CIPS', 'PlanCache']
    assert technical_name_gaps('ReAct和AutoTool。', ['ReAct with Auto-\nTool']) == []
    assert technical_name_gaps('CIPS改善所有任务。', ['CIPS failed on some tasks.']) == []  # Not semantic support.
    base, _ = review_scene; scene = repair(base)
    proposal = decisions(scene)[0]
    proposal.update(verdict='revised', statement='采用CIPS算法。')
    result = scene.submit_claim_repair([proposal], 'Test hypothesis.')
    assert result['status'] == 'pending_claim_decisions'
    assert 'lack technical names: CIPS' in result['issues'][0]['error']
    assert not scene.completed


def test_mcp_submission_schema_exposes_conditional_anchor_and_bounds():
    from pdf_repair_tools import make_server
    class Scene:
        statement_limit = 80
        calls = []
        def read_claim_repair_packet(self): pass
        def search_claim_evidence(self): pass
        def read_claim_evidence(self): pass
        def read_claim_evidence_plan(self): pass
        def submit_claim_repair(self, decisions, synthesis_hypothesis):
            self.calls.append(decisions)
            return {'status': 'fixture'}
    scene = Scene(); server = make_server(scene)
    schema = next(t.input_schema for t in asyncio.run(server.list_tools()) if t.name == 'submit_claim_repair')
    defs = schema['$defs']
    assert 'support_anchor' in defs['AuditSupportedDecision']['required']
    assert {'statement', 'citations', 'support_anchor'} <= set(defs['AuditRevisedDecision']['required'])
    assert defs['AuditRevisedDecision']['properties']['statement']['maxLength'] == 80
    assert defs['GapDecision']['additionalProperties'] is False
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool('submit_claim_repair', {'decisions': [{'claim_id':'x','verdict':'supported','reason':'ok'}], 'synthesis_hypothesis':'test'}))
    assert scene.calls == []
    asyncio.run(server.call_tool('submit_claim_repair', {'decisions': [{'claim_id':'x','verdict':'supported','reason':'ok',
        'support_anchor':'A complete source sentence with sufficient length.'}], 'synthesis_hypothesis':'test'}))
    assert scene.calls[0][0]['support_anchor'].endswith('.')
    scene.statement_limit = 120
    schema = next(t.input_schema for t in asyncio.run(make_server(scene).list_tools()) if t.name == 'submit_claim_repair')
    assert 'support_anchor' not in schema['$defs']['SupportedDecision']['properties']
    assert schema['$defs']['RevisedDecision']['properties']['statement']['maxLength'] == 120
