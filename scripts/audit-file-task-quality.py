"""Independent frozen-input, archived-postcondition, native-event and cost replay."""
from __future__ import annotations
import argparse,csv,io,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from common import PREFIX,digest,sha,save,snapshot
from file_tools import FileScene

def native(events):
    calls={e['data']['callId']:e for e in events if e.get('type')=='tool/call'}; results=[]
    for e in events:
        if e.get('type')!='tool/result':continue
        for b in e['data']['message'].get('content',[]):
            call=calls.get(b.get('toolCallId'))
            if not call or b.get('type')!='tool-result' or b.get('isError'):continue
            try:v=json.loads(b['content'][0]['text'])
            except (ValueError,KeyError,IndexError,TypeError):continue
            results.append((call['data']['name'],call['seq'],e['seq'],v))
    return results

def parse(path):
    try:status,text,meta=FileScene.__new__(FileScene).parse(path)
    except Exception:return 'unreadable','',{},False
    return status,text[:6000],meta,len(text)>6000

def replay(spec,pristine,root,delivery,events,task_version,original_delivery):
    c=spec['task_contract'];initial=spec['initial_snapshot'];expected=dict(initial);kind=c['kind'];prefix=c.get('source_prefix','inbox/'); errors=[]; required=set();generated={}
    if kind=='rename':
        targets={n:f'{c.get("destination_prefix","normalized/")}{Path(n).suffix.lower()[1:] or "no-extension"}/item_{i:02d}{Path(n).suffix.lower()}' for i,n in enumerate(sorted(n for n in initial if n.startswith(prefix)),1)}
        for n,dest in targets.items():expected[dest]=expected.pop(n)
    elif kind=='content_classify':
        required={n for n in initial if n.startswith(prefix) and Path(n).suffix.lower() in ('.txt','.md','.docx')}
        for n in required:
            status,text,_,_=parse(pristine/n)
            if status=='readable' and text.strip():
                route=next((r for r in c['routes'] if r['literal'].casefold() in text.casefold()),None)
                if route:expected[route['destination_prefix']+n[len(prefix):]]=expected.pop(n)
    else:
        for row in c['conversions']:
            required.add(row['source']);generated[row['destination']]=row;output=root/row['destination'];source=pristine/row['source']
            if not output.is_file():errors.append('conversion missing');continue
            expected[row['destination']]=sha(output)
            if row['format']=='jpeg':
                from PIL import Image
                with Image.open(source) as image:
                    buf=io.BytesIO();image.convert('RGB').save(buf,'JPEG')
                if buf.getvalue()!=output.read_bytes():errors.append('JPEG bytes differ')
            else:
                status,text,meta=FileScene.__new__(FileScene).parse(source)
                if status!='readable':errors.append('conversion source unreadable')
                elif row['format']=='text' and output.read_text(encoding='utf-8')!=text:errors.append('text differs')
                elif row['format']=='csv' and list(csv.reader(io.StringIO(output.read_text(encoding='utf-8'))))!=meta['rows']:errors.append('CSV differs')
    current=snapshot(root)
    if current!=expected:errors.append('postconditions differ')
    actual=native(events);reads=[json.loads(p.read_text()) for p in (delivery/'reads').glob('*.json')]
    allowed_optional=({n for n in initial if n!='.experiment-copy'} | set(targets.values())) if c.get('allow_optional_original_reads') and kind=='rename' else set()
    allowed_outputs=set(generated) if c.get('allow_output_verification_reads',True) else set()
    paths={r['path'] for r in reads}
    if not required<=paths or paths-required-allowed_outputs-allowed_optional:errors.append('read scope differs')
    if c.get('require_output_verification_reads') and not allowed_outputs<=paths:errors.append('required output read missing')
    if {digest(v) for n,_,_,v in actual if n==PREFIX+'read_file'}!={digest(r) for r in reads}:errors.append('read artifact/event set differs')
    for r in reads:
        source=pristine/r['path'] if r['path'] in initial else root/r['path']
        if not source.is_file() or sha(source)!=r['sha256']:errors.append('read bytes differ');continue
        status,text,meta,truncated=parse(source)
        if (r['status'],r.get('text',''),r.get('metadata',{}),r.get('truncated',False))!=(status,text,meta,truncated):errors.append('observation differs')
        if r['source_version']!=digest({'path':r['path'],'sha':r['sha256'],'parser':'fm-parser-v1'}):errors.append('source version differs')
        if r['path'] in generated:
            row=generated[r['path']];fid='file:local:'+digest({'path':row['source'],'sha':initial[row['source']]})[:24]
            journals=[json.loads(p.read_text()) for p in (delivery/'journals').glob('*.json')]
            matches=[j for j in journals if j.get('status')=='executed_verified' and j.get('after',{}).get(row['destination'])==r['sha256'] and j['before'].get(row['source'])==initial[row['source']] and any(
                a['op']=='convert' and a['file_ids']==[fid] and a['destination']==row['destination'] and a['format']==row['format'] for a in j.get('completed',[]))]
            if not matches:errors.append('output journal missing')
            if not any(es<rs and v.get('status')=='executed_verified' and any(v.get('plan_id')==j['plan_id'] and v.get('journal_sha256')==digest(j) for j in matches)
                for name,_,es,v in actual if name==PREFIX+'execute_plan' for rn,rs,_,rv in actual if rn==PREFIX+'read_file' and digest(rv)==digest(r)):
                errors.append('output event order differs')
    packets=[json.loads(p.read_text()) for p in (delivery/'collections').glob('*/summary.json')]
    if required and not any({r['path'] for r in p['files']}==required for p in packets):errors.append('complete input collection missing')
    for packet in packets:
        if packet['coverage_sha256']!=digest(packet['files']) or not any(n==PREFIX+'collect_reads' and digest(v)==digest(packet) for n,_,_,v in actual):errors.append('packet actual result differs')
        for row in packet['files']:
            if not any(r['source_id']==row['source_id'] and digest(r)==row['read_sha256'] for r in reads):errors.append('packet read binding differs')
    report_path=delivery/'report.json';report=json.loads(report_path.read_text()) if report_path.is_file() else None
    if not report:errors.append('report missing')
    else:
        receipts=[v for n,_,_,v in actual if n==PREFIX+'submit_report']
        if not receipts or receipts[-1].get('artifact_sha256')!=digest(report) or receipts[-1].get('input_sha256')!=digest(spec) or Path(receipts[-1]['artifact'])!=original_delivery/'report.json':errors.append('actual receipt differs')
        wanted={'file:local:'+digest({'path':n,'sha':h})[:24] for n,h in current.items() if n!='.experiment-copy'}
        if set(report['file_ids'])!=wanted or report['final_snapshot']!=current or report['input_sha256']!=digest(spec):errors.append('report current identities differ')
        if report.get('task_execution_version_sha256')!=task_version or report.get('task_contract_version')!=c['version']:errors.append('task report version differs')
        if report['read_statuses']!={r['source_id']:r['status'] for r in reads}:errors.append('report read statuses differ')
    return {'passed':not errors,'errors':errors,'file_postconditions_passed':current==expected,'reads':len(reads),'output_reads':len(paths&set(generated)),'complete_collections':len(packets)}

