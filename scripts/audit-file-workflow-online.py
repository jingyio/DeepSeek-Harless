"""Independent byte, event, original-limit and HTTP fee audit; never calls a model."""
import argparse,json,math,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import digest,sha,save,snapshot,PREFIX
from workflow_contract import verify_workflow
from src.adapters.file_job_budget import job_command
from src.adapters.file_cost_gate import observed_peak_cost

def audit(experiments):
    results=[];usage=Counter();total_raw=0;total_accounted=0;requests=0;documentation_updates={};adapter_updates={}
    for exp in experiments:
        p=json.loads((exp/'protocol.json').read_text());library=Path(p['library']);lock=json.loads((library/'library-lock.json').read_text())
        assert sha(library/'library-lock.json')==p['library_lock_sha256']
        for n,h in lock['groups']['recovery15']['dependencies'].items():assert sha(ROOT/n)==h
        for n,h in p['source_code'].items():
            assert sha(exp/'frozen-source'/n)==h
            current=sha(ROOT/n)
            if n in ('scenarios/file-management/README.md','scenarios/file-management/workflow-catalog.json','scenarios/file-management/workflow-evaluation-plan.json','scenarios/file-management/workflow-evaluation-plan.md') and current!=h:documentation_updates[n]={'frozen_sha256':h,'current_sha256':current}
            elif n=='src/adapters/file_entry_motif.ts' and current!=h:adapter_updates[exp.name]={'path':n,'frozen_sha256':h,'current_sha256':current,'basis':'original frozen runtime and retained native events; old bindings now invalid, not recertified by this audit'}
            else:assert current==h,'unrecorded source change: '+n
        for n,h in p['original_pdfs'].items():assert sha(ROOT/'testpdf'/n)==h
        base=json.loads((Path(p['parent'])/'protocol.json').read_text())
        for c in base['tasks']:
            td=Path(c['task_dir']);b=p['parent_protected'][c['task_id']]
            assert sha(td/'input-template.json')==b['template_sha256'] and sha(td/'oracle.json')==b['oracle_sha256'] and digest(snapshot(c['pristine']))==b['snapshot_sha256']
        for c in p['tasks']:
            for file in Path(c['task_dir']).glob('attempts/*/outcome.json'):
                o=json.loads(file.read_text());out=file.parent;spec=json.loads((out/'input.json').read_text());state=job_command(out/'job.json','state')['state']
                assert c['role']=='online_development' and o['normal_harness_only'] is False and not o['learning_performed']
                assert digest(spec)==o['input_sha256'] and sha(out/'input.json')==state['task_sha256']
                assert digest(json.loads((out/'source-code.json').read_text()))==o['source_sha256']==digest(p['source_code'])
                cfg=json.loads((out/'config.json').read_text());assert digest(json.loads((out/'tool-schemas.json').read_text()))==cfg['schemas_sha256']
                assert len(json.loads((out/'tool-schemas.json').read_text()))==15
                initial=json.loads((out/'job.json.events/000001.json').read_text())['state']
                for n in ('limits','task_sha256','task_file','delivery_root','execution_version_sha256'):assert state[n]==initial[n]
                assert state['requests']<=state['limits']['max_requests'] and state['steps']<=state['limits']['max_steps'] and state['repairs']<=state['limits']['max_repairs']
                assert state['spent_units']<=math.floor(state['limits']['budget_usd']*1e9) and state['checks']<=state['limits']['max_repairs']+1 and not state['pending']
                events=[];raw=0;accounted=0;actual=0;decisions=[];checks=[]
                for run in o['runs']:
                    r=Path(run['output_dir']);ep=r/'agent-events.jsonl'
                    if ep.exists():events += [json.loads(l) for l in ep.read_text().splitlines()]
                    all_rows=[json.loads(l) for l in (r/'cost-ledger.jsonl').read_text().splitlines()]
                    rows=[row for row in all_rows if row.get('kind')!='budget_denied']
                    assert all(row.get('kind')=='budget_denied' or 'response_usage' in row for row in all_rows)
                    assert len(rows)==run['upstream_requests']
                    for row in rows:
                        u=row['response_usage'];fee=observed_peak_cost(row['model'],u)
                        assert abs(fee-row['observed_peak_usd'])<1e-8 and fee<=row['reserved_upper_usd']+1e-8 and row['response_status']==200
                        raw+=fee;usage.update(u)
                    actual+=len(rows);accounted+=run['budget_accounted_usd']
                    for f in (r/'.local/online-motif').glob('*.jsonl'):decisions += [json.loads(l) for l in f.read_text().splitlines()]
                assert actual==state['requests']==o['run']['upstream_requests'] and abs(accounted-state['spent_units']/1e9)<1e-9
                assert abs(raw-accounted)<=actual*1e-9+1e-8
                assert not any(e.get('type')=='tool/call' and e['data']['name'] in (PREFIX+'pin_file',PREFIX+'read_file') for e in events)
                auto=[e['data'] for e in events if e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-plan-')]
                assert all(r['name'] in (PREFIX+'authorize_plan',PREFIX+'execute_plan') for r in auto)
                repaired=False
                for e in events:
                    if e.get('type')=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair':repaired=True
                    if repaired and e.get('type')=='tool/call':assert not e['data']['callId'].startswith('sss-plan-')
                if state['repairs']>0:assert state['motif_disabled']
                if c['task_id']=='stale-runtime':assert not auto and any(r['kind']=='durable_plan_deferred' for r in decisions)
                if c['task_id']=='revoke-before-execute':assert state['status']=='revoked' and len(auto)==1 and auto[0]['name']==PREFIX+'authorize_plan'
                if not c['expected_delivery']:assert state['status']!='completed' and snapshot(spec['workspace'])==spec['initial_snapshot']
                if c['task_id']=='dollar-budget':
                    denials=[json.loads(f.read_text()) for f in (out/'job.json.events').glob('*.json') if json.loads(f.read_text())['kind']=='request_denied']
                    assert actual>=1 and denials and state['limits']['budget_usd']==0.01 and state['requests']<state['limits']['max_requests']
                report=json.loads((out/'delivery/report.json').read_text()) if (out/'delivery/report.json').exists() else None
                last=Path(o['runs'][-1]['output_dir'])/'agent-events.jsonl';last_events=[json.loads(l) for l in last.read_text().splitlines()] if last.exists() else []
                review=verify_workflow(spec,report if o['receipt_verified'] else None,out/'delivery',last_events)
                assert review['passed']==o['acceptance']['passed']
                if c['task_id']=='acceptance-repair':
                    trace=Path(o['runs'][-1]['acceptance_trace_dir']);checks=[json.loads(f.read_text()) for f in sorted(trace.glob('round-*/result.json'))]
                    assert state['repairs']>=1 and checks and not checks[0]['passed'] and checks[-1]['passed']
                if c['task_id']=='crash-recovery':assert any(e.get('type')=='tool/call' and e['data']['name']==PREFIX+'restore_plan' and not e['data']['callId'].startswith('sss-') for e in events)
                assert o['condition_passed']
                verified=sum(r['kind']=='plan_model_request_bypassed_verified' for r in decisions)
                assert verified==o['run']['plan_model_requests_bypassed_verified']
                results.append({'experiment':exp.name,'task_id':c['task_id'],'requests':actual,'raw_peak_usage_cost_usd':raw,'durable_accounted_usd':accounted,'delivery_passed':review['passed'],
                                'original_limits_preserved':True,'content_reads':0,'verified_skips':verified,'repairs':state['repairs'],'checks':state['checks'],'status':state['status'],'outcome_sha256':sha(file)})
                requests+=actual;total_raw+=raw;total_accounted+=accounted
    r={'status':'passed','experiments':[e.name for e in experiments],'checks':len(results),'requests':requests,'raw_peak_usage_cost_usd':total_raw,'durable_accounted_usd':total_accounted,
       'usage':dict(usage),'original_54_templates_oracles_pristine_and_3_pdfs_unchanged':True,'old_library_lock_and_recovery_dependencies_unchanged':True,'holdout_runs':0,
       'actual_bill_verified':False,'human_blind_review':False,'results':results,'post_run_documentation_updates':documentation_updates,'archived_adapter_updates':adapter_updates,'auditor_source_sha256':sha(Path(__file__))}
    for exp in experiments:save(exp/'online-independent-audit.json',r)
    return r

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiments',nargs='+',type=Path,required=True);args=a.parse_args()
    print(json.dumps(audit([p.resolve() for p in args.experiments]),ensure_ascii=False))
