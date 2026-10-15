"""有界输出特征上的离线状态条件学习；不是模型生成工具，也不授予执行。

特征/搜索算法由工程提供。值及组合从已记录的正反状态决定；诊断样本
必须与真实轨迹分列。未见分支、不可分状态或独立认证失败不发布守卫。
"""
from itertools import combinations
import math


def typed_features(output):
    if type(output) is not dict or len(output) > 64:
        raise ValueError('bounded_output_object_required')
    result = {}
    for key, value in sorted(output.items()):
        if not isinstance(key, str) or not key or len(key) > 128 or key in ('__proto__', 'constructor', 'prototype'):
            raise ValueError('safe_output_field_required')
        if type(value) is bool:
            result[key + ':true'] = value
        elif type(value) is list and len(value) <= 2000:
            result[key + ':empty'] = not value
        elif type(value) in (int, float) and math.isfinite(value):
            result[key + ':zero'] = value == 0
    return result


def allows(conditions, output):
    try:
        features = typed_features(output)
    except (ValueError, TypeError):
        return False
    if type(conditions) is not list or not 1 <= len(conditions) <= 8:
        return False
    seen = set()
    for condition in conditions:
        if (type(condition) is not dict or set(condition) != {'feature', 'equals'} or
                type(condition['feature']) is not str or type(condition['equals']) is not bool or
                condition['feature'] in seen or condition['feature'] not in features or
                features[condition['feature']] != condition['equals']):
            return False
        seen.add(condition['feature'])
    return True


def learn_conjunction(samples, max_terms=4):
    if type(samples) is not list or not 2 <= len(samples) <= 2000 or not 1 <= max_terms <= 8:
        raise ValueError('bounded_guard_training_required')
    if any(type(s.get('allowed')) is not bool for s in samples):
        raise ValueError('explicit_boolean_labels_required')
    positives = [typed_features(s['output']) for s in samples if s['allowed']]
    negatives = [typed_features(s['output']) for s in samples if not s['allowed']]
    if not positives or not negatives:
        return {'status': 'insufficient_classes', 'conditions': None}
    candidates = [{'feature': key, 'equals': value} for key, value in sorted(positives[0].items())
                  if all(p.get(key) == value for p in positives)]
    # Irrelevant constants cannot help separate a negative, and excluding them
    # keeps exhaustive search bounded without selecting a domain-specific field.
    candidates = [c for c in candidates if any(n.get(c['feature']) != c['equals'] for n in negatives)]
    if len(candidates) > 24:
        return {'status': 'search_space_exceeded', 'conditions': None}
    for size in range(1, min(max_terms, len(candidates)) + 1):
        for subset in combinations(candidates, size):
            conditions = list(subset)
            if all(not allows(conditions, s['output']) for s in samples if not s['allowed']):
                return {'status': 'candidate', 'conditions': conditions}
    return {'status': 'not_separable', 'conditions': None}


def certify_conditions(conditions, heldout):
    if type(heldout) is not list or not heldout or any(type(s.get('allowed')) is not bool for s in heldout):
        raise ValueError('independent_guard_cases_required')
    failures = [{'case_id': s['case_id'], 'expected': s['allowed'], 'actual': allows(conditions, s['output'])}
                for s in heldout if allows(conditions, s['output']) != s['allowed']]
    return {'status': 'passed' if not failures else 'failed', 'cases': len(heldout), 'failures': failures,
            'scope': 'diagnostic_state_classification_not_model_or_task_quality'}
