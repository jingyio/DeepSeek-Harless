"""Independent v1 invalidation/repair, new v2 provenance, fresh five-arm bytes and all HTTP costs."""
import argparse,json,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import sha,digest,snapshot,save,PREFIX
from script_adaptation_study import frozen,ARMS
from script_adaptation_learning import load_witness,RUNTIME_FILES
from workflow_contract import verify_workflow
from experiment import accounting
from src.adapters.deepseek_cost_gate import observed_peak_cost

def audit(exp,partial=False):
    p=json.loads((exp/'protocol.json').read_text());frozen(exp,p,True)
    for n,h in p['source_code'].items():assert sha(exp/'frozen-source'/n)==h
    for n,h in p['test_sources'].items():assert sha(exp/n)==h
    for n,h in p['original_pdfs'].items():assert sha(ROOT/'testpdf'/n)==h
    cert=None
    if (exp/'candidate-lock.json').exists():
        lock=json.loads((exp/'candidate-lock.json').read_text());assert lock['protocol_sha256']==sha(exp/'protocol.json')
        for rec in lock['scripts']:
            s=json.loads(Path(rec['path']).read_text());assert sha(rec['path'])==rec['sha256'];guards=[]
            assert s['runtime_source']=={n:sha(ROOT/n) for n in RUNTIME_FILES}
            for w in s['training']:
                c=next(c for c in p['tasks'] if c['task_id']==w['task_id']);program,review,guard=load_witness(c);assert review==w
                assert {k:v for k,v in s.items() if k not in ('training','guard_cases','runtime_source','script_digest')}==program;guards.append(guard)
            assert {digest(g) for g in guards}=={digest(g) for g in s['guard_cases']}
    if (exp/'certificate-v2.json').exists():
        cert=json.loads((exp/'certificate-v2.json').read_text());assert cert['status']=='certified_v2' and cert['candidate_lock_sha256']==sha(exp/'candidate-lock.json')
        assert len(cert['reviews'])==8
        for v in cert['reviews']:assert sha(v['outcome_file'])==v['outcome_sha256']
    tasks=list(p['tasks']);templates=list(p['templates'])
    if (exp/'holdout.json').exists():
        held=json.loads((exp/'holdout.json').read_text());assert sha(exp/'holdout.json')==json.loads((exp/'holdout-lock.json').read_text())['sha256'];assert held['certificate_sha256']==sha(exp/'certificate-v2.json') and held['model_holdout_runs_when_frozen']==0 and not held['learning_from_holdout_permitted']
        tasks+=held['tasks'];templates+=held['templates']
    for c in templates:
        td=Path(c['task_dir']);assert sha(td/'input-template.json')==c['input_template_sha256'] and sha(td/'oracle.json')==c['oracle_sha256'] and sha(td/'prompt.md')==c['prompt_sha256'] and sha(td/'scenario.json')==c['scenario_sha256'] and digest(snapshot(c['pristine']))==c['snapshot_sha256']
    rows=[];usage=Counter();requests=0;cost=0;groups={};repairs=0
    for c in tasks:
        files=list(Path(c['task_dir']).glob('attempts/*/outcome.json'))
        if partial and not files:continue
        assert len(files)==1,c['task_id'];f=files[0];o=json.loads(f.read_text());a=f.parent;spec=json.loads((a/'input.json').read_text());base=json.loads((Path(c['template_dir'])/'input-template.json').read_text());schemas=json.loads((a/'tool-schemas.json').read_text())
        assert o['role']==c['role'] and o['arm']==c['arm'] and o['accounting_complete'] and not o['learning_performed'] and o['input_sha256']==digest(spec)
        source=json.loads((Path(c['origin_experiment'])/'protocol.json').read_text())['source_code'] if c.get('origin_experiment') else p['source_code']
        assert {k:v for k,v in spec.items() if k!='workspace'}=={k:v for k,v in base.items() if k!='workspace'} and json.loads((a/'source-code.json').read_text())==source
        assert o['source_sha256']==digest(source)
        if c.get('origin_experiment'):
            rec=next(r for r in p['imported_maintenance'] if r['task_id']==c['task_id']);assert sha(f)==rec['outcome_sha256'] and sha(Path(c['origin_experiment'])/'protocol.json')==rec['protocol_sha256']
            for n,hv in source.items():assert sha(Path(c['origin_experiment'])/'frozen-source'/n)==hv
        assert len(schemas)==14;events=[];rq=0;usd=0
        if c['arm']=='S':assert o['run']['upstream_requests']==o['run']['budget_accounted_usd']==0
        else:
            for run in o['runs']:
                r=Path(run['output_dir']);events+=[json.loads(l) for l in (r/'agent-events.jsonl').read_text().splitlines()]
                ledgers=[json.loads(l) for l in (r/'cost-ledger.jsonl').read_text().splitlines()] if (r/'cost-ledger.jsonl').exists() else []
                paid=[v for v in ledgers if v.get('kind')!='budget_denied'];assert len(paid)==run['upstream_requests']
                for v in paid:
                    u=v.get('response_usage');assert u and v.get('observed_peak_usd') is not None,'unknown usage must be reconciled';assert abs(observed_peak_cost(v['model'],u)-v['observed_peak_usd'])<1e-8;usage.update(u)
                rq+=len(paid);usd+=run['budget_accounted_usd']
            assert rq==o['run']['upstream_requests'] and abs(usd-o['run']['budget_accounted_usd'])<1e-9 and rq<=96 and usd<=5 and len(o['runs'])==1
            auto=[e for e in events if e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-')]
            if c['arm']=='H':assert not auto
            if c['arm']=='M':assert all(e['data']['name'] in {PREFIX+n for n in ('pin_file','read_file','collect_reads')} for e in auto)
            if c['arm'] in ('L1','L2'):
                audit=[json.loads(l) for l in (a/'script-audit.jsonl').read_text().splitlines()];assert o['script_steps']==sum(v['kind'] in ('learned_script_step_verified','script_v2_step_verified') for v in audit)
                assert all(e['data']['name'] in {PREFIX+n for n in ('read_task','list_files','pin_file','read_file','hash_files','preview_actions','execute_plan','submit_report')} for e in auto)
            after_repair=False;rc=0
            for e in events:
                if e.get('type')=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair':after_repair=True;rc+=1
                if after_repair and e.get('type')=='tool/call':assert not e['data']['callId'].startswith('sss-')
            assert rc==o['acceptance_repairs'] and rc<=2;repairs+=rc
            if c.get('controlled_draft'):
                marker=o['repair_probe_marker'];assert marker and o['script_deferred'] and rc>=1
                trace=Path(o['run']['acceptance_trace_dir']);first=json.loads((trace/'round-00/result.json').read_text());assert not first['passed'] and first['workspace_snapshot_sha256']==digest(spec['initial_snapshot']) and not first['receipt_verified']
                assert first['task_sha256']==sha(a/'input.json')
        report=json.loads((a/'delivery/report.json').read_text()) if (a/'delivery/report.json').exists() else None;review=verify_workflow(spec,report if o['receipt_verified'] else None,a/'delivery',events);assert review['passed']==o['acceptance']['passed']
        assert digest(snapshot(spec['workspace']))==o['final_snapshot_sha256']
        for read in (a/'delivery/reads').glob('*.json'):
            v=json.loads(read.read_text());assert v['path'] in spec['workflow_contract']['allowed_reads'] and v['sha256']==spec['initial_snapshot'][v['path']]
        if c['condition']=='V':
            marker=o['control_marker'];assert marker and not review['passed'];current=dict(spec['initial_snapshot'])
            for jf in (a/'delivery/journals').glob('*.json'):
                j=json.loads(jf.read_text());assert c['workflow_id']=='FM17';ids={'file:local:'+digest({'path':n,'sha':h})[:24]:n for n,h in j['before'].items()}
                for v in j['completed']:assert v['op']=='copy' and v['destination'].startswith('backup-set/');current[v['destination']]=j['before'][ids[v['file_ids'][0]]]
            current[marker['target']]=marker['after_sha256'];assert current==snapshot(spec['workspace'])
        if c['role']=='holdout':
            group=groups.setdefault(c['pair_id'],{'input':digest(base),'schema':digest(schemas),'prompt':sha(Path(c['template_dir'])/'prompt.md'),'arms':set()});assert group['input']==digest(base) and group['schema']==digest(schemas);group['arms'].add(c['arm'])
        requests+=rq;cost+=usd;rows.append({'task_id':c['task_id'],'passed':review['passed'],'requests':rq,'estimated_usd':usd})
    if not partial:assert len(rows)==len(tasks) and len(groups)==8 and all(g['arms']==set(ARMS) for g in groups.values()) and cert
    result={'status':'passed','checks':len(rows),'requests':requests,'estimated_usd':round(cost,9),'usage':dict(usage),'acceptance_repairs':repairs,'v1_and_old_holdout_unchanged':True,'only_new_clean_ordinary_training':True,'holdout_not_learned':True,'series':accounting(),'rows':rows}
    save(exp/('partial-audit.json' if partial else 'independent-audit.json'),result);print(json.dumps({k:v for k,v in result.items() if k!='rows'}));return result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);a.add_argument('--partial',action='store_true');args=a.parse_args();audit(args.experiment.resolve(),args.partial)
