"""Frozen paired normal-Harness/learned-entry experiment; all model calls use SDK budget."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from pdf_tools import ROOT,digest,save_private
from pdf_repair_tools import RepairScene

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def lines(text):
 result=[]
 for line in text.splitlines():
  try:
   v=json.loads(line)
   if isinstance(v,dict):result.append(v)
  except ValueError:pass
 return result
def code_snapshot():
 files=list(HERE.glob('*.py'))+list(HERE.glob('*.ts'))+list(HERE.glob('*.json'))
 files += [ROOT/p for p in ['src/motif_core/entry_read_policy.ts','src/motif_core/offline/entry_compiler.py',
  'src/adapters/dsh_entry_motif.ts','src/adapters/scenario.py','scripts/run-scenario.py','src/motif_core/online_skill_runtime.mjs','package-lock.json']]
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}

def prepare(root):
 policy=root/'learned-v3/entry-policy.json'
 recipes=[('single-paper-five','b1ba72ba-56bb-4528-a64a-6513e343cb34',
  ['claim:pdf:local:59dc83f25e1849393f8e42c1:'+f for f in ('research_goal','method','evaluation','findings','limitations')],'normal_targeted_review'),
  ('two-claims','8df37d70-f13a-40cb-b178-50bee0854928',
  ['claim:pdf:local:90e21289c9609e0f42cfa006:research_goal','claim:pdf:local:90e21289c9609e0f42cfa006:limitations'],'normal_targeted_review'),
  ('one-gap','159c2f1f-d5fa-4ddd-b6d8-c60bfbefe530',['claim:pdf:local:59dc83f25e1849393f8e42c1:method'],'controlled_missing_data_diagnostic')]
 cases=[]
 for label,parent,targets,kind in recipes:
  directory=root/'cases'/label;job=ROOT/'.local/literature-notes/agent-jobs'/parent
  candidate=read(job/'evidence.json');snapshot=read(job/'source-snapshot.json')
  for name,value in [('evidence.json',candidate),('pdf-input-snapshot.json',snapshot),('repair-targets.json',
   {'input_sha256':digest(candidate),'claim_ids':targets,'round_number':1,'review_mode':'compare_existing_claim','scope':'claim_support_audit'}),
   ('input-provenance.json',{'kind':kind,'original_job':parent,'synthetic_native_events':False,'gold_visible_to_model':False})]:save_private(directory/name,value)
  scene=RepairScene(directory,root/'preflight'/label)
  packets={cid:digest(scene.read_claim_repair_packet(cid)) for cid in targets}
  cases.append({'label':label,'directory':str(directory),'kind':kind,'parent_job':parent,'input_sha256':scene.input_digest,
   'target_ids':targets,'packet_sha256':packets,'source_snapshot_sha256':digest(snapshot)})
 order=[{'case':case['label'],'round':r+1,'arm':arm} for c,case in enumerate(cases) for r in range(3)
  for arm in (['harness','motif'] if (c+r)%2==0 else ['motif','harness'])]
 protocol={'schema_version':1,'created_before_paid_calls':True,'policy':str(policy),'policy_digest':read(policy)['policy_digest'],
  'cases':cases,'order':order,'model':'deepseek-flash','reasoning_effort':'off','total_budget_usd':5,'per_run_budget_usd':.5,
  'repeats':3,'same_prompt_and_tools':True,'quality':'same frozen source packets; citations/current sources and non-target retention; no expert semantic equivalence claim',
  'code':code_snapshot(),'training_reuse':'known-corpus original workflow traces; evaluation scopes not used to compile or certify',
  'metrics':'actual HTTP requests and provider output tokens; synthetic runtime batches separately counted; all failure fees retained'}
 save_private(root/'comparison-protocol.json',protocol);return protocol

def verify_output(case,output):
 baseline=read(Path(case['directory'])/'evidence.json');final=read(output/'revised-evidence.json')
 before={(p['paper_id'],f['name']):f for p in baseline['draft']['papers'] for f in p['fields']}
 after={(p['paper_id'],f['name']):f for p in final['draft']['papers'] for f in p['fields']}
 targets=set(case['target_ids'])
 if set(before)!=set(after):raise ValueError('delivery field set changed')
 for key,value in before.items():
  if 'claim:'+key[0]+':'+key[1] not in targets and after[key]!=value:raise ValueError('non-target changed')
 return {'source_receipt_collected':True,'non_target_fields_preserved':len(before)-len(targets),
  'target_evidence_count':sum(v['status']=='evidence' for (pid,name),v in after.items() if 'claim:'+pid+':'+name in targets),
  'target_count':len(targets),'gap_count':len(final['gaps']),'scientific_truth_certified':False}

def compare(root,call):
 protocol=read(root/'comparison-protocol.json')
 if protocol['code']!=code_snapshot() or read(protocol['policy'])['policy_digest']!=protocol['policy_digest']:raise ValueError('frozen code/policy changed')
 for c in protocol['cases']:
  scene=RepairScene(Path(c['directory']),root/'replay'/c['label'])
  if scene.input_digest!=c['input_sha256'] or {cid:digest(scene.read_claim_repair_packet(cid)) for cid in c['target_ids']}!=c['packet_sha256']:raise ValueError('frozen source packets changed')
 if not call:print(json.dumps({'protocol':str(root/'comparison-protocol.json'),'model_call_enabled':False,'case_targets':[len(c['target_ids']) for c in protocol['cases']],'runs':len(protocol['order']),'total_budget_usd':5}));return
 if (root/'comparison-progress.json').exists():raise ValueError('preserve prior results; do not silently rerun')
 progress={'status':'running','rows':[],'total_requests':0,'total_estimated_usd':0}
 try:
  for index,slot in enumerate(protocol['order']):
   case=next(c for c in protocol['cases'] if c['label']==slot['case']);remaining=5-progress['total_estimated_usd']
   if remaining<.002:raise ValueError('experiment budget exhausted')
   command=[sys.executable,str(HERE/'repair-pdf.py'),'--run',case['directory'],'--budget-usd',str(min(.5,remaining)),'--call-model']
   if slot['arm']=='motif':command+=['--entry-policy',protocol['policy']]
   save_private(root/'active-comparison.json',{'index':index+1,**slot});start=time.monotonic()
   r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
   for name,text in [('stdout',r.stdout),('stderr',r.stderr)]:
    p=root/'raw'/(str(index+1)+'-'+name+'.txt');p.parent.mkdir(mode=0o700,parents=True,exist_ok=True);p.write_text(text);p.chmod(0o600)
   summaries=[v for v in lines(r.stdout) if 'output_dir' in v];out=next((v for v in lines(r.stdout) if 'claim_repair' in v),None)
   row={**slot,'exit_code':r.returncode,'elapsed_seconds':time.monotonic()-start,'summaries':summaries,
    'actual_requests':sum(v.get('upstream_requests',0) for v in summaries),
    'estimated_usd':sum(v.get('budget_accounted_usd',0) for v in summaries),
    'output_tokens':sum(v.get('outputTokens',0) for v in summaries),
    'verified_runtime_batches':sum(v.get('entry_model_requests_bypassed_verified',0) for v in summaries),
    'repair_directory':out['claim_repair'] if out else None}
   progress['rows'].append(row);progress['total_requests']+=row['actual_requests'];progress['total_estimated_usd']+=row['estimated_usd'];save_private(root/'comparison-progress.json',progress)
   if not summaries or any('budget_accounted_usd' not in v for v in summaries):raise ValueError('missing actual accounting')
   if out:row['quality']=verify_output(case,Path(out['claim_repair']))
   row['status']='delivered' if out and r.returncode==0 else 'failed'
   save_private(root/'comparison-progress.json',progress);print(json.dumps({k:v for k,v in row.items() if k!='summaries'},ensure_ascii=False),flush=True)
   if row['status']=='failed':raise ValueError('paid run failed; retained costs and stopped before new run')
  progress['status']='completed'
 except Exception as e:progress['status']='failed';progress['error']=str(e);raise
 finally:save_private(root/'comparison-progress.json',progress)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);p.add_argument('--prepare',action='store_true');p.add_argument('--call-model',action='store_true');a=p.parse_args();root=a.experiment.resolve()
 if not root.is_relative_to(ROOT/'.local'):raise ValueError('experiment must be private')
 if a.prepare:
  if a.call_model or (root/'comparison-protocol.json').exists():raise ValueError('prepare a fresh protocol before paid calls')
  prepare(root)
 compare(root,a.call_model)
