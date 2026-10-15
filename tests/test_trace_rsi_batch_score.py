"""完整请求计数的诊断回归，不是模型行为验收。"""
import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'scripts/paper-rsi-batch-shadow.py'
spec = importlib.util.spec_from_file_location('batch_score', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    blocks = [{'type': 'tool-call', 'id': 'a', 'name': 'check', 'arguments': '{"input_id":"live"}'},
              {'type': 'tool-call', 'id': 'b', 'name': 'read', 'arguments': {}}]
    prediction = {'expected_tools': [{'tool': 'check', 'arguments': {'input_id': 'live'}},
                                     {'tool': 'read', 'arguments': {}}],
                  'expected_results': [{'output': True}, {'report': 'current'}]}
    return blocks, prediction, {'a': {'output': True}, 'b': {'report': 'current'}}


def test_requires_every_declared_operation_and_result_in_order():
    blocks, prediction, results = fixture()
    assert module.ordered_outcome(blocks, prediction, results, True) == 'strict_whole_request'
    assert module.ordered_outcome(blocks[::-1], prediction, results, True) == 'different_whole_tool_batch'
    assert module.ordered_outcome(blocks[:1], prediction, results, True) == 'different_whole_tool_batch'
    results['b'] = {'report': 'stale'}
    assert module.ordered_outcome(blocks, prediction, results, True) == 'different_result_or_version'


def test_text_failure_or_absent_live_verification_never_counts_as_strict():
    blocks, prediction, results = fixture()
    assert module.ordered_outcome(blocks, prediction, results, False) == 'live_batch_unverified'
    blocks.insert(0, {'type': 'text', 'text': '新的判断不能抹去'})
    assert module.ordered_outcome(blocks, prediction, results, True) == 'whole_batch_match_text_requires_review'
    assert module.ordered_outcome(blocks, None, results, True) == 'no_prediction'
    del results['b']
    assert module.ordered_outcome(blocks, prediction, results, True) == 'different_result_or_version'


def test_cost_mapping_rejects_retries_subagents_and_missing_usage():
    rows = [{'ordinal': 1, 'outcome': 'strict_whole_request'}, {'ordinal': 2, 'outcome': 'no_prediction'}]
    files = [Path('202.json'), Path('201.json')]
    ledger = [{'request_id': 201, 'observed_peak_usd': 0.1, 'response_status': 200},
              {'request_id': 202, 'observed_peak_usd': 0.9, 'response_status': 200}]
    value = module.matched_request_cost(rows, ledger, files, 2)
    assert value['matched_request_observed_usd'] == 0.1
    assert value['matched_observed_cost_fraction'] == 0.1
    assert value['actual_cost_saved_usd'] == 0
    assert module.matched_request_cost(rows, ledger, files, 3)['matched_request_observed_usd'] is None
    ledger[0]['observed_peak_usd'] = None
    assert module.matched_request_cost(rows, ledger, files, 2)['matched_request_observed_usd'] is None
