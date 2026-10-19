import importlib.util,json,sys
from pathlib import Path
from uuid import uuid4
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import sha,digest
from management_tools import ManagementScene,tree
from management_contract import VERSION as QUALITY_VERSION

@pytest.fixture
def case(tmp_path):
    work=tmp_path/'workspace';external=tmp_path/'external';work.mkdir();external.mkdir()
    (work/'.experiment-copy').write_text('trusted-task-copy')
    (work/'note.txt').write_text('original bytes');(work/'existing.txt').write_text('old destination')
    (external/'outside.txt').write_text('owned external bytes')
    spec={'task_id':uuid4().hex,'workspace':str(work),'workspace_id':'workspace-1','owner':'alice','objective':'自主整理工作区副本',
      'workspace_marker_sha256':sha(work/'.experiment-copy'),'initial_tree':{'workspace':tree(work),'external-owned':tree(external)},
      'external_roots':{'external-owned':{'path':str(external),'owner':'alice'}}}
    out=ROOT/'.local/management-tests'/uuid4().hex
    scene=ManagementScene(spec,out);scene.read_task()
    return scene,spec,work,external,out

def fid(scene,path):return next(r['file_id'] for r in scene.list_files()['files'] if r['path']==path)
def approve(scene,plan):
    scene.approve(plan['plan_id'],plan['plan_sha256'],{'outcome':'allowed-once','approval_event_id':'fixture-native-approval','session_id':'session-alice','task_sha256':scene.input_digest})

def test_low_risk_planning_is_autonomous_and_directories_restore(case):
    s,spec,w,x,out=case
    plan=s.preview_actions([{'op':'mkdir','destination':'empty'},{'op':'rename','file_ids':[fid(s,'note.txt')],'destination':'organized/topic/named.txt'}])
    assert plan['status']=='validated_management_plan' and plan['risks']==[]
    result=s.execute_plan(plan['plan_id']);assert (w/'organized/topic/named.txt').read_text()=='original bytes'
    assert s.execute_plan(plan['plan_id'])['receipt_id']==result['receipt_id']
    view=s.inspect_plan_result(result['receipt_id']);assert view['directories']==[{'root_id':'workspace','path':'empty'}]
    s.restore_plan(plan['plan_id']);assert tree(w)==spec['initial_tree']['workspace']
    with pytest.raises(Exception,match='restored plan'):s.execute_plan(plan['plan_id'])

@pytest.mark.parametrize('action',[{'op':'overwrite','source':'note.txt','destination':'existing.txt'},{'op':'delete','source':'note.txt'},{'op':'copy','source':'note.txt','destination_root':'external-owned','destination':'new.txt'}])
def test_risks_require_a_fresh_matching_one_plan_confirmation(case,action):
    s,spec,w,x,out=case;plan=s.preview_actions([action]);assert plan['status']=='confirmation_required'
    with pytest.raises(Exception,match='confirmation'):s.execute_plan(plan['plan_id'])
    assert s.actual_tree()==spec['initial_tree']
    with pytest.raises(Exception,match='approval plan'):s.approve(plan['plan_id'],'wrong',{})
    approve(s,plan);s.execute_plan(plan['plan_id'])
    assert (out/'approvals'/f"{plan['plan_id']}.json").exists()
    if action['op']=='delete':
        assert not (w/'note.txt').exists()
        with pytest.raises(Exception,match='permanent deletion'):s.restore_plan(plan['plan_id'])
    else:
        with pytest.raises(Exception,match='restoration confirmation'):s.restore_plan(plan['plan_id'])
        s.approve_restore(plan['plan_id'],s.restore_sha(plan['plan_id']),{'outcome':'allowed-once','approval_event_id':'fixture-restore','session_id':'session-alice','task_sha256':s.input_digest})
        s.restore_plan(plan['plan_id']);assert s.actual_tree()==spec['initial_tree']

