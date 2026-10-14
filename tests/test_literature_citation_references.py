"""Opaque addressing is exact provenance, never a scientific support verdict."""
import copy
import json
from pathlib import Path
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import POPPLER, PdfScene, corpus, task, draft, CHECK
from test_literature_pdf_repair import review_scene, repair


@POPPLER
def test_single_reference_admits_same_quote_without_mutating_model_arguments(corpus):
    directory, cache = corpus; s = PdfScene(directory, cache, task(directory)); value = draft(s)
    for paper in value['papers']:
        for f in paper['fields']:
            sid = f['citations'][0]['source_id']; context = s.read_pinned_pdf_context(sid)
            f['citations'] = [{'citation_id': context['quote_spans'][0]['citation_id']}]
    original = copy.deepcopy(value); result = s.preview_research_notes(value)
    assert value == original
    for p in result['draft']['papers']:
        for f in p['fields']:
            assert set(f['citations'][0]) == {'source_id', 'quote_id'}
    assert len(result['citation_checks']) == 10 and not result['claim_support_assessed']


@POPPLER
def test_alias_does_not_authorize_unread_cross_paper_or_changed_sources(corpus):
    directory, cache = corpus; s = PdfScene(directory, cache, task(directory)); value = draft(s)
    a, b = value['papers']; sid = b['fields'][0]['citations'][0]['source_id']
    alias = s.read_pinned_pdf_context(sid)['quote_spans'][0]['citation_id']
    other = PdfScene(directory, cache, task(directory))
    with pytest.raises(ToolError, match='unknown citation_id'): other.resolve_citation({'citation_id': alias})
    a['fields'][0]['citations'] = [{'citation_id': alias}]
    with pytest.raises(ToolError, match='wrong_paper'): s.preview_research_notes(value)
    path = directory / s.rows[b['paper_id']]['filename']; path.write_bytes(path.read_bytes() + b'\n% changed')
    with pytest.raises(ToolError, match='changed'): s.resolve_citation({'citation_id': alias})


@POPPLER
def test_repair_reference_keeps_claim_scope_and_rejects_fabricated_offsets(review_scene):
    base, _ = review_scene; s = repair(base); cid, other = s.targets[:2]
    s.read_claim_repair_packet(cid); s.read_claim_repair_packet(other)
    context = s.read_claim_evidence(cid, '1', start=12); alias = context['quote_spans'][0]['citation_id']
    decision = {'claim_id': cid, 'verdict': 'revised', 'statement': 'A bounded protocol fixture.',
                'reason': 'No scientific certification.', 'citations': [{'citation_id': alias}]}
    result = s._validate_decision(decision)
    assert result['citations'] == [{'source_id': context['source_id'], 'quote_id': context['quote_spans'][0]['quote_id']}]
    with pytest.raises(ToolError, match='not read for this claim'):
        s._validate_decision({**decision, 'claim_id': other})
    with pytest.raises(ToolError, match='unknown citation_id'):
        s._validate_decision({**decision, 'citations': [{'citation_id': 'cite-'+ '0'*32}]})


@POPPLER
def test_actual_harness_continues_same_session_after_promise_without_receipt(corpus, monkeypatch):
    directory, _ = corpus; original = CHECK.protocol_action; injected = []
    def action(values):
        tool, args = original(values)
        if tool == CHECK.PREFIX + 'preview_research_notes' and not injected:
            injected.append(True)
            return None, {'message': 'I will now finish the evidence submission.'}
        return tool, args
    monkeypatch.setattr(CHECK, 'protocol_action', action)
    result = CHECK.check(directory)
    events = [json.loads(x) for x in (Path(result['task_directory'])/'agent-events.jsonl').read_text().splitlines()]
    steering = [e for e in events if e['type']=='user/message' and e['data'].get('source',{}).get('kind')=='task-completion-guard']
    assert len(steering)==1 and steering[0]['data']['source']['continuation']==1
    assert result['paid_api_requests']==0 and result['harness']['delivery']['status']=='needs_review'
    assert sum(e['type']=='turn/start' for e in events)==1
    assert sum(e['type']=='turn/end' for e in events)==1
