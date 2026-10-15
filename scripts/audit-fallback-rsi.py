"""Independent fresh-task pairing, actual bytes, bounded repairs and HTTP accounting."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scenarios/file-management'))
import auto_rsi as rsi
from common import sha,digest,snapshot,save
from src.adapters.deepseek_cost_gate import observed_peak_cost
from script_adaptation_learning import load_witness


def audit_attempt(case,p):
    file=next(Path(case['task_dir']).glob('attempts/*/outcome.json'))
    o=rsi.read(file);out=file.parent;spec=rsi.read(out/'input.json')
    assert o['arm']==case['arm'] and o['role']==case['role'] and o['accounting_complete'] and not o['learning_performed']
    assert o['input_sha256']==digest(spec) and o['source_sha256']==digest(p['source_code'])
    assert rsi.read(out/'source-code.json')==p['source_code']
    td=Path(case['template_dir']);base=rsi.read(td/'input-template.json')
    assert {k:v for k,v in spec.items() if k!='workspace'}=={k:v for k,v in base.items() if k!='workspace'}
    actual=snapshot(spec['workspace']);assert digest(actual)==o['final_snapshot_sha256']
    if case['condition']=='V':
        marker=rsi.read(out/'control-marker.json')
        assert not o['acceptance']['passed'] and o['condition_passed'] and marker['mode']=='version'
        assert sha(Path(spec['workspace'])/case['control']['target'])==marker['after_sha256']
    assert sha(spec['workflow_oracle_file'])==spec['workflow_oracle_sha256']
    oracle=rsi.read(spec['workflow_oracle_file']);c=spec['workflow_contract']
    report=rsi.read(out/'delivery/report.json') if (out/'delivery/report.json').exists() else None
    receipt_ok=bool(report and o['receipt_verified'] and report['input_sha256']==digest(spec) and report['final_snapshot']==actual)
    reads=[rsi.read(f) for f in (out/'delivery/reads').glob('*.json')]
    assert all(row['path'] in c['allowed_reads'] and row['sha256']==spec['initial_snapshot'][row['path']] for row in reads)
    required=set(c['required_reads'])<={row['path'] for row in reads}
    qualified=receipt_ok and required and actual==oracle['expected_snapshot']
    if qualified:
        expected_ids={'file:local:'+digest({'path':n,'sha':h})[:24] for n,h in actual.items() if n!='.experiment-copy'}
        assert set(report['file_ids'])==expected_ids and len(report['file_ids'])==len(expected_ids)
        assert report['workflow_contract_version']==c['version']
        if 'scenarios/file-management/workflow_delivery.py' in p['source_code']:
            assert 'structural_provenance' in report
        if 'structural_provenance' in report:
            provenance=report['structural_provenance']
            assert provenance['version']=='sss-current-workflow-report-v1' and provenance['generator']=='current_mcp_state'
            assert provenance['input_sha256']==digest(spec) and provenance['snapshot_sha256']==digest(actual)
            assert report['file_ids']==sorted(expected_ids) and provenance['file_ids_sha256']==digest(report['file_ids'])
            assert provenance['file_count']==len(expected_ids) and provenance['receipts_sha256']==digest(report['receipts'])
            assert provenance['model_fields']==['summary','gaps']
        assert all(actual.get(n)==h for n,h in spec['initial_snapshot'].items())
        if c['workflow_id']=='FM17':
            copied=[]
            for f in (out/'delivery/journals').glob('*.json'):
                journal=rsi.read(f);ids={'file:local:'+digest({'path':n,'sha':h})[:24]:n for n,h in journal['before'].items()}
                copied.extend(ids[fid] for a in journal['completed'] if a['destination'].startswith('recovery-drill/') for fid in a['file_ids'])
            assert set(copied)==set(oracle['backup_sources'])
    assert bool(qualified)==o['acceptance']['passed'],case['task_id']
    paid_requests=0;paid_cost=0;events=[]
    if case['arm']=='S':
        events=[json.loads(l) for l in (out/'mcp-calls.jsonl').read_text().splitlines()]
        assert o['run']['upstream_requests']==o['run']['budget_accounted_usd']==0
        assert sha(out/'mcp-calls.jsonl')==o['events_sha256']
    else:
        for run in o['runs']:
            directory=Path(run['output_dir']);assert sha(directory/'agent-events.jsonl')==o['events_sha256']
            events.extend(json.loads(l) for l in (directory/'agent-events.jsonl').read_text().splitlines())
            ledger=[json.loads(l) for l in (directory/'cost-ledger.jsonl').read_text().splitlines()] if (directory/'cost-ledger.jsonl').exists() else []
            paid=[r for r in ledger if r.get('kind')!='budget_denied'];cost=0
            for row in paid:
                assert row.get('response_usage') and row.get('observed_peak_usd') is not None
                current=observed_peak_cost(row['model'],row['response_usage']);assert abs(current-row['observed_peak_usd'])<1e-8
                cost+=current
            assert len(paid)==run['upstream_requests'] and abs(cost-run['budget_accounted_usd'])<1e-8
            paid_requests+=len(paid);paid_cost+=cost
        assert paid_requests<=96 and paid_cost<=5 and o['acceptance_repairs']<=2
        repairing=False
        for event in events:
            if event.get('type')=='user/message' and event['data'].get('source',{}).get('kind')=='task-acceptance-repair':repairing=True
            if event.get('type')=='tool/call' and (case['arm']=='H' or repairing):assert not event['data']['callId'].startswith('sss-')
        if case['role']=='diagnose' and case['arm']=='F':
            assert not o['experience_selected'] and not o['script_steps']
            assert len(o['experience_deferred'])==1 and o['experience_deferred'][0]['reason']=='no_verified_experience'
        # Check actual tool observations and report receipt independently of outcome flags.
        observations=[]
        for event in events:
            if event.get('type')!='tool/result':continue
            for block in event['data']['message'].get('content',[]):
                if block.get('type')=='tool-result' and not block.get('isError'):
                    content=block.get('content',[])
                    if len(content)==1 and content[0].get('type')=='text':
                        observations.append(json.loads(content[0]['text']))
        if qualified:
            task_results=[v for v in observations if v.get('input_sha256')==digest(spec) and 'workflow_execution_version_sha256' in v]
            assert task_results and report['workflow_execution_version_sha256']==task_results[0]['workflow_execution_version_sha256']
            assert any(v.get('artifact_sha256')==digest(report) and v.get('input_sha256')==digest(spec) for v in observations)
    assert paid_requests==o['run']['upstream_requests'] and abs(paid_cost-o['run']['budget_accounted_usd'])<1e-8
    if qualified and 'structural_provenance' in report:
        if case['arm']=='S':
            observed=[json.loads(e['result']['content'][0]['text']) for e in events if not e.get('is_error')]
        else:observed=observations
        receipts={}
        for v in observed:
            if v.get('plan_id') and v.get('status') in ('executed_verified','restored_verified'):
                receipts[v['plan_id']]=v
        assert {v['plan_id']:v for v in report['receipts']}==receipts
    return o,{'input':digest(base),'schema':digest(rsi.read(out/'tool-schemas.json'))}


def audit(exp):
    p=rsi.read(exp/'protocol.json');assert sha(exp/'protocol.json')==rsi.read(exp/'protocol-lock.json')['sha256']
    for n,h in p['source_code'].items():assert sha(exp/'frozen-source'/n)==h
    for n,h in p['test_sources'].items():assert sha(exp/n)==h
    for n,h in p['original_pdfs'].items():assert sha(ROOT/'testpdf'/n)==h
    cases={c['task_id']:c for c in p['tasks']}
    # Diagnostics inherit parent metadata, but execute only their own paired tasks.
    for part in ([] if p.get('phase') else p.get('seeds',[])):
        for c in part['origins']:cases[c['task_id']]=c
    for f in exp.glob('*-materials.json'):
        for c in rsi.read(f)['tasks']:cases[c['task_id']]=c
    groups={};rows=[]
    for c in cases.values():
        o,identity=audit_attempt(c,p);rows.append(o)
        if c['role'] in ('diagnose','observe','holdout'):
            group=groups.setdefault(c['pair_id'],{'identity':identity,'arms':{}})
            assert group['identity']==identity;group['arms'][c['arm']]=o
    if p.get('phase'):
        assert len(groups)==6 and all(set(g['arms'])==set('HF') for g in groups.values())
        assert p['learning_permitted'] is False and not list(exp.glob('upgrade-*'))
    else:
        expected_pairs=p.get('operational_pairs',10)+len(rsi.read(exp/'final-materials.json')['tasks'])//4
        assert len(groups)==expected_pairs and all(set(g['arms'])==set('HSFR') for g in groups.values())
        old=None
        for f in sorted((exp/'registry/versions').glob('*.json')):
            value=rsi.read(f);assert value['parent_digest']==old
            assert value['registry_digest']==digest({k:v for k,v in value.items() if k!='registry_digest'})
            for e in value['entries']:assert sha(exp/'registry'/e['payload'])==e['sha256']
            old=value['registry_digest']
        seed=rsi.read(exp/'seed-lock.json');assert sha(seed['registry_file'])==seed['registry_sha256']
        held=rsi.read(exp/'final-materials.json');assert sha(exp/'final-materials.json')==rsi.read(exp/'final-lock.json')['sha256']
        assert held['learning_from_holdout_permitted'] is False and held['final_model_calls_when_frozen']==0
        assert sha(held['registry_file'])==held['registry_sha256']
        for n in (1,2,3,4,5,6):
            d=exp/f'upgrade-{n}';lock=rsi.read(d/'candidate-lock.json');cert=rsi.read(d/'certificate.json')
            activation=rsi.read(d/'activation.json')
            assert cert['status']=='certified_v2' and not cert['holdout_used'] and cert['candidate_lock_sha256']==sha(d/'candidate-lock.json')
            assert activation['certificate_sha256']==sha(d/'certificate.json') and activation['automatic'] and not activation['holdout_used']
            for rec in lock['scripts']:
                program=rsi.read(rec['path']);assert sha(rec['path'])==rec['sha256'] and 'profile_id' not in program
                for w in program['training']:
                    case=cases[w['task_id']];assert case['role']=='explore' and case['arm']=='H'
                    recovered,actual_witness,g=load_witness(case);recovered.pop('profile_id',None);assert actual_witness==w
                    assert recovered=={k:v for k,v in program.items() if k not in ('script_digest','guard_cases','training','runtime_source')}
                for review in cert['reviews']:
                    o=rsi.read(review['outcome_file']);assert sha(review['outcome_file'])==review['outcome_sha256']
                    assert o['role']=='certify' and o['arm']=='C' and o['acceptance']['passed'] and o['receipt_verified']
                    assert o['run']['upstream_requests']==0 and o['acceptance_repairs']==0 and o['script_steps']>0 and not o['experience_deferred']
                    assert review['task_fingerprint'] not in {w['task_fingerprint'] for w in program['training']}
        final_seen=False;prior=None;used_prior=False
        for f in sorted((exp/'controller-events').glob('*.json')):
            event=rsi.read(f);assert event['previous_sha256']==prior;prior=sha(f)
            if event['kind']=='final_holdout_frozen':final_seen=True
            if event['kind']=='prior_upgrade_executed_in_next_round':
                o=rsi.read(event['detail']['outcome_file']);assert o['script_steps']>0 and o['acceptance']['passed'] and not o['run']['upstream_requests'];used_prior=True
            if final_seen:assert event['kind'] not in ('certified_version_activated','opportunity_observed','experiences_disabled','candidate_rejected')
        assert used_prior and final_seen
        for o in rows:
            if o['arm'] not in 'FR':continue
            binding=rsi.read(Path(o['attempt'])/'experience-binding.json')
            if o['arm']=='F':assert binding['registry_sha256']==seed['registry_sha256']
            elif o['role']=='holdout':assert binding['registry_sha256']==held['registry_sha256']
        # Recompute all cost components from raw attempt rows, separately from the study summary.
        summary=rsi.read(exp/'summary.json');validation=sum(r['cost_usd'] for r in p['diagnostic_cost_sources'])
        seed_tasks={c['task_id'] for part in p['seeds'] for c in part['origins']}
        for pattern in ('seed-supplement-*-materials.json',*[f'certification-{part["round"]}-materials.json' for part in p['seeds']]):
            for f in exp.glob(pattern):seed_tasks.update(c['task_id'] for c in rsi.read(f)['tasks'])
        seed_cost=sum(o['run']['budget_accounted_usd'] for o in rows if o['task_id'] in seed_tasks)
        assert abs(seed_cost-seed['fresh_seed_cost_usd'])<1e-8
        old_cost=0
        for f,h in seed['prior_upgrade_cost_source'].items():
            assert sha(f)==h;old_out=rsi.read(f);assert old_out['role'] in ('explore','certify');old_cost+=old_out['run']['budget_accounted_usd']
        assert abs(old_cost-seed['prior_upgrade_build_cost_usd'])<1e-8
        for r in p['diagnostic_cost_sources']:
            assert sha(Path(r['experiment'])/'summary.json')==r['summary_sha256']
        shared=seed['historical_seed_cost_usd']+old_cost+seed_cost
        for arm in 'HSFR':
            execution=[o for o in rows if o['arm']==arm and o['role'] in ('observe','holdout')]
            learned=[o for o in rows if o['role'] in ('explore','certify') and o['task_id'] not in seed_tasks] if arm=='R' else []
            cost=sum(o['run']['budget_accounted_usd'] for o in execution+learned)+validation+(shared if arm in 'FR' else 0)
            assert abs(cost-summary['arms'][arm]['full_api_cost_usd'])<1e-8
    value={'status':'passed','experiment_id':exp.name,'audited_attempts':len(rows),'paired_conditions':len(groups),
           'requests':sum(o['run']['upstream_requests'] for o in rows),'cost_usd':sum(o['run']['budget_accounted_usd'] for o in rows),
           'actual_bytes_and_original_read_scope':True,'all_HTTP_usage_recomputed':True,'repair_limits_preserved':True,
           'old_final_holdout_not_training':True,'current_final_holdout_not_training':True,'actual_bill_verified':False,
           'audit_source_sha256':sha(__file__)}
    save(exp/'independent-audit.json',value);print(json.dumps(value),flush=True)
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--experiment',type=Path,required=True);args=parser.parse_args()
    audit(args.experiment.resolve())
