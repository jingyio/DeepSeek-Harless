"""Re-certify a historical operation DAG without rewriting its original proof.

Historical decisions propose the graph only. A current native witness and two
independent actual executions must pass the ordinary v2 admission contract.
This offline service does not expand the online runtime or its permissions.
"""
from __future__ import annotations
import copy
import json
import os
from contextlib import nullcontext
from pathlib import Path

from src.adapters.continuous_rsi import ROOT, load_config, private, source_map, state_event, writer_lock
from src.adapters.continuous_motif_learning import frame, run_material, verify_operation_execution, RecoveryPending
from src.adapters.mcp_learning import adapter
from src.motif_core.offline.experience_registry import (
    ExperienceRegistry, check_motif_certificate, digest, durable, read, sha,
)
from src.motif_core.offline.operation_graph import certify_graph, witnesses


def native_view(f, nodes):
    """Prove an exact contiguous prefix of an actual native connected witness.

The complete task/events remain sealed and are still checked by frame(). Only
the graph observation ends at its final result; intervening barriers remain.
"""
    matches = [w for w in witnesses(f['rows'], f['tools'], f['scope'])
               if w['nodes'][:len(nodes)] == nodes]
    if not matches:
        raise ValueError('current native decisions did not demonstrate historical graph')
    w = matches[0]
    calls = w['calls'][:len(nodes)]
    used = [r for r in f['rows'] if r['call_id'] in calls]
    if len(used) != len(nodes) or any(r.get('generated') or r.get('message_seq') is None for r in used):
        raise ValueError('re-certification requires every node to be a native model decision')
    end = used[-1]['result_seq']
    view = {**f, 'rows': [r for r in f['rows'] if r['call_seq'] <= end], 'parents': []}
    proof = {'format': 'sss-native-connected-prefix-v1', 'calls': calls,
             'view_end_result_seq': end, 'full_events_sha256': f['record']['events_sha256'],
             'full_native_witness_calls': w['calls'], 'raw_events_unchanged': True}
    return view, proof


def rebuild(old, f, provenance):
    """Keep the historical nodes/bindings; replace declarations, never evidence."""
    nodes = copy.deepcopy(old['artifact']['nodes'])
    if old.get('format')=='sss-operation-flow-v3':
        a=old['artifact'];tools={n['tool']:f['tools'][n['tool']] for n in nodes}
        if not 2<=len(nodes)<=16 or any(tools[n]['contract'].get('control_fields',{})!=a['tool_contracts'][n]['contract'].get('control_fields',{}) for n in tools):
            raise ValueError('historical control domains changed')
        for e in a['edges']:
            if e['to'] is not None and (not tools[e['to']]['contract']['auto_continue'] or set(e['bindings'])!=set(tools[e['to']]['schema'].get('required',[]))
                or any(p not in tools[e['from']]['contract']['exports'] for p in e['bindings'].values())):
                raise ValueError('historical control-flow transfer changed')
        return {**{k:copy.deepcopy(v) for k,v in a.items() if k not in ('certified_digest','validation_task_fingerprint','validation_edges')},
                'status':'compiled_candidate','tool_contracts':tools,'execution_version':f['scope']['execution_version'],'recertification_provenance':provenance,
                'interleaving_contracts':{n:t for n,t in f['tools'].items() if t['contract']['effect']=='read' and (t['contract'].get('flow_interleaving') or t['contract'].get('safe_interleaving'))}}
    if not 2 <= len(nodes) <= 8:
        raise ValueError('historical graph outside current node bounds')
    for i, node in enumerate(nodes):
        tool = f['tools'].get(node['tool'])
        if not tool:
            raise ValueError('historical tool has no current learning contract')
        if i == 0:
            if node['bindings']:
                raise ValueError('historical root must remain a native semantic decision')
            continue
        if not tool['contract']['auto_continue'] or set(node['bindings']) != set(tool['schema'].get('required', [])):
            raise ValueError('historical continuation no longer satisfies the current tool schema')
        for binding in node['bindings'].values():
            parent = binding['node']
            if type(parent) is not int or not 0 <= parent < i:
                raise ValueError('historical parameter binding is not a DAG edge')
            if binding['path'] not in f['tools'][nodes[parent]['tool']]['contract']['exports']:
                raise ValueError('historical parameter is no longer an exported field')
    a = old['artifact']
    return {'kind': 'learned_mcp_operation_dag', 'status': 'compiled_candidate', 'nodes': nodes,
            'tool_contracts': {n['tool']: f['tools'][n['tool']] for n in nodes},
            'max_nodes': 8, 'execution_version': f['scope']['execution_version'],
            'certification_contract': 'sss-operation-certification-v2',
            'interleaving_contracts': {n: t for n, t in f['tools'].items()
                                     if t['contract'].get('safe_interleaving') and t['contract']['effect'] == 'read'},
            'request_lane_contracts':{n:t for n,t in f['tools'].items() if t['contract'].get('request_lane')=='sss-prepared-request-v1'}
                if f['tools'][nodes[0]['tool']]['contract'].get('request_lane')=='sss-prepared-request-v1' else {},
            'source_task_fingerprints': a['source_task_fingerprints'],
            'witnesses': copy.deepcopy(a['witnesses']),
            'recertification_provenance': provenance}


