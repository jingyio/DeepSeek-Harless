"""Actual copy effects, permissions, durable restart and conservative restore checks."""
import copy,importlib.util,sys
from pathlib import Path
import pytest
from tests.test_file_management import common,fm
prior={n:sys.modules.get(n) for n in ('common','file_tools')};sys.modules.update(common=common,file_tools=fm)
sp=importlib.util.spec_from_file_location('authorized_plan_test',Path(__file__).resolve().parents[1]/'scenarios/file-management/plan_tools.py')
mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod)
for n,v in prior.items():
 if v is None:sys.modules.pop(n,None)
 else:sys.modules[n]=v
@pytest.fixture
def scene(tmp_path,monkeypatch):
 monkeypatch.setattr(fm,'ROOT',tmp_path);monkeypatch.setattr(fm,'DATA',tmp_path/'data');monkeypatch.setattr(mod,'ROOT',tmp_path);monkeypatch.setattr(mod,'execution_version',lambda:'a'*64)
 root=tmp_path/'data/copy';root.mkdir(parents=True);(root/'.experiment-copy').write_text('test');(root/'a.txt').write_text('first');(root/'b.txt').write_text('second')
 spec={'workspace':str(root),'task_id':'one','family':'test','objective':'copy','rules':{},'initial_snapshot':common.snapshot(root),
  'allowed_operations':['copy','move','quarantine'],'write_grant':{'schema_version':1,'allowed_ops':['copy','move','quarantine'],'source_paths':['a.txt','b.txt'],'destination_prefixes':['processed/','quarantine/'],'max_actions':6,'allow_restore':True}}
 s=mod.PlanScene(spec,tmp_path/'.local/out');s.read_task();return s

def prepared(s,op='move',name='a.txt',dest='processed/a.txt'):
 row=next(r for r in s.list_files()['files'] if r['path']==name)
 p=s.preview_actions([fm.Action(op=op,file_ids=[row['file_id']],destination=dest)]);a=s.authorize_plan(p['plan_id']);return p,a

def test_restart_and_idempotent_effect_and_restore(scene):
 p,a=prepared(scene);r=scene.execute_plan(p['plan_id'],a['authorization_id']);s=mod.PlanScene(scene.spec,scene.output);s.read_task()
 assert s.execute_plan(p['plan_id'],a['authorization_id'])==r
 rr=s.restore_plan(p['plan_id'],a['authorization_id']);s2=mod.PlanScene(scene.spec,scene.output);s2.read_task();assert s2.restore_plan(p['plan_id'],a['authorization_id'])==rr
 assert common.snapshot(s2.root)==s2.spec['initial_snapshot']
 with pytest.raises(fm.ToolError):s2.execute_plan(p['plan_id'],a['authorization_id'])
@pytest.mark.parametrize('kind',['operation','destination','source','count','escape'])
def test_exact_task_permission_rejects(scene,kind):
 row=scene.list_files()['files'][0];a=fm.Action(op='copy',file_ids=[row['file_id']],destination='processed/x.txt');actions=[a]
 if kind=='operation':scene.grant['allowed_ops']=['move']
 if kind=='destination':a.destination='unapproved/x.txt'
 if kind=='escape':a.destination='processed/../../escape.txt'
 if kind=='source':scene.grant['source_paths']=['b.txt']
 if kind=='count':scene.grant['max_actions']=1;actions=[a,a]
 with pytest.raises(fm.ToolError):scene.preview_actions(actions)
 assert common.snapshot(scene.root)==scene.spec['initial_snapshot']
def test_wrong_token_and_stale_snapshot_no_effect(scene):
 p,a=prepared(scene)
 with pytest.raises(fm.ToolError):scene.execute_plan(p['plan_id'],'wrong-token')
 p2,a2=prepared(scene,op='copy',name='b.txt',dest='processed/b.txt');scene.execute_plan(p2['plan_id'],a2['authorization_id'])
 with pytest.raises(fm.ToolError):scene.execute_plan(p['plan_id'],a['authorization_id'])
