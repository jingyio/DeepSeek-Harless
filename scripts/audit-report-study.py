"""Independent raw-evidence audit, including stopped negative versions and effectful final copies."""
import argparse,json,hashlib,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
sys.path.insert(0,str(ROOT))
from common import digest,sha,snapshot,save,PREFIX
from file_tools import FileScene
from verify import verify as legacy_verify
from src.motif_core.offline.collection_compiler import collection_witness
from src.motif_core.offline.reentry_compiler import reentry_witness

def audit(exp):
    p=json.loads((exp/'protocol.json').read_text());assert all(sha(exp/'frozen-source'/n)==h for n,h in p['source_code'].items())
    lock=json.loads((exp/'library-lock.json').read_text()) if (exp/'library-lock.json').exists() else {}
    for arm in ('L1','L2'):
        if (exp/arm/'policy.json').exists():
            policy=json.loads((exp/arm/'policy.json').read_text());assert policy['policy_digest']==digest({k:v for k,v in policy.items() if k!='policy_digest'})
            expected=lock.get(arm+'_sha256',p.get(arm+'_sha256'))
            if expected:assert sha(exp/arm/'policy.json')==expected
    native_proofs={};residual_proofs={}
    if (exp/'L1/learning-result.json').exists():
        native_proofs={w['trace_id']:w for values in json.loads((exp/'L1/learning-result.json').read_text())['witnesses'].values() for w in values}
    if (exp/'L2/policy.json').exists() and p.get('library_retrained'):
        art=json.loads((exp/'L2/policy.json').read_text())['artifact'];residual_proofs={w['trace_id']:w for w in [*art['training_episodes'],art['validation_episode']]}
    rows=[];groups={};schemas=set();runtime=0;replays=0;searches=0;error_kinds={};parser=FileScene.__new__(FileScene);order=[];native_recomputed=0;residual_recomputed=0
    for c in p['tasks']:
        td=Path(c['task_dir']);spec=json.loads((td/'input.json').read_text());assert digest(spec)==c['input_sha256'];assert snapshot(c['pristine'])==c['initial_snapshot']
        groups.setdefault(c['pair_id'],[]).append((digest(spec),sha(td/'prompt.md')))
        for op in td.glob('attempts/*/outcome.json'):
            o=json.loads(op.read_text());a=op.parent;m=o['run'];assert o['accounting_complete'] and m
            run=Path(m['output_dir']);cfg=json.loads((a/'config.json').read_text());assert cfg['task_sha256']==digest(spec)
            assert json.loads((a/'execution-source-code.json').read_text())==p['source_code'];assert all(p['source_code'][n]==h for n,h in json.loads((a/'source-code.json').read_text()).items())
            ss=json.loads((a/'tool-schemas.json').read_text());schemas.add(digest(ss));assert cfg['schema_sha256']==digest(ss)
            if c['arm'] in ('L1','L2'):assert cfg['collection_policy_sha256' if c['arm']=='L1' else 'reentry_policy_sha256']==sha(exp/c['arm']/'policy.json')
            final=json.loads((a/'final-copy.json').read_text());assert snapshot(final['path'])==final['snapshot']
            ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];assert len(ledger)==m['upstream_requests'];cost=0
            for r in ledger:
                assert r['response_status']==200;u=r['response_usage'];assert u['prompt_tokens']==u['prompt_cache_hit_tokens']+u['prompt_cache_miss_tokens']
                cost+=(u['prompt_cache_hit_tokens']*.006+u['prompt_cache_miss_tokens']*.3+u['completion_tokens']*1.2)/1e6
            assert math.isclose(cost,m['budget_accounted_usd'],abs_tol=1e-12)
            for field,key in [('outputTokens','completion_tokens'),('inputTokens','prompt_cache_miss_tokens'),('cacheReadTokens','prompt_cache_hit_tokens')]:assert m[field]==sum(r['response_usage'][key] for r in ledger)
            assert sha(run/'agent-events.jsonl')==o['events_sha256'];events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
            calls={e['data']['callId']:e for e in events if e['type']=='tool/call'};results={b['toolCallId']:(e,b) for e in events if e['type']=='tool/result' for b in e['data']['message'].get('content',[]) if b.get('type')=='tool-result'}
            def actual(cid):
                e,b=results[cid];assert not b.get('isError');assert calls[cid]['seq']<e['seq'];return json.loads(b['content'][0]['text'])
            model_calls={b['id'] for e in events if e['type']=='assistant/message' and e['data'].get('usage') and e['data']['message'].get('source',{}).get('kind')=='model' for b in e['data']['message'].get('content',[]) if b.get('type')=='tool-call'}
            for cid,e in calls.items():
                if e['data']['name']==PREFIX+'select_files':assert cid in model_calls and not cid.startswith('sss-')
                if cid.startswith('sss-'):assert c['arm']!='H' and e['data']['name'] in {PREFIX+n for n in ('pin_file','read_file','collect_reads')};runtime+=1
            reads={}
            for rp in (a/'delivery/reads').glob('*.json'):
                r=json.loads(rp.read_text());source=Path(c['pristine'])/r['path']
                if not source.exists():
                    source=Path(final['path'])/r['path'];assert source.exists()
                    journals=[json.loads(j.read_text()) for j in (a/'delivery/journals').glob('*.json')]
                    assert any(action['destination']==r['path'] for journal in journals for action in journal['actions']),('read lacks recorded effect origin',r['path'])
                assert sha(source)==r['sha256']
                try:status,text,meta=parser.parse(source)
                except Exception:assert r['status']=='unreadable'
                else:assert status==r['status'] and text[:6000]==r.get('text','') and meta==r.get('metadata',{})
                replays+=1;reads[r['source_id']]=r
            packets={}
            for rp in (a/'delivery/collections').glob('*/summary.json'):
                packet=json.loads(rp.read_text());assert packet['coverage_sha256']==digest(packet['files']);packets[packet['collection_id']]=packet
                assert packet['execution_version_sha256']==p['execution_version_sha256']
                for r in packet['files']:assert digest(reads[r['source_id']])==r['read_sha256']
            ap=run/'.local/online-motif'/(hashlib.sha256(m['session_id'].encode()).hexdigest()+'.jsonl');log=[json.loads(l) for l in ap.read_text().splitlines()] if ap.exists() else []
            if c['arm'] in ('L1','L2'):
                loaded=[r for r in log if r['kind'] in ('collection_motif_loaded','reentry_motif_loaded')];assert len(loaded)==1 and loaded[0]['policy_digest']==json.loads((exp/c['arm']/'policy.json').read_text())['policy_digest']
                assert sum(r['kind']=='collection_model_request_bypassed_verified' for r in log)==m['collection_model_requests_bypassed_verified']
                assert sum(r['kind']=='reentry_epoch_batch_verified' for r in log)==m['reentry_epoch_batches_verified']
                for r in [v for v in log if v['kind']=='collection_motif_read_verified']:assert digest(actual(r['call_id']))==r['observation_sha256']
            for cid,(e,b) in results.items():
                if b.get('isError'):
                    name=calls[cid]['data']['name'];error_kinds[name]=error_kinds.get(name,0)+1
            if run.name in native_proofs:
                recorded=native_proofs[run.name];scope=json.loads((td/'scope.json').read_text());tools=[PREFIX+n for n in ('select_files','pin_file','read_file','collect_reads')]
                recomputed=collection_witness(events,scope,tools,trace_id=run.name,task_fingerprint=recorded['task_fingerprint'])
                assert digest({k:v for k,v in recorded.items() if k!='family'})==digest(recomputed);native_recomputed+=1
            if run.name in residual_proofs:
                recorded=residual_proofs[run.name];scope=json.loads((td/'scope.json').read_text());parent=json.loads((exp/'L1/policy.json').read_text())
                recomputed=reentry_witness(events,scope,parent,log,run.name,recorded['task_fingerprint'])
                assert digest(recomputed['residual_witness'])==digest(recorded['residual_witness']) and recomputed['parent_boundary']==recorded['parent_boundary'];residual_recomputed+=1
            if c['role'] in ('quality','benchmark'):assert run.name not in native_proofs and run.name not in residual_proofs
            report=json.loads((a/'delivery/report.json').read_text()) if (a/'delivery/report.json').exists() else None
            if report:
                published=[actual(cid) for cid,(e,b) in results.items() if calls[cid]['data']['name']==PREFIX+'submit_report' and not b.get('isError')]
                assert published[-1]['artifact_sha256']==digest(report) and report['input_sha256']==digest(spec)
                assert report['final_snapshot']==final['snapshot'];assert report['report_execution_version_sha256']==p['report_execution_version_sha256']
                assert report['report_kind']==spec['report_contract']['kind'] and report['contract_version']==spec['report_contract']['version']
                if report['report_kind']=='inspection':
                    expected_ids={r['file_id'] for packet in packets.values() for r in packet['files']}
                    assert set(report['file_ids'])==expected_ids=={r['file_id'] for r in reads.values()}
                    assert {digest(r) for r in report['inspection_receipts']}=={digest(r) for r in packets.values()}
                search=report.get('search_receipt')
                if search:
                    searches+=1;assert search['search_sha256']==digest({k:v for k,v in search.items() if k!='search_sha256'})
                    assert search['collection_id'] in packets;target=packets[search['collection_id']];assert target['coverage_sha256']==search['coverage_sha256']
                    target_rows=[reads[r['source_id']] for r in target['files']];wanted={r['file_id'] for r in target_rows if search['query'].casefold() in r.get('text','').casefold()}
                    assert set(report['file_ids'])==set(search['file_ids'])=={r['file_id'] for r in search['matches']}==wanted
                    assert any(actual(cid)==search for cid,(e,b) in results.items() if calls[cid]['data']['name']==PREFIX+'search_index' and not b.get('isError'))
                    for match in search['matches']:assert match['excerpt'] in reads[match['source_id']]['text'] and search['query'].casefold() in match['excerpt'].casefold()
            # Independently recompute accepted task postconditions on retained final bytes, not reused live workspace.
            if o['acceptance']['passed']:
                assert report and o['receipt_verified']
                if c['role'] in ('quality','learn','certify'):
                    expected_a={n for n in spec['initial_snapshot'] if n.startswith('stage_a/')};ext=spec['notice_data']['followup_extensions'];expected_b={n for n in spec['initial_snapshot'] if n.startswith('stage_b/') and ('*' in ext or Path(n).suffix.lower() in ext)}
                    assert {r['path'] for r in reads.values()}==expected_a|expected_b and len(packets)==2
                    assert sorted(sorted(r['path'] for r in x['files']) for x in packets.values())==sorted([sorted(expected_a),sorted(expected_b)])
                    assert final['snapshot']==spec['initial_snapshot']
                    if c['family']=='content_search':assert set(report['file_ids'])=={r['file_id'] for r in reads.values() if r['path'] in expected_b and spec['notice_data']['query'].casefold() in r.get('text','').casefold()}
                elif c['role'] in ('bootstrap','bootstrap_certify'):
                    assert {r['path'] for r in reads.values()}=={n for n in spec['initial_snapshot'] if n!='.experiment-copy'} and len(packets)==1
                    assert final['snapshot']==spec['initial_snapshot']
                else:
                    surrogate={**spec,'workspace':final['path'],'family':'index' if c['family']=='content_search' else c['family']}
                    check=legacy_verify(surrogate,report,a/'delivery',events);assert check['passed'],(c['task_id'],check)
            order.append((cfg['series_before']['estimated_usd'],c['task_id']))
            rows.append({'task':c['task_id'],'role':c['role'],'arm':c['arm'],'passed':o['acceptance']['passed'],'requests':len(ledger),'estimated_usd':cost,'tool_errors':o['tool_errors'],'errors':o['acceptance']['errors']})
    assert len(schemas)==1 and all(len(set(v))==1 for v in groups.values())
    actual_ids={r['task'] for r in rows};assert [tid for _,tid in sorted(order)]==[c['task_id'] for c in p['tasks'] if c['task_id'] in actual_ids]
    result={'experiment':exp.name,'audited':len(rows),'passed':sum(r['passed'] for r in rows),'failed':sum(not r['passed'] for r in rows),'runtime_nodes_not_training':runtime,
            'actual_read_replays':replays,'search_receipts_replayed':searches,'new_native_witnesses_recomputed':native_recomputed,'new_residual_witnesses_recomputed':residual_recomputed,
            'tool_error_kinds':error_kinds,'original_events_http_tokens_cost_source_input_prompt_schema_final_library_verified':True,
            'holdout_used_for_learning':False,'actual_bill_verified':False,'human_blind_review':False,'rows':rows}
    save(exp/'independent-audit.json',result);return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();result=audit(a.experiment.resolve());print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
if __name__=='__main__':main()
