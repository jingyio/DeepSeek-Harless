"""Free diagnostics of frozen delivery, source lineage and failure boundaries."""
import copy,json,sys
from pathlib import Path
from uuid import uuid4
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from management_tools import ManagementScene
from management_contract import verify_management
from common import sha,digest


def scene(tmp_path,requirements=None,objective='Complete the explicitly frozen file task.'):
    work=tmp_path/'work';work.mkdir()
    (work/'a.txt').write_text('same original bytes')
    (work/'b.txt').write_text('same original bytes')
    out=ROOT/'.local/management-quality-tests'/uuid4().hex
    spec=prepare(out,work,task_id=uuid4().hex,objective=objective,owner='quality-test',workspace_id=uuid4().hex,quality=requirements)
    s=ManagementScene(spec,out/'delivery');s.read_task()
    return s,spec,work


def perform(s,**action):
    p=s.preview_actions([action]);return s.execute_plan(p['plan_id'])


def test_explicit_predicates_freeze_complete_file_set_and_mapping(tmp_path):
    s,spec,work=scene(tmp_path,[{'kind':'file','source':'a.txt','path':'backup/a.txt'}])
    goal=spec['quality']['goal']
    assert goal['expected_tree']['files']['backup/a.txt']==sha(work/'a.txt')
    public=s.read_task()['goal_acceptance']
    assert public['state']=='frozen' and not {'expected_tree','expected_roots','expected_origins','intermediate_sources'}.intersection(public)
    with pytest.raises(Exception,match='frozen goal'):
        s.preview_actions([{'op':'copy','source':'a.txt','destination':'backup/source/a.txt'}])
    with pytest.raises(Exception,match='source lineage'):
        s.preview_actions([{'op':'copy','source':'b.txt','destination':'backup/a.txt'}])
    perform(s,op='copy',source='a.txt',destination='backup/a.txt')
    assert s.submit_report('complete',list(s.files()),[])['semantic_quality_verified']


def test_goal_does_not_allow_extra_quarantine_or_accidental_source_copy(tmp_path):
    s,spec,work=scene(tmp_path,[{'kind':'file','source':'a.txt','path':'target/a.txt'},{'kind':'missing','path':'a.txt'}])
    with pytest.raises(Exception,match='frozen goal'):
        s.preview_actions([{'op':'copy','source':'a.txt','destination':'target/a.txt'}])
    with pytest.raises(Exception,match='frozen goal'):
        s.preview_actions([{'op':'quarantine','source':'a.txt','destination':'quarantine/a.txt'}])
    perform(s,op='move',source='a.txt',destination='target/a.txt')
    assert s.submit_report('moved',list(s.files()),[])['semantic_quality_verified']


def test_intermediate_read_survives_rename_and_process_restart(tmp_path):
    s,spec,work=scene(tmp_path,objective='Review the intermediate copy and arrange it.')
    perform(s,op='copy',source='a.txt',destination='temporary/a.txt')
    fid=next(r['file_id'] for r in s.list_files()['files'] if r['path']=='temporary/a.txt')
    rb=s.read_file(s.pin_file(fid)['source_id'])
    perform(s,op='rename',source='temporary/a.txt',destination='final/a.txt')
    recovered=ManagementScene(spec,s.output);recovered.read_task()
    assert recovered.reads[rb['source_id']]['provenance']['origin']=='workspace/a.txt'
    from management_provenance import resolve_read_source
    pristine=tmp_path/'pristine';pristine.mkdir();(pristine/'a.txt').write_text('same original bytes')
    source=resolve_read_source(spec,recovered.reads[rb['source_id']],json.loads(recovered.state_file.read_text()),pristine)
    assert source==pristine/'a.txt' and sha(source)==rb['sha256']
    altered=copy.deepcopy(recovered.reads[rb['source_id']]);altered['provenance']['origin']='workspace/b.txt'
    with pytest.raises(ValueError,match='provenance'):
        resolve_read_source(spec,altered,json.loads(recovered.state_file.read_text()),pristine)
    altered['provenance']['proof_sha256']=digest({k:v for k,v in altered['provenance'].items() if k!='proof_sha256'})
    with pytest.raises(ValueError,match='provenance'):
        resolve_read_source(spec,altered,json.loads(recovered.state_file.read_text()),pristine)


def test_report_rechecks_exact_files_independently_of_preview_guard(tmp_path):
    s,spec,work=scene(tmp_path,[{'kind':'file','source':'a.txt','path':'backup/a.txt'}])
    # Model-independent negative injection: valid journal, wrong final task.
    original=s.spec['quality'];s.spec['quality']={}
    perform(s,op='copy',source='a.txt',destination='extra/a.txt')
    s.spec['quality']=original
    perform(s,op='copy',source='a.txt',destination='backup/a.txt')
    with pytest.raises(Exception,match='coverage differs'):
        s.submit_report('all correct',list(s.files()),[])