@pytest.mark.parametrize('index',[0,1,2,3])
def test_process_exit_recovers_only_remaining_directory_and_file_boundaries(case,index):
    s,spec,w,x,out=case;plan=s.preview_actions([{'op':'move','source':'note.txt','destination':'a/b/note.txt'}])
    s.crash_after_effect=index
    with pytest.raises(SystemExit):s.execute_plan(plan['plan_id'])
    recovered=ManagementScene(spec,out);recovered.read_task();r=recovered.execute_plan(plan['plan_id'])
    assert (w/'a/b/note.txt').read_text()=='original bytes' and not (w/'note.txt').exists()
    assert len(recovered.journals[plan['plan_id']]['completed'])==4
    assert recovered.execute_plan(plan['plan_id'])['receipt_id']==r['receipt_id']
    recovered.restore_plan(plan['plan_id']);assert tree(w)==spec['initial_tree']['workspace']

def test_unknown_external_changes_and_approval_replay_are_rejected(case):
    s,spec,w,x,out=case;plan=s.preview_actions([{'op':'overwrite','source':'note.txt','destination':'existing.txt'}]);approve(s,plan)
    (w/'unrecorded.txt').write_text('another actor')
    with pytest.raises(Exception,match='unrecorded'):ManagementScene(spec,out)
    with pytest.raises(Exception,match='outside recorded'):s.execute_plan(plan['plan_id'])

@pytest.mark.parametrize('target',['../escape.txt','/absolute.txt','.experiment-copy','dir/../escape.txt'])
def test_paths_cannot_expand_workspace_authority(case,target):
    s,*_=case
    with pytest.raises(Exception):s.preview_actions([{'op':'copy','source':'note.txt','destination':target}])

def test_report_freezes_independent_goal_quality_and_actual_file_identities(case):
    s,spec,w,x,out=case
    s.spec['quality']={'version':QUALITY_VERSION,'requirements':[{'kind':'file','source':'note.txt','path':'copy.txt'}]}
    # New task quality must be fixed before constructing its service.
    spec={**spec,'quality':s.spec['quality']};out=out.parent/uuid4().hex;s=ManagementScene(spec,out);s.read_task()
    with pytest.raises(Exception,match='delivery rejected'):s.submit_report('not yet done',list(s.files()),[])
    plan=s.preview_actions([{'op':'copy','source':'note.txt','destination':'copy.txt'}]);s.execute_plan(plan['plan_id'])
    r=s.submit_report('copied',list(s.files()),[]);assert r['semantic_quality_verified']

def test_read_only_selection_cannot_reuse_write_permission(case):
    _,spec,w,x,out=case
    spec={**spec,'rules':{'read_only':True}};s=ManagementScene(spec,out.parent/uuid4().hex);r=s.read_task()
    assert r['default_operations']==[]
    with pytest.raises(Exception,match='read-only'):s.preview_actions([{'op':'copy','source':'note.txt','destination':'changed.txt'}])
    assert tree(w)==spec['initial_tree']['workspace']

def test_verifier_rejects_changes_beyond_recorded_effects(case):
    _,spec,w,x,out=case
    spec={**spec,'quality':{'version':QUALITY_VERSION,'requirements':[]}}
    s=ManagementScene(spec,out.parent/uuid4().hex);s.read_task();p=s.preview_actions([{'op':'copy','source':'note.txt','destination':'copy.txt'}]);s.execute_plan(p['plan_id'])
    s.submit_report('copy done',list(s.files()),[])
    import json
    from management_contract import verify_management
    data=json.loads(s.state_file.read_text());data['journals'][p['plan_id']]['boundaries'][0]['after']['workspace']['files']['unrequested.txt']='f'*64
    s.state_file.write_text(json.dumps(data));result=verify_management(spec,json.loads((s.output/'report.json').read_text()),s.output)
    assert not result['passed'] and 'state integrity differs' in result['errors']
    assert 'effect changed files beyond recorded primitive' in result['errors']

def test_collection_selection_and_pin_use_identical_current_versions(case):
    s,*_=case;files=list(s.files());selected=s.select_files(files)
    reads=[s.read_file(s.pin_file(f)['source_id']) for f in files]
    assert s.collect_reads(selected['collection_id'],[r['source_id'] for r in reads])['status']=='collection_complete'

