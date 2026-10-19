"""Historical proposals cannot bypass current native or independent read proof."""
import copy
import json
import pytest
from src.adapters.management_recertification import native_view, rebuild, verify_read_checks
from src.motif_core.offline.operation_graph import discover_graphs, certify_graph
from src.motif_core.offline.experience_registry import digest, read, sha
from test_operation_graph import frames


def native():
    ff = frames()
    for f in ff:
        for i, r in enumerate(f['rows']):
            r.update(call_seq=3*i+2, result_seq=3*i+3, generated=False)
    c = discover_graphs(ff[:2])[0][0]
    return ff, c


def test_shorter_historical_graph_requires_real_connected_native_prefix_and_preserves_raw():
    ff, c = native(); f = ff[2]; original = copy.deepcopy(f)
    nodes = c['compiled']['nodes'][:2]
    view, proof = native_view(f, nodes)
    old = {'artifact': {**c['compiled'], 'nodes': nodes}}
    compiled = rebuild(old, f, {'old_policy_digest': 'historical'})
    p = certify_graph(compiled, view)
    assert len(p['artifact']['nodes']) == 2 and len(proof['full_native_witness_calls']) == 3
    assert proof['calls'] == [r['call_id'] for r in f['rows'][:2]]
    assert f == original
    assert compiled['recertification_provenance']['old_policy_digest'] == 'historical'


@pytest.mark.parametrize('damage', ['generated', 'failed', 'barrier', 'authority'])
def test_missing_native_or_failed_intermediate_call_cannot_be_erased(damage):
    ff, c = native(); f = ff[2]
    if damage == 'generated':
        f['rows'][1].update(generated=True, message_seq=None)
    elif damage == 'failed':
        f['rows'][1]['out'] = None
    elif damage == 'authority':
        f['rows'][1]['out']['_sss_authorized'] = False
    else:
        f['rows'].insert(1, {'name': 'unknown', 'call_id': 'barrier', 'call_seq': 4, 'out': None})
    with pytest.raises(ValueError, match='native'):
        native_view(f, c['compiled']['nodes'][:2])


@pytest.mark.parametrize('damage', ['semantic', 'required', 'export', 'future'])
def test_current_schema_and_export_authority_replace_stale_declarations(damage):
    ff, c = native(); f = ff[2]; old = {'artifact': copy.deepcopy(c['compiled'])}
    node = old['artifact']['nodes'][1]; tc = f['tools'][node['tool']]
    if damage == 'semantic': tc['contract']['auto_continue'] = False
    if damage == 'required': tc['schema']['required'].append('new_permission')
    if damage == 'export': node['bindings']['handle']['path'] = 'undeclared'
    if damage == 'future': node['bindings']['handle']['node'] = 2
    with pytest.raises(ValueError): rebuild(old, f, {})


def test_output_read_goal_binds_fresh_original_bytes_and_full_read(tmp_path):
    origin = tmp_path/'origin'; delivery = tmp_path/'delivery'; template = tmp_path/'template'
    origin.mkdir(); (delivery/'reads').mkdir(parents=True); template.mkdir()
    (origin/'task.json').write_text(json.dumps({'initial_tree': {'workspace': {'files': {'a.txt': 'fresh'}}}}))
    (template/'recertification-checks.json').write_text(json.dumps({'complete_reads': [{'source': 'a.txt', 'path': 'out/a.txt'}]}))
    record = {'origin': str(origin), 'delivery': str(delivery)}
    file = delivery/'reads'/'a.json'
    for damage in ('missing', 'stale', 'truncated'):
        file.write_text(json.dumps({'path': 'workspace/out/a.txt', 'sha256': 'stale' if damage == 'stale' else 'fresh',
                                   'status': 'readable', 'truncated': damage == 'truncated'} if damage != 'missing' else {}))
        with pytest.raises(ValueError, match='complete output read'): verify_read_checks(record, template)
    file.write_text(json.dumps({'path': 'workspace/out/a.txt', 'sha256': 'fresh', 'status': 'readable', 'truncated': False}))
    verify_read_checks(record, template)


def offline_job(tmp_path, monkeypatch):
    import src.adapters.management_recertification as m
    cfg = tmp_path/'config.json'; cfg.write_text('{}')
    policy = tmp_path/'old-policy.json'
    value = {'format': 'sss-operation-graph-v2', 'artifact': {}}
    policy.write_text(json.dumps({**value, 'policy_digest': digest(value)}))
    certificate = tmp_path/'old-certificate.json'; certificate.write_text('{}')
    template = tmp_path/'template'; template.mkdir()
    (template/'task.json').write_text(json.dumps({'role': 'native_certification'}))
    monkeypatch.setattr(m, 'private', lambda p: __import__('pathlib').Path(p).resolve())
    monkeypatch.setattr(m, 'load_config', lambda _: {'adapter': 'management_v3', 'provider_mode': 'real',
                                                   'mode': 'learn', 'state_root': str(tmp_path/'state')})
    monkeypatch.setattr(m, 'check_motif_certificate', lambda *args: None)
    monkeypatch.setattr(m, 'source_map', lambda *args: {})
    monkeypatch.setattr(m, 'state_event', lambda *args: None)
    return m, (cfg, policy, certificate, template, tmp_path/'job')


def test_missing_replay_file_seals_failure_and_resume_does_not_repeat_paid_work(tmp_path, monkeypatch):
    m, args = offline_job(tmp_path, monkeypatch); calls = []
    before = [sha(p) for p in args[:3]]
    def interrupted(*unused):
        calls.append(True)
        raise FileNotFoundError('intermediate version absent from sealed final snapshot')
    monkeypatch.setattr(m, 'run_material', interrupted)
    first = m.recertify(*args); second = m.recertify(*args)
    assert first == second and first['status'] == 'rejected' and len(calls) == 1
    assert 'FileNotFoundError' in first['reason'] and first['candidate_inactive']
    assert not (args[-1]/'activation.json').exists()
    assert [sha(p) for p in args[:3]] == before
    args[0].write_text('{"changed":true}')
    with pytest.raises(ValueError, match='frozen'):
        m.recertify(*args)
    assert len(calls) == 1


def test_interrupted_original_enrollment_stays_pending_without_fresh_failure(tmp_path, monkeypatch):
    m, args = offline_job(tmp_path, monkeypatch)
    def pending(*unused): raise m.RecoveryPending('resume the original enrollment and budget')
    monkeypatch.setattr(m, 'run_material', pending)
    with pytest.raises(m.RecoveryPending): m.recertify(*args)
    assert (args[-1]/'candidate-lock.json').exists()
    assert not (args[-1]/'failure.json').exists()
    assert not (args[-1]/'activation.json').exists()
