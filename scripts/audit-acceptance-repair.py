"""Independent replay of acceptance stages, original budget, lineage and ordinary repair."""
import argparse,hashlib,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import digest,sha,snapshot,save
from report_study import verify_report

def audit(exp):
    p=json.loads((exp/'protocol.json').read_text());assert all(sha(exp/'frozen-source'/n)==h for n,h in p['source_code'].items())
    assert sha(exp/'L2/policy.json')==p['L2_sha256'];rows=[]
    for c in p['tasks']:
        td=Path(c['task_dir']);spec=json.loads((td/'input.json').read_text());assert digest(spec)==c['input_sha256']
        assert snapshot(c['pristine'])==c['initial_snapshot']
        for op in td.glob('attempts/*/outcome.json'):
            o=json.loads(op.read_text());a=op.parent;m=o['run'];cfg=json.loads((a/'config.json').read_text())
            run=Path(m['output_dir']);events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
            assert sha(run/'agent-events.jsonl')==o['events_sha256'];assert cfg['budget_usd']==5
            assert m['budget_accounted_usd']<=cfg['budget_usd'] and m['agent_steps']<=cfg['max_steps']
            ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];assert len(ledger)==m['upstream_requests']
            cost=0
            for row in ledger:
                assert row['response_status']==200;u=row['response_usage'];assert u['prompt_tokens']==u['prompt_cache_hit_tokens']+u['prompt_cache_miss_tokens']
                cost+=(u['prompt_cache_hit_tokens']*.006+u['prompt_cache_miss_tokens']*.3+u['completion_tokens']*1.2)/1e6
            assert math.isclose(cost,m['budget_accounted_usd'],abs_tol=1e-12)
            repairs=[e for e in events if e['type']=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair']
            assert len(repairs)==m['acceptance_repairs'] and len(repairs)<=p['max_repairs']
            if repairs:
                assert not any(e['type']=='tool/call' and e['seq']>repairs[0]['seq'] and str(e['data']['callId']).startswith('sss-') for e in events)
            trace=Path(m['acceptance_trace_dir']);checks=[]
            for stage in sorted(trace.glob('round-*')):
                result=json.loads((stage/'result.json').read_text());original=json.loads((stage/'task.json').read_text())
                assert digest(original)==digest(spec);assert result['task_sha256']==sha(td/'input.json')
                assert result['workspace_snapshot_sha256']==digest(snapshot(stage/'workspace'))
                rp=stage/'delivery/report.json';report=json.loads(rp.read_text()) if rp.exists() else None
                # Alternate archived location is solely for byte/postcondition replay; original receipt input is separately bound.
                archived={**spec,'workspace':str(stage/'workspace')}
                review=verify_report(archived,report,stage/'delivery',json.loads((stage/'events.json').read_text()))
                assert review['passed']==result['passed'],(c['task_id'],result['round'],review,result)
                if report:assert report['final_snapshot']==snapshot(stage/'workspace')
                assert (stage/'cost-ledger.jsonl').exists();checks.append(result)
            assert len(checks)==m['acceptance_checks'];assert checks[-1]['passed']==o['acceptance']['passed']
            assert snapshot(a/'retained-final')==snapshot(c['workspace'])
            if c['expected_terminal_failure']:
                assert not o['acceptance']['passed'] and len(repairs)==2 and snapshot(c['workspace'])==c['initial_snapshot']
            else:assert o['acceptance']['passed']
            rows.append({'task':c['task_id'],'final_passed':o['acceptance']['passed'],'expected_terminal_failure':c['expected_terminal_failure'],
                'checks':len(checks),'failed_stages':sum(not x['passed'] for x in checks),'repairs':len(repairs),
                'ordinary_after_repair_verified':bool(repairs),'requests':m['upstream_requests'],'estimated_usd':m['budget_accounted_usd']})
    body={'experiment':exp.name,'audited_tasks':len(rows),'rows':rows,'http_cost_frozen_input_permissions_stages_verified':True,
          'no_motif_calls_after_repair':True,'model_requests':sum(x['requests'] for x in rows),'estimated_usd':sum(x['estimated_usd'] for x in rows),
          'actual_bill_verified':False,'human_blind_review':False}
    save(exp/'independent-recovery-audit.json',body);return body
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();r=audit(a.experiment.resolve());print(json.dumps({k:v for k,v in r.items() if k!='rows'},ensure_ascii=False))
if __name__=='__main__':main()
