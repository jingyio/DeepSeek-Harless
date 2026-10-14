"""Offline approval witnesses, schema binding and no retroactive authorization."""
import copy
import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from src.adapters.dsh_trajectory import DshTrace, ToolRecord
from src.adapters.tool_contract_loader import parse_tool_contracts
from src.adapters.tool_schema_contracts import bind_mcp_descriptions
from src.motif_core.offline.continuation_policy import policy_digest
from src.motif_core.offline.chain_compiler import compile_witnessed_chain_motif, certify_witnessed_chain_motif
from src.motif_core.offline.trace_compiler import contract_signature
from src.motif_core.offline.library_builder import library_from_certified

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('grant_test_exporter', ROOT / 'scripts/export-online-motif-manifest.py')
EXPORT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EXPORT)


def fixture():
    raw = json.loads((ROOT / 'scenarios/literature-notes/pdf-evidence-contracts.json').read_text())
    contracts = parse_tool_contracts(raw)
    policy = next(c.continuation_policy for c in contracts.values() if c.continuation_policy)
    steps = policy['steps']

    def trace(label):
        char = {'A': 'a', 'B': 'b', 'C': 'c'}[label]
        plan_id = 'source-' + char * 32
        ids = ['source-' + ('1' + char) * 16, 'dataset-' + char * 32, 'result-' + char * 32]
        rows = []
        for i, s in enumerate(steps):
            grant = {'schema_version': 1, 'policy_sha256': policy_digest(policy),
                     'task_input_version': char * 64, 'execution_version': char * 64,
                     'plan_id': plan_id, 'completed_steps': i + 1, 'receipt': ids[i]}
            output = {'status': s['success_status'], s['receipt_field']: ids[i],
                      'task_sha256': char * 64, 'execution_version_sha256': char * 64,
                      'continuation_grant': grant}
            provenance = None if i == 0 else {s['param']: {'from_tool': steps[i - 1]['tool'],
                                                          'from_field': steps[i - 1]['receipt_field']}}
            rows.append(ToolRecord(s['tool'], {s['param']: plan_id if i == 0 else ids[i - 1]},
                                   policy_digest(output), True, 'eligible_read', i, output, provenance))
        return DshTrace(label, tuple(rows), (tuple(s['tool'] for s in steps),), 'task-' + label)
    first, second = [dict(status='candidate_only', from_tool=steps[i - 1]['tool'],
        from_field=steps[i - 1]['receipt_field'], to_tool=steps[i]['tool'], to_param=steps[i]['param'],
        source_trace_ids=['A', 'B']) for i in (1, 2)]
    return raw, contracts, policy, first, second, [trace(l) for l in ('A', 'B', 'C')]


def test_witnessed_grant_policy_is_bound_to_certificate_and_export():
    raw, contracts, policy, first, second, traces = fixture()
    compiled = compile_witnessed_chain_motif(first, second, traces[:2], contracts)
    certified = certify_witnessed_chain_motif(compiled, traces[2], contracts)
    fields = {s['tool']: 'execution_version_sha256' for s in policy['steps']}
    manifest = EXPORT.export_manifest(library_from_certified([certified]), raw, version_fields=fields)
    assert manifest['artifacts'][0]['continuation_policy_digest'] == policy_digest(policy)
    assert all(manifest['contracts'][s['tool']]['continuation_policy'] == policy for s in policy['steps'])
    changed = copy.deepcopy(raw)
    changed[policy['steps'][1]['tool']]['continuation_policy']['steps'][1]['success_status'] = 'any_status'
    assert contract_signature(certified['tools'], parse_tool_contracts(changed)) != certified['contract_signature']
    with pytest.raises(ValueError): EXPORT.export_manifest(library_from_certified([certified]), changed, version_fields=fields)


@pytest.mark.parametrize('bad', ['missing', 'task', 'plan', 'version', 'status', 'receipt', 'policy', 'step'])
def test_training_and_heldout_cannot_certify_missing_or_inconsistent_grants(bad):
    raw, contracts, policy, first, second, traces = fixture()
    compiled = compile_witnessed_chain_motif(first, second, traces[:2], contracts)
    for index in (1, 2):
        damaged = copy.deepcopy(traces[index])
        out = damaged.records[1].observation
        if bad == 'missing': del out['continuation_grant']
        elif bad == 'status': out['status'] = 'needs_review'
        elif bad == 'step': out['continuation_grant']['completed_steps'] = 3
        else:
            key = {'task': 'task_input_version', 'plan': 'plan_id', 'version': 'execution_version',
                   'receipt': 'receipt', 'policy': 'policy_sha256'}[bad]
            out['continuation_grant'][key] = 'source-' + '9' * 32 if bad in ('plan', 'receipt') else '9' * 64
        with pytest.raises(ValueError):
            if index == 1: compile_witnessed_chain_motif(first, second, [traces[0], damaged], contracts)
            else: certify_witnessed_chain_motif(compiled, damaged, contracts)


def test_old_contract_signature_is_unchanged_and_old_traces_cannot_gain_permission():
    raw, contracts, policy, first, second, traces = fixture()
    old_raw = copy.deepcopy(raw)
    for c in old_raw.values(): c.pop('continuation_policy', None)
    old = parse_tool_contracts(old_raw)
    tools = [s['tool'] for s in policy['steps']]
    assert contract_signature(tools, old) == contract_signature(tools,
        {k: replace(v, continuation_policy=None) for k, v in contracts.items()})
    old_artifact = certify_witnessed_chain_motif(compile_witnessed_chain_motif(first, second, traces[:2], old), traces[2], old)
    with pytest.raises(ValueError): EXPORT.export_manifest(library_from_certified([old_artifact]), raw)


def test_policy_rejects_unbounded_defaults_and_schema_drift():
    raw, contracts, policy, *_ = fixture()
    name = policy['steps'][0]['tool']
    bad = copy.deepcopy(raw); bad[name]['default_params'] = [['unbounded', 'anything']]
    with pytest.raises(ValueError): parse_tool_contracts(bad)
    schemas = [{'name': n, 'description': c.description, 'inputSchema': {'type': 'object',
                'required': list(c.required_params), 'properties': {p: {'type': 'string'} for p in c.required_params}}}
               for n, c in contracts.items()]
    with pytest.raises(ValueError, match='schema changed'): bind_mcp_descriptions(contracts, schemas)
