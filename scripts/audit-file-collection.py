"""Independent collection experiment audit, using raw tool events and HTTP usage."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import digest,sha,snapshot,save
from collection_study import verify_collection

def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);args=p.parse_args();exp=args.experiment.resolve()
    protocol=json.loads((exp/'protocol.json').read_text());policy=json.loads((exp/'learned/policy.json').read_text())
    assert all(sha(exp/'frozen-source'/name)==value for name,value in protocol['source_code'].items())
    assert policy['policy_digest']==digest({k:v for k,v in policy.items() if k!='policy_digest'})
    schemas=set();pair_inputs={};rows=[];read_count=0;batch_count=0;synthetic_count=0;source_proofs=[]
    for case in protocol['tasks']:
        td=Path(case['task_dir']);spec=json.loads((td/'input.json').read_text());assert digest(spec)==case['input_sha256']
        if case['role']=='evaluate':pair_inputs.setdefault(case['pair_id'],[]).append((digest(spec),sha(td/'prompt.md')))
        for op in (td/'attempts').glob('*/outcome.json'):
            outcome=json.loads(op.read_text());a=op.parent;run=Path(outcome['run']['output_dir']);metrics=outcome['run']
            assert json.loads((a/'source-code.json').read_text())==protocol['source_code']
            schemas.add(digest(json.loads((a/'tool-schemas.json').read_text())))
            assert sha(run/'agent-events.jsonl')==outcome['events_sha256']
            final=json.loads((a/'final-state.json').read_text());assert snapshot(final['retained'])==final['snapshot']
            events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
            calls={e['data']['callId']:e['data'] for e in events if e['type']=='tool/call'}
            results={b['toolCallId']:b for e in events if e['type']=='tool/result' for b in e['data']['message'].get('content',[]) if b.get('type')=='tool-result'}
            generated={cid:call for cid,call in calls.items() if cid.startswith('sss-collection-')}
            ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];assert len(ledger)==metrics['upstream_requests']
            cost=0
            for r in ledger:
                assert r['response_status']==200
                u=r['response_usage'];assert u['prompt_tokens']==u['prompt_cache_hit_tokens']+u['prompt_cache_miss_tokens']
                calculated=(u['prompt_cache_hit_tokens']*.006+u['prompt_cache_miss_tokens']*.3+u['completion_tokens']*1.2)/1e6
                assert math.isclose(calculated,r['observed_peak_usd'],abs_tol=5.1e-9);cost+=calculated
            assert math.isclose(cost,metrics['budget_accounted_usd'],abs_tol=1e-12)
            for field,key in [('outputTokens','completion_tokens'),('inputTokens','prompt_cache_miss_tokens'),('cacheReadTokens','prompt_cache_hit_tokens')]:
                assert metrics[field]==sum(r['response_usage'][key] for r in ledger)
            if case['arm']=='H':assert not generated and metrics['collection_model_requests_bypassed_verified']==0
            else:
                audit=run/'.local/online-motif'/(hashlib.sha256(metrics['session_id'].encode()).hexdigest()+'.jsonl')
                log=[json.loads(l) for l in audit.read_text().splitlines()]
                batches=[r for r in log if r['kind']=='collection_model_request_bypassed_verified']
                assert len(batches)==metrics['collection_model_requests_bypassed_verified']
                assert sum(r['count'] for r in batches)==len(generated)
                selections=[r for r in log if r['kind']=='collection_motif_selection_verified'];assert len(selections)==1
                selection=selections[0];cid=selection['call_id'];assert cid in calls and not cid.startswith('sss-')
                raw=json.loads(results[cid]['content'][0]['text']);assert digest(raw)==selection['selection_sha256']
                assert any(e['type']=='assistant/message' and e['data'].get('usage') and e['data']['message'].get('source',{}).get('kind')=='model'
                           and any(b.get('id')==cid for b in e['data']['message'].get('content',[])) for e in events)
                recorded=[r for r in log if r['kind']=='collection_motif_read_verified']
                assert len(recorded)==raw['count']
                for r in recorded:
                    call=calls[r['call_id']];value=json.loads(results[r['call_id']]['content'][0]['text'])
                    assert not results[r['call_id']].get('isError') and digest(value)==r['observation_sha256']
                    assert json.loads(call['arguments'])=={'source_id':value['source_id']}
                    assert value['file_id']==r['file_id'] and value['source_version']==r['source_version']
                assert len({r['file_id'] for r in recorded})==raw['count']
                assert len([r for r in log if r['kind']=='collection_motif_complete'])==1
                read_count+=len(recorded);batch_count+=len(batches);synthetic_count+=len(generated)
                source_proofs.append({'task':case['task_id'],'actual_model_source_call':cid,'member_count':raw['count']})
            report=json.loads((a/'delivery/report.json').read_text())
            receipt_calls=[cid for cid,c in calls.items() if c['name']=='mcp__file_management__submit_report' and cid in results and not results[cid].get('isError')]
            assert receipt_calls
            receipt=json.loads(results[receipt_calls[-1]]['content'][0]['text']);assert receipt['artifact_sha256']==digest(report)
            # Task workspace may now hold the other arm; use retained bytes for postconditions.
            for path,value in spec['initial_snapshot'].items():assert final['snapshot'][path]==value
            rows.append({'task':case['task_id'],'arm':case['arm'],'role':case['role'],'passed':outcome['acceptance']['passed'],
                         'requests':len(ledger),'estimated_usd':cost,'tool_errors':outcome['tool_errors']})
    assert len(schemas)==1 and all(len(values)==2 and len(set(values))==1 for values in pair_inputs.values())
    schedule=json.loads((exp/'evaluation-schedule.json').read_text());ordered=sorted(
        [(float(json.loads(next(Path(c['task_dir']).glob('attempts/*/config.json')).read_text())['series_before']['estimated_usd']),c['task_id'])
         for c in protocol['tasks'] if c['role']=='evaluate' and list(Path(c['task_dir']).glob('attempts/*/outcome.json'))])
    assert [name for _,name in ordered]==schedule['schedule'][:len(ordered)]
    result={'tasks_audited':len(rows),'pair_inputs_prompts_equal':True,'one_tool_schema':True,'frozen_source_and_final_copies_verified':True,
            'provider_usage_matches_sdk':True,'actual_selected_model_sources':source_proofs,'verified_runtime_reads':read_count,
            'verified_batches':batch_count,'verified_runtime_tool_calls':synthetic_count,'balanced_schedule_verified':True,
            'actual_bill_verified':False,'human_blind_review':False,'rows':rows}
    save(exp/'independent-audit.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('rows','actual_selected_model_sources')},ensure_ascii=False))

if __name__=='__main__':main()
