"""Matched H/handwritten-script/certified-Motif triples; original results never overwritten."""
import argparse,json,shutil,sys,itertools
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import DATA,HERE,PREFIX,digest,sha,save,snapshot,source_code
from collection_study import task_scope,verify_collection,GRAPH_TOOLS
from collection_tools import execution_version
from experiment import run_one,outcomes,accounting

def code():return {**source_code(),'scripts/file-batch-study.py':sha(__file__),'src/motif_core/collection_batch_script.ts':sha(ROOT/'src/motif_core/collection_batch_script.ts')}
def prepare(parent):
 old=json.loads((parent/'protocol.json').read_text());name='fm-batch-20261013-'+uuid4().hex[:8]
 exp=ROOT/'.local/file-management'/name;data=DATA/name;exp.mkdir(parents=True,mode=0o700)
 policy=json.loads((parent/'learned/policy.json').read_text())
 if policy['execution_version_sha256']!=execution_version():raise ValueError('scene changed: cannot reuse old read certification')
 save(exp/'learned/policy.json',policy)
 schemas=json.loads(next((parent/'tasks').glob('*/attempts/*/tool-schemas.json')).read_text())
 names=GRAPH_TOOLS;g={'source_tool':names[0],'pin_tool':names[1],'read_tool':names[2],'gather_tool':names[3],
  'selection':'actual_model_selected_members','array_field':'files','identity_field':'file_id','pin_param':'file_id',
  'read_param':'source_id','gather_param':'source_ids','max_targets':32,'max_batch':8,'stop':'semantic_handoff_after_complete_gather'}
 script={'schema_version':1,'format':'sss-collection-script-v1','origin':'handwritten_no_library','graph':g,'tools':names,
  'execution_version_sha256':execution_version(),'tool_schema_sha256':{PREFIX+r['name']:digest(r.get('inputSchema',r.get('input_schema'))) for r in schemas if PREFIX+r['name'] in names}}
 script['script_digest']=digest(script);save(exp/'script.json',script)
 tasks=[];permutations=list(itertools.permutations(('H','S','M')))
 pairs=[c for c in old['tasks'] if c['role']=='evaluate' and c['arm']=='H']
 for i,c in enumerate(pairs):
  pair=c['pair_id'];pristine=data/'pristine'/pair;work=data/'workspaces'/pair
  shutil.copytree(c['pristine'],pristine);shutil.copytree(pristine,work)
  origin=Path(c['task_dir']);spec=json.loads((origin/'input.json').read_text());spec.update(workspace=str(work),task_id=name+'-'+pair)
  for arm in permutations[i%6]:
   td=exp/'tasks'/(pair+'-'+arm);save(td/'input.json',spec);(td/'prompt.md').write_text((origin/'prompt.md').read_text());(td/'prompt.md').chmod(0o600)
   scenario=json.loads((origin/'scenario.json').read_text());scenario['prompt']=str(td/'prompt.md');save(td/'scenario.json',scenario)
   save(td/'collection-task.json',task_scope(spec))
   tasks.append({**c,'task_id':pair+'-'+arm,'task_dir':str(td),'arm':arm,'workspace':str(work),'pristine':str(pristine),'input_sha256':digest(spec)})
 protocol={**{k:old[k] for k in ('model','total_cap_usd','per_task_cap_usd','max_steps','max_output')},'experiment_id':name,'tasks':tasks,
  'source_code':code(),'execution_version_sha256':execution_version(),'source_library_digest':policy['policy_digest'],
  'parent_experiment':parent.name,'paired_conditions_reused':True,'new_generalization_claim':False,'planned_runs':18,
  'arm_difference':'H ordinary; S handwritten graph no library; M certified library; same dispatcher guards/batch8/tools/prompt',
  'schedule':'six permutations; each arm occurs twice in each position; frozen before any new result','human_blind_review':False}
 save(exp/'protocol.json',protocol)
 for n in protocol['source_code']:
  d=exp/'frozen-source'/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,d);d.chmod(0o600)
 save(ROOT/'.local/file-management/batch-current.json',{'experiment':str(exp)})
 print(json.dumps({'experiment':str(exp),'planned_runs':18,'per_task_cap_usd':5,'stage_max_usd':90,'series_before':accounting(),'paid':False}),flush=True)
 return exp

def summarize(exp):
 rows=[r for r in outcomes() if str(exp) in r['attempt']];fields=['upstream_requests','outputTokens','inputTokens','cacheReadTokens','budget_accounted_usd','elapsed_seconds']
 arms={a:{'runs':sum(r['arm']==a for r in rows),'passed':sum(r['arm']==a and r['acceptance']['passed'] for r in rows),
  'tool_errors':sum(r['tool_errors'] for r in rows if r['arm']==a),**{f:sum((r['run'] or {}).get(f,0) for r in rows if r['arm']==a) for f in fields}} for a in ('H','S','M')}
 result={'experiment':exp.name,'attempts':len(rows),'arms':arms,'series_accounting':accounting(),'outcomes':rows};save(exp/'summary.json',result);return result

def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path);p.add_argument('--experiment',type=Path);p.add_argument('--call-model',action='store_true');p.add_argument('--summary',action='store_true');p.add_argument('--limit',type=int);a=p.parse_args()
 exp=a.experiment.resolve() if a.experiment else prepare(a.parent.resolve());protocol=json.loads((exp/'protocol.json').read_text())
 if a.summary:
  print(json.dumps({k:v for k,v in summarize(exp).items() if k!='outcomes'}));return
 if not a.call_model:return
 if code()!=protocol['source_code']:raise ValueError('frozen execution source changed')
 cases=[c for c in protocol['tasks'] if not list((Path(c['task_dir'])/'attempts').glob('*/outcome.json'))]
 if a.limit:cases=cases[:a.limit]
 lock=ROOT/'.local/file-management/active.lock'
 with lock.open('x') as f:f.write(exp.name)
 try:
  for c in cases:
   work=Path(c['workspace']);pristine=Path(c['pristine']);td=Path(c['task_dir'])
   if not work.resolve().is_relative_to((DATA/exp.name).resolve()) or not (work/'.experiment-copy').is_file():raise ValueError('unsafe reset')
   if snapshot(pristine)!=c['initial_snapshot']:raise ValueError('pristine changed')
   shutil.rmtree(work);shutil.copytree(pristine,work)
   r=run_one(exp,c,protocol,call_model=True,server_path=HERE/'collection_tools.py',verify_result=verify_collection,
    collection_policy=exp/'learned/policy.json' if c['arm']=='M' else None,collection_task=td/'collection-task.json' if c['arm']=='M' else None,
    collection_script=exp/'script.json' if c['arm']=='S' else None,collection_script_task=td/'collection-task.json' if c['arm']=='S' else None)
   save(Path(r['attempt'])/'execution-source-code.json',code())
   dest=DATA/exp.name/'retained-final'/c['task_id']/Path(r['attempt']).name;shutil.copytree(work,dest);save(Path(r['attempt'])/'final-copy.json',{'path':str(dest),'snapshot':snapshot(dest)})
   summarize(exp)
 finally:lock.unlink()
if __name__=='__main__':main()
