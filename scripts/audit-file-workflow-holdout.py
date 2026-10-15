"""Independent frozen-pair, byte, restriction, raw-HTTP and full-cost audit; no provider calls."""
import argparse,json,math,hashlib,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import digest,sha,snapshot,save,PREFIX
from workflow_contract import verify_workflow
from experiment import accounting
from src.adapters.deepseek_cost_gate import observed_peak_cost
from src.adapters.file_job_budget import job_command

def audit(exp,partial=False):
 p=json.loads((exp/'protocol.json').read_text());pl=json.loads((exp/'protocol-lock.json').read_text());assert sha(exp/'protocol.json')==pl['sha256']
 library=Path(p['library']);lock=json.loads((library/'library-lock.json').read_text());assert sha(library/'library-lock.json')==p['library_lock_sha256']
 documentation={}
 for n,h in p['source_code'].items():
  assert sha(exp/'frozen-source'/n)==h
  if sha(ROOT/n)!=h:
   assert n.endswith('.md') and n.startswith('scenarios/file-management/'),n
   documentation[n]={'frozen_sha256':h,'current_sha256':sha(ROOT/n)}
 for group in lock['groups'].values():
  for n,h in group['dependencies'].items():assert sha(ROOT/n)==h
 for rec in lock['artifacts']:assert sha(library/'libraries'/rec['path'])==rec['sha256']
 for n,h in p['test_sources'].items():assert sha(exp/n)==h
 for n,h in p['original_pdfs'].items():assert sha(ROOT/'testpdf'/n)==h
 base=json.loads((Path(p['parent'])/'protocol.json').read_text())
 for c in base['tasks']:
  td=Path(c['task_dir']);f=p['parent_protected'][c['task_id']]
  assert sha(td/'input-template.json')==f['template_sha256'] and sha(td/'oracle.json')==f['oracle_sha256'] and digest(snapshot(c['pristine']))==f['snapshot_sha256']
 by_pair={};rows=[];usage=Counter();raw_cost=0;accounted=0;real_requests=0;unknown_usage=[]
 for c in p['tasks']:
  files=list(Path(c['task_dir']).glob('attempts/*/outcome.json'))
  if partial and not files:continue
  assert len(files)==1,(c['task_id'],len(files))
  file=files[0];o=json.loads(file.read_text());out=file.parent;spec=json.loads((out/'input.json').read_text());td=Path(c['template_dir']);template=json.loads((td/'input-template.json').read_text())
  assert o['role']=='holdout' and not o['learning_performed'] and o['arm']==c['arm']
  assert digest(spec)==o['input_sha256'] and digest(json.loads((out/'source-code.json').read_text()))==o['source_sha256']==digest(p['source_code'])
  assert {k:v for k,v in spec.items() if k!='workspace'}=={k:v for k,v in template.items() if k!='workspace'}
  pair=by_pair.setdefault(c['pair_id'],{'template_sha256':sha(td/'input-template.json'),'prompt_sha256':sha(td/'prompt.md'),'input_snapshot_sha256':digest(spec['initial_snapshot']),'arms':{}})
  assert pair['template_sha256']==sha(td/'input-template.json') and pair['input_snapshot_sha256']==digest(spec['initial_snapshot']) and pair['prompt_sha256']==sha(td/'prompt.md')
  pair['arms'][c['arm']]=o
  config=json.loads((out/'config.json').read_text());schemas=json.loads((out/'tool-schemas.json').read_text());assert digest(schemas)==config['schemas_sha256']
  assert len(schemas)==(15 if c['workflow_id']=='FM38' else 14)
  events=[];request_count=0;observed=0;charged=0;decisions=[]
  if o['zero_model']:
   assert o['run']['upstream_requests']==o['run']['budget_accounted_usd']==0
   calls=[json.loads(l) for l in (out/'mcp-calls.jsonl').read_text().splitlines()]
   assert all(row['name'] in {r['name'] for r in schemas} for row in calls)
   assert not any(row['name']=='pin_file' for row in calls) or c['workflow_id']=='FM05'
   assert not any(row['name'] in ('run_code','exec','read_oracle') for row in calls)
  else:
   for run in o['runs']:
    r=Path(run['output_dir']);ep=r/'agent-events.jsonl'
    if ep.exists():events += [json.loads(l) for l in ep.read_text().splitlines()]
    all_ledger=[json.loads(l) for l in (r/'cost-ledger.jsonl').read_text().splitlines()]
    ledger=[v for v in all_ledger if v.get('kind')!='budget_denied'];assert len(ledger)==run['upstream_requests']
    for row in ledger:
     u=row.get('response_usage',{})
     if not u:unknown_usage.append({'task':c['task_id'],'run':run['output_dir'],'request_id':row['request_id'],'reservation_held':row['reserved_upper_usd']});continue
     cost=observed_peak_cost(row['model'],u);assert abs(cost-row['observed_peak_usd'])<1e-8 and cost<=row['reserved_upper_usd']+1e-8
     usage.update(u);observed+=cost
    request_count+=len(ledger);charged+=run['budget_accounted_usd']
    for f in (r/'.local/online-motif').glob('*.jsonl'):decisions += [json.loads(l) for l in f.read_text().splitlines()]
   assert request_count==o['run']['upstream_requests'] and abs(charged-o['run']['budget_accounted_usd'])<1e-9
   assert charged<=5 and request_count<=96
   if not any(r['task']==c['task_id'] for r in unknown_usage):assert abs(observed-charged)<=request_count*1e-9+1e-7
   if c['arm']=='H':assert not decisions and not any(e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-') for e in events)
   if c['arm']=='S':assert not any(row['kind'].startswith(('plan_motif','entry_motif','reentry_motif','collection_motif')) for row in decisions)
   automatic=[e['data'] for e in events if e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-')]
   allowed={PREFIX+n for n in (('authorize_plan','execute_plan') if c['workflow_id']=='FM38' else ('pin_file','read_file','collect_reads'))}
   assert all(row['name'] in allowed for row in automatic)
   if c['workflow_id']=='FM17':assert not automatic
   repair_seen=False
   for e in events:
    if e.get('type')=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair':repair_seen=True
    if repair_seen and e.get('type')=='tool/call':assert not e['data']['callId'].startswith('sss-')
   cv=sum(row.get('kind')=='collection_model_request_bypassed_verified' for row in decisions);pv=sum(row.get('kind')=='plan_model_request_bypassed_verified' for row in decisions);sv=sum(row.get('kind')=='collection_script_batch_verified' for row in decisions)
   assert cv==o['run']['collection_model_requests_bypassed_verified'] and pv==o['run']['plan_model_requests_bypassed_verified'] and sv==o['run']['collection_script_batches_verified']
  report=json.loads((out/'delivery/report.json').read_text()) if (out/'delivery/report.json').exists() else None
  review=verify_workflow(spec,report if o['receipt_verified'] else None,out/'delivery',events);assert review['passed']==o['acceptance']['passed']
  reads=[json.loads(f.read_text()) for f in (out/'delivery/reads').glob('*.json')]
  assert all(row['path'] in spec['workflow_contract']['allowed_reads'] and row['sha256']==spec['initial_snapshot'][row['path']] for row in reads)
  assert digest(snapshot(spec['workspace']))==o['final_snapshot_sha256']
  marker=o['control_marker']
  if c['condition']=='V':
   assert marker and marker['mode']=='version' and not review['passed']
   assert sha(Path(spec['workspace'])/marker['target'])==marker['after_sha256']
   journals=[json.loads(f.read_text()) for f in (out/'delivery/journals').glob('*.json')]
   current=dict(spec['initial_snapshot'])
   if c['workflow_id']=='FM17':
    # Before the frozen backup mutation, only declared backups may have been copied.
    for j in journals:
     for a in j.get('completed',[]):
      assert a['destination'].startswith('backup-set/') and a['op']=='copy'
      ids={'file:local:'+digest({'path':n,'sha':h})[:24]:n for n,h in j['before'].items()}
      current[a['destination']]=j['before'][ids[a['file_ids'][0]]]
   elif c['workflow_id']=='FM38':
    assert len(journals)==1 and journals[0]['status'] in ('executing','partial_failure')
    candidates=journals[0]['inflight_states'];current=next((s for s in candidates if {**s,marker['target']:marker['after_sha256']}==snapshot(spec['workspace'])),None);assert current is not None
   else:assert not journals
   current={**current,marker['target']:marker['after_sha256']};assert current==snapshot(spec['workspace']),c['task_id']
   assert (Path(spec['workspace'])/'outside-scope/sentinel.txt').read_bytes()==(Path(c['pristine'])/'outside-scope/sentinel.txt').read_bytes()
  elif c['workflow_id']=='FM38' and review['passed']:
   if not o['zero_model']:
    assert len(o['runs'])==2 and (out/'cold-restart.json').exists()
    boundary=json.loads((out/'cold-restart.json').read_text());assert boundary['same_task_and_budget']
   else:assert (out/'script-cold-before.json').exists()
  if c['workflow_id']=='FM38':
   state=job_command(out/'job.json','state')['state'];initial=json.loads((out/'job.json.events/000001.json').read_text())['state']
   assert all(state[n]==initial[n] for n in ('limits','task_sha256','task_file','execution_version_sha256','delivery_root'))
   assert state['requests']==request_count and state['spent_units']<=5e9 and state['repairs']<=2 and state['checks']<=3 and not state['pending']
   if not o['zero_model']:assert abs(state['spent_units']/1e9-charged)<1e-9
   if state['repairs']:assert state['motif_disabled']
   assert state['status']=='completed' if review['passed'] else state['status']!='completed'
  rows.append({'task':c['task_id'],'arm':c['arm'],'condition':c['condition'],'workflow_id':c['workflow_id'],'delivery_passed':review['passed'],'condition_passed':o['condition_passed'],
               'requests':request_count,'observed_peak_usd':observed,'accounted_usd':charged,'zero_model':o['zero_model'],'outcome_sha256':sha(file),'original_grants_limits_versions_preserved':True})
  real_requests+=request_count;raw_cost+=observed;accounted+=charged
 if not partial:assert len(rows)==54 and len(by_pair)==18 and all(set(v['arms'])=={'H','S','M'} for v in by_pair.values())
 overhead=Counter()
 for o in p['overhead_sources']:
  assert sha(Path(o['path']))==o['sha256'];overhead[o['category']]+=o['estimated_usd']
 result={'status':'passed','partial':partial,'experiment_id':exp.name,'frozen_triples':18,'runs':len(rows),'requests':real_requests,'observed_peak_usd':raw_cost,'accounted_usd':accounted,'usage':dict(usage),'unknown_usage_conservatively_accounted':unknown_usage,
    'library_acquisition_usd':overhead['acquisition'],'online_validation_usd':overhead['online_validation'],'all_upfront_usd':sum(overhead.values()),'parent54_and_three_original_pdfs_unchanged':True,
    'holdout_used_for_learning':False,'current_documentation_updates':documentation,'human_blind_review':False,'actual_bill_verified':False,'results':rows,'series':accounting(),'auditor_source_sha256':sha(Path(__file__))}
 save(exp/('partial-independent-audit.json' if partial else 'independent-audit.json'),result);return result

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);a.add_argument('--partial',action='store_true');args=a.parse_args();print(json.dumps(audit(args.experiment.resolve(),args.partial),ensure_ascii=False))
