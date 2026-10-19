"""Synthetic diagnostics: archival imports never substitute for current proof."""
import copy
import json
from pathlib import Path
import pytest
from src.adapters import experience_library as lib, continuous_rsi as rsi
from src.adapters import continuous_motif_learning as learner_module
from src.adapters import management_backup as backup
from src.motif_core.offline.experience_registry import ExperienceRegistry, digest, durable, read, sha
from src.motif_core.offline.operation_graph import discover_graphs, certify_graph
from test_operation_graph import frames


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(rsi, 'ROOT', tmp_path)
    monkeypatch.setattr(rsi, 'STATE_HOME', tmp_path/'.local/rsi')
    runtime = tmp_path/'runtime.py'; runtime.write_text('current fixture runtime')
    monkeypatch.setattr(lib, 'sources', lambda: {'runtime.py': sha(runtime)})
    monkeypatch.setattr(rsi, 'source_map', lambda *unused: {'runtime.py': sha(runtime)})
    tools = frames()[0]['tools']; monkeypatch.setattr(lib, 'current_contracts', lambda unused: tools)
    monkeypatch.setattr(lib, 'current_execution_version', lambda: 'a'*64)
    monkeypatch.setattr(backup, 'budget_snapshot', lambda unused: {'series': {'estimated_usd': 9}, 'pending_usd': 10,
                                                                'learning_spent_usd': 1, 'learning_reserved_usd': 0})
    root = tmp_path/'.local/rsi/daily-management-real-v3'
    ExperienceRegistry(root/'registry').publish(reason='empty fixture active view')
    durable(root/'pool.json', {'runs': {}})
    config = tmp_path/'.local/daily.json'
    cfg = {'state_root': str(root), 'adapter': 'management_v3', 'provider_mode': 'real', 'mode': 'learn',
           'config_file': str(config), 'limits': {'budget_usd': 5}, 'learning_cap_usd': 25, 'series_cap_usd': 1000}
    durable(config, cfg); cfg['config_sha256'] = sha(config)
    return tmp_path, root, cfg, runtime


def historical(home, label='first', *, current=True, template_role=None):
    project, root, cfg, runtime = home
    origin_root = project/'.local/rsi'/('archive-'+label)
    ff = frames(); candidate = discover_graphs(ff[:2])[0][0]
    policy = certify_graph(candidate['compiled'], ff[2])
    policy['artifact']['diagnostic_label'] = label
    policy['artifact']['certified_digest'] = digest({k: v for k, v in policy['artifact'].items() if k != 'certified_digest'})
    policy['policy_digest'] = digest({k: v for k, v in policy.items() if k != 'policy_digest'})
    payload = origin_root/'policy.json'; durable(payload, policy)
    lock = origin_root/'candidate-lock.json'; durable(lock, {'fixture': True})
    reviews = []
    for i, role in enumerate(('native_certification', 'candidate_certification', 'candidate_certification')):
        origin = origin_root/'runs'/str(i); work = origin/'pristine'; work.mkdir(parents=True)
        (work/'a.txt').write_text('original material '+str(i))
        spec = {'role': template_role or role, 'quality': {'version': lib.QUALITY, 'goal': {'state': 'frozen'}},
                'initial_snapshot': rsi.snapshot(work), 'external_roots': {}}
        durable(origin/'task.json', spec)
        audit = origin/'experience-audit.jsonl'; audit.write_text('{}\n')
        record = {'role': role, 'adapter': 'management_v3', 'accepted': True, 'lifecycle_verified': True,
                  'provider_mode': 'real', 'metrics': {'acceptance_repairs': 0}, 'observed_usage_complete': True,
                  'policy_digest': policy['policy_digest'], 'verified_motif_batches': 2, 'deferred': [],
                  'run_dir': str(origin), 'origin': str(origin), 'task_sha256': sha(origin/'task.json'),
                  'task_fingerprint': digest(label+'-independent-'+str(i))}
        file = origin_root/'records'/str(i); durable(file, record)
        reviews.append({'role': role, 'task_fingerprint': record['task_fingerprint'], 'record_file': str(file),
                        'record_sha256': sha(file), 'completion_count': 1, 'audit_sha256': sha(audit)})
    runtime_source = lib.sources() if current else {'runtime.py': '0'*64}
    cert = {'status': 'certified_motif_v2', 'holdout_used': False, 'policy_digest': policy['policy_digest'],
            'payload_sha256': sha(payload), 'candidate_lock_file': str(lock), 'candidate_lock_sha256': sha(lock),
            'quality_and_permission_required': True, 'material_quality_contract': lib.QUALITY,
            'certification_contract': lib.CERTIFICATION, 'runtime_source': runtime_source,
            'native_review': reviews[0], 'reviews': reviews[1:]}
    certfile = origin_root/'certificate.json'; durable(certfile, cert)
    registry = ExperienceRegistry(origin_root/'registry')
    entry = registry.entry('operation_graph', payload, runtime_source, certfile)
    registry.publish([entry], reason='synthetic independent certificate fixture')
    return registry, entry, policy, certfile


