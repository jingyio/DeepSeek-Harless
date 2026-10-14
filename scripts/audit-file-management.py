"""Independent post-run audit; never participates in the online policy."""
import hashlib,json,math,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scenarios/file-management'))
from common import digest,sha,snapshot,save
exp=Path(sys.argv[1]).resolve();protocol=json.loads((exp/'protocol.json').read_text());checks=[]
assert all(sha(exp/'frozen-source'/p)==value for p,value in protocol['source_code'].items())
manifest=json.loads((exp/'online-manifest.json').read_text())
assert manifest['manifest_digest']==digest({k:v for k,v in manifest.items() if k!='manifest_digest'})
schemas=set();pairs={};batches=0;synthetic_count=0;failures=[];ledger_totals={a:{k:0 for k in ('requests','output','cache_hit','cache_miss','input','cost','http200')} for a in ('H','M')}
for c in protocol['tasks']:
    td=Path(c['task_dir']);spec=json.loads((td/'input.json').read_text())
    assert digest(spec)==c['input_sha256']
    prompt=(td/'prompt.md').read_bytes();paired=pairs.setdefault(c['pair_id'],[]);paired.append((digest(spec),hashlib.sha256(prompt).hexdigest()))
    for file in (td/'attempts').glob('*/outcome.json'):
        out=json.loads(file.read_text());attempt=file.parent;run=Path(out['run']['output_dir']);metrics=out['run']
        assert json.loads((attempt/'source-code.json').read_text())==protocol['source_code']
        schemas.add(digest(json.loads((attempt/'tool-schemas.json').read_text())))
        assert sha(run/'agent-events.jsonl')==out['events_sha256']
        final=json.loads((attempt/'final-state.json').read_text());assert final['embedding_requests']==0
        assert snapshot(final['retained'])==final['snapshot']
        rows=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()]
        assert len(rows)==metrics['upstream_requests']
        totals=ledger_totals[c['arm']]
        totals['requests']+=len(rows)
        for row in rows:
            assert row['response_status']==200
            usage=row['response_usage'];assert usage['prompt_tokens']==usage['prompt_cache_hit_tokens']+usage['prompt_cache_miss_tokens']
            cost=(usage['prompt_cache_hit_tokens']*.006+usage['prompt_cache_miss_tokens']*.3+usage['completion_tokens']*1.2)/1e6
            assert math.isclose(cost,row['observed_peak_usd'],abs_tol=5.1e-9)
            for target,key in [('output','completion_tokens'),('cache_hit','prompt_cache_hit_tokens'),('cache_miss','prompt_cache_miss_tokens'),('input','prompt_tokens')]:totals[target]+=usage[key]
            totals['cost']+=cost;totals['http200']+=1
        exact=sum((r['response_usage']['prompt_cache_hit_tokens']*.006+r['response_usage']['prompt_cache_miss_tokens']*.3+r['response_usage']['completion_tokens']*1.2)/1e6 for r in rows)
        assert math.isclose(exact,metrics['budget_accounted_usd'],abs_tol=1e-12)
        assert sum(r['response_usage']['completion_tokens'] for r in rows)==metrics['outputTokens']
        assert sum(r['response_usage']['prompt_cache_hit_tokens'] for r in rows)==metrics['cacheReadTokens']
        assert sum(r['response_usage']['prompt_cache_miss_tokens'] for r in rows)==metrics['inputTokens']
        events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
        calls={e['data']['callId']:e['data'] for e in events if e['type']=='tool/call'}
        synthetic={cid:v for cid,v in calls.items() if cid.startswith('sss-motif-')}
        if c['arm']=='H':assert not synthetic and metrics['model_requests_skipped_verified']==0
        else:
            audit=run/'.local/online-motif'/(hashlib.sha256(metrics['session_id'].encode()).hexdigest()+'.jsonl')
            log=[json.loads(l) for l in audit.read_text().splitlines()]
            verified={r['call_id'] for r in log if r['kind']=='motif_tool_result_verified'}
            assert verified==set(synthetic)
            skips=[r for r in log if r['kind']=='model_request_skipped_verified']
            assert len(skips)==metrics['model_requests_skipped_verified']
            assert sum(r['tool_count'] for r in skips)==len(synthetic)
            batches+=len(skips);synthetic_count+=len(synthetic)
            for cid,call in synthetic.items():
                assert call['name']=='mcp__file_management__read_file'
                args=json.loads(call['arguments']);assert set(args)=={'source_id'}
                result=next(b for e in events if e['type']=='tool/result' for b in e['data']['message']['content'] if b.get('toolCallId')==cid)
                assert not result.get('isError')
                value=json.loads(result['content'][0]['text'])
                assert value['source_id']==args['source_id']
                assert value['source_version'] in json.loads((td/'motif-task.json').read_text())['source_versions']['mcp__file_management__read_file']
        if not out['acceptance']['passed']:failures.append({'task':c['task_id'],'errors':out['acceptance']['errors']})
        checks.append(c['task_id'])
assert len(schemas)<=1
assert all(len(set(values))==1 and len(values)==2 for values in pairs.values())
parent=json.loads((Path(protocol['parent'])/'protocol.json').read_text())
originals=sorted((root/'testpdf').glob('*.pdf'))
assert [sha(p) for p in originals]==[d['pdf']['sha256'] for d in parent['datasets'][:3]]
result={'tasks_audited':len(checks),'pair_inputs_and_prompts_equal':True,'single_tool_schema':True,
        'frozen_execution_code_equal':True,'source_original_pdfs_unchanged':True,'retained_final_copies_verified':True,
        'embedding_requests':0,'verified_batches':batches,'verified_synthetic_reads':synthetic_count,
        'provider_ledger_matches_sdk':True,'ledger_totals':ledger_totals,'failures':failures,
        'actual_bill_verified':False,'human_blind_review':False}
save(exp/'independent-audit.json',result);print(json.dumps(result,ensure_ascii=False))