def test_native_conversation_alias_closes_old_budget_without_reset(case):
    _,spec,w,x,out=case
    import json
    from src.adapters.operation_runner import initialize_job
    from src.adapters.file_web_task_budget import TaskBudgetRegistry
    from src.adapters.file_cost_gate import State
    limits={'budget_usd':1,'max_steps':96,'max_output':100,'max_repairs':2}
    registry=TaskBudgetRegistry(run_state=State(cap_usd=2,output_cap=100,request_limit=200,record=out.parent/(uuid4().hex+'.jsonl')),tasks_root=out.parent,task_request_limit=96,max_task_budget_usd=1)
    for index in (1,2):
        d=out.parent/uuid4().hex;d.mkdir();f=d/'input.json';f.write_text(json.dumps({**spec,'management_contract':'sss-management-v3'}))
        job=d/'operation-job.json';initialize_job(job,f,d/'delivery',limits)
        registry.register(d.name,'budget-'+str(index),1,job_file=str(job),ledger_file=str(d/'ledger.jsonl'))
    registry.alias('budget-1','visible-conversation');registry.activate('budget-1')
    with pytest.raises(ValueError):registry.alias('budget-2','visible-conversation')
    first=registry.state_for({'x-deepseek-harness-session-id':'visible-conversation'})
    booked=first.book(b'{"model":"deepseek-flash","max_tokens":100,"messages":[]}')
    usage={'prompt_tokens':12,'prompt_cache_hit_tokens':8,'prompt_cache_miss_tokens':4,'completion_tokens':3,'total_tokens':15}
    first.settle(booked[0],booked[1],200,usage)
    registry.cancel('budget-1');registry.alias('budget-2','visible-conversation');registry.activate('budget-2')
    assert registry.state_for({'x-deepseek-harness-session-id':'visible-conversation'}).task_id!=first.task_id
    assert registry.stats('budget-1')['upstream_requests']==1 and registry.stats('budget-2')['upstream_requests']==0
    assert registry.run_state.request_count==1

@pytest.mark.parametrize('index',[0,1,2,3])
def test_partial_publication_can_restore_without_executing_remaining_effects(case,index):
    s,spec,w,x,out=case;plan=s.preview_actions([{'op':'move','source':'note.txt','destination':'a/b/note.txt'}]);s.crash_after_effect=index
    with pytest.raises(SystemExit):s.execute_plan(plan['plan_id'])
    recovered=ManagementScene(spec,out);recovered.read_task();recovered.restore_plan(plan['plan_id'])
    assert tree(w)==spec['initial_tree']['workspace']
    assert len(recovered.journals[plan['plan_id']]['restore_boundaries'])==index+1

def test_narrower_task_operation_grant_is_enforced(case):
    _,spec,w,x,out=case;spec={**spec,'allowed_operations':['read']};s=ManagementScene(spec,out.parent/uuid4().hex);s.read_task()
    with pytest.raises(Exception,match='original task permission'):s.preview_actions([{'op':'copy','source':'note.txt','destination':'copy.txt'}])

def test_snapshot_compares_original_user_tree_and_records_empty_directories(case):
    s,*_=case;r=s.compare_snapshot();assert r['added']==r['modified']==r['deleted']==[]
    p=s.preview_actions([{'op':'mkdir','destination':'empty'},{'op':'copy','source':'note.txt','destination':'new/note.txt'}]);s.execute_plan(p['plan_id'])
    r=s.compare_snapshot();assert r['added']==['workspace/new/note.txt']
    assert r['added_directories']==['workspace/empty','workspace/new'] and not r['modified'] and not r['deleted']
    assert not any('.experiment-copy' in n for n in r['unchanged'])