def drain(home, records=()):
    project, root, cfg, runtime = home
    with rsi.writer_lock(root, 'worker'):
        return lib.maintain(cfg, root, list(records))


def test_import_is_append_only_idempotent_and_grants_no_authority(home):
    project, root, cfg, runtime = home
    registry, entry, policy, cert = historical(home)
    before = {str(p): sha(p) for p in registry.root.rglob('*.json') if p.name != 'current.json'}
    first = lib.synchronize(cfg)
    assert len(first['entries']) == 1 and first['entries'][0]['compatibility']['state'] == 'recertification_required'
    assert not ExperienceRegistry(root/'registry').load()['entries']
    assert lib.synchronize(cfg)['generation'] == first['generation']
    registry.publish(disable=[entry['entry_id']], reason='original failure remains')
    second = lib.synchronize(cfg)
    assert second['generation'] > first['generation']
    assert {n: sha(n) for n in before} == before
    assert len(second['entries'][0]['origins']) == 2
    assert lib.load(root)['digest'] == second['digest']


def test_current_original_certificate_migrates_once_without_model_calls(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home)
    from src.adapters import management_recertification as recert
    monkeypatch.setattr(recert, 'recertify', lambda *a, **k: pytest.fail('compatible original certificate must not be charged again'))
    first = drain(home); assert len(first['imported']) == 1 and not first['attempted']
    state = ExperienceRegistry(root/'registry').load()
    assert len(state['entries']) == 1 and state['entries'][0]['state'] == 'active'
    assert lib.summary(root)['states'] == {'active': 1}
    second = drain(home)
    assert not second['imported'] and not second['attempted']
    assert ExperienceRegistry(root/'registry').load()['generation'] == state['generation']


def test_disabled_historical_version_cannot_be_reactivated_by_import(home, monkeypatch):
    project, root, cfg, runtime = home; registry, entry, policy, cert = historical(home)
    registry.publish(disable=[entry['entry_id']], reason='actual task failed')
    catalog = lib.synchronize(cfg)
    assert lib.eligible_certificate(root, catalog['entries'][0]) is None
    from src.adapters import management_recertification as recert
    calls = []
    def reject(*args, **kwargs):
        calls.append(True)
        return {'status': 'rejected'}
    monkeypatch.setattr(recert, 'recertify', reject)
    drain(home)
    assert calls and not ExperienceRegistry(root/'registry').load()['entries']