def audit(exp):
    p=json.loads((exp/'protocol.json').read_text());assert all(sha(exp/'frozen-source'/n)==h for n,h in p['source_code'].items())
    assert sha(exp/'L2/policy.json')==p['L2_sha256'];rows=[]
    for c in p['tasks']:
        td=Path(c['task_dir']);spec=json.loads((td/'input.json').read_text());assert digest(spec)==c['input_sha256'];assert snapshot(c['pristine'])==c['initial_snapshot'];assert sha(td/'prompt.md')==c['prompt_sha256'];assert sha(td/'scope.json')==c['scope_sha256']
        for op in td.glob('attempts/*/outcome.json'):
            o=json.loads(op.read_text());a=op.parent;m=o['run'];cfg=json.loads((a/'config.json').read_text());run=Path(m['output_dir']);events=[json.loads(l) for l in (run/'agent-events.jsonl').read_text().splitlines()]
            assert o['accounting_complete'] and sha(run/'agent-events.jsonl')==o['events_sha256'];assert cfg['budget_usd']==p['per_task_cap_usd'];assert m['budget_accounted_usd']<=cfg['budget_usd'] and m['agent_steps']<=p['max_steps']
            assert json.loads((a/'execution-source-code.json').read_text())==p['source_code']
            if c['arm']=='L2':assert cfg['reentry_policy_sha256']==p['L2_sha256']
            else:assert cfg['reentry_policy_sha256'] is None
            ledger=[json.loads(l) for l in (run/'cost-ledger.jsonl').read_text().splitlines()];assert len(ledger)==m['upstream_requests'];cost=0;hit=miss=out=0
            for row in ledger:
                assert row['response_status']==200;u=row['response_usage'];assert u['prompt_tokens']==u['prompt_cache_hit_tokens']+u['prompt_cache_miss_tokens'];hit+=u['prompt_cache_hit_tokens'];miss+=u['prompt_cache_miss_tokens'];out+=u['completion_tokens'];cost+=(u['prompt_cache_hit_tokens']*.006+u['prompt_cache_miss_tokens']*.3+u['completion_tokens']*1.2)/1e6
            assert math.isclose(cost,m['budget_accounted_usd'],abs_tol=1e-12)
            # Harness inputTokens counts uncached input; cached input is a separate counter.
            assert (miss,hit,out)==(m['inputTokens'],m['cacheReadTokens'],m['outputTokens'])
            repairs=[e for e in events if e['type']=='user/message' and e['data'].get('source',{}).get('kind')=='task-acceptance-repair'];assert len(repairs)==m['acceptance_repairs']<=p['acceptance_max_repairs']
            if repairs:assert not any(e['type']=='tool/call' and e['seq']>repairs[0]['seq'] and e['data']['callId'].startswith('sss-') for e in events)
            checks=[];stage_review=None
            for stage in sorted(Path(m['acceptance_trace_dir']).glob('round-*')):
                result=json.loads((stage/'result.json').read_text());assert digest(json.loads((stage/'task.json').read_text()))==digest(spec);assert result['task_sha256']==sha(td/'input.json');assert result['workspace_snapshot_sha256']==digest(snapshot(stage/'workspace'))
                stage_events=json.loads((stage/'events.json').read_text());assert stage_events==events[:len(stage_events)]
                stage_ledger=[json.loads(l) for l in (stage/'cost-ledger.jsonl').read_text().splitlines()];assert stage_ledger==ledger[:len(stage_ledger)]
                stage_review=replay(spec,Path(c['pristine']),stage/'workspace',stage/'delivery',stage_events,p['task_execution_version_sha256'],a/'delivery')
                assert stage_review['passed']==result['passed'],(c['task_id'],stage_review,result);checks.append(result)
            assert len(checks)==m['acceptance_checks'] and checks[-1]['passed']==o['acceptance']['passed']
            retained=Path(json.loads((a/'final-copy.json').read_text())['path']);assert snapshot(retained)==snapshot(Path(m['acceptance_trace_dir'])/f'round-{len(checks)-1:02d}'/'workspace')
            rows.append({'task':c['task_id'],'pair_id':c['pair_id'],'family':c['family'],'arm':c['arm'],'passed':o['acceptance']['passed'],'file_postconditions_passed':stage_review['file_postconditions_passed'],
                'checks':len(checks),'failed_stages':sum(not r['passed'] for r in checks),'repairs':len(repairs),'tool_errors':o['tool_errors'],'requests':m['upstream_requests'],'estimated_usd':cost,'cache_hit_tokens':hit,'cache_miss_tokens':miss,'output_tokens':out,'reads':stage_review['reads'],'output_reads':stage_review['output_reads'],
                'verified_first_read_batches':m['collection_model_requests_bypassed_verified'],'verified_next_read_batches':m['reentry_epoch_batches_verified'],
                'automatic_tool_calls':sum(e['type']=='tool/call' and e['data']['callId'].startswith('sss-') for e in events)})
    pairs=[]
    for condition in p['conditions']:
        pair=[r for r in rows if r['pair_id']==condition['pair_id']]
        if len(pair)!=2:continue
        h=next(r for r in pair if r['arm']=='H');m=next(r for r in pair if r['arm']=='L2');cases=[c for c in p['tasks'] if c['pair_id']==condition['pair_id']]
        assert len({c['input_sha256'] for c in cases})==1 and len({c['prompt_sha256'] for c in cases})==1
        pairs.append({'pair_id':condition['pair_id'],'both_passed':h['passed'] and m['passed'],'H_usd':h['estimated_usd'],'L2_usd':m['estimated_usd'],'H_requests':h['requests'],'L2_requests':m['requests']})
    body={'experiment':exp.name,'audited_tasks':len(rows),'passed':sum(r['passed'] for r in rows),'file_postconditions_passed':sum(r['file_postconditions_passed'] for r in rows),'failed_stages':sum(r['failed_stages'] for r in rows),'repairs':sum(r['repairs'] for r in rows),'model_requests':sum(r['requests'] for r in rows),'estimated_usd':sum(r['estimated_usd'] for r in rows),
          'native_events_http_tokens_frozen_permissions_all_rounds_verified':True,'library_unchanged':True,'holdout_used_for_training':False,'actual_bill_verified':False,'human_blind_review':False,'rows':rows,'pairs':pairs,'analysis_source_sha256':sha(__file__)}
    save(exp/'independent-audit.json',body);return body

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--experiment',type=Path,required=True);a=parser.parse_args();r=audit(a.experiment.resolve());print(json.dumps({k:v for k,v in r.items() if k not in ('rows','pairs')},ensure_ascii=False))
if __name__=='__main__':main()
