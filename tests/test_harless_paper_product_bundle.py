"""Admission tests use the real committed release, never invented training certificates."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from src.adapters.harless_rsi_bundle import load_product_bundle

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / 'config/harless-scenes.json').read_text(encoding='utf-8'))
RELEASE = ROOT / next(row for row in REGISTRY['scenes'] if row['id'] == 'paper-proofreading')['rsi']['runtime_bundle']
PAIR = ['mcp__paper_checks__pin_document', 'mcp__paper_checks__read_pinned_document']


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_release(tmp_path):
    """Copy real bytes/locks to an isolated repository for destructive-negative tests."""
    root = tmp_path / 'repo'
    bundle = root / 'motif-libraries' / RELEASE.name
    shutil.copytree(RELEASE, bundle)
    paths = set(read(RELEASE / 'certification.json')['code_locks'])
    paths.add('scenarios/paper_proofreading/scenario.json')
    for name in paths:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    return root, bundle


def test_real_paper_product_bundle_admits_independent_traces_and_complete_unchanged_tools():
    entry = read(RELEASE / 'entry.json')
    evidence = read(RELEASE / 'source-evidence.json')
    report = read(RELEASE / 'learning-report.json')
    manifest = read(RELEASE / 'online-manifest.json')
    admitted = load_product_bundle(ROOT, RELEASE, 'paper-proofreading')
    assert entry['runtime_kind'] == admitted['runtime_kind'] == 'paper_document_read_v1'
    assert admitted['runtime_mode'] == 'execute'
    assert admitted['binding_policy'] == 'approved_uploaded_reads_v1'
    assert admitted['matching_policy'] == 'structural_only'
    assert admitted['quality_cost_promoted'] is False
    assert report['new_training'] is True
    assert report['training_tasks'] == len(evidence['train']) == 2
    assert report['heldout_tasks'] == len(evidence['heldout']) == 1
    identities = [*evidence['train'], *evidence['heldout']]
    for field in ('task_id', 'research_decision_id', 'question_sha256', 'events_sha256'):
        assert len({row[field] for row in identities}) == len(identities), field
    assert manifest['artifacts'][0]['tools'] == PAIR and len(manifest['artifacts']) == 1
    assert manifest['contracts'][PAIR[0]]['observed_anchor'] is True
    assert manifest['contracts'][PAIR[1]]['default_params'] == {'page': 1}
    read_schema = next(row for row in admitted['certified_tool_schemas'] if row['name'] == PAIR[1])
    assert read_schema['parameters']['properties']['page']['default'] == 1
    allowed = read(ROOT / 'scenarios/paper_proofreading/scenario.json')['allowed_tools']
    assert len(allowed) == 24
    assert sorted(row['name'] for row in admitted['certified_tool_schemas']) == sorted(allowed)
    for name, expected in entry['files'].items():
        assert sha(RELEASE / name) == expected, name


def test_three_product_defaults_select_execute_releases_with_exact_registered_capabilities():
    registry = {row['id']: row for row in read(ROOT / 'config/harless-scenes.json')['scenes']}
    for identity, count in [('ppt', 5), ('research-data-analysis', 17), ('paper-proofreading', 24)]:
        row = registry[identity]
        assert read(ROOT / row['rsi']['runtime_bundle'] / 'entry.json')['mode'] == 'execute'
        assert len(read(ROOT / row['scenario'])['allowed_tools']) == count


@pytest.mark.parametrize('identity', ['paper-proofreading', 'ppt'])
def test_product_bundle_reads_unicode_schemas_explicitly_even_with_a_cp936_default(monkeypatch, identity):
    """Linux must not hide a missing UTF-8 declaration on Windows."""
    registry = {row['id']: row for row in read(ROOT / 'config/harless-scenes.json')['scenes']}
    bundle = ROOT / registry[identity]['rsi']['runtime_bundle']
    # The root suite intentionally does not build optional PPT TypeScript.
    # Deployments still require every generated-file lock; the remote built
    # candidate runs this same CP936 check without skipping it.
    if identity == 'ppt':
        locks = read(bundle / 'certification.json')['code_locks']
        if any('/dist/' in name and not (ROOT / name).exists() for name in locks):
            pytest.skip('PPT renderer build required for complete release admission')
    expected = read(bundle / 'tool-schemas.json')
    original = Path.read_text

    def windows_default(path, *args, **kwargs):
        if args:
            args = (args[0] or 'cp936', *args[1:])
        elif kwargs.get('encoding') is None:
            kwargs['encoding'] = 'cp936'
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'read_text', windows_default)
    admitted = load_product_bundle(ROOT, bundle, identity)
    assert admitted['certified_tool_schemas'] == expected


@pytest.mark.parametrize('name', ['online-manifest.json', 'tool-schemas.json', 'source-evidence.json', 'library.json'])
def test_real_paper_release_rejects_modified_contract_schema_source_or_library(tmp_path, name):
    root, bundle = copy_release(tmp_path)
    assert load_product_bundle(root, bundle, 'paper-proofreading')['runtime_mode'] == 'execute'
    (bundle / name).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact changed'):
        load_product_bundle(root, bundle, 'paper-proofreading')


def test_real_paper_release_rejects_changed_runtime_and_wrong_scene(tmp_path):
    root, bundle = copy_release(tmp_path)
    name = next(iter(read(bundle / 'certification.json')['code_locks']))
    (root / name).write_bytes((root / name).read_bytes() + b'\n')
    with pytest.raises(ValueError, match='code changed'):
        load_product_bundle(root, bundle, 'paper-proofreading')
    with pytest.raises(ValueError):
        load_product_bundle(root, bundle, 'research-data-analysis')


def test_original_paper_shadow_release_stays_shadow_and_cannot_be_relabelled_as_new_training(tmp_path):
    original = ROOT / 'motif-libraries/paper'
    admitted = load_product_bundle(ROOT, original, 'paper-proofreading')
    assert admitted['runtime_kind'] == 'paper_shadow_v1'
    assert admitted['runtime_mode'] == 'shadow'
    bundle = tmp_path / 'motif-libraries/paper-web-v1'
    shutil.copytree(original, bundle)
    entry = read(bundle / 'entry.json')
    entry.update(runtime_kind='paper_document_read_v1', mode='execute')
    (bundle / 'entry.json').write_text(json.dumps(entry), encoding='utf-8')
    with pytest.raises(ValueError, match='invalid existing product library'):
        load_product_bundle(tmp_path, bundle, 'paper-proofreading')


@pytest.mark.parametrize('before,after,scene,record', [
    ('paper-web-v12','paper-web-v13','paper-proofreading','delivery_compatibility'),
    ('ppt-master-v7','ppt-master-v8','ppt','delivery_compatibility'),
    ('paper-web-v13','paper-web-v14','paper-proofreading','attachment_context_compatibility'),
    ('ppt-master-v8','ppt-master-v9','ppt','attachment_context_compatibility'),
    ('paper-web-v14','paper-web-v15','paper-proofreading','attachment_surface_compatibility'),
    ('ppt-master-v9','ppt-master-v10','ppt','attachment_surface_compatibility'),
    ('paper-web-v15','paper-web-v16','paper-proofreading','attachment_evidence_consumption_compatibility'),
    ('ppt-master-v10','ppt-master-v11','ppt','attachment_evidence_consumption_compatibility'),
    ('paper-web-v16','paper-web-v17','paper-proofreading','ppt_learning_compatibility'),
    ('ppt-master-v11','ppt-master-v12','ppt','ppt_learning_compatibility'),
])
def test_compatibility_reuses_validated_program_without_rewriting_previous_release(before,after,scene,record):
    original=ROOT/'motif-libraries'/before
    candidate=ROOT/'motif-libraries'/after
    report=read(candidate/'learning-report.json')[record]
    assert report['previous_certification_sha256']==sha(original/'certification.json')
    assert report['method']=='reexport_certified_serialized_library'
    assert report['model_requests']==0 and report['new_training_tasks']==0
    assert report['raw_traces_replayed'] is False
    for name in ('library.json','source-evidence.json','task.json','tool-schemas.json','online-manifest.json'):
        assert (candidate/name).read_bytes()==(original/name).read_bytes()
    assert read(candidate/'online-manifest.json')==read(original/'online-manifest.json')
    if record=='attachment_evidence_consumption_compatibility':
        assert report['changed_code_locks']==['src/adapters/harless_attachment_context.ts']
        assert set(report['additional_code_locks'])=={'src/adapters/harless_attachment_reading.ts',
                                                    'scripts/reexport-attachment-reading-compat.py'}
    if record in ('attachment_context_compatibility','attachment_surface_compatibility',
                  'attachment_evidence_consumption_compatibility'):
        # New certificate hashes must describe the LF bytes Git will commit,
        # including when this release is exported on Windows.
        for path in candidate.iterdir():
            if path.is_file():
                assert b'\r\n' not in path.read_bytes(),path.name
    current=next(row for row in read(ROOT/'config/harless-scenes.json')['scenes'] if row['id']==scene)['rsi']['runtime_bundle']
    if candidate==ROOT/current:
        assert load_product_bundle(ROOT,candidate,scene)['quality_cost_promoted'] is False
    else:
        # Historical release bytes stay valid for their original runtime, and
        # must fail closed against today's changed attachment implementation.
        with pytest.raises(ValueError,match='code changed'):
            load_product_bundle(ROOT,candidate,scene)


@pytest.mark.parametrize('name',[
    'src/adapters/harless_attachment_context.ts',
    'src/adapters/geneloop_attachment_cache.ts',
    'src/adapters/harless_public_output.ts',
    'src/adapters/harless_task_progress.ts',
    'scripts/reexport-attachment-context-compat.py',
    'scripts/reexport-surface-context-compat.py',
    'src/adapters/harless_attachment_reading.ts',
    'scripts/reexport-attachment-reading-compat.py',
])
def test_attachment_compatibility_locks_each_new_context_and_evidence_boundary(tmp_path,name):
    root,bundle=copy_release(tmp_path)
    assert name in read(bundle/'certification.json')['code_locks']
    assert load_product_bundle(root,bundle,'paper-proofreading')['runtime_mode']=='execute'
    (root/name).write_bytes((root/name).read_bytes()+b'\n')
    with pytest.raises(ValueError,match='code changed'):
        load_product_bundle(root,bundle,'paper-proofreading')