def test_runtime_invalidation_queues_current_recertification_and_retains_failure(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home)
    drain(home); original = ExperienceRegistry(root/'registry').load()
    runtime.write_text('new fixture runtime')
    from src.adapters import management_recertification as recert
    calls = []
    def reject(config, old, cert, template, job, **kw):
        assert kw['worker_locked'] and read(root/'worker.lock')['pid'] == __import__('os').getpid()
        calls.append(job)
        durable(job/'candidate-lock.json', {'source_code': lib.sources()})
        durable(job/'compiled.json', read(old)['artifact'])
        result = {'status': 'rejected', 'candidate_inactive': True, 'failures_and_costs_retained': True}
        durable(job/'failure.json', result)
        return result
    monkeypatch.setattr(recert, 'recertify', reject)
    result = drain(home); assert len(calls) == 1 and result['attempted'][0]['status'] == 'rejected'
    assert ExperienceRegistry(root/'registry').load()['entries'][0]['state'] == 'disabled'
    assert read(root/'registry/versions/000002.json') == original
    again = drain(home); assert len(calls) == 1 and not again['attempted']
    assert any(d['state'] == 'awaiting_new_evidence' for d in again['deferred'])
    runtime.write_text('another registered fixture runtime')
    drain(home); assert len(calls) == 2 and calls[0] != calls[1]


def test_incomplete_original_job_resumes_before_new_evidence_without_new_budget(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home, current=False)
    from src.adapters import management_recertification as recert
    calls = []
    def pending(config, old, cert, template, job, **kw):
        calls.append((job, str(template)))
        raise recert.RecoveryPending('original admission still pending')
    monkeypatch.setattr(recert, 'recertify', pending)
    first = drain(home); job = calls[0][0]; request = read(job/'request.json')
    assert first['attempted'][0]['status'] == 'pending'
    monkeypatch.setattr(backup, 'budget_snapshot', lambda _: {'series': {'estimated_usd': 999}, 'pending_usd': 5,
                                                           'learning_spent_usd': 24, 'learning_reserved_usd': 5})
    second = drain(home)
    assert second['attempted'][0]['status'] == 'pending' and calls[0] == calls[1]
    assert read(job/'request.json') == request and not (job/'failure.json').exists()
    runtime.write_text('source changed while original job was pending')
    blocked = drain(home)
    assert len(calls) == 2 and any(d['state'] == 'source_version_blocked' for d in blocked['deferred'])


def test_budget_exhaustion_does_not_call_provider_or_reset_pool(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home, current=False)
    from src.adapters import management_recertification as recert
    monkeypatch.setattr(recert, 'recertify', lambda *a, **k: pytest.fail('budget must block admission'))
    monkeypatch.setattr(backup, 'budget_snapshot', lambda _: {'series': {'estimated_usd': 9}, 'pending_usd': 10,
                                                           'learning_spent_usd': 24, 'learning_reserved_usd': 0})
    original = sha(root/'pool.json'); result = drain(home)
    assert not result['attempted'] and result['deferred'][0]['state'] == 'budget_blocked'
    assert sha(root/'pool.json') == original


def test_new_ordinary_evidence_allows_one_new_attempt_but_same_evidence_does_not(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home, current=False)
    from src.adapters import management_recertification as recert, continuous_motif_learning as learner
    calls = []
    def reject(config, old, cert, template, job, **kw):
        calls.append(job)
        durable(job/'candidate-lock.json', {'source_code': lib.sources()})
        durable(job/'compiled.json', read(old)['artifact'])
        durable(job/'failure.json', {'status': 'rejected'})
        return {'status': 'rejected'}
    monkeypatch.setattr(recert, 'recertify', reject)
    drain(home); assert len(calls) == 1
    f = frames()[2]
    f['spec'] = {'quality': {'goal': {'state': 'frozen'}}}
    f['audit'] = []
    for i, row in enumerate(f['rows']):row.update(call_seq=i*3+1, result_seq=i*3+2, generated=False)
    monkeypatch.setattr(learner, 'frame', lambda r: f)
    record = {'role': 'ordinary', 'adapter': 'management_v3', 'origin': str(project/'.local/rsi/archive-first/runs/0'),
              'task_fingerprint': digest('fresh ordinary independent evidence')}
    drain(home, [record]); assert len(calls) == 2 and calls[0] != calls[1]
    drain(home, [record]); assert len(calls) == 2


