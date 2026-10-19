"""Recompute native provenance, candidate certification, frozen inputs, bytes and full API cost."""
import argparse,json,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import sha,digest,snapshot,save,PREFIX
from workflow_contract import verify_workflow
from script_reuse_learning import load_witness
from src.adapters.file_cost_gate import observed_peak_cost
from experiment import accounting

def audit(exp,partial=False):
    p=json.loads((exp/'protocol.json').read_text());assert sha(exp/'protocol.json')==json.loads((exp/'protocol-lock.json').read_text())['sha256']
    for rec in p.get('imported_exploration',[]):assert sha(Path(rec['experiment'])/'protocol.json')==rec['protocol_sha256'] and sha(rec['outcome_file'])==rec['outcome_sha256']
    documentation={}
    for n,h in p['source_code'].items():
        assert sha(exp/'frozen-source'/n)==h,n
        if sha(ROOT/n)!=h:
            assert n.endswith('.md') and n.startswith('scenarios/file-management/'),n
            documentation[n]={'frozen':h,'current':sha(ROOT/n)}
    library=Path(p['library']);assert sha(library/'library-lock.json')==p['library_lock_sha256']
    old=Path(p['old_holdout']);assert sha(old/'protocol.json')==p['old_protocol_sha256']
    for t in p['old_holdout_protected']:
        td=Path(t['task_dir']);assert sha(td/'input-template.json')==t['input_template_sha256'] and sha(td/'oracle.json')==t['oracle_sha256'] and sha(td/'prompt.md')==t['prompt_sha256'] and digest(snapshot(t['pristine']))==t['snapshot_sha256']
    for n,h in p['original_pdfs'].items():assert sha(ROOT/'testpdf'/n)==h
    lock=json.loads((exp/'candidate-lock.json').read_text());cert=json.loads((exp/'certificate.json').read_text()) if (exp/'certificate.json').exists() else None
    for rec in lock['scripts']:
        assert sha(rec['path'])==rec['sha256'];s=json.loads(Path(rec['path']).read_text());w=[]
        for source in s['training']:
            c=next(c for c in p['tasks'] if c['task_id']==source['task_id']);program,review=load_witness(c);assert review==source
            assert {k:v for k,v in s.items() if k not in ('training','script_digest')}==program;w.append(review)
        assert len(w)>=2 and len({v['source_count'] for v in w})>=2
    if cert:
        assert cert['candidate_lock_sha256']==sha(exp/'candidate-lock.json') and cert['status']=='certified'
        for r in cert['reviews']:assert sha(r['outcome_file'])==r['outcome_sha256']
    tasks=list(p['tasks']);templates=list(p['templates'])
    if (exp/'holdout.json').exists():
        held=json.loads((exp/'holdout.json').read_text());assert sha(exp/'holdout.json')==json.loads((exp/'holdout-lock.json').read_text())['sha256'] and held['certificate_sha256']==sha(exp/'certificate.json')
        assert held['model_holdout_runs_when_frozen']==0 and not held['learning_from_holdout_permitted'];tasks+=held['tasks'];templates+=held['templates']
    for t in templates:
        td=Path(t['task_dir']);assert sha(td/'input-template.json')==t['input_template_sha256'] and sha(td/'oracle.json')==t['oracle_sha256'] and sha(td/'scenario.json')==t['scenario_sha256'] and sha(td/'prompt.md')==t['prompt_sha256'] and digest(snapshot(t['pristine']))==t['snapshot_sha256']
    usage=Counter();rows=[];groups={};actual_requests=0;cost=0
    for c in tasks:
        files=list(Path(c['task_dir']).glob('attempts/*/outcome.json'))
        if partial and not files:continue
        assert len(files)==1,c['task_id'];f=files[0];o=json.loads(f.read_text());a=f.parent;spec=json.loads((a/'input.json').read_text());template=json.loads((Path(c['template_dir'])/'input-template.json').read_text())
        assert o['role']==c['role'] and o['arm']==c['arm'] and not o['learning_performed'] and o['accounting_complete']
        assert {k:v for k,v in spec.items() if k!='workspace'}=={k:v for k,v in template.items() if k!='workspace'} and o['input_sha256']==digest(spec)
        source=json.loads((Path(c['origin_experiment'])/'protocol.json').read_text())['source_code'] if c.get('origin_experiment') else p['source_code']
        assert json.loads((a/'source-code.json').read_text())==source and digest(source)==o['source_sha256'];schemas=json.loads((a/'tool-schemas.json').read_text());assert len(schemas)==14
        if c.get('origin_experiment'):
            for n,h in source.items():assert sha(Path(c['origin_experiment'])/'frozen-source'/n)==h
        if c['role']=='holdout':
            g=groups.setdefault(c['pair_id'],{'prompt':sha(Path(c['template_dir'])/'prompt.md'),'input':digest(template),'schemas':digest(schemas),'arms':set()});assert g['input']==digest(template) and g['schemas']==digest(schemas);g['arms'].add(c['arm'])
        events=[];requests=0;amount=0
        if c['arm']=='S':assert o['run']['upstream_requests']==o['run']['budget_accounted_usd']==0
        else:
            for r in o['runs']:
                run=Path(r['output_dir']);events += [json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
                ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()] if (run/'cost-ledger.jsonl').exists() else []
                paid=[v for v in ledger if v.get('kind')!='budget_denied'];assert len(paid)==r['upstream_requests']
                for v in paid:
                    u=v.get('response_usage');assert u and v.get('observed_peak_usd') is not None,'unknown usage requires reconciliation'
                    price=observed_peak_cost(v['model'],u);assert abs(price-v['observed_peak_usd'])<1e-8;usage.update(u)
                amount+=r['budget_accounted_usd'];requests+=len(paid)
            assert requests==o['run']['upstream_requests'] and abs(amount-o['run']['budget_accounted_usd'])<1e-9 and requests<=96 and amount<=5
            auto=[e['data'] for e in events if e.get('type')=='tool/call' and e['data']['callId'].startswith('sss-')]
            if c['arm']=='H':assert not auto
            if c['arm']=='M':assert all(v['name'] in {PREFIX+n for n in ('pin_file','read_file','collect_reads')} for v in auto)
            if c['arm']=='L':
                assert all(v['callId'].startswith('sss-learned-script-') for v in auto)
                audit=[json.loads(l) for l in (a/'learned-script-audit.jsonl').read_text().splitlines()]
                assert o['learned_script_steps']==sum(v['kind']=='learned_script_step_verified' for v in audit)
                assert all(v['name'] in {PREFIX+n for n in ('read_task','list_files','pin_file','read_file','hash_files','preview_actions','execute_plan','submit_report')} for v in auto)
            repairing=False
            for e in events:
                if e.get('type')=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair':repairing=True
                if repairing and e.get('type')=='tool/call':assert not e['data']['callId'].startswith('sss-')
        report=json.loads((a/'delivery/report.json').read_text()) if (a/'delivery/report.json').exists() else None
        review=verify_workflow(spec,report if o['receipt_verified'] else None,a/'delivery',events);assert review['passed']==o['acceptance']['passed']
        assert digest(snapshot(spec['workspace']))==o['final_snapshot_sha256']
        for read in (a/'delivery/reads').glob('*.json'):
            r=json.loads(read.read_text());assert r['path'] in spec['workflow_contract']['allowed_reads'] and r['sha256']==spec['initial_snapshot'][r['path']]
        if c['condition']=='V':
            marker=o['control_marker'];assert marker and not review['passed'];current=dict(spec['initial_snapshot'])
            for jfile in (a/'delivery/journals').glob('*.json'):
                j=json.loads(jfile.read_text());assert c['workflow_id']=='FM17'
                by_id={'file:local:'+digest({'path':n,'sha':h})[:24]:n for n,h in j['before'].items()}
                for v in j['completed']:assert v['op']=='copy' and v['destination'].startswith('backup-set/');current[v['destination']]=j['before'][by_id[v['file_ids'][0]]]
            current[marker['target']]=marker['after_sha256'];assert current==snapshot(spec['workspace'])
        actual_requests+=requests;cost+=amount;rows.append({'task_id':c['task_id'],'passed':review['passed'],'requests':requests,'estimated_usd':amount})
    if not partial:assert len(rows)==len(tasks) and len(groups)==6 and all(g['arms']==set('HSML') for g in groups.values()) and cert
    result={'status':'passed','checks':len(rows),'requests':actual_requests,'estimated_usd':round(cost,9),'usage':dict(usage),'original_pdfs_and_old_holdout_unchanged':True,
            'new_ordinary_witnesses_only':True,'independent_candidate_execution':True,'holdout_not_learned':True,'series':accounting(),'current_documentation_updates':documentation,'rows':rows}
    save(exp/('partial-audit.json' if partial else 'independent-audit.json'),result);print(json.dumps({k:v for k,v in result.items() if k!='rows'}));return result

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--experiment',type=Path,required=True);a.add_argument('--partial',action='store_true');args=a.parse_args();audit(args.experiment.resolve(),args.partial)
