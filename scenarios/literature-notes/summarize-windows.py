"""Actual request accounting, batch lineage and paired source-set comparison."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from pdf_tools import ROOT,digest,save_private
from pdf_dependencies import private_file


def inspect(work):
    outcome=json.loads((work/'outcome.json').read_text());metrics=outcome['run'];run=Path(metrics['output_dir'])
    events=[json.loads(l)for l in (run/'agent-events.jsonl').read_text().splitlines()]
    calls={e['data']['callId']:e for e in events if e['type']=='tool/call'};results={}
    for e in events:
        if e['type']=='tool/result':
            for b in e['data']['message']['content']:results[b['toolCallId']]=(e,b)
    native=[];synthetic=[];errors=[];pin_sources={};read_bindings=[]
    for event in events:
        if event['type']=='tool/call':
            data=event['data'];args=json.loads(data['arguments']);result=results[data['callId']];block=result[1]
            name=data['name'].split('__')[-1]
            if block.get('isError'):errors.append({'name':name,'call_seq':event['seq'],'message':block['content']});continue
            value=json.loads(block['content'][0]['text'])
            if name=='pin_pdf_context':pin_sources[value['source_id']]={'args':args,'value':value,'result_seq':result[0]['seq']}
            if name=='read_pinned_pdf_context':
                source=pin_sources.get(args['source_id'])
                if (not source or source['result_seq']>=event['seq']or source['value']['version_sha256']!=value['version_sha256']
                        or source['value']['document_version_sha256']!=value['document_version_sha256']):raise ValueError('read binding/version changed')
                read_bindings.append({'call_id':data['callId'],'source_id':args['source_id'],'version_sha256':value['version_sha256'],
                                      'runtime_generated':data['callId'].startswith('sss-'),'result_sha256':digest(value)})
        if event['type']!='assistant/message':continue
        data=event['data'];message=data.get('message',{})
        if message.get('source',{}).get('kind')!='model':continue
        blocks=[b for b in message['content']if b['type']=='tool-call'];names=[b['name'].split('__')[-1]for b in blocks]
        if blocks and all(b['id'].startswith('sss-')for b in blocks):synthetic.append(event['seq']);continue
        if not data.get('usage'):continue
        category=('final_text'if not names else'pure_model_read'if set(names)=={'read_pinned_pdf_context'}
                  else'publish_or_repair'if 'submit_workflow_report'in names else'mixed_read_and_selection'if 'read_pinned_pdf_context'in names
                  else'input_read'if set(names)=={'read_workflow_input'}else'query_or_window_selection')
        native.append({'seq':event['seq'],'category':category,'usage':data['usage'],'tool_names':names})
    ledger=[json.loads(l)for l in (run/'cost-ledger.jsonl').read_text().splitlines()]
    if len(ledger)!=metrics['upstream_requests']or len(native)!=metrics['upstream_requests']:
        raise ValueError('original provider messages differ from actual HTTP accounting')
    artifact=outcome['receipt']['artifact']if outcome['receipt']else None
    report=json.loads(Path(artifact).read_text())if artifact else {'sources':{},'rows':[]}
    if artifact and digest(report)!=outcome['receipt']['artifact_sha256']:raise ValueError('published artifact changed')
    read_rows=[r for r in native if r['category']=='pure_model_read']
    return {'case':work.name,'metrics':metrics,'status':outcome['status'],'raw_categories':dict(Counter(r['category']for r in native)),
            'category_outputs':{c:sum(r['usage'].get('outputTokens',0)for r in native if r['category']==c)for c in {r['category']for r in native}},
            'pure_model_read_requests':len(read_rows),'pure_model_read_output_tokens':sum(r['usage'].get('outputTokens',0)for r in read_rows),
            'synthetic_read_batches':len(synthetic),'runtime_reads_verified':sum(b['runtime_generated']for b in read_bindings),
            'read_bindings':read_bindings,'tool_errors':errors,'http_statuses':dict(Counter(r['response_status']for r in ledger)),
            'source_ids':sorted(report['sources']),'sources_sha256':digest(report['sources']),
            'selected_sources':{r['target_id']:r['references']for r in report['rows']},'sdk_complete':metrics['status']=='done',
            'scientific_support_verified':False,'original_events_sha256':hashlib.sha256((run/'agent-events.jsonl').read_bytes()).hexdigest()}


def summarize(out):
    protocol=json.loads((out/'protocol.json').read_text());rows=[];pairs=[]
    for item in protocol['schedule']:
        work=out/item['name']
        if (work/'outcome.json').exists():rows.append({**item,**inspect(work)})
    groups={}
    for row in rows:groups.setdefault((row.get('case',row['name']).rsplit('-',2)[0],row['repeat']),{})[row['arm']]=row
    for (case,repeat),pair in groups.items():
        if set(pair)=={'H','M'}:
            h,m=pair['H'],pair['M'];pairs.append({'case':case,'repeat':repeat,
                'full_source_packets_equal':h['sources_sha256']==m['sources_sha256'],
                'delivered_source_ids_equal':h['selected_sources']==m['selected_sources'],
                'both_sdk_complete':h['sdk_complete']and m['sdk_complete']})
    summary={'experiment_id':out.name,'actual_rows':len(rows),'rows':rows,'pairs':pairs,
        'actual_upstream_requests':sum(r['metrics']['upstream_requests']for r in rows),
        'accounted_usd':sum(r['metrics']['budget_accounted_usd']for r in rows),
        'verified_batches':sum(r['metrics']['model_requests_skipped_verified']for r in rows),
        'runtime_read_results_verified':sum(r['runtime_reads_verified']for r in rows),
        'pure_model_read_requests_H':sum(r['pure_model_read_requests']for r in rows if r['arm']=='H'),
        'pure_model_read_requests_M':sum(r['pure_model_read_requests']for r in rows if r['arm']=='M'),
        'pure_model_read_output_H':sum(r['pure_model_read_output_tokens']for r in rows if r['arm']=='H'),
        'tool_error_count':sum(len(r['tool_errors'])for r in rows),'scientific_support_verified':False}
    save_private(out/'lineage-accounting.json',summary)
    print(json.dumps({k:v for k,v in summary.items()if k not in ('rows','pairs')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args();summarize(private_file(a.experiment/'protocol.json').parent)