def test_historical_final_material_cannot_seed_automatic_recertification(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home, current=False, template_role='holdout')
    from src.adapters import management_recertification as recert
    monkeypatch.setattr(recert, 'recertify', lambda *a, **k: pytest.fail('final evidence must not enter certification'))
    result = drain(home)
    assert not result['attempted'] and result['deferred'][0]['state'] == 'material_required'


def test_default_worker_runs_managed_maintenance_before_new_discovery(home, monkeypatch):
    project, root, cfg, runtime = home
    from src.adapters import continuous_motif_learning as learner
    calls = []
    monkeypatch.setattr(lib, 'maintain', lambda *a: calls.append('maintenance') or {'retained': True})
    monkeypatch.setattr(learner, 'discover', lambda *a: (calls.append('discover') or [], []))
    result = learner._drain_locked(cfg, root)
    assert calls == ['maintenance', 'discover']
    assert result['experience_library'] == {'retained': True}


def test_unsupported_or_unproved_history_is_managed_without_execution(home, monkeypatch):
    project, root, cfg, runtime = home
    folder = project/'.local/file-management/archive'; folder.mkdir(parents=True)
    value = {'format': 'sss-old-collection', 'artifact': {'kind': 'legacy_foreach'}}
    durable(folder/'policy.json', {**value, 'policy_digest': digest(value)})
    from src.adapters import management_recertification as recert
    monkeypatch.setattr(recert, 'recertify', lambda *a, **k: pytest.fail('unsupported IR must never activate'))
    result = drain(home)
    assert not result['attempted'] and lib.summary(root)['states'] == {'adapter_required': 1}
    assert not ExperienceRegistry(root/'registry').load()['entries']


def test_final_material_and_symlink_are_not_automatically_imported(home):
    project, root, cfg, runtime = home
    ignored = project/'.local/file-management/experiment/tasks/holdout-test'; ignored.mkdir(parents=True)
    (ignored/'policy.json').write_text('this final material must never be parsed')
    outside = project/'private.txt'; outside.write_text('unrelated')
    linked = project/'.local/file-management/experiment/policy.json'; linked.symlink_to(outside)
    result = lib.synchronize(cfg)
    assert not result['entries'] and len(result['issues']) == 1
    assert 'symlink' in result['issues'][0]['reason']


def test_byte_variants_preserve_original_bytes_and_never_count_as_different_structure(home):
    project, root, cfg, runtime = home; registry, entry, policy, cert = historical(home)
    alternate = project/'.local/file-management/alternate/policy.json'; alternate.parent.mkdir(parents=True)
    alternate.write_text(json.dumps(policy, sort_keys=True, separators=(',', ':')))
    result = lib.synchronize(cfg)
    assert len(result['entries']) == 2 and lib.summary(root)['structure_count'] == 1
    assert {e['sha256'] for e in result['entries']} == {entry['sha256'], sha(alternate)}


def test_quality_metadata_migration_retains_exact_predicates_and_permissions(tmp_path):
    from src.adapters.continuous_rsi import snapshot
    original = tmp_path/'original'; work = original/'pristine'; work.mkdir(parents=True)
    (work/'a.txt').write_text('old independent source')
    old = {'quality': {'version': 'sss-management-quality-v3', 'requirements': [{'kind': 'read', 'path': 'a.txt'}]},
           'initial_snapshot': snapshot(work), 'owner': 'original-owner', 'workspace_id': 'original-workspace',
           'objective': 'read the original file', 'rules': {'read_only': True}, 'allowed_operations': ['read']}
    durable(original/'task.json', old)
    job = tmp_path/'job'; job.mkdir()
    seed = {'origin': str(original), 'upgrade_quality': True, 'record': {'origin': str(original)}}
    directory = lib.material_template(seed, job); fresh = read(directory/'task.json')
    assert fresh['quality']['version'] == lib.QUALITY
    assert fresh['quality']['requirements'] == old['quality']['requirements']
    assert fresh['allowed_operations'] == ['read'] and fresh['rules']['read_only'] is True
    before = sha(job/'material-migration.json')
    assert lib.material_template(seed, job) == directory and sha(job/'material-migration.json') == before
    (work/'a.txt').write_text('changed original source')
    with pytest.raises(ValueError, match='material changed'):lib.material_template(seed, job)