def test_partial_failure_restart_restore_no_reexecution(scene):
 spec=copy.deepcopy(scene.spec);spec['fault_after_operations']=1;scene=mod.PlanScene(spec,scene.output.with_name('fault-out'));scene.read_task()
 rows=scene.list_files()['files'];p=scene.preview_actions([fm.Action(op='move',file_ids=[r['file_id']],destination='processed/'+r['path']) for r in rows]);a=scene.authorize_plan(p['plan_id'])
 with pytest.raises(fm.ToolError):scene.execute_plan(p['plan_id'],a['authorization_id'])
 s=mod.PlanScene(scene.spec,scene.output);s.read_task()
 with pytest.raises(fm.ToolError):s.execute_plan(p['plan_id'],a['authorization_id'])
 s.restore_plan(p['plan_id'],a['authorization_id']);assert common.snapshot(s.root)==s.spec['initial_snapshot']
def test_later_plan_prohibits_old_restore(scene):
 p,a=prepared(scene,'copy');scene.execute_plan(p['plan_id'],a['authorization_id']);p2,a2=prepared(scene,'copy','b.txt','processed/b.txt');scene.execute_plan(p2['plan_id'],a2['authorization_id'])
 with pytest.raises(fm.ToolError):scene.restore_plan(p['plan_id'],a['authorization_id'])
def test_external_change_and_version_restart_rejected(scene,monkeypatch):
 p,a=prepared(scene,'copy');scene.execute_plan(p['plan_id'],a['authorization_id']);(scene.root/'external.txt').write_text('later work')
 with pytest.raises(fm.ToolError):scene.restore_plan(p['plan_id'],a['authorization_id'])
 with pytest.raises(ValueError):mod.PlanScene(scene.spec,scene.output)
 (scene.root/'external.txt').unlink();monkeypatch.setattr(mod,'execution_version',lambda:'b'*64)
 with pytest.raises(ValueError):mod.PlanScene(scene.spec,scene.output)
def test_recorded_atomic_move_boundary_recovers(scene):
 p,a=prepared(scene);plan=scene.plans[p['plan_id']];before=scene.expected.copy();both={**before,'processed/a.txt':before['a.txt']};after={k:v for k,v in both.items() if k!='a.txt'}
 for n in before:
  d=scene.output/'backups'/p['plan_id']/n;d.parent.mkdir(parents=True,exist_ok=True);d.write_bytes((scene.root/n).read_bytes())
 scene.journals[p['plan_id']]={'status':'executing','before':before,'after':before,'completed':[],'inflight_states':[before,both,after]};scene.persist();scene.publish(scene.root/'a.txt',scene.root/'processed/a.txt')
 s=mod.PlanScene(scene.spec,scene.output);s.read_task();s.restore_plan(p['plan_id'],a['authorization_id']);assert common.snapshot(s.root)==before
def test_restore_grant_revocation_no_effect(scene):
 p,a=prepared(scene);scene.execute_plan(p['plan_id'],a['authorization_id']);scene.grant['allow_restore']=False
 with pytest.raises(fm.ToolError):scene.restore_plan(p['plan_id'],a['authorization_id'])

def test_independent_verifier_uses_frozen_scope_after_effect(scene):
 # Regression for the first paid trial: constructing the initial scene after writes rejected valid effects.
 import importlib.util
 path=Path(__file__).resolve().parents[1]/'scenarios/file-management';sys.path.insert(0,str(path))
 sp=importlib.util.spec_from_file_location('plan_study_verifier_test',path/'plan_study.py');study=importlib.util.module_from_spec(sp);sp.loader.exec_module(study);sys.path.remove(str(path))
 spec=copy.deepcopy(scene.spec);spec.update(expected_effects=[{'op':'copy','source':'a.txt','destination':'processed/a.txt'}],expected_restore=False)
 s=mod.PlanScene(spec,scene.output.with_name('verify-out'));s.read_task();p,a=prepared(s,'copy');r=s.execute_plan(p['plan_id'],a['authorization_id']);report={'receipts':[r]}
 assert study.scope(spec)['snapshot_sha256']==common.digest(spec['initial_snapshot'])
 assert study.verify_plan(spec,report,s.output,[])['passed']
