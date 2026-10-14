"""只读诊断：保留完整请求分母，文字审阅不能升级为严格整请求替代。

用法：python3 scripts/audit-trace-control-text.py RUN [RUN ...] [--reviews FILE]
输出仅含摘要、计数及人工类别；不输出文字、参数、结果或私人路径。
人工 reviews 用输出中的四个摘要及 request_ordinal 绑定原始证据。
本脚本不判断自然语言等价、不调用模型，也不执行候选或修改运行产物。
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

CATEGORIES = {
    'schedule_only',
    'prior_receipt_then_schedule',
    'prior_source_facts_then_schedule',
    'revision_decision_or_new_content',
    'final_conclusion_or_quality_claims',
    'mixed_or_unresolved',
    'unreviewed',
}
REVIEW_FIELDS = {
    'events_sha256', 'audit_sha256', 'request_ordinal',
    'message_sha256', 'text_sha256', 'category',
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('non_json_number')))


def read_jsonl(path):
    # splitlines() 会把合法 JSON 字符串中的 U+2028/U+2029 误当记录边界。
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').split('\n')
            if line.strip()]


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def review_key(row):
    return tuple(row.get(k) for k in (
        'events_sha256', 'audit_sha256', 'request_ordinal', 'message_sha256', 'text_sha256'))


def load_reviews(path):
    if path is None:
        return {}
    data = read_json(path)
    if set(data) != {'schema_version', 'reviews'} or data['schema_version'] != 1:
        raise ValueError('review_schema_invalid')
    indexed = {}
    for row in data['reviews']:
        if not isinstance(row, dict) or set(row) != REVIEW_FIELDS or row['category'] not in CATEGORIES:
            raise ValueError('review_row_invalid')
        if type(row['request_ordinal']) is not int or row['request_ordinal'] < 1:
            raise ValueError('review_ordinal_invalid')
        key = review_key(row)
        if key in indexed:
            raise ValueError('review_duplicate')
        indexed[key] = row['category']
    return indexed


def parse_result(block):
    content = block.get('content', [])
    if block.get('isError') is not False or not content or any(x.get('type') != 'text' for x in content):
        return None, False
    try:
        return json.loads(''.join(x.get('text', '') for x in content)), True
    except (ValueError, TypeError):
        return None, False


def request_history_verified(messages, request_files):
    """用下一真实请求保存的 assistant 历史复核响应顺序；不裁剪文字。"""
    try:
        inputs = [read_json(p) for p in sorted(request_files, key=lambda p: int(p.stem))]
        for (_, event), request in zip(messages[:-1], inputs[1:]):
            prior = [x for x in request['messages'] if x.get('role') == 'assistant'][-1]
            blocks = event['data']['message']['content']
            texts = ''.join(x.get('text', '') for x in blocks if x.get('type') == 'text')
            calls = [{'id': x['id'], 'name': x['name'], 'arguments': json.loads(x['arguments'])
                      if isinstance(x['arguments'], str) else x['arguments']}
                     for x in blocks if x.get('type') == 'tool-call']
            saved = [{'id': x['id'], 'name': x['function']['name'],
                      'arguments': json.loads(x['function']['arguments'])}
                     for x in prior.get('tool_calls', [])]
            if (prior.get('content') or '') != texts or canonical(calls) != canonical(saved):
                return False
        return True
    except (ValueError, KeyError, TypeError, IndexError):
        return False


def audit_run(run, reviews=None):
    run = Path(run)
    config = read_json(run / 'config.json')
    metrics = read_json(run / 'metrics.json')
    if config.get('mode') not in ('baseline', 'shadow'):
        raise ValueError('baseline_or_shadow_required')
    sid = config.get('session_id')
    if not isinstance(sid, str) or not sid:
        raise ValueError('root_session_required')
    raw_events = read_jsonl(run / 'events.jsonl')
    events = [r['event'] for r in raw_events if r.get('sessionId', r.get('session_id')) == sid]
    messages = [(i, e) for i, e in enumerate(events) if e.get('type') == 'assistant/message']
    actual_requests = metrics.get('actual_requests')
    if type(actual_requests) is not int or actual_requests < 1:
        raise ValueError('actual_request_count_required')
    request_files = list((run / 'requests').glob('*.json'))
    count_complete = actual_requests == len(messages) == len(request_files)
    history_verified = count_complete and request_history_verified(messages, request_files)
    boundary_complete = count_complete and history_verified
    audit_path = run / 'work/shadow.jsonl'
    audits = read_jsonl(audit_path) if audit_path.exists() else []
    if config['mode'] == 'shadow' and not audits:
        raise ValueError('shadow_audit_required')
    if any(a.get('session_id') != sid for a in audits):
        raise ValueError('audit_session_mismatch')
    if any(a.get('execution_authorized') is True for a in audits):
        raise ValueError('execution_authorized_not_shadow')
    predictions = [a for a in audits if a.get('kind') in ('prediction', 'deferred')]
    prospective_boundaries = config['mode'] == 'shadow' and (
        [p.get('request_ordinal') for p in predictions] == list(range(1, len(messages) + 1)))
    if config['mode'] == 'shadow' and not prospective_boundaries:
        raise ValueError('prospective_boundaries_incomplete')
    ehash = file_sha(run / 'events.jsonl')
    ahash = file_sha(audit_path) if audits else None
    review_index = reviews or {}
    rows = []
    consumed_reviews = set()
    for ordinal, (event_index, message_event) in enumerate(messages, 1):
        content = message_event['data']['message']['content']
        texts = [x.get('text', '') for x in content if x.get('type') == 'text']
        has_text = any(t.strip() for t in texts)
        calls = [x for x in content if x.get('type') == 'tool-call']
        other_count = sum(x.get('type') not in ('text', 'tool-call') for x in content)
        try:
            actual = [{'tool':x['name'], 'arguments':json.loads(x['arguments'])
                       if isinstance(x['arguments'], str) else x['arguments']} for x in calls]
        except (KeyError, ValueError, TypeError):
            raise ValueError('tool_call_invalid') from None
        prediction = predictions[ordinal - 1].get('prediction') if prospective_boundaries else None
        outcome = 'no_prediction'
        if prediction:
            if prediction.get('execution_authorized') is True:
                raise ValueError('prediction_authorizes_execution')
            if canonical(actual) != canonical(prediction.get('expected_tools')):
                outcome = 'different_next_operation'
            elif len(calls) != 1:
                outcome = 'unsupported_result_contract'
            else:
                call_id = calls[0].get('id')
                # 结果必须在该请求之后、下个根 assistant 请求之前实际出现。
                end = messages[ordinal][0] if ordinal < len(messages) else len(events)
                blocks = [b for e in events[event_index + 1:end] if e.get('type') == 'tool/result'
                          for b in e.get('data', {}).get('message', {}).get('content', [])
                          if b.get('type') == 'tool-result' and b.get('toolCallId') == call_id]
                result, success = parse_result(blocks[0]) if len(blocks) == 1 else (None, False)
                verified = any(a.get('kind') == 'shadow_result' and a.get('request_ordinal') == ordinal
                               and a.get('call_id') == call_id and a.get('verified') is True for a in audits)
                if not success or canonical(result) != canonical(prediction.get('expected_result')):
                    outcome = 'different_result_or_version'
                elif not verified:
                    outcome = 'live_result_unverified'
                elif has_text or other_count:
                    outcome = 'local_match_text_requires_review'
                elif not boundary_complete:
                    outcome = 'local_match_incomplete_request_boundary'
                else:
                    outcome = 'strict_whole_request'
        row = {
            'events_sha256': ehash, 'audit_sha256': ahash, 'request_ordinal': ordinal,
            'message_sha256': digest(message_event['data']['message']), 'text_sha256': digest(texts),
            'has_text': has_text, 'text_chars': sum(map(len, texts)), 'tool_count': len(calls),
            'tools_sha256': digest(actual), 'other_block_count': other_count, 'outcome': outcome,
            'manual_category': 'unreviewed', 'deterministic_text_certified': False,
        }
        key = review_key(row)
        if key in review_index:
            row['manual_category'] = review_index[key]
            consumed_reviews.add(key)
        rows.append(row)
    matched = [r for r in rows if r['outcome'] in (
        'strict_whole_request', 'local_match_text_requires_review', 'local_match_incomplete_request_boundary')]
    strict = sum(r['outcome'] == 'strict_whole_request' for r in rows)
    return {
        'run_id': 'run-' + ehash[:12], 'mode': config['mode'],
        'events_sha256': ehash, 'audit_sha256': ahash,
        'actual_requests': actual_requests, 'root_messages': len(messages),
        'saved_request_inputs': len(request_files), 'complete_request_boundaries': boundary_complete,
        'request_history_chain_verified': history_verified,
        'prospective_boundaries_recorded': prospective_boundaries,
        'prospective_timing_independently_proven': False,
        'matching_local_operation': len(matched), 'strict_whole_request': strict,
        'strict_ratio': strict / actual_requests,
        'actual_model_skips': metrics.get('actual_model_skips'),
        'manual_categories': dict(Counter(r['manual_category'] for r in rows)),
        'matched_manual_categories': dict(Counter(r['manual_category'] for r in matched)),
        'deterministic_text_certified': 0,
        'semantic_quality': 'not_established_by_this_audit',
        'rows': rows,
    }, consumed_reviews


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--reviews', type=Path)
    args = parser.parse_args()
    try:
        reviews = load_reviews(args.reviews)
        results = [audit_run(run, reviews) for run in args.runs]
        used = set().union(*(used for _, used in results))
        if set(reviews) != used:
            raise ValueError('review_evidence_drift_or_unselected_run')
        payload = {'schema_version': 1, 'diagnostic_only': True,
                   'manual_review_never_upgrades_strict': True,
                   'runs': [r for r, _ in results]}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError):
        # 异常可能包含原文/路径，公共诊断仅输出稳定代码。
        print(json.dumps({'passed':False, 'error':'audit_input_or_evidence_invalid'}))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