def test_catalog_tamper_fails_closed_and_busy_writer_can_use_last_complete_snapshot(home):
    project, root, cfg, runtime = home; historical(home); lib.synchronize(cfg)
    with rsi.writer_lock(root, 'experience'):
        assert lib.synchronize(cfg)['generation'] == 1
    state = lib.load(root); obj = root/'experience'/state['entries'][0]['payload']
    obj.write_text('{}')
    with pytest.raises(ValueError, match='object changed'):lib.load(root)


def test_schema_only_update_also_invalidates_compatibility_without_runtime_file_edit(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home); drain(home)
    old_version = lib.target_version(lib.sources()); old_file = sha(runtime)
    tools = lib.current_contracts(lib.sources())
    tools[next(iter(tools))]['schema']['properties'] = {'intent': {'type': 'string', 'description': 'new actual MCP schema'}}
    assert sha(runtime) == old_file and lib.target_version(lib.sources()) != old_version
    from src.adapters import management_recertification as recert
    calls = []
    def reject(*args, **kw):
        calls.append(True)
        return {'status': 'rejected'}
    monkeypatch.setattr(recert, 'recertify', reject)
    drain(home)
    assert calls and ExperienceRegistry(root/'registry').load()['entries'][0]['state'] == 'disabled'


def test_verified_inherited_calls_can_supply_material_but_not_native_certification():
    from src.adapters.management_recertification import native_view
    ff = frames(); f = ff[2]; nodes = discover_graphs(ff[:2])[0][0]['compiled']['nodes']
    f['audit'] = []
    for i, row in enumerate(f['rows']):row.update(call_seq=3*i+1, result_seq=3*i+2, generated=False)
    middle = f['rows'][1]; middle.update(generated=True, message_seq=None)
    f['audit'].append({'kind': 'operation_model_request_bypassed_verified', 'call_id': middle['call_id']})
    assert lib.material_graph_observed(f, nodes)
    with pytest.raises(ValueError):native_view(f, nodes)
    f['audit'] = []
    assert not lib.material_graph_observed(f, nodes)


def test_newest_sealed_material_is_selected_and_completed_evidence_does_not_starve_other_material(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home, current=False)
    from src.adapters import management_recertification as recert, continuous_motif_learning as learner
    f = frames()[2]; f.update(spec={'quality': {'goal': {'state': 'frozen'}}}, audit=[])
    for i, row in enumerate(f['rows']):row.update(call_seq=3*i+1, result_seq=3*i+2, generated=False)
    monkeypatch.setattr(learner, 'frame', lambda r: f)
    observed = []
    def reject(config, old, cert, template, job, **kw):
        observed.append(read(job/'request.json')['seed'])
        durable(job/'candidate-lock.json', {'source_code': lib.sources()})
        durable(job/'compiled.json', read(old)['artifact'])
        durable(job/'failure.json', {'status': 'rejected'})
        return {'status': 'rejected'}
    monkeypatch.setattr(recert, 'recertify', reject)
    rows = []
    for i, name in enumerate(('z-old', 'a-new'), 1):
        row = {'role': 'ordinary', 'adapter': 'management_v3', 'session_id': name,
               'origin': str(project/'.local/rsi/archive-first/runs/0'), 'task_fingerprint': digest(name)}
        file = root/'records'/(name+'.json'); durable(file, row); __import__('os').utime(file, ns=(i*1_000_000_000, i*1_000_000_000)); rows.append(row)
    drain(home, [rows[1], rows[0]])
    assert observed == [rows[1]['task_fingerprint']]
    drain(home, [rows[1], rows[0]])
    assert observed == [rows[1]['task_fingerprint'], rows[0]['task_fingerprint']]
    drain(home, [rows[1], rows[0]])
    assert len(observed) == 2


