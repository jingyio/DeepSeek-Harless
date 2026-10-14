"""Selected coverage, citation isolation and real guards, not model quality tests."""
import json
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import POPPLER, PdfScene, corpus, task
from test_literature_pdf_evidence import evidence_corpus, scene, plan
from pdf_read_plan import normalize_windows


def coverage(windows):
    return {(p, i) for p, start, n in windows for i in range(start, start + n)}


@pytest.mark.parametrize('windows', [
    [{'page': '1', 'start': 5, 'length': 8}, {'page': '1', 'start': 1, 'length': 9}],
    [{'page': '2', 'start': 10, 'length': 20}, {'page': '1', 'start': 0, 'length': 15},
     {'page': '2', 'start': 10, 'length': 20}],
    [{'page': '1', 'start': 0, 'length': 20}, {'page': '1', 'start': 15, 'length': 20}],
])
def test_normalization_preserves_exact_coverage_and_bounds(windows):
    pages = ['x' * 31, 'y' * 19]
    keys, report = normalize_windows(pages, windows, window_chars=20)
    selected = [(w['page'], w['start'], min(w['length'], len(pages[int(w['page']) - 1]) - w['start'])) for w in windows]
    assert coverage(keys) == coverage(selected)
    assert sum(k[2] for k in keys) == len(coverage(selected))
    assert all(0 < n <= 20 for _, _, n in keys)
    assert all(report['requested_to_contexts'])
    assert not report['semantic_selection_performed']


def test_actual_overflow_requires_new_selection_not_silent_truncation():
    windows = [{'page': '1', 'start': 0, 'length': 20}, {'page': '2', 'start': 0, 'length': 20}]
    with pytest.raises(ToolError, match='40.*no selected text'):
        normalize_windows(['x' * 30, 'y' * 30], windows, total_chars=39)


@POPPLER
def test_context_cache_is_copy_isolated_and_source_guarded(corpus):
    directory, cache = corpus
    s = PdfScene(directory, cache, task(directory)); pid = next(iter(s.rows))
    version = s.document_version(pid)
    batch = s.read_pdf_evidence_plan(pid, version, [{'page': '1', 'start': 0, 'length': 1200},
        {'page': '1', 'start': 5, 'length': 1200}, {'page': '1', 'start': 0, 'length': 1200}])
    assert len(batch['contexts']) == 1
    original = batch['contexts'][0]; sid = original['source_id']
    repeated = s.read_pinned_pdf_context(sid)
    repeated['text'] = 'caller mutation'; repeated['quote_spans'].clear()
    assert {'source_id': sid, **s.read_pinned_pdf_context(sid)} == original
    assert s.stats['context_cache_hits'] >= 2 and s.stats['parser_runs'] == 1
    path = directory / s.rows[pid]['filename']; path.write_bytes(path.read_bytes() + b'\n% changed\n')
    with pytest.raises(ToolError, match='changed'): s.read_pinned_pdf_context(sid)


@POPPLER
def test_evidence_clips_page_ends_and_merges_only_same_purpose(evidence_corpus):
    s = scene(evidence_corpus); value = plan(s)
    for w in value['windows']: w['length'] = 6000
    value['windows'].append(dict(value['windows'][0]))
    # Requested 18000, actual selected page text far below 12000: no retry.
    receipt = s.register_reading_plan(json.dumps(value))
    approved = s._plan(receipt['plan_id'])
    assert len(approved['windows']) == 2
    assert sum(w['length'] for w in approved['windows']) < 12000
    assert receipt['selected_coverage_preserved']
    value['windows'][-1]['purpose'] = 'A different explicit research question.'
    separate = s._plan(json.dumps(value))
    assert len(separate['windows']) == 3
    assert separate['windows'][-1]['purpose'] == value['windows'][-1]['purpose']


@POPPLER
def test_invalid_last_evidence_window_does_not_authorize_partial_plan(evidence_corpus):
    s = scene(evidence_corpus); value = plan(s)
    value['windows'].append({**value['windows'][0], 'page': '999'})
    with pytest.raises(ToolError): s.register_reading_plan(json.dumps(value))
    assert not s.receipts and not s.delivered