@pytest.mark.parametrize('replace',[False,True])
def test_cross_volume_publication_and_restore_keep_atomic_user_tree(case,monkeypatch,replace):
    s,spec,w,x,out=case
    import errno,os
    link,swap=os.link,os.replace
    def cross_link(src,dst):
        if Path(src).is_relative_to(out) and (Path(dst).is_relative_to(w) or Path(dst).is_relative_to(x)):raise OSError(errno.EXDEV,'cross-volume diagnostic')
        return link(src,dst)
    def cross_swap(src,dst):
        if Path(src).is_relative_to(out) and (Path(dst).is_relative_to(w) or Path(dst).is_relative_to(x)):raise OSError(errno.EXDEV,'cross-volume diagnostic')
        return swap(src,dst)
    monkeypatch.setattr(os,'link',cross_link);monkeypatch.setattr(os,'replace',cross_swap)
    p=s.preview_actions([{'op':'overwrite' if replace else 'copy','source':'note.txt','destination':'existing.txt' if replace else 'new/copy.txt'}])
    if replace:approve(s,p)
    r=s.execute_plan(p['plan_id']);assert not s.local_staging
    if replace:s.approve_restore(p['plan_id'],s.restore_sha(p['plan_id']),{'outcome':'allowed-once','approval_event_id':'fixture-inverse','session_id':'session-alice','task_sha256':s.input_digest})
    s.restore_plan(p['plan_id']);assert s.actual_tree()==spec['initial_tree'] and not s.local_staging

@pytest.mark.parametrize('phase',['partial-copy','published'])
@pytest.mark.parametrize('direction',['resume','restore'])
@pytest.mark.parametrize('replace',[False,True])
def test_cross_volume_process_exit_keeps_partial_bytes_private_and_recovers(case,monkeypatch,phase,direction,replace):
    s,spec,w,x,out=case
    import errno,os,shutil
    link,swap,copy_bytes=os.link,os.replace,shutil.copyfileobj
    crashed=False
    def publication(fn,src,dst):
        nonlocal crashed
        if Path(src).is_relative_to(out) and Path(dst).is_relative_to(w):
            raise OSError(errno.EXDEV,'cross-volume diagnostic')
        result=fn(src,dst)
        if phase=='published' and Path(src).name.startswith('.sss-management-') and not crashed:
            crashed=True;raise SystemExit('local publication interrupted')
        return result
    def partial(src,dst,*args,**kwargs):
        nonlocal crashed
        if phase=='partial-copy' and Path(dst.name).name.startswith('.sss-management-') and not crashed:
            dst.write(src.read(3));dst.flush();crashed=True
            raise SystemExit('local copy interrupted')
        return copy_bytes(src,dst,*args,**kwargs)
    monkeypatch.setattr(os,'link',lambda src,dst:publication(link,src,dst))
    monkeypatch.setattr(os,'replace',lambda src,dst:publication(swap,src,dst))
    monkeypatch.setattr(shutil,'copyfileobj',partial)
    p=s.preview_actions([{'op':'overwrite' if replace else 'copy','source':'note.txt','destination':'existing.txt' if replace else 'new/copy.txt'}])
    if replace:approve(s,p)
    with pytest.raises(SystemExit):s.execute_plan(p['plan_id'])
    assert s.local_staging
    target=w/('existing.txt' if replace else 'new/copy.txt')
    if phase=='partial-copy':
        assert (target.read_text()=='old destination') if replace else not target.exists()
    recovered=ManagementScene(spec,out);recovered.read_task()
    assert not any('.sss-management-' in r['path'] for r in recovered.list_files()['files'])
    if direction=='resume':
        result=recovered.execute_plan(p['plan_id'])
        assert target.read_text()=='original bytes' and not recovered.local_staging
        assert recovered.execute_plan(p['plan_id'])['receipt_id']==result['receipt_id']
    if replace:recovered.approve_restore(p['plan_id'],recovered.restore_sha(p['plan_id']),{'outcome':'allowed-once','approval_event_id':'fixture-inverse','session_id':'session-alice','task_sha256':recovered.input_digest})
    recovered.restore_plan(p['plan_id'])
    assert recovered.actual_tree()==spec['initial_tree'] and not recovered.local_staging
    assert not list(w.rglob('.sss-management-*'))

def test_unknown_staging_file_is_never_hidden_from_recovery(case):
    s,spec,w,x,out=case
    (w/'.sss-management-unknown.tmp').write_text('foreign bytes')
    with pytest.raises(Exception,match='unrecorded'):ManagementScene(spec,out)
    with pytest.raises(Exception,match='outside recorded'):s.list_files()