def test_schema_change_does_not_inherit_rejection_from_previous_catalog(home, monkeypatch):
    project, root, cfg, runtime = home; historical(home, current=False)
    from src.adapters import management_recertification as recert
    calls = []
    def reject(config, old, cert, template, job, **kw):
        calls.append(job)
        durable(job/'candidate-lock.json', {'source_code': lib.sources()})
        durable(job/'compiled.json', read(old)['artifact'])
        durable(job/'failure.json', {'status': 'rejected'})
        return {'status': 'rejected'}
    monkeypatch.setattr(recert, 'recertify', reject)
    drain(home); assert len(calls) == 1
    original = sha(runtime)
    tools = lib.current_contracts(lib.sources())
    tools[next(iter(tools))]['schema']['description'] = 'new schema without runtime file edit'
    drain(home)
    assert len(calls) == 2 and calls[0] != calls[1] and sha(runtime) == original


def test_supplemental_copy_read_checks_use_only_frozen_source_byte_predicates(tmp_path):
    origin = tmp_path/'origin'; delivery = tmp_path/'delivery'; (delivery/'reads').mkdir(parents=True)
    record = {'origin': str(origin), 'delivery': str(delivery)}
    spec = {'initial_tree': {'workspace': {'files': {'original.txt': 'source-hash'}}},
            'quality': {'requirements': [{'kind': 'file', 'source': 'original.txt', 'path': 'out/copy.txt'}]}}
    durable(delivery/'reads'/'copy.json', {'path': 'workspace/out/copy.txt', 'sha256': 'source-hash', 'status': 'readable', 'truncated': False})
    durable(delivery/'reads'/'unrelated.json', {'path': 'workspace/unrequested.txt', 'sha256': 'other', 'status': 'readable', 'truncated': False})
    assert lib.supplemental_reads(spec, record) == [{'source': 'original.txt', 'path': 'out/copy.txt'}]
    value = read(delivery/'reads'/'copy.json'); value['sha256'] = 'changed'; durable(delivery/'reads'/'copy.json', value)
    assert not lib.supplemental_reads(spec, record)


def test_startup_probe_delegates_programmes_to_legacy_queue_and_keeps_graph_work(home, monkeypatch):
    from src.adapters import management_legacy as legacy
    _, _, cfg, _ = home
    item = {'kind': 'management_program', 'compatibility': {'state': 'recertification_required'}}
    monkeypatch.setattr(lib, 'synchronize', lambda unused: {'jobs': [], 'entries': [item]})
    def wrong_adapter(*args):
        raise AssertionError('a programme cannot be admitted through the operation-graph maintenance queue')
    monkeypatch.setattr(lib, 'eligible_certificate', wrong_adapter)
    monkeypatch.setattr(lib, 'original_template', wrong_adapter)
    monkeypatch.setattr(legacy, 'pending', lambda unused: False)
    assert not lib.needs_maintenance(cfg)
    monkeypatch.setattr(legacy, 'pending', lambda unused: True)
    assert lib.needs_maintenance(cfg)
    item['kind'] = 'operation_graph'
    monkeypatch.setattr(lib, 'eligible_certificate', lambda *args: None)
    monkeypatch.setattr(lib, 'prior_rejection', lambda *args: None)
    monkeypatch.setattr(lib, 'original_template', lambda *args: {'original': 'frozen-material'})
    monkeypatch.setattr(legacy, 'pending', lambda unused: False)
    assert lib.needs_maintenance(cfg)
