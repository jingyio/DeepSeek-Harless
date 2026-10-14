"""Explicit permission for a finite, witnessed mechanical preparation chain.

This declaration is a permission boundary, not a learned workflow. Actual
parameter edges and independent certification remain the compiler's job.
"""
import hashlib
import json
import re


def policy_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def validate_policy(policy):
    if (not isinstance(policy, dict)
            or set(policy) != {'schema_version', 'kind', 'steps'}
            or type(policy['schema_version']) is not int or policy['schema_version'] != 1
            or policy['kind'] != 'approved_plan_continuation'
            or not isinstance(policy['steps'], list) or len(policy['steps']) != 3):
        raise ValueError('invalid approved-plan continuation policy')
    tools = []
    for step in policy['steps']:
        if (not isinstance(step, dict) or set(step) != {'tool', 'param', 'receipt_field',
                'success_status', 'input_schema_sha256'}
                or any(not isinstance(step[k], str) or not step[k] for k in step)
                or not re.fullmatch(r'[a-f0-9]{64}', step['input_schema_sha256'])
                or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', step[k])
                       for k in ('param', 'receipt_field', 'success_status'))):
            raise ValueError('invalid continuation step')
        tools.append(step['tool'])
    if len(set(tools)) != 3:
        raise ValueError('continuation needs three distinct tools')
    return policy


def valid_granted_record(record, policy):
    """Validate the original trusted tool observation, never model-written text."""
    index = next((i for i, s in enumerate(policy['steps']) if s['tool'] == record.name), -1)
    if index < 0 or not record.eligible or not isinstance(record.observation, dict):
        return False
    out = record.observation
    grant = out.get('continuation_grant')
    step = policy['steps'][index]
    if (not isinstance(grant, dict) or set(grant) != {'schema_version', 'policy_sha256',
            'task_input_version', 'execution_version', 'plan_id', 'completed_steps', 'receipt'}
            or type(grant['schema_version']) is not int or grant['schema_version'] != 1
            or grant['policy_sha256'] != policy_digest(policy)
            or type(grant['completed_steps']) is not int or grant['completed_steps'] != index + 1
            or out.get('status') != step['success_status']
            or grant['task_input_version'] != out.get('task_sha256')
            or grant['execution_version'] != out.get('execution_version_sha256')
            or any(not isinstance(grant[k], str) or not re.fullmatch(r'[a-f0-9]{64}', grant[k])
                   for k in ('task_input_version', 'execution_version'))
            or not isinstance(grant['plan_id'], str)
            or not re.fullmatch(r'source-[a-f0-9]{32}', grant['plan_id'])
            or not isinstance(grant['receipt'], str)
            or not re.fullmatch(r'(?:source|dataset|result)-[a-f0-9]{32}', grant['receipt'])
            or grant['receipt'] != out.get(step['receipt_field'])
            or not isinstance(record.arguments, dict)
            or set(record.arguments) != {step['param']}
            or (index == 0 and record.arguments[step['param']] != grant['plan_id'])):
        return False
    return True


def same_grant(left, right):
    a, b = left.observation['continuation_grant'], right.observation['continuation_grant']
    return all(a[k] == b[k] for k in ('policy_sha256', 'task_input_version',
                                      'execution_version', 'plan_id'))