def verify_read_checks(record, template):
    """Additional frozen output-read goals; never weaken the product acceptance."""
    checks_file = Path(template)/'recertification-checks.json'
    if not checks_file.exists():
        return
    spec = read(Path(record['origin'])/'task.json')
    reads = [read(p) for p in (Path(record['delivery'])/'reads').glob('*.json')]
    for check in read(checks_file)['complete_reads']:
        expected = spec['initial_tree']['workspace']['files'][check['source']]
        if not any(r.get('path') == 'workspace/'+check['path'] and r.get('sha256') == expected
                   and r.get('status') == 'readable' and r.get('truncated') is False for r in reads):
            raise ValueError('frozen complete output read missing: '+check['path'])


def recertify(config_file, old_policy, old_certificate, template, job, *, worker_locked=False):
    cfg = load_config(config_file)
    if cfg.get('adapter') != 'management_v3' or cfg['provider_mode'] != 'real' or cfg['mode'] != 'learn':
        raise ValueError('re-certification requires the existing real management learning budget')
    root = Path(cfg['state_root']); job = private(job); template = private(template)
    if worker_locked and (not (root/'worker.lock').exists() or read(root/'worker.lock').get('pid') != os.getpid()):
        raise ValueError('automatic re-certification requires the original worker owner')
    old_policy = private(old_policy); old_certificate = private(old_certificate)
    job.mkdir(parents=True, exist_ok=True, mode=0o700)
    old = read(old_policy)
    is_flow=old.get('format')=='sss-operation-flow-v3'
    cert_contract='sss-operation-certification-v3' if is_flow else 'sss-operation-certification-v2'
    if old.get('format') not in ('sss-operation-graph-v1', 'sss-operation-graph-v2','sss-operation-flow-v3'):
        raise ValueError('legacy collection/reentry IR requires a separate functional migration')
    if old['policy_digest'] != digest({k: v for k, v in old.items() if k != 'policy_digest'}):
        raise ValueError('historical policy digest changed')
    check_motif_certificate(old, old_certificate, sha(old_policy))
    template_spec = read(template/'task.json')
    if template_spec.get('role') in ('holdout', 'evaluate', 'benchmark'):
        raise ValueError('final evaluation cannot be used for re-certification')
    frozen = {'old_policy_file': str(old_policy), 'old_policy_sha256': sha(old_policy),
              'old_certificate_file': str(old_certificate), 'old_certificate_sha256': sha(old_certificate),
              'source_code': source_map(), 'recertifier_sha256': sha(__file__),
              'template': {str(p.relative_to(template)): sha(p) for p in sorted(template.rglob('*')) if p.is_file()},
              'config_sha256': sha(config_file), 'holdout_used': False,
              'historical_evidence_role': 'candidate_provenance_only',
              'certification_contract': cert_contract}
    lock_file = job/'candidate-lock.json'
    if lock_file.exists():
        if read(lock_file) != frozen:
            raise ValueError('frozen re-certification provenance/source/material/config changed')
    else:
        durable(lock_file, frozen, exclusive=True)
    if (job/'activation.json').exists():
        return read(job/'activation.json')
    if (job/'failure.json').exists():
        return read(job/'failure.json')

    def guard():
        if source_map() != frozen['source_code'] or sha(__file__) != frozen['recertifier_sha256']:
            raise ValueError('source changed during re-certification')
        for p, h in ((old_policy, frozen['old_policy_sha256']), (old_certificate, frozen['old_certificate_sha256']),
                     (Path(config_file), frozen['config_sha256'])):
            if sha(p) != h:
                raise ValueError('frozen re-certification input changed')
        if {str(p.relative_to(template)): sha(p) for p in sorted(template.rglob('*')) if p.is_file()} != frozen['template']:
            raise ValueError('frozen material template changed')

    try:
        guard()
        empty = job/'native-empty-registry.json'
        if not empty.exists():
            state = {'schema_version': 1, 'format': 'sss-experience-registry-v1', 'generation': 0,
                     'parent_digest': None, 'reason': 'independent native re-certification',
                     'automatic_selection_uses_profile_id': False, 'entries': []}
            durable(empty, {**state, 'registry_digest': digest(state)}, exclusive=True)
        origin = {'origin': str(template)}
        native = run_material(cfg, job, 'native-cert', origin, 'native_certification', empty)
        f = frame(native)
        verify_read_checks(native, template)
        if is_flow:view,prefix=f,{'format':'sss-native-control-flow-v3','full_events_sha256':f['record']['events_sha256'],'raw_events_unchanged':True}
        else:view, prefix = native_view(f, old['artifact']['nodes'])
        compiled = rebuild(old, f, {'old_policy_digest': old['policy_digest'],
                                   'old_payload_sha256': frozen['old_policy_sha256'],
                                   'old_certificate_sha256': frozen['old_certificate_sha256'],
                                   'candidate_lock_sha256': sha(lock_file),
                                   'recertifier_sha256': frozen['recertifier_sha256'], 'native_prefix': prefix})
        if is_flow:
            from src.motif_core.offline.control_flow import certify_flow
            policy=certify_flow(compiled,view)
        else:policy = certify_graph(compiled, view)
        for name, value in (('compiled.json', compiled), ('policy.json', policy), ('native-prefix.json', prefix)):
            if (job/name).exists():
                if read(job/name) != value:
                    raise ValueError('resumed re-certification policy differs')
            else:
                durable(job/name, value, exclusive=True)
        policy_file = job/'policy.json'; registry = ExperienceRegistry(root/'registry')
        relative, raw = registry.object(policy_file)
        runtime = source_map(adapter('management_v3').runtime_sources())
        manifest = {'schema_version': 1, 'format': 'sss-experience-registry-v1', 'generation': 0,
                    'parent_digest': None, 'reason': 'isolated independent re-certification execution',
                    'automatic_selection_uses_profile_id': False,
                    'entries': [{'entry_id': policy['policy_digest'], 'artifact_digest': policy['policy_digest'],
                                 'kind': 'operation_graph', 'payload': relative, 'sha256': raw,
                                 'runtime_source': runtime, 'state': 'candidate', 'activated_generation': 1}]}
        manifest['registry_digest'] = digest(manifest)
        candidate_view = job/'certification-registry.json'
        if not candidate_view.exists():
            durable(candidate_view, manifest, exclusive=True)
        elif read(candidate_view) != manifest:
            raise ValueError('isolated candidate registry changed')
        reviews = []; failures = []
        for i in (0, 1):
            guard()
            record = run_material(cfg, job, 'execute-cert-'+str(i), origin, 'candidate_certification', candidate_view)
            verify_read_checks(record, template)
            audit_file = Path(record['run_dir'])/'experience-audit.jsonl'
            audit = [json.loads(l) for l in audit_file.read_text().splitlines()]
            if (not verify_operation_execution(policy, record, audit) or not record['accepted']
                    or record['policy_digest'] != policy['policy_digest'] or record['metrics'].get('acceptance_repairs')):
                failures.append({'session_id': record['session_id'], 'reason': 'actual guarded graph and clean delivery required'})
            file = root/'records'/(record['session_id']+'.json')
            reviews.append({'role': 'candidate_certification', 'task_fingerprint': record['task_fingerprint'],
                            'record_file': str(file), 'record_sha256': sha(file), 'audit_sha256': sha(audit_file),
                            'completion_count': sum(r['kind'] == 'operation_graph_complete' for r in audit)})
        native_file = root/'records'/(native['session_id']+'.json')
        certificate = {'status': 'rejected' if failures else 'certified_motif_v3' if is_flow else 'certified_motif_v2', 'kind': 'operation_graph',
                       'policy_digest': policy['policy_digest'], 'payload_sha256': sha(policy_file),
                       'candidate_lock_file': str(lock_file), 'candidate_lock_sha256': sha(lock_file),
                       'native_review': {'role': 'native_certification', 'task_fingerprint': native['task_fingerprint'],
                                         'record_file': str(native_file), 'record_sha256': sha(native_file)},
                       'reviews': reviews, 'failures': failures, 'holdout_used': False,
                       'quality_and_permission_required': True, 'net_benefit_required': False,
                       'runtime_source': runtime, 'material_quality_contract': 'sss-management-quality-v7',
                       'certification_contract': cert_contract}
        if not (job/'certificate.json').exists():
            durable(job/'certificate.json', certificate, exclusive=True)
        if failures:
            raise ValueError('independent actual re-certification rejected; old and failed proofs retained')
        guard()
        entry = registry.entry('operation_graph', policy_file, runtime, job/'certificate.json')
        with (nullcontext() if worker_locked else writer_lock(root, 'worker')):
            state = registry.load()
            existing = next((e for e in state['entries'] if e['entry_id'] == entry['entry_id']), None)
            if existing:
                if any(existing.get(k) != entry[k] for k in entry):
                    raise ValueError('existing re-certification activation changed')
                file = root/'registry'/read(root/'registry/current.json')['file']
            else:
                file = registry.publish([entry], reason='historical graph re-certified with current independent native/actual proofs', expected=state['generation'])
        activation = {'status': 'activated', 'kind': 'operation_graph', 'policy_digest': policy['policy_digest'],
                      'old_policy_digest': old['policy_digest'], 'registry_file': str(file), 'registry_sha256': sha(file),
                      'certificate_sha256': sha(job/'certificate.json'), 'holdout_used': False,
                      'opportunity_key': digest({'nodes': compiled['nodes'], 'catalog': f['tools'], 'execution_version': f['scope']['execution_version']})}
        durable(job/'activation.json', activation, exclusive=True)
        state_event(root, 'historical_motif_recertified', activation)
        return activation
    except RecoveryPending:
        raise
    except (ValueError, KeyError, RuntimeError, StopIteration, OSError) as error:
        failure = {'status': 'rejected', 'reason': type(error).__name__+': '+str(error),
                   'candidate_inactive': True, 'old_policy_digest': old['policy_digest'],
                   'failures_and_costs_retained': True, 'holdout_used': False}
        durable(job/'failure.json', failure, exclusive=True)
        state_event(root, 'historical_motif_recertification_rejected', {'job': str(job), **failure})
        return failure
