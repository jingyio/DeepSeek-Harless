"""Fixed-plan fairness and failed-attempt accounting; not research-quality tests."""
import copy
import hashlib
import json

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_literature_pdf import POPPLER, module
from test_literature_pdf_evidence import HERE, RUN, CHECK, evidence_corpus, scene, plan

COMPARE = module(HERE / 'compare-evidence.py', 'evidence_comparison_test')
CACHE = module(HERE / 'reuse-evidence.py', 'evidence_cache_test')


def test_rotating_order_balances_positions_without_claiming_independent_tasks():
    schedule = COMPARE.order(3)
    assert len(schedule) == 9
    for arm in ('baseline', 'script', 'motif'):
        assert {r['position'] for r in schedule if r['arm'] == arm} == {1, 2, 3}
    for bad in (0, 13, True, 1.5):
        with pytest.raises(ValueError):
            COMPARE.order(bad)


@POPPLER
def test_same_frozen_input_gives_identical_prompts_and_execution_version_in_all_arms(evidence_corpus):
    value = plan(scene(evidence_corpus))
    prompts, versions = [], []
    for mode, script in [('baseline', False), ('baseline', True), ('execute', False)]:
        output, _env = RUN.prepare_task(evidence_corpus[0], scene(evidence_corpus).task['question'],
                                        frozen_plan=value, mode=mode, script_chain=script)
        snapshot = json.loads((output / 'input-snapshot.json').read_text())
        prompts.append(hashlib.sha256((output / 'prompt.md').read_bytes()).hexdigest())
        versions.append(snapshot['execution_version_sha256'])
        assert snapshot['frozen_plan'] == scene(evidence_corpus)._plan(json.dumps(value))
        assert snapshot['execution_options']['model_call_enabled'] is False
    assert len(set(prompts)) == len(set(versions)) == 1


@POPPLER
@pytest.mark.parametrize('invalid', ['permission', 'task', 'schema'])
def test_frozen_plan_does_not_override_permission_task_or_schema(evidence_corpus, invalid):
    value = plan(scene(evidence_corpus))
    if invalid == 'permission':
        value['allow_deterministic_continuation'] = False
    elif invalid == 'task':
        value['task_sha256'] = '0' * 64
    else:
        value['extra'] = 'not permitted'
    with pytest.raises((ToolError, ValueError)):
        RUN.prepare_task(evidence_corpus[0], scene(evidence_corpus).task['question'], frozen_plan=value)


@pytest.mark.parametrize('stdout', ['', '{}', '{"output_dir":"fake"}',
    '{"output_dir":"fake","budget_accounted_usd":-1}',
    '{"output_dir":"fake","budget_accounted_usd":NaN}'])
def test_missing_or_invalid_costs_are_incomplete_and_cannot_pass(stdout):
    result = COMPARE.summarize_attempt(stdout, 2, {}, 'expected')
    assert not result['accepted'] and not result['cost_complete']


def test_failed_paid_attempt_retains_cost_even_without_packet():
    result = COMPARE.summarize_attempt(json.dumps({'output_dir': 'fake', 'budget_accounted_usd': 0.012}),
                                        2, {}, 'expected')
    assert not result['accepted'] and result['cost_complete']
    assert result['accounted_usd'] == 0.012


@POPPLER
def test_exact_source_packet_with_different_plan_still_fails_frozen_comparison(evidence_corpus):
    result = CHECK.check(evidence_corpus[0], frozen_plan=plan(scene(evidence_corpus)))
    assert result['identical_packets'] and [r['model_requests'] for r in result['arms']] == [6, 4]
    task_dir = __import__('pathlib').Path(result['arms'][0]['task_directory'])
    snapshot = json.loads((task_dir / 'input-snapshot.json').read_text())
    snapshot['frozen_plan'] = copy.deepcopy(snapshot['frozen_plan'])
    snapshot['frozen_plan']['windows'][0]['purpose'] = 'A different approved decision.'
    (task_dir / 'input-snapshot.json').write_text(json.dumps(snapshot))
    with pytest.raises(ValueError, match='differs from frozen'):
        RUN.collect_packet(task_dir, task_dir)


@POPPLER
def test_synthetic_provider_packet_cannot_be_reused_as_real_model_approval(evidence_corpus):
    result = CHECK.check(evidence_corpus[0])
    with pytest.raises(ValueError, match='private shared-run'):
        COMPARE.approved_origin(result['arms'][0]['task_directory'], evidence_corpus[0],
                                 evidence_corpus[1], evidence_corpus[2])


@POPPLER
@pytest.mark.parametrize('change', ['question', 'plan', 'permission'])
def test_result_cache_rejects_different_current_request(evidence_corpus, change):
    s = scene(evidence_corpus)
    value = plan(s)
    packet = {'question': s.task['question'], 'plan': copy.deepcopy(value)}
    question = s.task['question']
    if change == 'question':
        question += ' A different research goal.'
    elif change == 'plan':
        value['windows'][0]['purpose'] = 'Different requested plan.'
    else:
        value['allow_deterministic_continuation'] = False
    with pytest.raises(ValueError, match='cache miss'):
        CACHE.validate_request(packet, question, value)


def test_cache_entry_never_loads_key_and_checks_native_origin(monkeypatch, tmp_path):
    from pathlib import Path
    from pdf_tools import ROOT, save_private
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT / '.local') as temporary:
        root = Path(temporary)
        value = {'allow_deterministic_continuation': True}
        packet = {'question': 'A protocol request', 'plan': value,
                  'execution_version_sha256': 'current'}
        save_private(root / 'plan.json', value)
        save_private(root / 'evidence-packet.json', packet)
        called = []
        def origin(run, directory, cache, delivery):
            called.append(run)
            return packet, {'task': {'sources': {}}}, {}, 'native-event-hash'
        monkeypatch.setattr(CACHE.comparison, 'approved_origin', origin)
        monkeypatch.setenv('DEEPSEEK_API_KEY', '')
        result = CACHE.reuse(tmp_path, root, 'A protocol request', root / 'plan.json')
        assert called == [root] and result['model_requests'] == result['accounted_usd'] == 0
        assert result['research_quality'] == 'unreviewed'
