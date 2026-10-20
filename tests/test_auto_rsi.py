import json
import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scenarios/file-management'))
from auto_rsi import opportunity, learn_candidate, fresh_material_from_observed_task
import auto_rsi
from src.motif_core.offline.experience_registry import ExperienceRegistry, read, durable, digest, sha


def test_final_holdout_cannot_trigger_learning():
    with pytest.raises(ValueError, match='holdout'):
        opportunity([{'role': 'holdout'}])


def test_real_repeat_cost_drives_opportunity_without_profile_id():
    one = {'role': 'observe', 'retrievals': [], 'acceptance': {'passed': True}, 'run': {'upstream_requests': 8}}
    assert opportunity([one])['worth_learning'] is False
    assert opportunity([one, one])['worth_learning'] is True


def test_registry_versions_remain_immutable_and_writer_conflicts_reject(tmp_path):
    registry = ExperienceRegistry(tmp_path)
    first = registry.publish(reason='seed', expected=0)
    original = first.read_bytes()
    registry.publish(reason='independent upgrade', expected=1)
    assert first.read_bytes() == original
    assert registry.load()['generation'] == 2
    with pytest.raises(ValueError, match='writer/version'):
        registry.publish(expected=1)


def test_changed_current_pointer_is_rejected(tmp_path):
    registry = ExperienceRegistry(tmp_path)
    file = registry.publish()
    file.write_bytes(file.read_bytes() + b' ')
    with pytest.raises(ValueError, match='pointer'):
        registry.load()


def test_unsigned_candidate_cannot_enter_active_store(tmp_path):
    program = {'script_digest': 'wrong'}
    source = tmp_path / 'candidate.json'
    durable(source, program)
    with pytest.raises(ValueError, match='signature'):
        ExperienceRegistry(tmp_path / 'registry').entry('script_v2', source, {})


def test_script_with_no_certificate_is_not_promoted(tmp_path):
    program = {'format': 'candidate'}
    program['script_digest'] = digest(program)
    source = tmp_path / 'candidate.json';durable(source, program)
    with pytest.raises(ValueError, match='independent certification'):
        ExperienceRegistry(tmp_path / 'registry').entry('script_v2', source, {})


def test_failed_candidate_and_disabled_version_remain_in_history(tmp_path):
    registry = ExperienceRegistry(tmp_path / 'registry')
    source = tmp_path / 'motif.json'
    value = read(ROOT / 'examples/motif-library/file-management-v1/collection-v1/policy.json')
    durable(source, value)
    entry = registry.entry('collection', source, {})
    first = registry.publish([entry]);original = first.read_bytes()
    registry.publish(disable=[entry['entry_id']], reason='fixed acceptance failed')
    assert registry.load()['entries'][0]['state'] == 'disabled'
    assert first.read_bytes() == original
    with pytest.raises(ValueError, match='reenable'):
        registry.publish([entry])


def test_resume_rejected_learning_keeps_original_record_and_never_exposes_certification(tmp_path):
    file = tmp_path / 'upgrade-1/learning-attempt-1.json'
    failed = {'scripts': [], 'excluded': [{'reason': 'failed original exploration'}]}
    durable(file, failed)
    before = sha(file)
    assert learn_candidate(tmp_path, {}, 1, {'tasks': [{'role': 'holdout'}]}) == failed
    assert sha(file) == before
    assert not (file.parent / 'candidate-lock.json').exists()


def test_independent_materials_keep_rules_permissions_duplicates_and_empty_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(auto_rsi, 'DATA', tmp_path / 'data')
    origin = tmp_path / 'original';origin.mkdir()
    for name, data in [('source/a.txt', b'same'), ('source/b.txt', b'same'), ('source/empty.txt', b''), ('rules/r.txt', b'unchanged rule')]:
        file = origin / name;file.parent.mkdir(exist_ok=True);file.write_bytes(data)
    initial = auto_rsi.snapshot(origin)
    td = tmp_path / 'template';td.mkdir()
    contract = {'source_paths': ['source/a.txt', 'source/b.txt', 'source/empty.txt'], 'context_paths': ['rules/r.txt'],
                'allowed_reads': ['rules/r.txt']}
    spec = {'task_id': 'seen', 'role': 'observe', 'workflow_contract': contract, 'initial_snapshot': initial, 'allowed_operations': ['copy']}
    durable(td / 'input-template.json', spec)
    durable(td / 'oracle.json', {'expected_snapshot': {**initial, 'backup/a.txt': initial['source/a.txt']}})
    durable(td / 'scenario.json', {'prompt': str(td / 'prompt.md')});(td / 'prompt.md').write_text('known authorized objective')
    observed = {'task_id': 'seen-R', 'pair_id': 'seen', 'template_dir': str(td), 'pristine': str(origin),
                'control': {'mode': 'none', 'target': 'source/a.txt', 'before_sha256': initial['source/a.txt']}}
    experiment = tmp_path / 'experiment';experiment.mkdir()
    template, cases = fresh_material_from_observed_task(experiment, observed, 'certify', 'new-certify', 'C')
    new = auto_rsi.read(Path(template['task_dir']) / 'input-template.json')
    assert new['initial_snapshot']['source/a.txt'] == new['initial_snapshot']['source/b.txt'] != initial['source/a.txt']
    assert new['initial_snapshot']['source/empty.txt'] == initial['source/empty.txt']
    assert new['initial_snapshot']['rules/r.txt'] == initial['rules/r.txt']
    assert new['allowed_operations'] == ['copy'] and new['workflow_contract'] == contract
    assert cases[0]['role'] == 'certify' and 'profile_id' not in cases[0]
    assert auto_rsi.snapshot(origin) == initial
