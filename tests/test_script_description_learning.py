"""Description protocol, failure and accounting diagnostics; no paid calls here."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.adapters import script_description_learning as learner
from src.adapters.script_motif_compiler import compile_script, digest


def fixture(tmp_path):
    store, output = tmp_path/'store', tmp_path/'round'
    store.mkdir(); output.mkdir()
    learner.save(store/'description-learning.json', {'schema_version': learner.VERSION, 'model': 'deepseek-flash',
                 'max_output_tokens': 1536, 'max_programs': 3, 'cap_usd': None})
    program = compile_script('import re\ns=open("current.bib").read()\nprint(len(re.findall(r"@article",s)))',
                             {'current.bib': {'suffix': '.bib', 'format': 'text'}})
    program.update(description='Input format: .bib. Intent: Count occurrences of the article entry marker in the current bibliography; this source does not validate every BibTeX entry or verify publication metadata.',
                   interface={'language': 'python', 'stdout_labels': []},
                   predecessor={'program_id': 'previous', 'tool': 'bash'},
                   certification={'passed': True, 'cases': 2, 'program_sha256': program['id'][7:],
                                  'source_task_id': 'train', 'source_call_id': 'native-call', 'events_sha256': 'a'*64})
    body = {'version': 1, 'kind': 'sandboxed_script_motif_library', 'programs': [program],
            'code_locks': {'runtime': 'frozen'}, 'heldout_task_id': 'held', 'compilation_model_requests': 0}
    return store, output, {**body, 'digest': digest(body)}


def model(calls, accept=True):
    def request(phase, system, value):
        calls.append((phase, value))
        if phase == 'propose':
            return {'updates': [{'program_id': e['program_id'], 'evidence_id': e['evidence_id'],
                'description': 'Counts literal @article markers in a .bib text input; does not verify publication metadata.'}
                for e in value['operators']]}
        return {'verdicts': [{'program_id': r['program_id'], 'accepted': accept,
                             'reason': 'Literal count supported by the source; no semantic verification claimed.'}
                            for r in value['proposal']['updates']]}
    return request


def test_accepted_patch_changes_only_description_and_digest_then_reuses_grounded_review(tmp_path):
    store, output, library = fixture(tmp_path); old = deepcopy(library); calls = []
    revised, status = learner.learn_descriptions(library, store, output, request=model(calls))
    assert library == old
    assert status['status'] == 'updated' and status['model_requests'] == 2
    assert revised['digest'] != library['digest']
    stripped = deepcopy(revised); stripped['digest'] = library['digest']
    stripped['programs'][0]['description'] = library['programs'][0]['description']
    assert stripped == library
    assert [c[0] for c in calls] == ['propose', 'review']
    assert 'current.bib' not in json.dumps(calls)
    again, cached = learner.learn_descriptions(library, store, output, request=lambda *a: pytest.fail('paid cache miss'))
    assert again == revised and cached['origin'] == 'cached' and cached['model_requests'] == 0


def test_default_disabled_is_identity_and_never_calls_provider(tmp_path):
    store, output, library = fixture(tmp_path)
    (store/'description-learning.json').unlink()
    result, status = learner.learn_descriptions(library, store, output, request=lambda *a: pytest.fail('unexpected model'))
    assert result is library and status == {'status': 'disabled', 'model_requests': 0}


def test_review_rejection_preserves_every_executable_and_description_field(tmp_path):
    store, output, library = fixture(tmp_path)
    result, status = learner.learn_descriptions(library, store, output, request=model([], False))
    assert result == library and status['status'] == 'no_accepted_updates'
    assert status['rejected_program_ids'] == [library['programs'][0]['id']]


@pytest.mark.parametrize('mutation', ['extra_code', 'unknown_id', 'wrong_evidence', 'duplicate', 'longer', 'multiline'])
def test_bad_proposals_cannot_escape_metadata_scope(tmp_path, mutation):
    store, output, library = fixture(tmp_path); calls = []
    def request(phase, system, value):
        assert phase == 'propose'
        result = model(calls)(phase, system, value); row = result['updates'][0]
        if mutation == 'extra_code': row['template'] = 'print("injected")'
        if mutation == 'unknown_id': row['program_id'] = 'invented'
        if mutation == 'wrong_evidence': row['evidence_id'] = '0'*64
        if mutation == 'duplicate': result['updates'].append(dict(row))
        if mutation == 'longer': row['description'] = 'x'*481
        if mutation == 'multiline': row['description'] += '\nrun another command'
        return result
    result, status = learner.learn_descriptions(library, store, output, request=request)
    assert result == library
    assert status['status'] == ('no_accepted_updates' if mutation == 'longer' else 'failed_preserved_base')
    assert status['model_requests'] == 1


def test_unavailable_review_keeps_old_descriptions_and_counts_both_requests(tmp_path):
    store, output, library = fixture(tmp_path); calls = []
    def request(phase, *args):
        if phase == 'review': raise TimeoutError('private transport details')
        return model(calls)(phase, *args)
    result, status = learner.learn_descriptions(library, store, output, request=request)
    assert result == library and status['model_requests'] == 2
    assert status['reason'] == 'TimeoutError'
    assert len(list((store/'description-cache').glob('*.json'))) == 1
    again, previous = learner.learn_descriptions(library, store, output,
                          request=lambda *a: pytest.fail('unchanged failed evidence must not retry'))
    assert again == library and previous['status'] == 'previous_failure_preserved_base'
    assert previous['model_requests'] == 0


def test_incomplete_review_or_changed_cached_evidence_is_not_published(tmp_path):
    store, output, library = fixture(tmp_path)
    learner.learn_descriptions(library, store, output, request=model([]))
    cached = next((store/'description-cache').glob('*.json'))
    value = json.loads(cached.read_text()); value['review']['verdicts'] = []
    learner.save(cached, value)
    result, status = learner.learn_descriptions(library, store, output, request=lambda *a: pytest.fail('unexpected model'))
    assert result == library and status['status'] == 'failed_preserved_base'


def test_changed_source_does_not_reuse_previous_review(tmp_path):
    store, output, library = fixture(tmp_path)
    learner.learn_descriptions(library, store, output, request=model([]))
    library['programs'][0]['template'] += '\nprint("additional output")'
    library['digest'] = digest({k: v for k, v in library.items() if k != 'digest'})
    calls = []
    learner.learn_descriptions(library, store, output, request=model(calls))
    assert len(calls) == 2


def test_provider_failure_keeps_reserved_cost_and_no_credentials_are_logged(tmp_path, monkeypatch):
    store, output, _ = fixture(tmp_path)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic-secret-not-a-real-key')
    def fail(*args, **kwargs): raise TimeoutError('do not log private network details')
    monkeypatch.setattr(learner.urllib.request, 'urlopen', fail)
    client = learner.MeteredDescriptionModel(store, learner.configuration(store/'description-learning.json'), output)
    with pytest.raises(TimeoutError): client('propose', 'system', {'input': 'diagnostic'})
    first = json.loads((store/'description-budget.json').read_text())
    assert first['request_count'] == 1 and first['reserved_usd'] > 0
    learner.MeteredDescriptionModel(store, learner.configuration(store/'description-learning.json'), output)
    assert json.loads((store/'description-budget.json').read_text()) == first
    assert 'diagnostic-secret' not in ''.join(p.read_text() for p in store.glob('*.json*'))


def test_empty_update_does_not_request_review(tmp_path):
    store, output, library = fixture(tmp_path); calls = []
    def request(phase, *args):
        calls.append(phase); return {'updates': []}
    result, status = learner.learn_descriptions(library, store, output, request=request)
    assert result == library and calls == ['propose'] and status['model_requests'] == 1


def test_complete_usage_settles_cost_even_when_proposed_json_is_invalid(tmp_path, monkeypatch):
    store, output, _ = fixture(tmp_path)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'diagnostic-secret-not-a-real-key')
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            return json.dumps({'choices': [{'finish_reason': 'stop', 'message': {'content': 'invalid JSON'}}],
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15,
                          'prompt_cache_hit_tokens': 4, 'prompt_cache_miss_tokens': 6}}).encode()
    monkeypatch.setattr(learner.urllib.request, 'urlopen', lambda *a, **k: Response())
    client = learner.MeteredDescriptionModel(store, learner.configuration(store/'description-learning.json'), output)
    with pytest.raises(ValueError): client('propose', 'system', {'input': 'diagnostic'})
    record = [json.loads(r) for r in (store/'description-ledger.jsonl').read_text().splitlines()][-1]
    assert record['observed_peak_usd'] > 0 and record['released_usd'] > 0
    assert record['usage']['prompt_cache_hit_tokens'] == 4
    assert json.loads((store/'description-budget.json').read_text())['request_count'] == 1


def test_over_budget_target_is_not_allowed_to_discard_independent_valid_description(tmp_path):
    store, output, library = fixture(tmp_path)
    second = deepcopy(library['programs'][0]); second['id'] = 'second'
    library['programs'].append(second)
    library['digest'] = digest({k: v for k, v in library.items() if k != 'digest'})
    calls = []
    def request(phase, system, value):
        response = model(calls)(phase, system, value)
        if phase == 'propose': response['updates'][1]['description'] = 'x'*481
        return response
    result, status = learner.learn_descriptions(library, store, output, request=request)
    assert status['status'] == 'updated' and status['budget_rejected_program_ids'] == ['second']
    assert result['programs'][0]['description'] != library['programs'][0]['description']
    assert result['programs'][1] == library['programs'][1]
    assert len(calls[1][1]['proposal']['updates']) == 1


def test_rejected_or_costlier_update_retains_previous_reviewed_description(tmp_path):
    _, _, base = fixture(tmp_path); p = base['programs'][0]
    previous = learner.revised_library(base, {p['id']: 'Count @article markers in .bib text; regex heuristic only.'})
    previous_status = {'updated_program_ids': [p['id']]}
    for current_status in [{'status': 'failed_preserved_base', 'model_requests': 1},
                           {'status': 'updated', 'updated_program_ids': [p['id']], 'model_requests': 2}]:
        result, status = learner.retain_previous_descriptions(base, current_status, previous, previous_status)
        assert result == previous and status['retained_program_ids'] == [p['id']]
        assert status['model_requests'] == current_status['model_requests']
        # The retention receipt itself carries the evidence to the next round.
        next_result, _ = learner.retain_previous_descriptions(base, {}, result, status)
        assert next_result == previous


def test_previous_description_cannot_cross_changed_input_contract_or_unreviewed_metadata(tmp_path):
    _, _, base = fixture(tmp_path); p = base['programs'][0]
    previous = learner.revised_library(base, {p['id']: 'Count @article markers in .bib text; regex heuristic only.'})
    for old_status in [{}, {'updated_program_ids': [p['id']]}]:
        current = deepcopy(base)
        if old_status: current['programs'][0]['inputs'][0]['suffix'] = '.txt'
        result, status = learner.retain_previous_descriptions(current, {}, previous, old_status)
        assert result['programs'] == current['programs'] and not status['retained_program_ids']