def test_backup_copy_keeps_actual_origin_through_two_stages(tmp_path):
    checks=[{'kind':'file','source':'a.txt','path':p} for p in ('backup/a.txt','recovery/a.txt')]
    s,spec,work=scene(tmp_path,checks)
    perform(s,op='copy',source='a.txt',destination='backup/a.txt')
    perform(s,op='copy',source='backup/a.txt',destination='recovery/a.txt')
    assert s.submit_report('verified backup and recovery',list(s.files()),[])['semantic_quality_verified']


def test_replay_uses_the_observed_extension_after_rename(tmp_path):
    s,spec,work=scene(tmp_path,objective='Read the renamed intermediate file.')
    perform(s,op='copy',source='a.txt',destination='temporary.bin')
    fid=next(r['file_id'] for r in s.list_files()['files'] if r['path']=='temporary.bin')
    rb=s.read_file(s.pin_file(fid)['source_id'])
    assert rb['status']=='unsupported'
    from management_provenance import ReadReplayPath
    assert s.parse(ReadReplayPath(work/'a.txt',rb['path']))==('unsupported','',{})


def test_read_only_probe_cannot_forge_a_copy_as_retrieval_evidence():
    from src.adapters.continuous_motif_learning import verify_generated_provenance
    scope={'input_sha256':'current-input'};name='mcp__file_management__list_files';out={'_sss_scope':scope,'files':[]}
    row={'name':name,'call_id':'sss-program-probe','generated':True,'args':{},'out':out}
    audit={'kind':'management_program_probe_verified','call_id':row['call_id'],'source_kind':'management_program','stage':'inventory','tool':name,
           'arguments_sha256':digest({}),'result_sha256':digest(out),'scope_sha256':digest(scope),'model_request_bypassed':False}
    tools={name:{'contract':{'effect':'read'}}}
    verify_generated_provenance([row],[audit],tools,scope,'management_v3')
    changed=copy.deepcopy(row);changed['name']='mcp__file_management__execute_plan'
    with pytest.raises(ValueError,match='probe'):verify_generated_provenance([changed],[audit],tools,scope,'management_v3')
    for field in ('arguments_sha256','result_sha256','scope_sha256'):
        changed=copy.deepcopy(audit);changed[field]='forged'
        with pytest.raises(ValueError,match='probe'):verify_generated_provenance([row],[changed],tools,scope,'management_v3')


def test_json_is_in_the_declared_complete_text_read_scope(tmp_path):
    s,spec,work=scene(tmp_path,objective='Read all original text.')
    assert s.parse(work/'a.txt')[0]=='readable'
    from management_provenance import ReadReplayPath
    assert s.parse(ReadReplayPath(work/'a.txt','workspace/note.json'))[0]=='readable'


def test_declared_intermediate_read_then_rename_has_strict_daily_acceptance(tmp_path):
    s,spec,work=scene(tmp_path,objective='把 a.txt 复制到 intermediate.txt，完整读取该副本，再重命名为 final.txt，保留原件。完成后核验并提交报告。')
    assert spec['quality']['goal']['state']=='frozen'
    perform(s,op='copy',source='a.txt',destination='intermediate.txt')
    fid=next(r['file_id'] for r in s.list_files()['files'] if r['path']=='intermediate.txt')
    readback=s.read_file(s.pin_file(fid)['source_id'])
    perform(s,op='rename',source='intermediate.txt',destination='final.txt')
    assert s.submit_report('read and renamed',list(s.files()),[])['semantic_quality_verified']
    assert not (work/'intermediate.txt').exists()
    from management_provenance import resolve_read_source
    pristine=tmp_path/'pristine';pristine.mkdir();(pristine/'a.txt').write_text('same original bytes')
    assert resolve_read_source(spec,readback,json.loads(s.state_file.read_text()),pristine)==pristine/'a.txt'


def test_interrupted_plan_cannot_leave_an_unproven_read_in_the_task(tmp_path):
    s,spec,work=scene(tmp_path,objective='Recover the original local copy operation.')
    p=s.preview_actions([{'op':'copy','source':'a.txt','destination':'staging/a.txt'}]);s.crash_after_effect=0
    with pytest.raises(SystemExit):s.execute_plan(p['plan_id'])
    recovered=ManagementScene(spec,s.output);recovered.read_task()
    fid=next(r['file_id'] for r in recovered.list_files()['files'] if r['path']=='a.txt')
    sid=recovered.pin_file(fid)['source_id']
    with pytest.raises(Exception,match='unfinished plan'):recovered.read_file(sid)
    assert not recovered.reads
    recovered.execute_plan(p['plan_id'])
    assert recovered.read_file(sid)['provenance']['origin']=='workspace/a.txt'
