"""Inspect original native decisions and actual parameter lineage; never authorize bypass."""
import argparse
from collections import Counter
import json
from pathlib import Path
from pdf_tools import ROOT, digest, save_private
from pdf_dependencies import private_file


def analyze(experiment):
    protocol=json.loads((experiment/'protocol.json').read_text()); reports=[]
    for case in protocol['tasks']:
        work=experiment/case['name']
        if not (work/'outcome.json').exists(): continue
        outcome=json.loads((work/'outcome.json').read_text())
        run=outcome['run']; spec=json.loads((work/'input.json').read_text())
        events=[json.loads(l) for l in (Path(run['output_dir'])/'agent-events.jsonl').read_text().splitlines()]
        calls={e['data']['callId']:e for e in events if e['type']=='tool/call'}
        results={}
        for event in events:
            if event['type']=='tool/result':
                for block in event['data']['message']['content']:
                    results.setdefault(block['toolCallId'],[]).append((event,block))
        pins={}; scans=set(); reads=set(); checks=set(); rows=[]; errors=[]; links=[]
        target_ids={t['reference_id'] for t in spec['citations']}
        papers={t['paper_id'] for t in spec['task']['sources']['papers']}
        for event in events:
            if event['type']!='assistant/message': continue
            data=event['data'];message=data.get('message',{})
            if message.get('source',{}).get('kind')!='model':continue
            blocks=[b for b in message['content'] if b['type']=='tool-call']
            names=[b['name'].split('__')[-1] for b in blocks]
            lineage=[]; exact=True
            for block in blocks:
                cid=block['id']; args=json.loads(block['arguments']); call=calls.get(cid)
                observations=results.get(cid,[])
                if (cid.startswith('sss-') or call is None or len(observations)!=1
                        or call['data']['name']!=block['name'] or json.loads(call['data']['arguments'])!=args):
                    exact=False;continue
                result_event,result=observations[0]
                if result.get('isError'):
                    errors.append({'call_seq':call['seq'],'name':names[len(lineage)] if len(lineage)<len(names) else block['name'],
                                   'message':result.get('content')}); exact=False;continue
                value=json.loads(result['content'][0]['text']); name=block['name'].split('__')[-1]
                if name=='pin_pdf_context':
                    pins[value['source_id']]={'result_seq':result_event['seq'],'call_seq':call['seq'],
                        'paper_id':args['paper_id'],'version_sha256':value['version_sha256']}
                elif name=='read_pinned_pdf_context':
                    parent=pins.get(args['source_id'])
                    if parent is None or parent['result_seq']>=call['seq'] or parent['version_sha256']!=value['version_sha256']:
                        exact=False
                    else:
                        links.append({'parent':parent,'read_call_seq':call['seq'],'read_result_seq':result_event['seq'],
                                      'source_id':args['source_id'],'result_sha256':digest(value)})
                        lineage.append(args['source_id']);reads.add(args['source_id'])
                elif name=='check_citation_target':
                    ref=args['reference_id']
                    if ref not in target_ids or value['reference_id']!=ref:exact=False
                    else:checks.add(ref);lineage.append(ref)
                elif name=='find_resource_links':
                    if args['paper_id'] not in papers or value['paper_id']!=args['paper_id']:exact=False
                    else:scans.add(args['paper_id']);lineage.append(args['paper_id'])
            if not blocks:category='final_semantic_or_reporting'
            elif set(names)=={'read_workflow_input'}:category='input_read_candidate'
            elif exact and set(names)=={'check_citation_target'}:category='citation_work_foreach_candidate'
            elif exact and set(names)=={'find_resource_links'}:category='all_paper_url_scan_candidate'
            elif exact and set(names)=={'read_pinned_pdf_context'}:category='existing_pin_read_family_candidate'
            elif 'submit_workflow_report' in names:category='semantic_report_or_validation_repair'
            elif 'read_pinned_pdf_context' in names:category='mixed_read_and_semantic_selection_keep_model'
            else:category='semantic_selection_keep_model'
            usage=data.get('usage') or {}
            rows.append({'message_seq':event['seq'],'category':category,'tool_names':names,
                         'output_tokens':usage.get('outputTokens',0), 'usage':usage,
                         'parameter_lineage_verified':exact,'observed_bindings':lineage,
                         'candidate_only':True,'approved_for_bypass':False})
        report={'case':case['name'],'kind':case['kind'],'target_count':case['target_count'],
                'run':run, 'receipt_status':outcome['status'],'source_replay_verified':outcome['source_replay_verified'],
                'categories':dict(Counter(r['category'] for r in rows)),
                'category_output_tokens':{cat:sum(r['output_tokens'] for r in rows if r['category']==cat) for cat in {r['category'] for r in rows}},
                'decisions':rows,'pin_read_links':links,'all_reference_targets_checked':checks==target_ids if target_ids else None,
                'all_paper_urls_scanned':scans==papers if spec['kind']=='resource_inventory' else None,
                'tool_errors':errors,'scientific_support_verified':False,'new_motif_certified':False,
                'models_bypassed_verified':0}
        save_private(work/'candidate-analysis.json',report);reports.append(report)
    total={'experiment_id':protocol['experiment_id'],'task_count':len(reports),
           'upstream_requests':sum(r['run']['upstream_requests'] for r in reports),
           'budget_accounted_usd':sum(r['run']['budget_accounted_usd'] for r in reports),
           'input_tokens':sum(r['run']['inputTokens'] for r in reports),
           'cache_read_tokens':sum(r['run']['cacheReadTokens'] for r in reports),
           'output_tokens':sum(r['run']['outputTokens'] for r in reports),
           'tool_error_count':sum(len(r['tool_errors']) for r in reports),
           'receipt_count':sum(r['source_replay_verified'] for r in reports),
           'candidates':dict(sum((Counter(r['categories']) for r in reports),Counter())),
           'models_bypassed_verified':0,'new_motif_certified':False,'efficiency_comparison_performed':False,
           'rows':[{k:v for k,v in r.items() if k not in ('decisions','pin_read_links','tool_errors')} for r in reports]}
    save_private(experiment/'candidate-summary.json',total)
    print(json.dumps({k:v for k,v in total.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--experiment',type=Path,required=True);a=p.parse_args()
    analyze(private_file(a.experiment/'protocol.json').parent)
